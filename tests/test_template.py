import json

import pytest

from apirunner.core.models import FieldSpec, RequestTemplate
from apirunner.core.template import (
    CoercionError,
    coerce,
    extract_fields,
    extract_placeholders,
    render_body,
    render_url,
    sample_json_to_template,
)


def test_extract_placeholders_with_types_and_order():
    text = '{"a": "{{name}}", "b": "{{age:integer}}", "c": "{{name}}", "d": "{{ address.city }}"}'
    assert extract_placeholders(text) == [("name", "string"), ("age", "integer"), ("address.city", "string")]


def test_unknown_type_falls_back_to_string():
    assert extract_placeholders("{{x:weird}}") == [("x", "string")]


def test_path_params_only_detected_in_path_not_scheme_or_port():
    url = "http://localhost:8080/users/:id/orders?x={{q}}"
    assert extract_placeholders(url, include_path_params=True) == [("q", "string"), ("id", "string")]


def test_extract_fields_keeps_existing_settings():
    t = RequestTemplate(url="https://x/{{id}}", body='{"n": "{{name}}"}',
                        fields=[FieldSpec(name="name", required=False, regex="[A-Z].*")])
    fields = {f.name: f for f in extract_fields(t)}
    assert list(fields) == ["id", "name"]
    assert fields["name"].required is False and fields["name"].regex == "[A-Z].*"


@pytest.mark.parametrize("value,typ,expected", [
    ("42", "integer", 42),
    (42.0, "integer", 42),
    ("3.5", "number", 3.5),
    ("yes", "boolean", True),
    ("0", "boolean", False),
    ("2024-05-01T10:00:00", "date", "2024-05-01"),
    ("a, b ,c", "array", ["a", "b", "c"]),
    ('["x", 1]', "array", ["x", 1]),
    ('{"k": 1}', "object", {"k": 1}),
    (1234.0, "string", "1234"),
    ("", "integer", None),
])
def test_coerce(value, typ, expected):
    assert coerce(value, typ) == expected


@pytest.mark.parametrize("value,typ", [("twenty", "integer"), ("1.5", "integer"), ("maybe", "boolean"),
                                       ("2024-13-01", "date"), ("[1,2]", "object")])
def test_coerce_errors(value, typ):
    with pytest.raises(CoercionError):
        coerce(value, typ)


def test_render_body_keeps_types_for_whole_placeholders():
    body = '{"name": "{{name}}", "age": "{{age:integer}}", "greeting": "Hi {{name}}!", "tags": "{{tags}}"}'
    rendered, text = render_body(body, {"name": "Ann", "age": 31, "tags": ["a", "b"]})
    assert text is None
    assert rendered == {"name": "Ann", "age": 31, "greeting": "Hi Ann!", "tags": ["a", "b"]}


def test_render_body_non_json_is_text_substitution():
    rendered, text = render_body("name={{name}}", {"name": "Ann"})
    assert rendered is None and text == "name=Ann"


def test_render_url_encodes_values_and_path_params():
    url = render_url("https://api/x/{{id}}/:part?q={{q}}", {"id": "a b", "part": "p/1", "q": "x&y"})
    assert url == "https://api/x/a%20b/p%2F1?q=x%26y"


def test_sample_json_to_template():
    sample = {"name": "Ann", "age": 3, "ok": True, "addr": {"city": "X"}, "tags": [1]}
    assert sample_json_to_template(sample) == {
        "name": "{{name}}", "age": "{{age:integer}}", "ok": "{{ok:boolean}}",
        "addr": {"city": "{{addr.city}}"}, "tags": "{{tags:array}}",
    }
    # And the result round-trips into fields
    t = RequestTemplate(body=json.dumps(sample_json_to_template(sample)))
    assert [f.name for f in extract_fields(t)] == ["name", "age", "ok", "addr.city", "tags"]
