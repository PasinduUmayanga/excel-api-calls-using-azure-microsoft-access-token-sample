"""Domain models shared by every layer. Pure data, no I/O."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

FieldType = Literal["string", "number", "integer", "boolean", "date", "array", "object"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    BASIC = "basic"
    AZURE_AD = "azure_ad"


class AuthConfig(BaseModel):
    type: AuthType = AuthType.NONE
    token: str = ""
    key_name: str = "x-api-key"
    key_value: str = ""
    key_in: Literal["header", "query"] = "header"
    username: str = ""
    password: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    scope: str = ""


class FieldSpec(BaseModel):
    """One placeholder of the JSON format. `name` may be a dotted path, e.g. address.city."""

    name: str
    type: FieldType = "string"
    required: bool = True
    regex: str | None = None
    allowed: list[str] | None = None
    default: Any = None


class RequestTemplate(BaseModel):
    """The generic contract: a request whose URL/headers/body contain {{placeholders}}."""

    name: str = "Untitled"
    method: HttpMethod = "POST"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    auth: AuthConfig = Field(default_factory=AuthConfig)
    fields: list[FieldSpec] = Field(default_factory=list)


class ParamLocation(str, Enum):
    AUTO = "auto"  # placeholder: substituted wherever it appears
    QUERY = "query"
    HEADER = "header"


class Param(BaseModel):
    name: str
    value: str = ""
    location: ParamLocation = ParamLocation.AUTO


class PreparedRequest(BaseModel):
    method: HttpMethod
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    json_body: Any = None
    text_body: str | None = None


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    backoff_seconds: float = 0.5
    retry_on_status: list[int] = Field(default_factory=lambda: [408, 429, 500, 502, 503, 504])
    retry_on_network_error: bool = True


class RunOptions(BaseModel):
    concurrency: int = 5
    timeout_seconds: float = 30.0
    retry: RetryPolicy = Field(default_factory=RetryPolicy)


class CallStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class CallResult(BaseModel):
    status: CallStatus
    http_code: int | None = None
    response_text: str = ""
    response_headers: dict[str, str] = Field(default_factory=dict)
    error: str = ""
    attempts: int = 0
    elapsed_ms: float = 0.0


class RowResult(BaseModel):
    row_index: int
    source: dict[str, Any]  # original Excel row (all columns)
    values: dict[str, Any] = Field(default_factory=dict)  # field -> coerced value
    result: CallResult = Field(default_factory=lambda: CallResult(status=CallStatus.PENDING))


class Job(BaseModel):
    id: str
    template: RequestTemplate
    columns: list[str]
    mapping: dict[str, str | None]
    rows: list[RowResult]
    created_at: str

    @property
    def success_count(self) -> int:
        return sum(r.result.status == CallStatus.SUCCESS for r in self.rows)

    @property
    def failed_count(self) -> int:
        return sum(r.result.status == CallStatus.FAILED for r in self.rows)

    @property
    def pending_count(self) -> int:
        return sum(r.result.status == CallStatus.PENDING for r in self.rows)
