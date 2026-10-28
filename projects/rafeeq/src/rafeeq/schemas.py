from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class Slots(StrictModel):
    district: Literal["Al-Shati", "Al-Jamiah", "Al-Rawdah", "Al-Olaya", "Al-Nakheel", "Al-Malqa"]
    date_from: date
    date_to: date


class Booking(Permit):
    slot: datetime


class Reschedule(Permit):
    inspection_id: str = Field(pattern=r"^INS-[A-Za-z0-9-]+$")
    slot: datetime


class Refund(Permit):
    reason: Literal["rejected", "withdrawn_before_review", "withdrawn_during_review", "duplicate_payment"]


class Verify(Permit):
    last4: str = Field(pattern=r"^[0-9]{4}$", repr=False)
    mobile: str = Field(pattern=r"^\+?[0-9]{9,14}$", repr=False)


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
