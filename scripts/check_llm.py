"""Smoke test: can this project talk to the configured LLM?

Usage (from the project folder):
    uv run python scripts/check_llm.py

It sends one chat request and one embedding request to whatever provider your
`.env` points at (Ollama by default) and prints what came back.
"""

import re
import sys
import time

from openai import OpenAI

from incident_intel.config import get_settings


def strip_thinking(text: str) -> str:
    """Some reasoning models (e.g. Qwen3) may wrap their private reasoning in
    <think>...</think>. We only want the final answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def main() -> int:
    s = get_settings()
    print(f"Provider : {s.llm_provider}")
    print(f"Endpoint : {s.llm_base_url}")
    print(f"Model    : {s.llm_model}\n")

    client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)

    # 1) Chat completion ----------------------------------------------------
    start = time.perf_counter()
    try:
        reply = client.chat.completions.create(
            model=s.llm_model,
            messages=[
                {"role": "system", "content": "You are a senior SRE. Answer in one sentence."},
                {"role": "user", "content": "What is an SLA breach in IT operations?"},
            ],
            temperature=0,
        )
    except Exception as exc:  # broad on purpose: this is a friendly diagnostic script
        print(f"[FAIL] Chat request failed: {exc}\n")
        if s.llm_provider == "ollama":
            print("Checklist: is the Ollama app running?  Did you run `ollama pull qwen3:8b`?")
        else:
            print("Checklist: is LLM_API_KEY correct in .env?  Is LLM_MODEL a valid model name?")
        return 1

    elapsed = time.perf_counter() - start
    answer = strip_thinking(reply.choices[0].message.content or "")
    print(f"[OK] Chat reply in {elapsed:.1f}s:\n     {answer}")
    if reply.usage:
        print(f"     tokens: {reply.usage.prompt_tokens} in / {reply.usage.completion_tokens} out")

    # 2) Embeddings (turn text into a vector of numbers; needed for RAG later) ---
    try:
        emb = client.embeddings.create(model=s.embedding_model, input="database connection timeout")
        vector = emb.data[0].embedding
        print(f"\n[OK] Embedding model '{s.embedding_model}' returned a {len(vector)}-dim vector.")
        print(f"     first 5 numbers: {[round(x, 3) for x in vector[:5]]}")
    except Exception as exc:
        print(f"\n[WARN] Embeddings not available here ({exc}).")
        print("       Fine for now: we will add a local embedding model in the RAG step.")

    print("\nLLM access works. You're ready for the next step.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
