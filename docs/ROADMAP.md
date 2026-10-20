# Roadmap

Each step is roughly one working session. Every step ends with: working code, passing tests, a commit pushed to GitHub, and a learning note in `docs/learning/` with interview questions.

**Who writes what:** Claude builds the plumbing; **you write the core AI pieces** marked "You write" (with hints and a review).

| # | Step | What gets built | You write | Interview angle |
|---|---|---|---|---|
| 1 | **Foundations** ✅ | Repo, uv, FastAPI skeleton, typed config, free local LLM, tests, CI | `/version` endpoint + test | Config & secrets, why local LLMs, CI |
| 2 | **Domain model & synthetic data** | Pydantic models (Incident, Ticket, LogLine, MetricPoint, Service, Deployment); generator for a fake company with ~15 services and **seeded incidents with known root causes** | One new incident scenario | "How do you evaluate with no real data?" |
| 3 | **Storage & ingestion API** | SQLModel + SQLite, POST/GET endpoints, validation, pagination; first feature branch + pull request | Filters on `GET /incidents` | REST design, ORMs, idempotency |
| 4 | **LLM layer** | Provider-agnostic client, structured outputs (Pydantic → JSON schema), retries/timeouts, prompt templates, token & latency logging, mock LLM for tests | Summarization prompt + schema | Structured output, prompt design, testing LLM code |
| 5 | **Triage** | Classifier (TF-IDF baseline → embeddings → LLM, compared), dedup by embedding similarity + time window, ITIL impact × urgency priority | Cosine-similarity dedup | Baselines first, precision vs recall, when *not* to use an LLM |
| 6 | **SLA breach prediction** | Feature engineering, gradient boosting, probability calibration, explanations | Feature engineering | Class imbalance, data leakage, calibration |
| 7 | **Anomaly detection** | Metrics: rolling z-score/MAD, STL seasonality, Isolation Forest. Logs: template mining, error-rate spikes, new-template alerts | Rolling z-score detector | Seasonality, false positives vs alert fatigue |
| 8 | **Service dependency knowledge graph** | NetworkX graph of services, dependencies and deployments; blast radius; upstream-cause search; deploy ↔ incident correlation | "Recent upstream deploys" query | Graph traversal for RCA, NetworkX vs Neo4j |
| 9 | **Hybrid RAG for runbooks** | ~20 runbooks, chunking, BM25 + vector search, Reciprocal Rank Fusion, citations, recall@k / MRR evaluation | RRF function | Why hybrid beats either alone, chunking trade-offs |
| 10 | **RCA agent with tool calling** | Tools over steps 5–9, bounded agent loop, hypotheses linked to evidence IDs, confidence scoring and **abstention** | Confidence/abstain policy | Grounding, hallucination control, agent failure modes |
| 11 | **Human approval workflow** | Remediation proposals with risk levels, state machine (proposed → approved/rejected → executed-simulated), audit log | State transition rules | Human-in-the-loop, safety, least privilege |
| 12 | **Timelines & postmortems** | Event timeline assembly, blameless postmortem generated from evidence with citations, Markdown export | Postmortem template | Blameless culture, grounded generation |
| 13 | **Dashboards** | Streamlit: incident queue, SLA risk, service-health graph, anomaly charts, approval inbox | One dashboard page | Communicating ML to operators |
| 14 | **Evaluation harness** | End-to-end runs on seeded incidents: triage F1, dedup precision, SLA AUC, anomaly P/R, retrieval recall@k, RCA top-k accuracy, abstention vs accuracy, latency/cost | One metric | "How do you know your AI works?" |
| 15 | **Ship it** | Docker Compose, demo script, architecture diagram, demo GIF, résumé bullets for software / IT / data / project roles, mock interview | Résumé bullets (we refine together) | Telling the project story in 2 minutes |
