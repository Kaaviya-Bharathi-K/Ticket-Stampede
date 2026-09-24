# Advanced performance runbook

The environment used to prepare this project could not launch its configured
PowerShell runtime. No load limit or slow database experiment has been executed.

## Load limit

Install requirements, start MySQL with a dedicated benchmark database, and
start the fixed FastAPI seller. Then run from the project root:

```powershell
python -m load_test.performance_suite --seller-url http://127.0.0.1:8000 --requests 50000 --concurrencies 100 500 1000 5000 10000 25000 50000
```

This holds the request count and ticket capacity at 50,000 across all levels so
concurrency is the changing input. It records request metrics, server and MySQL
CPU/memory samples, MySQL `Threads_connected`, and periodic `SELECT 1` latency
probes. Output includes `benchmark.csv` and raw data in `results/`.

Mark latency degradation only after comparing measured rows. Attribute a
bottleneck only when telemetry supports it; CPU, memory, connection usage, and
query probes are evidence, not presumed causes. If the seller/MySQL processes
or permissions prevent sampling, the corresponding CSV fields remain empty.

## Slow database

Follow `slow-database-README.md` on an isolated database. It adds a temporary
250 ms delay to each ticket insert for approximately ten seconds, runs a
concurrent purchase burst, removes the trigger, and records request/status
evidence. Run logs and results must distinguish the induced-delay window from
the recovery period. The trigger SQL is in `slow_db_insert_trigger.sql`; remove
it with `slow_db_drop_trigger.sql` even if the experiment is interrupted.

The invariant results in the client JSON are evaluated after `GET /status`
returns. The fixed backend's correctness still requires an actual completed run;
this runbook does not substitute for that evidence.
