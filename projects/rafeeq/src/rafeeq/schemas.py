from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISTRICT = Literal["Al-Shati", "Al-Jamiah", "Al-Rawdah", "Al-Olaya", "Al-Nakheel", "Al-Malqa"]


def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Search(StrictModel):
    query: str = Field(min_length=1, max_length=500)


class Fee(StrictModel):
    permit_type: Literal["BLD", "REN", "SGN", "FTR", "EVT"]
    area_m2: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    structural: bool = False
    sign_m2: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    illuminated: bool = False
    event_days: int | None = Field(default=None, ge=1, le=14)
    social_security: bool = False


class Permit(StrictModel):
    permit_id: str = Field(pattern=r"^(BLD|REN|SGN|FTR|EVT)-\d{5}$")

    @field_validator("permit_id", mode="before")
    @classmethod
    def canonical_reference(cls, value):
        return normalize_digits(value.strip().upper()).replace("‑", "-").replace("–", "-") if isinstance(value, str) else value


class Slots(StrictModel):
    district: DISTRICT | None = None
    date_from: date | None = None
    date_to: date | None = None


class Booking(Permit):
    slot: datetime

    @field_validator("slot", mode="before")
    @classmethod
    def iso_slot(cls, value):
        return datetime.fromisoformat(value) if isinstance(value, str) else value


class Reschedule(Permit):
    inspection_id: str = Field(pattern=r"^INS-[A-Za-z0-9-]+$")
    slot: datetime

    @field_validator("slot", mode="before")
    @classmethod
    def iso_slot(cls, value):
        return Booking.iso_slot(value)


class Refund(Permit):
    reason: Literal["rejected", "withdrawn_before_review", "withdrawn_during_review", "duplicate_payment"]


class Verify(Permit):
    last4: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    mobile: str = Field(pattern=r"^\+?[0-9]{9,14}$", repr=False)

    @field_validator("last4", "mobile", mode="before")
    @classmethod
    def canonical_identity(cls, value):
        return normalize_digits(value.strip()).replace(" ", "").replace("-", "") if isinstance(value, str) else value


class Empty(StrictModel):
    pass


class Register(StrictModel):
    display_name: str = Field(min_length=1, max_length=60)
    last4: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    mobile: str = Field(pattern=r"^\+?[0-9]{9,14}$", repr=False)
    consent: Literal[True]

    @field_validator("last4", "mobile", mode="before")
    @classmethod
    def canonical_identity(cls, value):
        return Verify.canonical_identity(value)


class Application(Fee):
    district: DISTRICT
    documents: list[str] = Field(default_factory=list, max_length=8)
    attendees: int | None = Field(default=None, ge=1, le=100000)
    # Reused by the confirmed proposal, never treated as officer approval.


class VerificationRequest(StrictModel):
    permit_id: str | None = None

    @field_validator("permit_id", mode="before")
    @classmethod
    def canonical_optional_reference(cls, value):
        return Permit.canonical_reference(value) if value is not None else None


class Chat(StrictModel):
    message: str = Field(min_length=1, max_length=4000)


class Decision(StrictModel):
    approve: bool


class Reply(BaseModel):
    reply: str
    tools: list[str]
    actions: list[dict]
    stopped: str
    usage: dict
    trace_id: str
    ui_requests: list[dict] = Field(default_factory=list)
    error_code: str | None = None
    tool_events: list[dict] = Field(default_factory=list)
