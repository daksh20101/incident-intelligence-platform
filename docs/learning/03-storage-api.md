# Step 3 — Storage & ingestion API

**Goal:** monitoring tools and the service desk can **send** incidents and tickets to the platform over HTTP, everything is stored in a real database, and anyone can **query** it back, page by page.

## 1. Why a database?

In Step 2 the data lived in files. Files are fine for a one-off script, but a running service needs more:

| Need | Files | Database |
|---|---|---|
| "P1 incidents on order-service this week" | read every line, filter in Python | one query; an **index** jumps straight to the rows |
| Two programs writing at once | they overwrite each other | **transactions** keep the data consistent |
| A crash halfway through saving | half-written file | all-or-nothing: the transaction rolls back |
| Add one incident | rewrite the file | insert one row |

We use **SQLite**: a full SQL database stored in one file (`data/incident_intel.db`), with nothing to install. Because the code talks to it through SQLAlchemy, moving to **PostgreSQL** in production means changing `DATABASE_URL` in `.env`, not the code.

## 2. Tour of the new code

| File | What it does |
|---|---|
| `storage/tables.py` | The tables, as Python classes (one class = one table, one attribute = one column) |
| `storage/db.py` | Connecting: the **engine** and **sessions** |
| `storage/repository.py` | Functions like `get_incident()` and `list_incidents()`. **The only code that touches tables**; everything else gets Pydantic models back |
| `storage/loader.py` + `scripts/load_data.py` | Load the Step 2 files into the database |
| `api/deps.py` | Shared pieces: `SessionDep`, pagination parameters, the `Page` response |
| `api/incidents.py`, `api/tickets.py`, `api/topology.py` | The endpoints, grouped by topic (FastAPI **routers**) |
| `api/main.py` | Puts the routers together; adds `/ready` |
| `tests/conftest.py` | Fixtures: every test gets a fresh, empty in-memory database |
| `.pre-commit-config.yaml` | Runs Ruff automatically before every commit |

The flow of one request:

```
POST /incidents  ->  api/incidents.py  ->  storage/repository.py  ->  storage/tables.py  ->  SQLite
  (JSON)            validates with the     converts the model         the rows
                    Incident model         into a row
```

## 3. Try it

```bash
uv sync
uv run python scripts/generate_data.py
uv run python scripts/load_data.py
uv run uvicorn incident_intel.api.main:app --reload
```

Open <http://127.0.0.1:8000/docs>:

1. **GET /incidents** → *Try it out* → set `limit` to 5 → *Execute*. You get the 5 newest incidents and `total`.
2. **POST /incidents** → *Try it out* → edit the example JSON: give it an `id` like `INC-9001`, an `opened_at` like `2026-10-21T09:00:00+02:00`, and valid values for the other fields. *Execute* → **201**. Execute again with the same JSON → **200** (a safe retry). Change the title and execute again → **409**.
3. **GET /incidents/INC-9001**: notice `opened_at` came back as `07:00:00Z`. It was converted to UTC.
4. **GET /deployments** with `service` = `order-service`: what changed on that service, and when.

Stop the server with `Ctrl + C`.

## 4. Concepts, in plain words

**ORM (Object-Relational Mapper).** SQLAlchemy lets you write `select(IncidentRow).where(IncidentRow.service == "order-service")` instead of the SQL text `SELECT * FROM incidents WHERE service = 'order-service'`. It builds the SQL for you, safely: values are sent separately from the SQL text, which prevents **SQL injection**.

**Engine, session, transaction.** The *engine* knows how to reach the database (one per app). A *session* is one unit of work. Changes are only saved on `session.commit()`, and they're saved **all together or not at all**: that's a *transaction*. The loader uses one transaction for everything, so a bad file leaves the database untouched.

**Index.** Like the index at the back of a book: instead of reading every page (row) to find "order-service", the database looks it up. We index the columns we filter and sort by (`service`, `priority`, `opened_at`). The cost: slightly slower writes and more disk space.

