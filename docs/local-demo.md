# Try a measured local aggregation example

Follow the [synthetic aggregation walkthrough](aggregation-walkthrough.md): simplify a numeric aggregation query while preserving the expected result. DataVouch combines performance, correctness and reliability evidence so that speed alone cannot approve the change.

This demo generates 1,000 groups with 3,000 sample rows in an in-memory SQLite database. Each group has values 45, 75 and 120 with respective weights 1, 2 and 3. An independent Python calculation supplies the expected weighted sum of 555,000 units. It executes each query three times and measures runtime; nothing connects to a cloud account.

## Run it

From the installed source environment, choose a new output directory:

```sh
.venv/bin/python -m datavouch demo --output-dir .local_context/weighted-aggregation-demo
.venv/bin/python -m datavouch serve .local_context/weighted-aggregation-demo/catalog.json --port 8767
```

The second command asks you to choose a password. Keep it running, open `http://127.0.0.1:8767`, and sign in as `datavouch`. Open **Example walkthrough**, then follow the links to **Weighted aggregation** reports. If using the installed command rather than this source environment, replace `.venv/bin/python -m datavouch` with `datavouch`.

| Scenario | What actually happens | Decision |
| --- | --- | --- |
| Equivalent rewrite | A single aggregate replaces repeated correlated aggregates; both return 555,000 units | Correctness PASS; overall PASS when measured runtime also meets policy |
| Incorrect rewrite | The faster query forgets to multiply sample values by weights and returns 240,000 units | FAIL even when performance improves |
| Missing evidence | Reuses the equivalent query measurements but deliberately omits correctness evidence | Correctness UNKNOWN; overall UNKNOWN when other checks pass |

The incorrect result is half the expected weighted total. The benefit is a reviewable release decision that catches this error before someone treats the optimization as successful. A production pipeline can use `datavouch gate` with a policy that blocks FAIL and UNKNOWN. DataVouch evaluates provided evidence; in this demo the independent checker is included so you can inspect how that evidence was produced.

Timing varies by machine and load. The demo does not promise a speedup, prove statistical significance, benchmark BigQuery or establish cloud savings. Aggregation correctness is a business check, not cloud cost evidence. Financial savings remain UNKNOWN because no pricing or billing evidence is supplied.

## Inspect and reproduce

The output directory contains the SQL, raw measurements, expected and observed totals (`observations.json`), a concise `summary.json`, verification inputs, reports and the UI catalog. To replay the wrong-result decision:

```sh
.venv/bin/python -m datavouch verify .local_context/weighted-aggregation-demo/incorrect-input.json
```

Exit code `1` means the verification correctly rejected the incorrect result. The equivalent case uses exit `0` when all checks pass; missing evidence uses `3` when no check fails. Replaying saved inputs produces byte-identical reports. Executing the demo again measures new timings, so use a new output directory; existing evidence is never overwritten.

## Run the same demo with Compose

First follow [container setup](container.md) to initialize the configuration/data directories and password. Then:

```sh
docker compose -f deployment/container/compose.yaml build
docker compose -f deployment/container/compose.yaml run --rm --no-deps datavouch demo --output-dir /data/demo
docker compose -f deployment/container/compose.yaml -f deployment/container/compose.demo.yaml up -d
```

Open the localhost port configured through `DATAVOUCH_PORT`. Use the same password file as the base container setup. Run `down` with the same Compose files when finished; the host data directory remains. For an intentional new measurement, select a new demo output directory and adjust the catalog path accordingly.

Use `--groups 100` to run a smaller example, up to 2,000 groups. Totals scale with group count.
