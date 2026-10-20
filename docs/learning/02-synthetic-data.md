# Step 2 — Domain model & synthetic data

**Goal:** a realistic, reproducible dataset of a company's operations (metrics, logs, alerts, tickets, deployments) with incidents planted inside, and the true answer for each one.

## 1. Why synthetic data?

To evaluate an AI system you need **labeled** data: "this alert was caused by *that* database running out of connections". Real companies rarely have that written down, and their data is private. So we build a fictional company, break it on purpose, and record exactly what we broke. That record is the **ground truth**. Every later step gets a score against it, which is what turns "I built an AI thing" into "I built an AI thing that finds the right root cause 8 times out of 12".

The trade-off: synthetic data only tests what you thought to plant. We fight that with noise (routine tickets, false alarms, typos) and traps (decoy deployments). Later we can sanity-check on public datasets like Loghub.

## 2. Tour of the new code

| File | What it does |
|---|---|
| `src/incident_intel/domain/models.py` | The vocabulary: `Service`, `Deployment`, `MetricPoint`, `LogEvent`, `Incident`, `Ticket`, and the ground-truth `SeededIncident`, plus enums like `Priority` and `MetricName` |
| `synthetic/topology.py` | ShopFast's 15 services and who calls whom; `callers_of()` computes the blast radius |
| `synthetic/signals.py` | What *normal* looks like: daily traffic waves, noise, background logs. Also `MetricEffect`: how incidents bend metrics |
| `synthetic/context.py` | `ScenarioContext`: the toolbox for planting an incident (`change_metric`, `log`, `alert`, `tickets`, `deploy`, …) |
| `synthetic/scenarios.py` | The recipes: one class per kind of incident. **You'll add one here** |
| `synthetic/background.py` | Everyday noise: harmless deploys, routine tickets, false alarms |
| `synthetic/world.py` | `World` collects everything, renumbers ids in time order and saves the files |
| `synthetic/generator.py` | `generate_world()` runs it all in order |
| `scripts/generate_data.py` | The command-line entry point |
| `docs/DATA.md` | Data dictionary: every file and field |

Run it:

```bash
uv run python scripts/generate_data.py
```

Then look inside `data/synthetic/`. In VS Code, open `ground_truth.json` and pick one seeded incident. Then find its alerts in `incidents.jsonl` and its tickets in `tickets.jsonl` (Cmd + F for the ids).

## 3. Concepts, in plain words

**Classes and inheritance.** `Scenario` is an *abstract base class*: it says "every scenario has a `root_cause`, `candidate_services` and an `inject()` method" but doesn't implement `inject()` itself. `BadDeployment(Scenario)` *inherits* from it and fills in the details. The generator can then treat every scenario the same way (`scenario.inject(ctx)`) without knowing which one it is. That idea is called *polymorphism*.

**dataclass vs Pydantic model.** Both define a class with typed fields. A `@dataclass` (like `World`, `MetricEffect`) is a plain container for our own internal objects. A Pydantic `BaseModel` (like `Ticket`) also **validates**, which we want for data crossing a boundary (files, the API). Rule of thumb: Pydantic at the edges, dataclasses inside.

**Enums.** `Priority.P1` instead of the string `"P1"`: only valid values are possible, the editor autocompletes them, and a typo is an error instead of a silent bug.

**Timezone-aware datetimes.** Every timestamp carries `+00:00` (UTC). Mixing "naive" times (no timezone) with aware ones causes off-by-hours bugs, the kind that wreck an incident timeline. Pydantic's `AwareDatetime` refuses naive ones.

**Reproducibility with seeds.** `random.Random(42)` produces the same "random" numbers every run. One `rng` object is passed everywhere, so the same seed gives byte-identical files. A test checks exactly that.

**Seasonality.** Traffic follows a sine wave over 24 hours (busy evenings, quiet mornings), and weekends are 20% busier. Anomaly detectors must not flag "it's 7 pm and busy" as an incident; that's Step 7's challenge.

**Propagation and blast radius.** When `order-db` breaks, `order-service` (1 hop) suffers most, then `api-gateway` (2 hops), then `web-frontend` (3 hops). `callers_of()` finds them with a *breadth-first search* over the dependency arrows, walked backwards. Symptoms show up far from the cause, which is why root-cause analysis is hard.

**Data leakage.** If incident tickets had been created last, they'd all have the highest ids, and a model could "detect incidents" by looking at the id. `World._renumber()` assigns ids in time order to remove that shortcut. Leakage (a model using information it won't have in real life) is one of the most common ML interview topics.

**JSON Lines.** One JSON object per line. Unlike one big JSON array, you can append to it and read it line by line without loading the whole file. That's ideal for logs and events.

## 4. Your turn ✍️ — add a `CertificateExpiry` scenario

**The story:** a service's TLS certificate expires at midnight. Nothing was deployed and nothing was changed; the clock simply ran out. Every caller suddenly fails the TLS handshake, so errors jump to almost 100% at one exact moment. Logs are full of `CERTIFICATE_VERIFY_FAILED`.

