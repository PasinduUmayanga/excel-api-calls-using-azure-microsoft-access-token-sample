"""Validate uploaded rows against the template's field definitions."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .mapping import usable_columns
from .models import FieldSpec
from .template import CoercionError, coerce, is_blank


class HeaderReport(BaseModel):
    missing_required: list[str] = Field(default_factory=list)  # required fields with no column
    missing_optional: list[str] = Field(default_factory=list)
    unused_columns: list[str] = Field(default_factory=list)  # columns not mapped to any field

    @property
    def ok(self) -> bool:
        return not self.missing_required


class RowValidation(BaseModel):
    index: int
    values: dict[str, Any] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)  # field -> message

    @property
    def valid(self) -> bool:
        return not self.errors


def validate_headers(columns: list[str], mapping: dict[str, str | None], fields: list[FieldSpec]) -> HeaderReport:
    mapped = {c for c in mapping.values() if c}
    report = HeaderReport(unused_columns=[c for c in usable_columns(columns) if c not in mapped])
    for f in fields:
        if not mapping.get(f.name):
            (report.missing_required if f.required and f.default is None else report.missing_optional).append(f.name)
    return report


def validate_value(raw: Any, spec: FieldSpec) -> tuple[Any, str | None]:
    if is_blank(raw):
        if spec.default is not None:
            raw = spec.default
        elif spec.required:
            return None, "required"
        else:
            return None, None
    try:
        value = coerce(raw, spec.type)
    except CoercionError as exc:
        return None, str(exc)
    if spec.allowed and str(value) not in spec.allowed:
        return value, f"must be one of: {', '.join(spec.allowed)}"
    if spec.regex and not re.fullmatch(spec.regex, str(value)):
        return value, f"does not match pattern {spec.regex}"
    return value, None


def validate_row(index: int, row: dict[str, Any], mapping: dict[str, str | None], fields: list[FieldSpec]) -> RowValidation:
    result = RowValidation(index=index)
    for spec in fields:
        column = mapping.get(spec.name)
        value, error = validate_value(row.get(column) if column else None, spec)
        result.values[spec.name] = value
        if error:
            result.errors[spec.name] = error
    return result


def validate_rows(rows: list[dict[str, Any]], mapping: dict[str, str | None], fields: list[FieldSpec]) -> list[RowValidation]:
    return [validate_row(i, row, mapping, fields) for i, row in enumerate(rows)]
