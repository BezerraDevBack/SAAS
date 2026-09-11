# IP — Caramurú Construções — assinatura do autor

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

TableName = Literal["projects", "assets", "inspections", "aprs"]
HLC_PATTERN = r"^[0-9]{13}:[0-9]{6}:[a-zA-Z0-9_-]{1,64}$"
HLCString = Annotated[str, Field(pattern=HLC_PATTERN, max_length=85)]
RawValue = JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TableChanges(StrictModel):
    created: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=500)
    updated: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=500)
    deleted: list[UUID] = Field(default_factory=list, max_length=500)


class MutationMetadata(StrictModel):
    client_version: HLCString
    changed_fields: list[str] = Field(default_factory=list, max_length=20)


class PushRequest(StrictModel):
    batch_id: UUID
    last_pulled_at: int = Field(ge=0, le=9007199254740991)
    changes: dict[TableName, TableChanges]
    metadata: dict[TableName, dict[UUID, MutationMetadata]]

    @model_validator(mode="after")
    def bounded_batch(self):
        count = sum(len(c.created) + len(c.updated) + len(c.deleted) for c in self.changes.values())
        if count > 500:
            raise ValueError("At most 500 mutations per batch")
        if len(self.model_dump_json().encode()) > 1_048_576:
            raise ValueError("Batch exceeds 1 MiB")
        return self


class PullTableChanges(StrictModel):
    created: list[dict[str, RawValue]] = Field(default_factory=list)
    updated: list[dict[str, RawValue]] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


class PullResponse(StrictModel):
    changes: dict[TableName, PullTableChanges]
    timestamp: int


class MergeConflict(StrictModel):
    table_name: TableName
    record_id: UUID
    rejected_fields: list[str]


class PushResponse(StrictModel):
    batch_id: UUID
    applied: int
    conflicts: list[MergeConflict]
    requires_pull: bool = True


def hlc_key(value: str) -> tuple[int, int, str]:
    if not re.fullmatch(HLC_PATTERN, value):
        raise ValueError("Invalid HLC")
    wall, counter, node = value.split(":")
    return int(wall), int(counter), node
