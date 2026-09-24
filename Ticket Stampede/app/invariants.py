from collections.abc import Mapping, Sequence
from typing import Any


def check_invariants(status: Mapping[str, Any]) -> list[str]:
    """Return descriptions of invariant violations in a status snapshot.

    This consumes the public snapshot shape rather than querying or relying on
    SQLAlchemy models, so the same checks can be used by an external client.
    An empty list means no violations were found.
    """
    total_tickets = status["total_tickets"]
    sold_count = status["sold_count"]
    tickets: Sequence[Mapping[str, Any]] = status["issued_tickets"]
    violations: list[str] = []

    if len(tickets) > total_tickets:
        violations.append(
            f"issued ticket count ({len(tickets)}) exceeds total_tickets ({total_tickets})"
        )

    ticket_numbers = [ticket["ticket_number"] for ticket in tickets]
    if len(ticket_numbers) != len(set(ticket_numbers)):
        violations.append("ticket_number values are not unique")

    request_ids = [ticket["request_id"] for ticket in tickets]
    if len(request_ids) != len(set(request_ids)):
        violations.append("request_id values correspond to multiple tickets")

    if sold_count != len(tickets):
        violations.append(
            f"sold_count ({sold_count}) does not equal issued ticket count ({len(tickets)})"
        )

    return violations
