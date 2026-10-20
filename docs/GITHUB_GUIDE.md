# Git & GitHub guide

## The mental model (memorize this; it comes up in interviews)

```
 your files  ──git add──▶  staging area  ──git commit──▶  local history  ──git push──▶  GitHub
 (working dir)            ("what goes in               (a snapshot with              (the shared,
                            the next snapshot")           a message)                    public copy)
```

- A **commit** is a saved snapshot of the project with a message explaining *why* it changed.
- A **repository (repo)** is the project folder plus its full history.
- **`.gitignore`** lists files git must never track: secrets (`.env`), the virtual environment (`.venv/`), caches, local data.

## Part A — one-time setup

1. **Create a GitHub account** at <https://github.com/signup>. Pick a professional username; it will be on your résumé.
2. **Tell git who you are** (shown on every commit):

   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "the-email-on-your-github-account@example.com"
   git config --global init.defaultBranch main
   ```

   Prefer to keep your email private? On GitHub go to *Settings → Emails*, tick *Keep my email address private*, and use the `...@users.noreply.github.com` address shown there.
3. **Log the GitHub CLI in** (no passwords or tokens to copy around):

   ```bash
   gh auth login
   ```

   Answer: **GitHub.com** → **HTTPS** → **Yes** (authenticate Git) → **Login with a web browser**. Copy the 8-character code, press Enter, paste the code in the browser page and click *Authorize*.
   Check: `gh auth status`

## Part B — first push (do this once, after `uv sync` and `uv run pytest` pass)

```bash
cd ~/Claude/incident-intelligence-platform
git init
git add .
git status
```

Read the `git status` list before committing:
- ✅ You **should** see `uv.lock`, `README.md`, `src/...`, `tests/...`, `.github/...`
- ❌ You should **not** see `.env` or `.venv/`. If you do, stop and tell Claude.

```bash
git commit -m "feat: project foundations (FastAPI skeleton, config, LLM check, tests, CI)"

gh repo create incident-intelligence-platform --public --source=. --remote=origin --push \
  --description "AI IT incident intelligence: triage, SLA prediction, anomaly detection, hybrid RAG, RCA agent with human approval"

gh repo view --web
```

On the GitHub page, open the **Actions** tab. A green check ✅ means CI (lint + tests) passed on GitHub's servers.

## Part C — the everyday loop

```bash
git status                       # what changed?
git add -A                       # stage everything that changed
git commit -m "feat: add /version endpoint"
git push                         # send it to GitHub
```

### Commit message style (Conventional Commits)

| Prefix | Use for |
|---|---|
| `feat:` | a new feature |
| `fix:` | a bug fix |
| `docs:` | documentation only |
| `test:` | adding or fixing tests |
| `refactor:` | code change that doesn't change behavior |
| `chore:` | tooling, dependencies, config |

## Part D — CI badge (optional, looks great)

Add this as the second line of `README.md`, replacing `YOUR-USERNAME`:

```markdown
![CI](https://github.com/YOUR-USERNAME/incident-intelligence-platform/actions/workflows/ci.yml/badge.svg)
```

## Coming in Step 3

Feature branches and pull requests (`git switch -c feature/...`, `gh pr create`) — the way real teams work, and a common interview topic.
