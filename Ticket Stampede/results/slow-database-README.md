# Slow database experiment (NOT EXECUTED)

No measurements are available for this experiment. Run only against a disposable
MySQL database and the local fixed seller. The trigger deliberately adds 250 ms
to each ticket insert while it exists. Leaving it installed for 10 seconds
simulates a period of degraded datastore service; queued transactions may
continue after recovery.

## Procedure

1. Start MySQL and the fixed API using a dedicated test database. Confirm the
   database contains the expected `sale` and `tickets` tables.
2. From the repository root, start the seller (`uvicorn app.main:app --host
   127.0.0.1 --port 8000`).
3. Open a second PowerShell window in the repository root. Install the delay
   trigger in the same database used by the API:

   ```powershell
   Get-Content results/slow_db_insert_trigger.sql | mysql -u ticket_stampede -p ticket_stampede
   $slowStart = [DateTimeOffset]::UtcNow
   ```

4. Start a 1,000-request burst at concurrency 100. This client calls `/reset`
   first, then writes per-request status, latency, request ID, ticket number,
   and outcome to CSV and a status/invariant snapshot to JSON:

   ```powershell
   $out = "results/slow-db-run"
   $client = Start-Process -FilePath python -WindowStyle Hidden -PassThru `
     -ArgumentList @("-m", "load_test.client", "--seller-url", "http://127.0.0.1:8000", `
       "--ticket-count", "1000", "--total-requests", "1000", "--concurrency", "100", `
       "--output-csv", "${out}-requests.csv", "--output-json", "${out}-report.json") `
     -RedirectStandardOutput "${out}.stdout.txt" -RedirectStandardError "${out}.stderr.txt"
   ```

5. Immediately after launching the client, hold the slowdown for approximately
   ten seconds and remove it. In that same PowerShell window:

   ```powershell
   Start-Sleep -Seconds 10
   Get-Content results/slow_db_drop_trigger.sql | mysql -u ticket_stampede -p ticket_stampede
   $slowEnd = [DateTimeOffset]::UtcNow
   "slow_window_start_utc,slow_window_end_utc`n$($slowStart.ToString('o')),$($slowEnd.ToString('o'))" | Set-Content results/slow-db-window.csv
   Wait-Process -Id $client.Id
   ```

6. Review `slow-db-run-report.json` and `slow-db-run-requests.csv`. Each request
   row includes a UTC start time so latency can be separated approximately by
   comparing it with `slow-db-window.csv`. The JSON status snapshot records `sold_count`
   and actual tickets; calculate duplicate ticket numbers from
   `status_snapshot.issued_tickets`. Check the four saved invariant results
   after recovery. Preserve stdout, stderr, CSV, JSON, and the SQL trigger logs
   together as the experiment evidence.

   Print the final sold count, ticket count, duplicate-number count, and
   invariant outcomes from the saved JSON:

   ```powershell
   python -c "import json; r=json.load(open('results/slow-db-run-report.json', encoding='utf-8')); s=r['status_snapshot']; t=s['issued_tickets']; n=[x['ticket_number'] for x in t]; print({'sold_count':s['sold_count'],'actual_tickets':len(t),'duplicate_ticket_numbers':len(n)-len(set(n)),'invariants':r['invariants'],'errors':r['errors'],'p99_ms':r['p99_latency_ms']})"
   ```

The 250 ms insert delay is applied per insert during the trigger window; it can
cause lock queues and longer request times. Trigger DDL requires the MySQL user
to have trigger privileges. If creation or removal fails, stop the client,
remove the trigger manually, and mark the run invalid rather than interpreting
partial data as a completed experiment. Never use this trigger on a production
database.
