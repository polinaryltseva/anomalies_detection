"""Centralised configuration: paths, API URLs, secrets loaded from .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LABELED_DIR = DATA_DIR / "labeled"
DOCS_DIR = PROJECT_ROOT / "docs"

for d in (RAW_DIR, PROCESSED_DIR, LABELED_DIR):
    d.mkdir(parents=True, exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class MarkerConfig:
    api_base: str = os.getenv("MARKER_API_BASE", "https://analytics.marker-zakupki.ru/api")
    auth_base: str = os.getenv("MARKER_AUTH_BASE", "https://accounts.marker-zakupki.ru")
    referer: str = os.getenv("MARKER_HOME_REFERER", "https://analytics.marker-zakupki.ru/Home")
    session_ticket: str | None = os.getenv("MARKER_SESSION_TICKET")
    username: str | None = os.getenv("MARKER_USERNAME")
    password: str | None = os.getenv("MARKER_PASSWORD")


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str | None = os.getenv("OPENAI_API_KEY")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o")


# Какого провайдера использовать по умолчанию: openai | anthropic
DEFAULT_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")


MARKER = MarkerConfig()
ANTHROPIC = AnthropicConfig()
OPENAI = OpenAIConfig()
