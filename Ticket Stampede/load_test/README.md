# Concurrent API load client

Run from the project root after installing `requirements.txt` and starting the
FastAPI seller. The client resets the sale before each run, makes concurrent
`POST /buy` calls, fetches `GET /status`, checks the four public snapshot
invariants, prints a report, and writes one row per attempt to a CSV file.

```powershell
python -m load_test.client `
  --seller-url http://127.0.0.1:8000 `
  --ticket-count 100 `
  --total-requests 150 `
  --concurrency 25 `
  --duplicate-request-id-percent 10
```

Options:

- `--seller-url`: API base URL (default `http://127.0.0.1:8000`).
- `--ticket-count`: positive ticket capacity for the reset sale (required).
- `--total-requests`: positive number of purchase attempts (required).
- `--concurrency`: maximum in-flight requests (default `20`).
- `--duplicate-request-id-percent`: percentage of attempts that reuse the first
  generated request ID (default `0`). The actual number is rounded down; for
  one-request runs, no replay is possible.
- `--output-csv`: result path (default `load_test/results.csv`).

The CSV records user ID, request ID, HTTP status, response time in milliseconds,
ticket number, success flag, outcome, and error detail for each request.
