# Ticket-Stampede
Concurrent ticket-selling service built with FastAPI and MySQL, with load testing, idempotency, concurrency control, and invariant verification.

# Ticket Stampede

A concurrent ticket-selling backend designed to handle a large number of buyers competing for a limited number of tickets.

The project is implemented using **Python, FastAPI, MySQL, and SQLAlchemy**. It focuses primarily on correctness under concurrency, request idempotency, database consistency, and performance measurement.

---

# 1. Problem Statement

The system is designed for a high-demand ticket sale where a large number of users may attempt to purchase a small number of available tickets within a short period of time.

For example:

- Number of buyers: up to 50,000
- Number of available tickets: 100
- Sale duration: approximately 60 seconds

The main challenge is not simply serving a large number of HTTP requests. The important requirement is maintaining correctness when many requests attempt to modify the same shared ticket state simultaneously.

The system must ensure that tickets are neither oversold nor duplicated, while also handling repeated requests from the same buyer.

---

# 2. Requirements

The seller exposes three HTTP endpoints.

## POST /reset

Starts a new ticket sale.

The endpoint accepts a ticket count and clears the previous sale state.

Example:

```json
{
    "ticket_count": 100
}
