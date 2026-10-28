from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT = Path(__file__).resolve().parents[2]
COURSE = PROJECT.parents[1]
if os.getenv("RAFEEQ_NO_DOTENV") != "1":
    load_dotenv(PROJECT / ".env", override=False)


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)
    runtime: Path = Field(default_factory=lambda: Path(os.getenv("RAFEEQ_RUNTIME", str(PROJECT / "runtime"))))
    api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""), repr=False)
    officer_token: str = Field(default_factory=lambda: os.getenv("RAFEEQ_OFFICER_TOKEN", ""), repr=False)
    reviewer_token: str = Field(default_factory=lambda: os.getenv("RAFEEQ_REVIEWER_TOKEN", ""), repr=False)
    model: str = Field(default_factory=lambda: os.getenv("RAFEEQ_MODEL", "nvidia/nemotron-3.5-lightning:free"))
    fallback_model: str = Field(
        default_factory=lambda: os.getenv("RAFEEQ_FALLBACK_MODEL", "google/gemma-4-31b-it:free"),
        validate_default=True,
    )

    @field_validator("fallback_model")
    @classmethod
    def named_backup(cls, value: str) -> str:
        value = value.strip()
        if value and ("/" not in value or value.startswith("openrouter/")):
            raise ValueError("RAFEEQ_FALLBACK_MODEL must be a specific model ID, not an automatic router")
        return value

    max_steps: int = Field(default=8, ge=1, le=12)
    max_tokens: int = Field(default=900, ge=64, le=2000)
    max_context_chars: int = 24000
    max_history_messages: int = 12
    max_cost: float = Field(default_factory=lambda: float(os.getenv("RAFEEQ_MAX_COST_USD", ".50")), gt=0)
    input_rate: float = Field(default_factory=lambda: float(os.getenv("RAFEEQ_INPUT_USD_PER_MILLION", "1")), gt=0)
    output_rate: float = Field(default_factory=lambda: float(os.getenv("RAFEEQ_OUTPUT_USD_PER_MILLION", "3")), gt=0)
    deadline_seconds: float = 60
    configuration: str = Field(default="B", pattern="^[AB]$")
