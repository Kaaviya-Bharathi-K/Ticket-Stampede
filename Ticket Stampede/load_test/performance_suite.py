"""Run concurrency scaling benchmarks and collect host/MySQL telemetry."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from sqlalchemy import text

from app.database import engine


class Telemetry:
    def __init__(self, port: int, interval: float = 1.0):
        self.port = port
        self.interval = interval
        self.rows: list[dict] = []
        self.probe_ms: list[float] = []
        self.probe_errors = 0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join()

    def _pids_on_port(self) -> set[int]:
        pids: set[int] = set()
        try:
            for connection in psutil.net_connections(kind="inet"):
                if connection.laddr and connection.laddr.port == self.port and connection.pid:
                    pids.add(connection.pid)
        except (psutil.AccessDenied, OSError):
            pass
        return pids

    def _sample(self) -> None:
        process_stats: dict[int, dict] = {}
        next_discovery = 0.0
        server_pids: set[int] = set()
        mysql_pids: set[int] = set()
        while not self.stop_event.is_set():
            now = time.monotonic()
            if now >= next_discovery:
                server_pids = self._pids_on_port()
                mysql_pids = {
                    proc.info["pid"] for proc in psutil.process_iter(["pid", "name"])
                    if proc.info.get("name") and "mysqld" in proc.info["name"].lower()
                }
                next_discovery = now + 5

            row = {"timestamp_utc": datetime.now(timezone.utc).isoformat()}
            for label, pids in (("seller", server_pids), ("mysql", mysql_pids)):
                cpu_values: list[float] = []
                memory_values: list[int] = []
                for pid in pids:
                    try:
                        proc = psutil.Process(pid)
                        cpu_values.append(proc.cpu_percent(interval=None))
                        memory_values.append(proc.memory_info().rss)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                        continue
                row[f"{label}_cpu_pct"] = sum(cpu_values) if cpu_values else ""
                row[f"{label}_memory_bytes"] = sum(memory_values) if memory_values else ""

            try:
                with engine.connect() as connection:
                    result = connection.execute(text("SHOW GLOBAL STATUS LIKE 'Threads_connected'"))
                    status = result.fetchone()
                    row["mysql_threads_connected"] = int(status[1]) if status else ""
                    probe_started = time.perf_counter()
                    connection.execute(text("SELECT 1"))
                    self.probe_ms.append((time.perf_counter() - probe_started) * 1000)
            except Exception as exc:  # telemetry should not abort the load run
                row["mysql_threads_connected"] = ""
                row["probe_error"] = type(exc).__name__
                self.probe_errors += 1
            self.rows.append(row)
            self.stop_event.wait(self.interval)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else 0.0


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("NOT EXECUTED\n", encoding="utf-8")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seller-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=50_000,
                        help="Same request count at every concurrency level")
    parser.add_argument("--concurrencies", nargs="+", type=int,
                        default=[100, 500, 1000, 5000, 10000, 25000, 50000])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.requests <= 0 or any(value <= 0 for value in args.concurrencies):
        parser.error("requests and concurrency values must be positive")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output_dir or Path("results") / f"performance-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    summary_rows: list[dict] = []
    for concurrency in args.concurrencies:
        name = f"concurrency-{concurrency}"
        json_path = out / f"{name}.json"
        telemetry = Telemetry(args.port)
        command = [
            sys.executable, "-m", "load_test.client",
            "--seller-url", args.seller_url,
            "--ticket-count", str(args.requests),
            "--total-requests", str(args.requests),
            "--concurrency", str(concurrency),
            "--output-csv", str(out / f"{name}-requests.csv"),
            "--output-json", str(json_path),
        ]
        telemetry.start()
        started = time.perf_counter()
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            completed = None
            launch_error = str(exc)
        else:
            launch_error = ""
        elapsed = time.perf_counter() - started
        telemetry.stop()
        (out / f"{name}.log").write_text(
            f"EXIT CODE: {completed.returncode if completed else 'NOT EXECUTED'}\n"
            f"LAUNCH ERROR: {launch_error}\n\nSTDOUT:\n{completed.stdout if completed else ''}"
            f"\nSTDERR:\n{completed.stderr if completed else ''}", encoding="utf-8")
        write_csv(out / f"{name}-telemetry.csv", telemetry.rows)

        report = None
        if json_path.exists():
            try:
                report = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        server_cpu = [float(row["seller_cpu_pct"]) for row in telemetry.rows
                      if row.get("seller_cpu_pct") not in (None, "")]
        server_mem = [int(row["seller_memory_bytes"]) for row in telemetry.rows
                      if row.get("seller_memory_bytes") not in (None, "")]
        mysql_cpu = [float(row["mysql_cpu_pct"]) for row in telemetry.rows
                     if row.get("mysql_cpu_pct") not in (None, "")]
        mysql_mem = [int(row["mysql_memory_bytes"]) for row in telemetry.rows
                     if row.get("mysql_memory_bytes") not in (None, "")]
        connections = [int(row["mysql_threads_connected"]) for row in telemetry.rows
                       if row.get("mysql_threads_connected") not in (None, "")]
        summary_rows.append({
            "status": "MEASURED" if report else "NOT EXECUTED",
            "concurrency": concurrency,
            "total_requests": args.requests,
            "successful_purchases": report.get("successful_purchases", "") if report else "",
            "sold_out_responses": report.get("sold_out_responses", "") if report else "",
            "errors": report.get("errors", "") if report else "",
            "throughput_requests_per_second": report.get("throughput_requests_per_second", "") if report else "",
            "median_latency_ms": report.get("median_latency_ms", "") if report else "",
            "p99_latency_ms": report.get("p99_latency_ms", "") if report else "",
            "seller_cpu_avg_pct": statistics.mean(server_cpu) if server_cpu else "",
            "seller_cpu_peak_pct": max(server_cpu) if server_cpu else "",
            "seller_memory_peak_bytes": max(server_mem) if server_mem else "",
            "mysql_cpu_avg_pct": statistics.mean(mysql_cpu) if mysql_cpu else "",
            "mysql_cpu_peak_pct": max(mysql_cpu) if mysql_cpu else "",
            "mysql_memory_peak_bytes": max(mysql_mem) if mysql_mem else "",
            "mysql_threads_connected_peak": max(connections) if connections else "",
            "select_1_probe_median_ms": statistics.median(telemetry.probe_ms) if telemetry.probe_ms else "",
            "select_1_probe_p99_ms": percentile(telemetry.probe_ms, .99) if telemetry.probe_ms else "",
            "probe_errors": telemetry.probe_errors,
            "wall_duration_seconds": elapsed if completed else "",
            "exit_code": completed.returncode if completed else "NOT EXECUTED",
        })
        print(f"{name}: {'MEASURED' if report else 'NOT EXECUTED'}")

    write_csv(out / "benchmark.csv", summary_rows)
    measured = [row for row in summary_rows if row["status"] == "MEASURED"]
    measured.sort(key=lambda row: row["concurrency"])
    degradation = None
    for previous, current in zip(measured, measured[1:]):
        if (current["median_latency_ms"] > previous["median_latency_ms"]
                and current["p99_latency_ms"] > previous["p99_latency_ms"]):
            degradation = (previous, current)
            break
    analysis_lines = [
        "# Performance analysis",
        "",
        "## OBSERVATION",
        "",
    ]
    if measured:
        analysis_lines.append("Measured points (latencies in ms, throughput in requests/s):")
        analysis_lines.append("")
        for row in measured:
            analysis_lines.append(
                f"- Concurrency {row['concurrency']}: throughput "
                f"{row['throughput_requests_per_second']}, median "
                f"{row['median_latency_ms']}, P99 {row['p99_latency_ms']}, "
                f"errors {row['errors']}."
            )
        if degradation:
            analysis_lines.extend([
                "",
                f"The first adjacent measured step where both median and P99 rose was "
                f"{degradation[0]['concurrency']} to {degradation[1]['concurrency']} concurrency.",
            ])
        else:
            analysis_lines.extend(["", "No adjacent measured step showed both median and P99 rising."])
    else:
        analysis_lines.append("NOT EXECUTED: no run produced a load-test JSON report.")
    analysis_lines.extend([
        "",
        "## INTERPRETATION",
        "",
        "No bottleneck is assigned automatically. Compare the observed latency and throughput changes with the recorded seller/MySQL CPU, memory, connection, and SELECT 1 probe samples before attributing a cause.",
        "",
    ])
    (out / "performance-analysis.md").write_text("\n".join(analysis_lines), encoding="utf-8")
    print(f"CSV benchmark: {out / 'benchmark.csv'}")
    return 0 if all(row["status"] == "MEASURED" for row in summary_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
