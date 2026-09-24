from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.invariants import check_invariants


@dataclass
class RequestResult:
    user_id: str
    request_id: str
    http_status: int | None
    response_time_ms: float
    ticket_number: int | None
    success: bool
    outcome: str
    error: str | None = None
    started_at_utc: str = ""


def build_request_ids(total_requests: int, duplicate_percentage: float) -> list[str]:
    request_ids = [f"req-{uuid4()}" for _ in range(total_requests)]
    replay_count = min(
        max(0, total_requests - 1),
        math.floor(total_requests * duplicate_percentage / 100),
    )
    if replay_count:
        replay_indices = random.sample(range(1, total_requests), replay_count)
        original_id = request_ids[0]
        for index in replay_indices:
            request_ids[index] = original_id
    return request_ids


async def post_purchase(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    index: int,
    request_id: str,
) -> RequestResult:
    user_id = f"user-{uuid4()}"
    started_at_utc = ""
    started = time.perf_counter()
    try:
        async with semaphore:
            started = time.perf_counter()
            started_at_utc = datetime.now(timezone.utc).isoformat()
            response = await client.post(
                "/buy", json={"user_id": user_id, "request_id": request_id}
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        ticket_number: int | None = None
        try:
            body: Any = response.json()
        except ValueError:
            body = None
        if response.is_success:
            if isinstance(body, dict) and isinstance(body.get("ticket_number"), int):
                ticket_number = body["ticket_number"]
            else:
                return RequestResult(
                    user_id, request_id, response.status_code, elapsed_ms, None,
                    False, "error", "successful response omitted ticket_number",
                    started_at_utc,
                )
            return RequestResult(
                user_id, request_id, response.status_code, elapsed_ms,
                ticket_number, True, "success", None, started_at_utc,
            )
        if response.status_code == 409:
            return RequestResult(
                user_id, request_id, response.status_code, elapsed_ms, None,
                False, "sold_out", None, started_at_utc,
            )
        return RequestResult(
            user_id, request_id, response.status_code, elapsed_ms, None,
            False, "error", response.text[:500], started_at_utc,
        )
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RequestResult(
            user_id, request_id, None, elapsed_ms, None, False, "error", str(exc),
            started_at_utc,
        )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(pct * len(ordered)) - 1)
    return ordered[index]


