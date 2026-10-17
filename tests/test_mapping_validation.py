from apirunner.core.mapping import auto_map
from apirunner.core.models import FieldSpec
from apirunner.core.validation import validate_headers, validate_row, validate_rows

FIELDS = [
    FieldSpec(name="name"),
    FieldSpec(name="email", regex=r"[^@\s]+@[^@\s]+"),
    FieldSpec(name="age", type="integer"),
    FieldSpec(name="address.city", required=False),
    FieldSpec(name="plan", allowed=["free", "pro"], default="free"),
]


def test_auto_map_exact_normalised_fuzzy_and_containment():
    columns = ["Full Name", "E-mail", "AGE", "City", "Plan", "_status", "Notes"]
    assert auto_map(columns, FIELDS) == {
        "name": "Full Name",  # containment
        "email": "E-mail",  # normalised
        "age": "AGE",  # normalised
        "address.city": "City",  # leaf of dotted path
        "plan": "Plan",
    }


def test_auto_map_never_uses_result_columns_or_a_column_twice():
    mapping = auto_map(["_status", "email"], [FieldSpec(name="status"), FieldSpec(name="email"),
                                              FieldSpec(name="mail")])
    assert mapping["status"] is None
    assert mapping["email"] == "email"
    assert mapping["mail"] is None


def test_auto_map_fuzzy_typo():
    assert auto_map(["Emial Adress"], [FieldSpec(name="email_address")]) == {"email_address": "Emial Adress"}


def test_validate_headers_reports_missing_and_unused():
    mapping = {"name": None, "email": "E-mail", "age": "Age", "address.city": None, "plan": None}
    rep = validate_headers(["E-mail", "Age", "Extra", "_error"], mapping, FIELDS)
    assert rep.missing_required == ["name"]
    assert rep.missing_optional == ["address.city", "plan"]  # plan has a default
    assert rep.unused_columns == ["Extra"]
    assert not rep.ok


def test_validate_row_errors_and_coercion():
    mapping = {"name": "n", "email": "e", "age": "a", "address.city": "c", "plan": "p"}
    ok = validate_row(0, {"n": "Ann", "e": "ann@x.io", "a": "31", "c": None, "p": None}, mapping, FIELDS)
    assert ok.valid and ok.values == {"name": "Ann", "email": "ann@x.io", "age": 31, "address.city": None,
                                      "plan": "free"}
    bad = validate_row(1, {"n": "", "e": "nope", "a": "x", "p": "gold"}, mapping, FIELDS)
    assert bad.errors == {
        "name": "required",
        "email": "does not match pattern [^@\\s]+@[^@\\s]+",
        "age": "expected integer, got 'x'",
        "plan": "must be one of: free, pro",
    }


def test_validate_rows_indexes():
    mapping = {"name": "n", "email": "e", "age": "a"}
    fields = FIELDS[:3]
    result = validate_rows([{"n": "A", "e": "a@b.c", "a": 1}, {"n": "B", "e": "", "a": 2}], mapping, fields)
    assert [(v.index, v.valid) for v in result] == [(0, True), (1, False)]
