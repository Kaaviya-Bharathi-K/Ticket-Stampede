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
```
## POST /buy

Attempts to purchase a ticket.

Request:
```json
{
    "user_id": "user_001",
    "request_id": "request_001"
}
```
The response should either contain the assigned ticket number or a clear indication that the sale is sold out.

The request_id is used to provide idempotency.

## GET /status

Returns the current state of the ticket sale.
The response contains:
- Total number of tickets
- Number of tickets sold
- Number of tickets remaining
- Issued ticket numbers
- User associated with each ticket
- Request ID associated with each purchase

# 3. Correctness Invariants

The system is evaluated against four important invariants.

## Invariant 1 — No Overselling
The number of tickets issued must never exceed the number of tickets available.
## Invariant 2 — Unique Ticket Numbers
A ticket number must never be assigned to more than one buyer.
## Invariant 3 — Request Idempotency
If the same request_id is submitted multiple times, it must result in only one successful ticket allocation.
## Invariant 4 — Status Consistency
The value reported by /status for the number of tickets sold must match the actual number of issued tickets.
# 4. Architecture
## Components
Load Client
The load client simulates a large number of buyers.
It is responsible for:

- Generating requests
- Sending concurrent requests
- Replaying duplicate request IDs
- Measuring response times
- Calculating throughput
- Checking the four invariants after a test
- FastAPI Seller
- 
The FastAPI application exposes the ticket-selling API.

It is responsible for:

Managing the ticket sale
Processing purchase requests
Maintaining ticket state
Communicating with MySQL
## MySQL

MySQL stores the persistent state of the sale.

It stores:

Current sale information
Ticket assignments
User IDs
Request IDs

Database constraints and transactional mechanisms are used to maintain correctness.

# 5. Technology Stack
##Python

Python is used as the primary programming language because it provides a simple development environment and a strong ecosystem for web services, database access, concurrency, and load testing.

## FastAPI

FastAPI is used to implement the HTTP API.

It provides:

Lightweight REST API development
Request validation
Automatic API documentation
Good support for concurrent request handling
## MySQL

MySQL is used as the persistent datastore.

The ticket allocation problem involves multiple concurrent requests modifying shared state. MySQL provides:

Transactions
Row-level locking
Unique constraints
Persistent storage

These capabilities are useful for enforcing the ticket allocation invariants.

## SQLAlchemy

SQLAlchemy is used as the database access layer between FastAPI and MySQL.

## Uvicorn

Uvicorn is used as the ASGI server for running the FastAPI application.

# 6.Conclusion

The Ticket Stampede project demonstrates the design of a ticket-selling service that must maintain correctness under high levels of concurrent access. The implementation uses FastAPI and MySQL, with the database acting as the persistent source of truth for ticket allocation and purchase state.

The project follows a naive implementation → concurrent testing → race-condition analysis → concurrency-safe implementation → performance evaluation approach. This makes it possible to understand not only how the final system works, but also why concurrency control is necessary.

The four key invariants—no overselling, unique ticket numbers, request idempotency, and status consistency—are treated as primary correctness requirements. Performance is considered only after correctness has been established.

The load-testing framework is designed to simulate high request volumes, including duplicate request IDs, while measuring throughput, median latency, and P99 latency. Additional experiments investigate system behavior under increasing load and temporary database slowdown.

Where experiments have not yet been executed, the results are explicitly marked as NOT EXECUTED rather than being estimated or fabricated. This keeps the performance analysis reproducible and evidence-based.

Overall, the project provides a practical demonstration of concurrency handling, database transactions, idempotency, load testing, and performance analysis in a backend system where correctness is more important than simply achieving high throughput.
