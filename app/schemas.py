from typing import Any
from pydantic import BaseModel, Field

class CreateCallRequest(BaseModel):
    from_number: str = Field(alias="from", min_length=1, max_length=100)
    to: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] | None = None

    class Config:
        populate_by_name = True

class CreateCallResponse(BaseModel):
    call_id: str
    state: str
    websocket_url: str

class CallResponse(BaseModel):
    call_id: str
    from_number: str
    to: str
    state: str
    metadata: dict[str, Any] | None = None
    recording_url: str | None = None

class MetricsResponse(BaseModel):
    total: int
    active: int
    cps: int
    uploads: int
