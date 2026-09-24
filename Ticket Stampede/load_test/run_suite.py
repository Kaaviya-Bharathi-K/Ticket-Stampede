"""Run the naive seller's progressively larger load-test matrix."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("naive", "fixed"), default="naive")
    parser.add_argument("--seller-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=100,
                        help="Concurrency for the four progressive tests")
    parser.add_argument("--duplicate-requests", type=int, default=1000,
                        help="Attempts in the concurrent duplicate-ID experiment")
    parser.add_argument("--duplicate-concurrency", type=int, default=100)
    parser.add_argument("--duplicate-percent", type=float, default=50.0)
    args = parser.parse_args()
    if min(args.concurrency, args.duplicate_requests, args.duplicate_concurrency) <= 0:
        parser.error("concurrency and request counts must be positive")
    if not 0 <= args.duplicate_percent <= 100:
        parser.error("--duplicate-percent must be between 0 and 100")

    result_dir = Path("results") / (args.variant + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    result_dir.mkdir(parents=True, exist_ok=False)
    cases = [(100, 100), (100, 1_000), (100, 10_000), (100, 50_000)]
    plan = [(f"tickets-{tickets}_requests-{requests}", tickets, requests,
             args.concurrency, 0.0) for tickets, requests in cases]
    plan.append((f"duplicate-ids-{args.duplicate_requests}", 100,
                 args.duplicate_requests, args.duplicate_concurrency,
                 args.duplicate_percent))

    suite_rows: list[str] = []
    for name, tickets, requests, concurrency, duplicate_pct in plan:
        csv_path = result_dir / f"{name}.csv"
        json_path = result_dir / f"{name}.json"
        log_path = result_dir / f"{name}.log"
        command = [
            sys.executable, "-m", "load_test.client",
            "--seller-url", args.seller_url,
            "--ticket-count", str(tickets),
            "--total-requests", str(requests),
            "--concurrency", str(concurrency),
            "--duplicate-request-id-percent", str(duplicate_pct),
            "--output-csv", str(csv_path),
            "--output-json", str(json_path),
        ]
        print(f"Running {name} (concurrency={concurrency})")
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        log_path.write_text(
            f"COMMAND: {' '.join(command)}\nEXIT CODE: {completed.returncode}\n\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}",
            encoding="utf-8",
        )
        suite_rows.append(
            f"{name}: exit={completed.returncode}; log={log_path}; report={json_path}"
        )
        if completed.returncode:
            print(f"{name} failed; evidence preserved in {log_path}")
        else:
            print(completed.stdout)

    summary_path = result_dir / "suite.txt"
    summary_path.write_text("\n".join(suite_rows) + "\n", encoding="utf-8")
    print(f"Suite artifacts: {result_dir}")
    if args.variant == "fixed":
        compare_command = [
            sys.executable, "-m", "load_test.compare_results",
            "--fixed-dir", str(result_dir),
            "--output", "results/comparison.md",
        ]
        comparison = subprocess.run(compare_command, text=True, capture_output=True, check=False)
        print(comparison.stdout)
        if comparison.returncode:
            print(comparison.stderr)
    return 0 if all("exit=0" in row for row in suite_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
