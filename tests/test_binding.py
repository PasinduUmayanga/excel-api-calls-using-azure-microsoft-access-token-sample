from apirunner.core.binding import bind_single, build_request, detect_param_names, sync_params, to_curl
from apirunner.core.models import Param, ParamLocation, RequestTemplate


def test_detect_param_names_from_url_body_and_headers():
    names = detect_param_names("https://x/users/{{id}}/:part", '{"n": "{{name}}"}', {"X-Tenant": "{{tenant}}"})
    assert names == ["id", "part", "name", "tenant"]


def test_sync_params_keeps_values_and_manual_params():
    current = [Param(name="id", value="7"), Param(name="old", value="x"),
               Param(name="page", value="2", location=ParamLocation.QUERY)]
    synced = sync_params(current, ["id", "name"])
    assert [(p.name, p.value, p.location) for p in synced] == [
        ("id", "7", ParamLocation.AUTO), ("name", "", ParamLocation.AUTO), ("page", "2", ParamLocation.QUERY)]


def test_bind_single_routes_params_by_location():
    t = RequestTemplate(method="POST", url="https://x/users/{{id}}", body='{"name": "{{name}}"}')
    req = bind_single(t, [Param(name="id", value="5"), Param(name="name", value="Ann"),
                          Param(name="page", value="2", location=ParamLocation.QUERY),
                          Param(name="X-Trace", value="abc", location=ParamLocation.HEADER)])
    assert req.url == "https://x/users/5"
    assert req.json_body == {"name": "Ann"}
    assert req.params == {"page": "2"}
    assert req.headers["X-Trace"] == "abc"


def test_get_requests_never_send_a_body():
    t = RequestTemplate(method="GET", url="https://x", body='{"a": "{{a}}"}')
    assert build_request(t, {"a": 1}).json_body is None


def test_headers_are_rendered():
    t = RequestTemplate(method="GET", url="https://x", headers={"Authorization": "Bearer {{token}}"})
    assert build_request(t, {"token": "t1"}).headers == {"Authorization": "Bearer t1"}


def test_to_curl():
    t = RequestTemplate(method="POST", url="https://x/u", body='{"a": "{{a:integer}}"}')
    curl = to_curl(bind_single(t, [Param(name="a", value="1")]))
    assert "curl -X POST 'https://x/u'" in curl and "-d '{\"a\": \"1\"}'" in curl
