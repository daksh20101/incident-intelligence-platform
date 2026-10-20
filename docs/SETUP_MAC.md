# One-time Mac setup

Everything here is free. Do it once; it takes about 20–30 minutes (most of it is downloading the AI model).

## 0. Open Terminal

Press `Cmd + Space`, type **Terminal**, press Enter. You type commands here and press Enter to run them.
Tip: when a command asks for your **Mac password**, nothing appears as you type. That's normal; type it and press Enter.

## 1. Apple developer tools (includes `git`)

```bash
xcode-select --install
```

A pop-up asks to install; click **Install**. If it says *already installed*, you're good. Check:

```bash
git --version
```

## 2. Homebrew (the Mac package manager)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes it prints **"Next steps"** with two commands. Run them. On Apple Silicon Macs they are:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Check: `brew --version`

## 3. Developer tools: uv, GitHub CLI, VS Code

```bash
brew install uv gh
brew install --cask visual-studio-code
```

- **uv** installs Python itself, creates the project's virtual environment and installs packages.
- **gh** is the GitHub command-line tool; it makes logging in and creating repos painless.
- **VS Code** is the code editor. Inside it, install the **Python** and **Ruff** extensions (Extensions icon on the left bar).

## 4. Free local LLM: Ollama

1. Download the Mac app from <https://ollama.com/download>, drag it into Applications, and open it. A llama icon appears in the menu bar; that means the Ollama server is running.
2. Download the models (about 5.5 GB total):

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

`qwen3:8b` is the chat / reasoning / tool-calling model; `nomic-embed-text` is the embedding model (for search and dedup).

3. Say hello:

```bash
ollama run qwen3:8b "In one sentence, what is an IT incident?"
```

**About your 16 GB of RAM:** `qwen3:8b` uses roughly 6 GB while loaded, which leaves room for VS Code, a browser and the app. Ollama unloads the model automatically after a few idle minutes. If things feel slow, close heavy apps (lots of Chrome tabs, Docker).

### Optional free cloud fallback

If your laptop is busy or you want a bigger model, both of these have free tiers with no credit card. They're rate-limited, which is fine for development:

- **Groq**: key from <https://console.groq.com/keys>
- **Google Gemini**: key from <https://aistudio.google.com/apikey>

Paste the key into your `.env` and switch the `LLM_*` lines (examples are in `.env.example`). Note that free tiers may use your prompts to improve their services, so only send synthetic data.

## 5. Run the project

```bash
cd ~/Claude/incident-intelligence-platform
cp .env.example .env
uv sync
uv run pytest
uv run python scripts/check_llm.py
uv run uvicorn incident_intel.api.main:app --reload
```

What to expect: the first `uv sync` downloads Python 3.12 and the packages; `pytest` prints **4 passed**; `check_llm.py` prints **[OK] Chat reply** and an embedding vector.

Open <http://127.0.0.1:8000/docs>, click **GET /health → Try it out → Execute**. You should see `{"status": "ok", ...}`.
Stop the server with `Ctrl + C`.

Open the project in VS Code: `code .` (or File → Open Folder).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: brew` | Run the two "Next steps" commands from step 2, then open a new Terminal window |
| `command not found: uv` / `gh` | `brew install uv gh` |
| `check_llm.py` says *Connection error* | Open the Ollama app (llama icon in the menu bar), then retry |
| `check_llm.py` says *model not found* | `ollama pull qwen3:8b` |
| First LLM reply is slow (10–30 s) | Normal: the model is loading into memory. The next replies are faster |