**1. Add the root cause.** In `src/incident_intel/domain/models.py`, add a fifth member (the last line here) to `RootCauseType`:

```python
class RootCauseType(StrEnum):
    BAD_DEPLOYMENT = "bad_deployment"
    DB_CONNECTION_POOL_EXHAUSTION = "db_connection_pool_exhaustion"
    THIRD_PARTY_OUTAGE = "third_party_outage"
    CACHE_MEMORY_PRESSURE = "cache_memory_pressure"
    CERTIFICATE_EXPIRY = "certificate_expiry"
```

**2. Write the scenario.** In `src/incident_intel/synthetic/scenarios.py`, paste this **above** the `SCENARIOS` list and replace every `____`. The other four scenarios in that file are your examples.

```python
class CertificateExpiry(Scenario):
    """A TLS certificate expires: every call to the service fails at once."""

    root_cause = RootCauseType.____
    candidate_services = ("auth-service", "catalog-service", "payment-service")
    duration_minutes = (15, 45)
    expected_runbook = "tls-certificate-expiry"

    def priority_for(self, service: str) -> Priority:
        return ____

    def inject(self, ctx: ScenarioContext) -> None:
        root = ctx.root_service
        callers = ctx.direct_callers()

        ctx.change_metric(root, ERROR_RATE, target=____)
        ctx.spread_to_callers(error_rate=____, latency_factor=1.5)

        for caller in callers:
            ctx.log(
                caller,
                [
                    f"SSL: CERTIFICATE_VERIFY_FAILED certificate has expired ({root}:443)",
                    ____,
                ],
                every_minutes=1,
            )

        ctx.alert(
            callers[0],
            ERROR_RATE,
            after_minutes=ctx.rng.randint(2, 5),
            title=____,
        )

        ctx.tickets(
            [
                (____, ____),
                (____, ____),
            ],
            category=TicketCategory.AVAILABILITY,
        )

        ctx.summary = ____
        ctx.remediation = ____
```

**Hints**
- Errors are near-total: a `target` around `0.9` for the root, and a similar `error_rate` for `spread_to_callers`.
- `priority_for` returns a `Priority`, for example `Priority.P1`. Make it depend on the service if you like (look at `BadDeployment.priority_for`).
- The second log message could be a retry or handshake error, e.g. `f"TLS handshake with {root} failed: certificate expired"`.
- Users don't see TLS errors directly. They see "login failed" or "page won't load", so write tickets the way a customer would.
- `summary` explains what happened. `remediation` says what to do: renew the certificate, deploy it, then automate renewal and add an expiry alert.

**3. Register it.** Add `CertificateExpiry` to the `SCENARIOS` list at the bottom of the file.

**4. Check it.** The existing tests automatically include your scenario, because they plant one of every type. They check that:
- your alert really crosses its threshold
- the root service shows a clear change in its metrics
- the ground truth is consistent

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run python scripts/generate_data.py --incidents 15
```

You're aiming for **24 passed** and your `certificate_expiry` incidents listed in the generator's output. If a test fails, its message names the incident and check that failed; paste it to Claude if you're stuck. Then commit and push.

## 5. Interview questions from this step

<details><summary><b>Why did you use synthetic data, and what are its limits?</b></summary>

Real incident data is private and unlabeled, and evaluation needs labels. Synthetic data gives ground truth, control over rare events and reproducibility. Its limit: it only contains failure modes I thought of, so a model can look great on it and still fail on reality. I mitigate with noise, decoys and false alarms, and would validate on public datasets (e.g., Loghub) or a pilot with real data.
</details>

<details><summary><b>How do you make data generation reproducible?</b></summary>

A single seeded `random.Random` instance passed everywhere (never the global one), deterministic ids, a fixed start date, and a test that generates twice and compares the files byte for byte.
</details>

<details><summary><b>What is data leakage? Give an example from your project.</b></summary>

When a model learns from information that won't exist at prediction time, or from an accidental shortcut. Here, ids assigned in creation order would have made incident tickets identifiable by id alone; I renumber ids chronologically. Another one is coming in Step 6: using a ticket's `resolved_at` to predict whether it will breach its SLA.
</details>

<details><summary><b>Why is the loudest alert often not the root cause?</b></summary>

Failures propagate up the dependency chain: a database problem shows up as gateway 5xx errors and frontend slowness. Alerts fire on symptoms. RCA has to walk the dependency graph back towards the cause, using timing (who broke first) and evidence (logs, deploys).
</details>

<details><summary><b>Why plant decoy deployments and false alarms?</b></summary>

So the system can't score well with lazy heuristics like "blame the latest deploy" or "every alert is an incident". They let me measure precision, not just recall.
</details>

<details><summary><b>JSON Lines vs CSV vs Parquet?</b></summary>

JSONL suits event records with varied or nested fields and is easy to stream and append. CSV suits flat numeric tables. Parquet is columnar and compressed, which is best for large analytical workloads. I'd switch metrics to Parquet if the data grew.
</details>
