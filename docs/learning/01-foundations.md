# Step 1 — Foundations

**Goal:** a professional project skeleton that runs, is tested, is checked automatically on GitHub, and can talk to a free LLM.

## 1. Tour of the files

| File | What it is | Why it matters |
|---|---|---|
| `pyproject.toml` | The project's ID card: name, Python version, dependencies, tool settings | One standard file every Python tool understands |
| `uv.lock` | Created by `uv sync`. Exact versions of every package | Everyone (you, CI, an interviewer cloning the repo) installs *identical* versions |
| `.python-version` | Says "use Python 3.12" | uv downloads that version automatically |
| `src/incident_intel/` | The application package. `__init__.py` makes a folder importable | The "src layout" stops tests from accidentally importing half-finished files |
| `src/incident_intel/config.py` | All settings, typed, read from environment variables / `.env` | No hard-coded URLs or secrets in code |
| `src/incident_intel/api/main.py` | The FastAPI app and its first endpoint, `/health` | The front door every other feature plugs into |
| `scripts/check_llm.py` | Sends one chat and one embedding request to the LLM | Proves your free LLM access works end to end |
| `tests/` | Automated checks run by `pytest` | Lets you change code without fear |
| `.github/workflows/ci.yml` | Instructions GitHub follows on every push | Green check on GitHub = lint + tests pass on a clean machine |
| `.env.example` / `.env` | Template of settings (committed) / your real settings (never committed) | Secrets stay off GitHub |
| `.gitignore` | Files git must ignore | Keeps the repo clean and safe |

## 2. Concepts, in plain words

**Virtual environment (`.venv/`).** A private folder of packages just for this project, so projects don't fight over versions. `uv sync` creates it; `uv run <command>` runs a command inside it.

| Command | Meaning |
|---|---|
| `uv sync` | Install exactly what `pyproject.toml` + `uv.lock` say |
| `uv run pytest` | Run the tests inside the project's environment |
| `uv add pandas` | Add a new dependency (updates `pyproject.toml` and `uv.lock`) |

**API and endpoint.** An API lets programs talk to your program over HTTP. An *endpoint* is one address + method, like `GET /health`. FastAPI turns a normal Python function into an endpoint with a *decorator*:

```python
@app.get("/health", response_model=HealthResponse)  # decorator: "call this for GET /health"
def health() -> HealthResponse:  # "-> HealthResponse" is a type hint
    return HealthResponse(status="ok", environment=settings.environment)
```

**Pydantic model.** A class that describes the *shape* of data. `class HealthResponse(BaseModel): status: str` means "a response always has a text field called status". Pydantic validates data against it and FastAPI uses it to generate the docs page at `/docs`. We will use Pydantic models everywhere, including to force the LLM to answer in a fixed JSON shape (Step 4).

**Configuration via environment variables (12-factor app).** Code reads settings from the environment instead of hard-coding them. `pydantic-settings` reads `LLM_MODEL=...` from your `.env` into `settings.llm_model`, with type checking. The same code then runs on your laptop, in CI and in production with different settings.

**Local LLM, Ollama and quantization.** Ollama runs open-weight models on your Mac. `qwen3:8b` has 8 billion parameters; stored at full 16-bit precision that's ~16 GB, but Ollama uses a *4-bit quantized* version (~5 GB) with only a small quality loss. That's why it fits in 16 GB of RAM.

**OpenAI-compatible API.** Ollama, Groq and Gemini all accept the same request format as OpenAI. So our code uses the `openai` Python package and only changes `base_url` + `api_key` + `model` to switch providers. That's an *abstraction*: the rest of the app never cares which provider is behind it.

**Embedding.** A list of numbers (a vector; 768 numbers for `nomic-embed-text`) that represents the *meaning* of a text. Texts with similar meaning get nearby vectors. We'll use this to spot duplicate incidents (Step 5) and to search runbooks (Step 9).

**Tests and CI.** `tests/test_health.py` calls the API in-process and asserts the answer. CI re-runs lint + tests on GitHub's machines for every push, so broken code is caught immediately.

## 3. Your turn ✍️

**Task:** add a `GET /version` endpoint that returns:

```json
{"name": "Incident Intelligence Platform", "version": "0.1.0"}
```

**Hints**

1. In `src/incident_intel/api/main.py`, copy the pattern of `HealthResponse`: create `class VersionResponse(BaseModel)` with two fields, `name: str` and `version: str`.
2. Add a function decorated with `@app.get("/version", response_model=VersionResponse, tags=["system"])`.
3. Use the values you already have in that file: `settings.app_name` and `__version__`.
4. In `tests/test_health.py`, add `test_version_returns_package_version()` that calls `client.get("/version")` and asserts the status code is 200 and `response.json()["version"] == __version__` (import it with `from incident_intel import __version__`).

**Check your work**

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

The first command auto-formats your code. Expect **All checks passed!** from the second and **5 passed** from the third.

Then commit and push (see `docs/GITHUB_GUIDE.md`, Part C), and paste your code to Claude for a review.

## 4. Interview questions from this step

<details><summary><b>Why FastAPI instead of Flask?</b></summary>

FastAPI validates requests and responses from type hints via Pydantic, generates OpenAPI docs automatically, and supports async natively, which matters for I/O-heavy services like ones that call LLMs and databases. Flask is simpler but you add validation and docs yourself.
</details>

<details><summary><b>What's a health check? Liveness vs readiness?</b></summary>

Liveness answers "is the process alive?" (if not, restart it). Readiness answers "can it serve traffic right now?" (are the database and LLM reachable?). Orchestrators like Kubernetes call both. Our `/health` is liveness; we'll add readiness once we have dependencies.
</details>

<details><summary><b>How do you handle configuration and secrets?</b></summary>

Environment variables, validated by a typed settings class. A committed `.env.example` documents them; the real `.env` is git-ignored. In production, secrets come from a secret manager (AWS Secrets Manager, Vault, Kubernetes secrets), never from the repo.
</details>

<details><summary><b>Why run the LLM locally instead of calling a hosted API?</b></summary>

Cost (free), privacy (incident data can contain hostnames, customer info, credentials in logs), no rate limits, works offline. Trade-offs: a small model is less capable than frontier models and slower on a laptop. Because the client is provider-agnostic, we can switch per environment.
</details>

<details><summary><b>What is quantization?</b></summary>

Storing model weights with fewer bits (e.g., 4 instead of 16). It cuts memory roughly 4× and speeds up inference with a small accuracy loss, which is what makes 8B models run on laptops.
</details>

<details><summary><b>Why commit a lock file and run CI?</b></summary>

The lock file pins exact versions so builds are reproducible ("works on my machine" goes away). CI runs lint and tests on a clean machine for every change, catching regressions before they're merged.
</details>
