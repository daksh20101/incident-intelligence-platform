"""Tests for configuration loading."""

import pytest

from incident_intel.config import Settings


def test_defaults_point_to_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make sure a developer's own environment variables don't leak into the test.
    for var in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)  # ignore any local .env file

    assert settings.llm_provider == "ollama"
    assert settings.llm_base_url.startswith("http://localhost:11434")


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "some-model")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "groq"
    assert settings.llm_model == "some-model"
