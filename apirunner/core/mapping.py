"""Map Excel columns to template fields: exact -> normalised -> fuzzy."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .models import FieldSpec

FUZZY_THRESHOLD = 80
RESULT_PREFIX = "_"  # result columns added by exports; ignored on re-upload


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def usable_columns(columns: list[str]) -> list[str]:
    return [c for c in columns if c and not str(c).startswith(RESULT_PREFIX)]


def auto_map(columns: list[str], fields: list[FieldSpec]) -> dict[str, str | None]:
    """Return {field_name: column or None}. Each column is used at most once."""
    cols = usable_columns(columns)
    mapping: dict[str, str | None] = {f.name: None for f in fields}
    taken: set[str] = set()

    def assign(match):
        for f in fields:
            if mapping[f.name] is not None:
                continue
            for c in cols:
                if c not in taken and match(f.name, c):
                    mapping[f.name] = c
                    taken.add(c)
                    break

    assign(lambda f, c: f == c)
    assign(lambda f, c: normalise(f) == normalise(c) or normalise(f.split(".")[-1]) == normalise(c))

    # Fuzzy: best remaining column per field above the threshold
    for f in fields:
        if mapping[f.name] is not None:
            continue
        best, best_score = None, 0.0
        for c in cols:
            if c in taken:
                continue
            score = max(
                fuzz.ratio(normalise(f.name), normalise(c)),
                fuzz.ratio(normalise(f.name.split(".")[-1]), normalise(c)),
            )
            if score > best_score:
                best, best_score = c, score
        if best and best_score >= FUZZY_THRESHOLD:
            mapping[f.name] = best
            taken.add(best)

    # Containment: "name" -> "Full Name", "email" -> "Customer Email Address"
    def contains(f: str, c: str) -> bool:
        leaf, col = normalise(f.split(".")[-1]), normalise(c)
        return len(leaf) >= 3 and len(col) >= 3 and (leaf in col or col in leaf)

    assign(contains)
    return mapping
