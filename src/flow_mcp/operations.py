from typing import Annotated, Literal

from pydantic import Field, model_validator

from flow_mcp.models import Scope, StrictModel

Identifier = Annotated[
    str, Field(pattern=r"^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$")
]
MediaIdentifier = Annotated[
    str,
    Field(pattern=r"^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}(?:_upsampled)?$"),
]
ImageModel = Literal["nano_banana_pro", "nano_banana_2", "nano_banana_lite"]

ScalarType = Literal["null", "string", "number", "boolean", "object", "undefined"]
StructuralType = Literal["array"] | ScalarType


class ResponseShape(StrictModel):
    type: Literal["array"]
    length: int = Field(ge=0, le=24000000)
    items: list["ResponseShape | StructuralType"] = Field(max_length=8)


class ImageInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=10000)
    model: ImageModel = "nano_banana_2"
    ratio: Literal["1:1", "9:16", "16:9", "3:4", "4:3"] = "1:1"
    references: list[Identifier] = Field(default_factory=list, max_length=4)


class VideoInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=10000)
    model: Literal["omni", "veo_lite"] = "omni"
    ratio: Literal["9:16", "16:9"] = "16:9"
    duration: Literal[4, 6, 8, 10] = 8
    resolution: Literal["360p", "720p"] = "720p"
    start: Identifier | None = None
    end: Identifier | None = None
    references: list[Identifier] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def modes(self) -> "VideoInput":
        if self.end and not self.start:
            raise ValueError("end_requires_start")
        if self.references and (self.start or self.end):
            raise ValueError("references_exclude_frames")
        if self.model != "omni" and (
            not self.start
            or self.end
            or self.references
            or self.duration != 8
            or self.resolution != "720p"
        ):
            raise ValueError("veo_requires_start_only_8s_720p")
        return self


class ImageUpscaleInput(StrictModel):
    media_id: Identifier
    resolution: Literal["2K", "4K"] = "2K"


class VideoUpscaleInput(StrictModel):
    media_id: Identifier
    scene_id: Identifier
    ratio: Literal["9:16", "16:9"] = "16:9"
    resolution: Literal["1080p"] = "1080p"


class UploadInput(StrictModel):
    data: str = Field(min_length=1, max_length=11184812)
    mime: Literal["image/png", "image/jpeg", "image/webp"]
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_. -]+$")


class Asset(StrictModel):
    media_id: MediaIdentifier
    kind: Literal["image", "video"]
    url: str | None = Field(default=None, max_length=8192)


RpcName = Literal[
    "jHPbke", "Zzl0ze", "UpteDb", "jwpduf", "as29s", "SPrCad", "p0UkFb", "maseQ", "ogiZ0b",
    "MZZa6b", "nprQif", "eb1hJf", "YhhmEf",
]
DiagnosticPhase = Literal["preflight", "transport", "body", "parse", "validate"]

BRIDGE_OR_RESPONSE_VALIDATION = "bridge_or_response_validation"


class RpcDiagnostics(StrictModel):
    rpc: RpcName | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    chunks: int | None = Field(default=None, ge=0, le=24000000)
    envelopes: int | None = Field(default=None, ge=0, le=24000000)
    rpc_code: int | None = Field(default=None, ge=0, le=16)
    phase: DiagnosticPhase | None = None
    envelope_shape: ResponseShape | None = None
    rpc_error_shape: ResponseShape | None = None
    payload_shape: ResponseShape | StructuralType | None = None
    record_len: int | None = Field(default=None, ge=0, le=64)
    record_id_valid: bool | None = None
    project_match: bool | None = None
    record_id: Identifier | None = None


class Outcome(StrictModel):
    scope: Scope
    state: Literal["completed", "pending", "not_submitted", "submitted_unverified"]
    assets: list[Asset] = Field(default_factory=list, max_length=4)
    encoded_image: str | None = Field(default=None, max_length=22000000)
    operation_id: Identifier | None = None
    media_id: MediaIdentifier | None = None
    error: str | None = Field(default=None, max_length=160)


class PollInput(StrictModel):
    operation_id: Identifier | None = None
    media_id: MediaIdentifier | None = None
    kind: Literal["image", "video"]
