# Load test results

Run the naive seller test matrix from the project root with:

```powershell
python -m load_test.run_suite --concurrency 100
```

The runner creates a timestamped `naive-*` directory here. Each experiment
stores a per-request CSV, a JSON metrics and invariant report, and a console log.
The matrix is 100 tickets with 100, 1,000, 10,000, and 50,000 attempts, followed
by a configurable concurrent duplicate-request-ID run. Failed runs keep their
logs in place as evidence. No measured results should be inferred until those
files have been produced by an actual run against the naive seller.