def save_results(path: Path, results: list[RequestResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent Ticket Stampede API client")
    parser.add_argument("--seller-url", default="http://127.0.0.1:8000",
                        help="Base URL of the seller API")
    parser.add_argument("--ticket-count", type=int, required=True,
                        help="Tickets to create for this experiment")
    parser.add_argument("--total-requests", type=int, required=True,
                        help="Number of concurrent purchase attempts")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Maximum in-flight purchase requests (default: 20)")
    parser.add_argument("--duplicate-request-id-percent", type=float, default=0,
                        help="Percent of requests replaying the first request ID (0-100)")
    parser.add_argument("--output-csv", type=Path, default=Path("load_test/results.csv"),
                        help="Path for per-request CSV results")
    parser.add_argument("--output-json", type=Path, default=None,
                        help="Path for machine-readable run summary (defaults beside CSV)")
    args = parser.parse_args()
    if args.ticket_count <= 0:
        parser.error("--ticket-count must be greater than zero")
    if args.total_requests <= 0:
        parser.error("--total-requests must be greater than zero")
    if args.concurrency <= 0:
        parser.error("--concurrency must be greater than zero")
    if not 0 <= args.duplicate_request_id_percent <= 100:
        parser.error("--duplicate-request-id-percent must be between 0 and 100")
    return args


async def run(args: argparse.Namespace) -> int:
    base_url = args.seller_url.rstrip("/") + "/"
    timeout = httpx.Timeout(30.0)
    limits = httpx.Limits(max_connections=args.concurrency)
    async with httpx.AsyncClient(
        base_url=base_url, timeout=timeout, limits=limits
    ) as client:
        reset = await client.post("reset", json={"ticket_count": args.ticket_count})
        if not reset.is_success:
            print(f"Reset failed: HTTP {reset.status_code}: {reset.text}")
            return 2

        request_ids = build_request_ids(
            args.total_requests, args.duplicate_request_id_percent
        )
        semaphore = asyncio.Semaphore(args.concurrency)
        test_started = time.perf_counter()
        results = await asyncio.gather(*(
            post_purchase(client, semaphore, index, request_id)
            for index, request_id in enumerate(request_ids)
        ))
        duration = time.perf_counter() - test_started

        status_response = await client.get("status")
        if status_response.is_success:
            snapshot = status_response.json()
            invariant_violations = check_invariants(snapshot)
        else:
            snapshot = None
            invariant_violations = [
                f"GET /status failed with HTTP {status_response.status_code}: "
                f"{status_response.text[:500]}"
            ]

    successful_responses = sum(result.success for result in results)
    # A replayed request_id can receive the existing ticket successfully, but
    # it does not represent a second purchase.
    successful = len({result.request_id for result in results if result.success})
    sold_out = sum(result.outcome == "sold_out" for result in results)
    errors = sum(result.outcome == "error" for result in results)
    latencies = [result.response_time_ms for result in results]
    requests_per_second = len(results) / duration if duration else 0.0
    save_results(args.output_csv, results)

    invariant_results: dict[str, bool | None] = {
        "issued_tickets_at_most_total_tickets": None,
        "ticket_numbers_unique": None,
        "request_ids_unique": None,
        "sold_count_matches_issued_tickets": None,
    }
    if snapshot is not None:
        tickets = snapshot.get("issued_tickets", [])
        ticket_numbers = [ticket.get("ticket_number") for ticket in tickets]
        request_ids_in_snapshot = [ticket.get("request_id") for ticket in tickets]
        invariant_results = {
            "issued_tickets_at_most_total_tickets": len(tickets) <= snapshot["total_tickets"],
            "ticket_numbers_unique": len(ticket_numbers) == len(set(ticket_numbers)),
            "request_ids_unique": len(request_ids_in_snapshot) == len(set(request_ids_in_snapshot)),
            "sold_count_matches_issued_tickets": snapshot["sold_count"] == len(tickets),
        }
    report = {
        "seller_url": args.seller_url,
        "ticket_count": args.ticket_count,
        "concurrency": args.concurrency,
        "total_requests": len(results),
        "successful_purchases": successful,
        "successful_responses": successful_responses,
        "sold_out_responses": sold_out,
        "errors": errors,
        "duration_seconds": duration,
        "throughput_requests_per_second": requests_per_second,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p99_latency_ms": percentile(latencies, 0.99),
        "invariants": invariant_results,
        "invariant_violations": invariant_violations,
        "status_snapshot": snapshot,
        "requests_csv": str(args.output_csv),
    }
    output_json = args.output_json or args.output_csv.with_suffix(".json")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Ticket Stampede load test report")
    print(f"Seller URL: {args.seller_url}")
    print(f"Tickets configured: {args.ticket_count}")
    print(f"Total requests: {len(results)}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Duplicate request ID target: {args.duplicate_request_id_percent:g}%")
    print(f"Successful purchases: {successful}")
    if successful_responses != successful:
        print(f"Successful HTTP responses (including replays): {successful_responses}")
    print(f"Sold-out responses: {sold_out}")
    print(f"Errors: {errors}")
    print(f"Purchase duration: {duration:.3f} s")
    print(f"Requests per second: {requests_per_second:.2f}")
    print(f"Median latency: {statistics.median(latencies) if latencies else 0.0:.2f} ms")
    print(f"P99 latency: {percentile(latencies, 0.99):.2f} ms")
    print(f"Status snapshot received: {'yes' if snapshot is not None else 'no'}")
    if snapshot is not None:
        print(f"Tickets reported by status: {len(snapshot.get('issued_tickets', []))}")
    print("Invariant check: " + ("PASS" if not invariant_violations else "FAIL"))
    for name, passed in invariant_results.items():
        print(f"  {name}: {'PASS' if passed is True else 'FAIL' if passed is False else 'NOT CHECKED'}")
    for violation in invariant_violations:
        print(f"  - {violation}")
    print(f"Per-request CSV: {args.output_csv}")
    print(f"Run report JSON: {output_json}")
    return 0 if not invariant_violations else 1


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
