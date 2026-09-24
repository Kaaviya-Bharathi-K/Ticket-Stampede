# Advanced performance analysis

## Status

**NOT EXECUTED.** The workspace could not start its configured PowerShell
runtime, so no seller or MySQL process was measured. Consult
`performance-load-limit.csv` for the unmeasured concurrency rows.

## OBSERVATION

No measured throughput, latency, error, CPU, memory, MySQL connection, or query
probe data is available. A latency degradation point cannot be identified.

## INTERPRETATION

No bottleneck attribution is possible without measurements. The local runner
records seller and MySQL process CPU/memory, `Threads_connected`, and timed
`SELECT 1` round-trip probes where permissions allow. The probe is a database
round-trip indicator, not a per-application-query trace. Compare the samples
with request latency before attributing a bottleneck.

Run the required matrix using `python -m load_test.performance_suite` after
installing requirements and starting the fixed seller and MySQL. The runner
uses a constant 50,000 requests and a 50,000-ticket sale at each concurrency
level, with levels 100, 500, 1,000, 5,000, 10,000, 25,000, and 50,000. It saves
the benchmark summary CSV, request CSVs, telemetry CSVs, and per-run logs under
a timestamped directory in `results/`.
