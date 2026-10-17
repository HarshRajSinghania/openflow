from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TabId = Annotated[int, Field(strict=True, ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Tab(StrictModel):
    tab_id: TabId
    origin: Literal["https://flow.google.com", "https://labs.google"]
    project_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9-]{36}$")


class Scope(Tab):
    document_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9-]+$")


class Observation(StrictModel):
    scope: Scope
    email: str | None = Field(default=None, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    email_confirmed: bool = False
    credits: int | None = Field(default=None, ge=0, le=9007199254740991)
    source: Literal["unavailable", "google_account_aria"] = "unavailable"
    credits_source: Literal[
        "unavailable", "account_settings_dialog", "flow_credits_rpc"
    ] = "unavailable"
    observed_at: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
    )

    @model_validator(mode="after")
    def evidence(self) -> "Observation":
        if (self.email is not None) != self.email_confirmed:
            raise ValueError("email_evidence_required")
        if (self.email is not None) != (self.source == "google_account_aria"):
            raise ValueError("email_source_required")
        if (self.credits is not None) != (self.credits_source != "unavailable"):
            raise ValueError("credits_source_required")
        if self.credits is not None and (self.email is None or self.observed_at is None):
            raise ValueError("credits_account_evidence_required")
        if self.observed_at is not None and self.email is None:
            raise ValueError("observation_evidence_required")
        return self


class Snapshot(StrictModel):
    tabs: list[Tab] = Field(max_length=100)
    selected: Scope | None = None


class Hello(StrictModel):
    type: Literal["hello"]
    version: Literal[1]
    secret: str = Field(min_length=32, max_length=128, repr=False)
    installation_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    nickname: str = Field(default="", max_length=48, pattern=r"^[a-zA-Z0-9 _.-]*$")

    def identity(self) -> str:
        return str(UUID(self.installation_id))


class PairingRequest(StrictModel):
    type: Literal["pair"]
    version: Literal[1]
    installation_id: str = Field(pattern=r"^[a-f0-9-]{36}$")

    def identity(self) -> str:
        return str(UUID(self.installation_id))


class Reply(StrictModel):
    type: Literal["reply"]
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    result: dict[str, object] | None = None
    error: (
        Literal["scope_changed", "tab_unavailable", "invalid_request", "inspection_failed"] | None
    ) = None


class Invalidated(StrictModel):
    type: Literal["invalidated"]


class Heartbeat(StrictModel):
    type: Literal["ping"]
