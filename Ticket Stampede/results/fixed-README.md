# Fixed-version load tests

Run from the repository root with the fixed FastAPI seller running and a
disposable MySQL database configured. The default suite uses the same conditions
as the naive suite: concurrency 100 for 100, 1,000, 10,000, and 50,000 attempts,
then 1,000 duplicate-ID attempts at concurrency 100 with 50% replayed IDs.

```powershell
python -m load_test.run_suite --variant fixed --seller-url http://127.0.0.1:8000 --concurrency 100 --duplicate-requests 1000 --duplicate-concurrency 100 --duplicate-percent 50
```

Runs save separate CSV, JSON, and console log files in a timestamped
`results/fixed-*` directory. The runner also writes `results/comparison.md`.
All measurements remain `NOT EXECUTED` until the load suite actually runs.