**Repository pattern.** The API never touches tables directly; it calls `repository.list_incidents()` and gets `Incident` models back. Storage details stay in one file, so swapping the database, or adding a cache, changes that file only.

**REST and HTTP status codes.** Resources are nouns (`/incidents`), actions are HTTP methods: `GET` reads, `POST` creates. The status code tells the client what happened:

| Code | Meaning | When we return it |
|---|---|---|
| 200 OK | worked | reads; a repeated identical POST |
| 201 Created | a new record was stored | first POST of an incident |
| 404 Not Found | no such record | `GET /incidents/NOPE` |
| 409 Conflict | clashes with what's stored | same id, different data |
| 422 Unprocessable | the request itself is invalid | `priority: "P9"`, `limit: 9999`, a time with no timezone |
| 503 Service Unavailable | can't work right now | `/ready` when the database is down |

**Idempotency.** An operation is idempotent if doing it twice has the same effect as doing it once. Networks fail and monitoring tools **retry**; without idempotency every retry would create a duplicate incident. Because the sender chooses the `id`, we can recognise a repeat.

**Pagination.** Never return "everything": 300,000 rows would freeze the client. `limit` is the page size (capped at 500) and `offset` is how many rows to skip. `total` tells the client how many pages there are. (At very large scale, *cursor* pagination such as "after id X" is faster than offsets.)

**Dependency injection.** Routes ask for `session: SessionDep` and FastAPI provides one, then closes it after the response. Tests replace the provider (`app.dependency_overrides`) with a test database, without changing a line of route code.

**Timezones in SQLite.** SQLite silently drops the `+02:00` part of a timestamp. Our `UTCDateTime` column type converts every time to UTC before saving and re-attaches UTC when reading. Without it, times would come back "naive" and could be off by hours in an incident timeline.

**Migrations.** `create_all()` creates missing tables, but it can't *change* an existing one, for example to add a column. Real projects use a migration tool (**Alembic** for SQLAlchemy) that keeps versioned scripts of every schema change. For now we rebuild the database from files whenever the schema changes.

**Branches, pull requests, pre-commit.** See Parts E and F of `docs/GITHUB_GUIDE.md`.

## 5. Ship Step 3 as your first pull request

First, once:

```bash
uv sync
uv run pre-commit install
uv run pytest
```

Expect **45 passed**. Then follow Part E of `docs/GITHUB_GUIDE.md` with the branch name `feature/storage-api`.

## 6. Your turn ✍️ — filter incidents (test first)

An on-call engineer doesn't want *all* incidents. They want "open P1s on order-service". Add three optional filters to `GET /incidents`: `service`, `priority` and `status`.

This time you'll work **test-first** (TDD, test-driven development): write the tests, watch them fail, then write the code that makes them pass.

**1. Start a new branch** (after your Step 3 PR is merged):

```bash
git switch main
git pull
git switch -c feature/incident-filters
```

**2. Paste these tests at the bottom of `tests/test_api_incidents.py`:**

```python
def test_incidents_can_be_filtered_by_service_and_priority(client: TestClient) -> None:
    client.post("/incidents", json=make_incident(id="INC-1", priority="P1"))
    client.post("/incidents", json=make_incident(id="INC-2", priority="P3"))
    client.post("/incidents", json=make_incident(id="INC-3", service="api-gateway"))

    by_service = client.get("/incidents", params={"service": "order-service"}).json()
    by_both = client.get("/incidents", params={"service": "order-service", "priority": "P1"})

    assert {i["id"] for i in by_service["items"]} == {"INC-1", "INC-2"}
    assert by_service["total"] == 2
    assert [i["id"] for i in by_both.json()["items"]] == ["INC-1"]


def test_incidents_can_be_filtered_by_status(client: TestClient) -> None:
    client.post("/incidents", json=make_incident(id="INC-1"))
    client.post("/incidents", json=make_incident(id="INC-2", status="resolved"))

    page = client.get("/incidents", params={"status": "open"}).json()

    assert [i["id"] for i in page["items"]] == ["INC-1"]


def test_unknown_priority_filter_is_rejected(client: TestClient) -> None:
    response = client.get("/incidents", params={"priority": "P9"})

    assert response.status_code == 422
```

