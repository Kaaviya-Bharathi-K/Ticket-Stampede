"""Build a Naive vs Fixed markdown table from saved load-test JSON reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TESTS = [
    "tickets-100_requests-100",
    "tickets-100_requests-1000",
    "tickets-100_requests-10000",
    "tickets-100_requests-50000",
    "duplicate-ids-1000",
]
INVARIANTS = [
    "issued_tickets_at_most_total_tickets",
    "ticket_numbers_unique",
    "request_ids_unique",
    "sold_count_matches_issued_tickets",
]


def latest_run(prefix: str) -> Path | None:
    candidates = sorted(Path("results").glob(prefix + "-*"))
    return candidates[-1] if candidates else None


def report(directory: Path | None, test_name: str) -> dict | None:
    if directory is None:
        return None
    path = directory / f"{test_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def fmt(value, digits: int = 2) -> str:
    if value is None:
        return "NOT EXECUTED"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--naive-dir", type=Path, default=None)
    parser.add_argument("--fixed-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("results/comparison.md"))
    args = parser.parse_args()
    naive_dir = args.naive_dir or latest_run("naive")
    lines = [
        "# Naive vs Fixed load test comparison",
        "",
        "Test conditions: 100 tickets; 100, 1,000, 10,000, and 50,000 purchase attempts at concurrency 100; plus 1,000 attempts at concurrency 100 with 50% duplicate request IDs.",
        "",
        "`NOT EXECUTED` means no saved measurement is available. Invariants are shown as PASS, FAIL, or NOT EXECUTED.",
        "",
        "| Test | Version | Concurrency | Requests | Successful | Sold out | Errors | Throughput (req/s) | Median (ms) | P99 (ms) | I1 | I2 | I3 | I4 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for test_name in TESTS:
        for variant, directory in (("Naive", naive_dir), ("Fixed", args.fixed_dir)):
            item = report(directory, test_name)
            if item is None:
                concurrency = "NOT EXECUTED"
                requests = "NOT EXECUTED"
                successful = sold_out = errors = throughput = median = p99 = "NOT EXECUTED"
                invariant_values = ["NOT EXECUTED"] * 4
            else:
                concurrency = item.get("concurrency")
                requests = item.get("total_requests")
                successful = item.get("successful_purchases")
                sold_out = item.get("sold_out_responses")
                errors = item.get("errors")
                throughput = fmt(item.get("throughput_requests_per_second"))
                median = fmt(item.get("median_latency_ms"))
                p99 = fmt(item.get("p99_latency_ms"))
                invariant_values = [
                    "NOT EXECUTED" if item.get("invariants", {}).get(key) is None
                    else "PASS" if item["invariants"][key] else "FAIL"
                    for key in INVARIANTS
                ]
            row = [test_name, variant, str(concurrency), str(requests), str(successful),
                   str(sold_out), str(errors), str(throughput), str(median), str(p99),
                   *invariant_values]
            lines.append("| " + " | ".join(row) + " |")
    lines.extend([
        "",
        f"Naive artifacts: `{naive_dir if naive_dir else 'NOT EXECUTED'}`",
        f"Fixed artifacts: `{args.fixed_dir}`",
        "",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Comparison written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
