
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOTENV_PATH = REPO_ROOT / ".env"
DEFAULT_STREAMLIT_SECRETS_PATH = REPO_ROOT / ".streamlit" / "secrets.toml"

DEFAULT_OLLAMA_MODEL = "qwen3-vl:4b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

_env_before_dotenv: dict[str, str] = {}
_dotenv_path = DEFAULT_DOTENV_PATH
_dotenv_values: dict[str, str] = {}
_streamlit_secrets_path = DEFAULT_STREAMLIT_SECRETS_PATH
_streamlit_secret_values: dict[str, Any] = {}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Read .env values without requiring python-dotenv."""
    if not path.exists():
        return {}

    try:
        from dotenv import dotenv_values

        return {
            key: str(value)
            for key, value in dotenv_values(path).items()
            if key and value not in (None, "")
        }
    except Exception:
        values: dict[str, str] = {}

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")

            if key and value:
                values[key] = value

        return values


def _read_streamlit_secrets(path: Path) -> dict[str, Any]:
    """Load supported configuration values from Streamlit secrets."""
    values: dict[str, Any] = {}

    if path.exists():
        try:
            values.update(tomllib.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass

    try:
        import streamlit as st

        secrets = getattr(st, "secrets", {})

        for key in (
            "OLLAMA_API_KEY",
            "OLLAMA_MODEL",
            "OLLAMA_BASE_URL",
            "TESSERACT_CMD",
        ):
            try:
                if key in secrets and secrets[key]:
                    values[key] = secrets[key]
            except Exception:
                continue
    except Exception:
        pass

    return values


def load_runtime_config(
    dotenv_path: str | Path | None = None,
    streamlit_secrets_path: str | Path | None = None,
) -> None:
    """Load configuration from environment, .env, and Streamlit secrets."""
    global _env_before_dotenv, _dotenv_path, _dotenv_values
    global _streamlit_secrets_path, _streamlit_secret_values

    _env_before_dotenv = dict(os.environ)

    _dotenv_path = Path(
        dotenv_path
        or os.getenv("VIDEO2SOP_DOTENV_PATH")
        or DEFAULT_DOTENV_PATH
    )

    _streamlit_secrets_path = Path(
        streamlit_secrets_path
        or os.getenv("VIDEO2SOP_STREAMLIT_SECRETS_PATH")
        or DEFAULT_STREAMLIT_SECRETS_PATH
    )

    _dotenv_values = _parse_dotenv(_dotenv_path)

    # Explicitly set environment variables take priority over .env values.
    for key, value in _dotenv_values.items():
        os.environ.setdefault(key, value)

    _streamlit_secret_values = _read_streamlit_secrets(
        _streamlit_secrets_path
    )


def get_config_with_source(
    key: str,
    default: str | None = None,
) -> tuple[str | None, str]:
    """Return a configuration value and the source it came from."""
    env_value = os.environ.get(key)
    dotenv_value = _dotenv_values.get(key)

    # Preserve environment values explicitly set before .env loading.
    if env_value:
        if (
            key in _env_before_dotenv
            or key not in _dotenv_values
            or env_value != dotenv_value
        ):
            return env_value, "environment"

    if dotenv_value:
        return dotenv_value, ".env"

    secret_value = _streamlit_secret_values.get(key)

    if secret_value not in (None, ""):
        return str(secret_value), "streamlit secrets"

    if env_value:
        return env_value, "environment"

    return default, "default"


def get_config(key: str, default: str | None = None) -> str | None:
    """Return a configuration value from the available sources."""
    return get_config_with_source(key, default=default)[0]


def config_source(key: str) -> str:
    """Return the source of a configuration value."""
    return get_config_with_source(key)[1]


def ollama_is_disabled() -> bool:
    """Check whether local vision-model inference has been disabled."""
    return _truthy(os.getenv("VIDEO2SOP_DISABLE_OLLAMA"))


def has_ollama_key() -> bool:
    """
    Check whether an Ollama API-key value is configured.

    Local Ollama installations may accept a placeholder key. This check
    confirms configuration only; it does not establish server connectivity.
    """
    if ollama_is_disabled():
        return False

    value = get_config("OLLAMA_API_KEY")

    return bool(
        value
        and value.strip()
        and value.strip().lower() != "replace_me"
    )


def has_vision_model_config() -> bool:
    """
    Check whether the vision-model settings are configured.

    This checks configuration values only. It does not test whether the
    Ollama server is running or whether the requested model is installed.
    """
    model = get_config("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    base_url = get_config("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)

    return bool(
        has_ollama_key()
        and model
        and model.strip()
        and base_url
        and base_url.strip()
    )


def runtime_config_status() -> dict[str, Any]:
    """Return configuration diagnostics without exposing secret values."""
    _, key_source = get_config_with_source("OLLAMA_API_KEY")
    model, model_source = get_config_with_source(
        "OLLAMA_MODEL",
        DEFAULT_OLLAMA_MODEL,
    )
    base_url, base_url_source = get_config_with_source(
        "OLLAMA_BASE_URL",
        DEFAULT_OLLAMA_BASE_URL,
    )

    configured = has_vision_model_config()
    disabled = ollama_is_disabled()
    key_present = has_ollama_key()

    return {
        "repo_root": str(REPO_ROOT),
        "dotenv_path": str(_dotenv_path),
        "dotenv_found": _dotenv_path.exists(),
        "streamlit_secrets_path": str(_streamlit_secrets_path),
        "streamlit_secrets_found": _streamlit_secrets_path.exists(),
        "ollama_configured": configured,
        "ollama_disabled": disabled,
        "ollama_key_source": "disabled" if disabled else key_source,
        "ollama_key_present": key_present,
        "OLLAMA_MODEL": model,
        "OLLAMA_MODEL_source": model_source,
        "OLLAMA_BASE_URL": base_url,
        "OLLAMA_BASE_URL_source": base_url_source,
    }


# Initialize configuration when this module is imported.
load_runtime_config()