**3. Run `uv run pytest`.** Expect **3 failed, 45 passed**. Red is good: it proves the tests really check something.

**4. Make them pass.** Two places to change.

*a) `src/incident_intel/storage/repository.py`, function `list_incidents`:*
- Add three keyword parameters: `service: str | None = None`, `priority: Priority | None = None` and `status: IncidentStatus | None = None`.
- Add `Priority` and `IncidentStatus` to the `from incident_intel.domain import (...)` list at the top.
- Right after `query = select(IncidentRow)`, add one `if ... is not None:` block per filter that does `query = query.where(...)`. **`list_deployments` in the same file does exactly this. Copy its pattern.**
- The `total` line already uses `query`, so the count respects your filters automatically.

*b) `src/incident_intel/api/incidents.py`, function `list_incidents`:*
- Add the same three parameters to the function, before `limit`. FastAPI turns plain parameters like `service: str | None = None` into query parameters (`?service=...`). Typing `priority` as `Priority` gives you the 422 for "P9" for free.
- Pass them on: `repository.list_incidents(session, service=service, priority=priority, status=status, limit=limit, offset=offset)`.
- Add `IncidentStatus, Priority` to the `from incident_intel.domain import Incident` line.
- Heads-up: a parameter called `status` hides the `status` module imported at the top, **inside this one function only**. That's fine here because this function doesn't use the module.

**5. Run `uv run pytest`** → **48 passed**. Then try it in `/docs`: `GET /incidents` now shows three new boxes.

**6. Ship it:**

```bash
git add -A
git commit -m "feat: filter incidents by service, priority and status"
git push -u origin feature/incident-filters
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git switch main
git pull
```

## 7. Interview questions from this step

<details><summary><b>Why separate the database tables from the domain models?</b></summary>

The domain models are the contract the rest of the system relies on. Tables are a storage detail: indexes, column types, timezone handling. Keeping them apart (with a repository converting between them) means I can change storage, or move to Postgres, without touching business logic, and the API can't accidentally expose database internals.
</details>

<details><summary><b>How did you make ingestion idempotent? What about two identical requests at the same moment?</b></summary>

The sender provides the id. On POST I look it up: not found → insert, 201; found and identical → 200 with the stored record; found but different → 409. Two simultaneous requests could both see "not found"; the primary key constraint makes the second insert fail, so the fix is to catch that integrity error and re-run the comparison. At higher scale you'd use an idempotency key header or an upsert (`INSERT ... ON CONFLICT`).
</details>

<details><summary><b>Offset vs cursor pagination?</b></summary>

Offset is simple and allows jumping to page N, but the database still walks past all skipped rows, and results shift if new rows arrive between requests. Cursor pagination ("give me 50 after this opened_at/id") uses the index directly and is stable under inserts. It's better for large, fast-changing feeds like an incident stream.
</details>

<details><summary><b>Why SQLite, and when would you switch?</b></summary>

Zero setup, one file, fast for a single server and for tests (in-memory). I'd switch to Postgres for many concurrent writers, several API servers sharing one database, or managed backups and replication. With SQLAlchemy that's a URL change plus a migration tool like Alembic.
</details>

<details><summary><b>What's SQL injection and how does your code avoid it?</b></summary>

When user input is pasted into SQL text, input like `x' OR '1'='1` can change the query's meaning. SQLAlchemy sends values as bound parameters, separate from the SQL text, so input is always treated as data, never as SQL.
</details>

<details><summary><b>How do your tests avoid touching real data?</b></summary>

A pytest fixture creates a fresh in-memory SQLite database per test and overrides the FastAPI session dependency to use it. Tests are isolated, fast and repeatable, with no cleanup needed.
</details>

<details><summary><b>Why branches and pull requests for a solo project?</b></summary>

`main` stays deployable, CI checks every change before it lands, and the PR is a written record of what changed and why. It's also exactly how teams work, so it shows I can collaborate.
</details>
