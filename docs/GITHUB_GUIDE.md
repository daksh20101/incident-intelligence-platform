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
git status
git add -A
git commit -m "feat: add /version endpoint"
git push
```

`git status` shows what changed, `git add -A` stages everything that changed, `git commit` saves the snapshot, `git push` sends it to GitHub.

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

## Part E — feature branches and pull requests

Until now every commit went straight to `main`. Real teams never do that: each change lives on its own **branch**, is proposed as a **pull request (PR)**, gets checked by CI and reviewed, and only then is **merged** into `main`. `main` always stays working.

```
main      ●────────────────────────●  (merge)
           \                      /
feature/x   ●───●───●  (your commits, CI runs on the PR)
```

The loop, from your project folder:

```bash
git switch -c feature/storage-api
git add -A
git commit -m "feat: SQLite storage and ingestion API"
git push -u origin feature/storage-api
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git switch main
git pull
```

What each line does:

| Command | Meaning |
|---|---|
| `git switch -c feature/storage-api` | Create a new branch and move onto it. Uncommitted changes come with you |
| `git push -u origin feature/storage-api` | Upload the branch. `-u` remembers where it goes, so later a plain `git push` works |
| `gh pr create --fill` | Open a pull request, using your commit message as its title |
| `gh pr checks --watch` | Wait for CI on the PR. Green means safe to merge |
| `gh pr merge --squash --delete-branch` | Merge into `main` as one tidy commit, then delete the branch |
| `git switch main` then `git pull` | Go back to `main` and download the merged result |

Want to see the PR in the browser (where reviewers comment line by line)? Run `gh pr view --web` before merging.

## Part F — automatic checks on every commit (pre-commit)

Once per project folder:

```bash
uv run pre-commit install
```

From then on, every `git commit` first runs Ruff on the files you're committing. If Ruff had to fix something, the commit **stops** and says `files were modified by this hook`. That's not an error: the files are fixed now. Stage the fixes and commit again:

```bash
git add -A
git commit -m "your same message"
```
