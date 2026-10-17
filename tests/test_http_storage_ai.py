import base64
from types import SimpleNamespace

import httpx
import pytest
import respx

from apirunner.core.models import AuthConfig, AuthType, CallStatus, Job, PreparedRequest, RequestTemplate
from apirunner.infra.ai import AiAssistant, AiError, MappingItem, MappingSuggestion
from apirunner.infra.http_client import HttpSender
from apirunner.infra.storage import Storage


@respx.mock
async def test_sender_success_and_json_body():
    route = respx.post("https://api.test/users").mock(return_value=httpx.Response(201, json={"id": 1}))
    sender = HttpSender()
    result = await sender(PreparedRequest(method="POST", url="https://api.test/users", json_body={"a": 1}), 5)
    await sender.aclose()
    assert result.status == CallStatus.SUCCESS and result.http_code == 201
    assert route.calls[0].request.content == b'{"a":1}'


@respx.mock
async def test_sender_http_error_and_network_error_never_raise():
    respx.get("https://api.test/err").mock(return_value=httpx.Response(503))
    respx.get("https://api.test/down").mock(side_effect=httpx.ConnectError("refused"))
    sender = HttpSender()
    err = await sender(PreparedRequest(method="GET", url="https://api.test/err"), 5)
    down = await sender(PreparedRequest(method="GET", url="https://api.test/down"), 5)
    await sender.aclose()
    assert err.http_code == 503 and err.status == CallStatus.FAILED
    assert down.http_code is None and "ConnectError" in down.error


@pytest.mark.parametrize("auth,check", [
    (AuthConfig(type=AuthType.BEARER, token="t"), lambda r: r.headers["Authorization"] == "Bearer t"),
    (AuthConfig(type=AuthType.API_KEY, key_name="k", key_value="v"), lambda r: r.headers["k"] == "v"),
    (AuthConfig(type=AuthType.API_KEY, key_name="k", key_value="v", key_in="query"),
     lambda r: r.url.params["k"] == "v"),
    (AuthConfig(type=AuthType.BASIC, username="u", password="p"),
     lambda r: r.headers["Authorization"] == "Basic " + base64.b64encode(b"u:p").decode()),
])
@respx.mock
async def test_auth_types(auth, check):
    route = respx.get("https://api.test/a").mock(return_value=httpx.Response(200))
    sender = HttpSender(auth)
    await sender(PreparedRequest(method="GET", url="https://api.test/a"), 5)
    await sender.aclose()
    assert check(route.calls[0].request)


@respx.mock
async def test_azure_ad_token_is_fetched_once_and_cached():
    token = respx.post("https://login.microsoftonline.com/tid/oauth2/v2.0/token").mock(
        return_value=httpx.Response(200, json={"access_token": "az", "expires_in": 3600}))
    api = respx.get("https://graph.test/me").mock(return_value=httpx.Response(200))
    sender = HttpSender(AuthConfig(type=AuthType.AZURE_AD, tenant_id="tid", client_id="c", client_secret="s"))
    for _ in range(3):
        await sender(PreparedRequest(method="GET", url="https://graph.test/me"), 5)
    await sender.aclose()
    assert token.call_count == 1 and api.calls[-1].request.headers["Authorization"] == "Bearer az"


def test_storage_templates_jobs_settings(tmp_path):
    st = Storage(tmp_path / "db.sqlite")
    st.save_template(RequestTemplate(name="T1", url="https://x"))
    assert [t.name for t in st.list_templates()] == ["T1"]
    exported = st.export_templates()
    st.delete_template("T1")
    assert st.get_template("T1") is None
    assert st.import_templates(exported) == 1 and st.get_template("T1").url == "https://x"

    job = Job(id="j1", template=RequestTemplate(name="T1"), columns=[], mapping={}, rows=[], created_at="2026-01-01")
    st.save_job(job)
    assert st.list_jobs()[0] == {"id": "j1", "template": "T1", "created_at": "2026-01-01", "total": 0,
                                 "success": 0, "failed": 0}
    assert st.get_job("j1").id == "j1"
    st.set_setting("k", "v")
    assert st.get_setting("k") == "v" and st.get_setting("missing", "d") == "d"


async def test_ai_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ai = AiAssistant(api_key="")
    assert not ai.enabled
    with pytest.raises(AiError):
        await ai.suggest_mapping(["a"], ["a"], [])


async def test_ai_uses_structured_output_and_sends_only_samples():
    captured = {}
    parsed = MappingSuggestion(items=[MappingItem(field="name", column="Full Name", confidence=0.9, reason="")])

    class FakeMessages:
        async def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=parsed)

    ai = AiAssistant(api_key="k", model="claude-opus-5-5")
    ai._client = SimpleNamespace(messages=FakeMessages())
    rows = [{"Full Name": f"n{i}"} for i in range(20)]
    result = await ai.suggest_mapping(["Full Name"], ["name"], rows)
    assert result.items[0].column == "Full Name"
    assert captured["output_format"] is MappingSuggestion and captured["model"] == "claude-opus-5-5"
    prompt = captured["messages"][0]["content"]
    assert "n4" in prompt and "n5" not in prompt  # only 5 sample rows leave the machine


async def test_ai_refusal_raises():
    class FakeMessages:
        async def parse(self, **kwargs):
            return SimpleNamespace(stop_reason="refusal", parsed_output=None)

    ai = AiAssistant(api_key="k")
    ai._client = SimpleNamespace(messages=FakeMessages())
    with pytest.raises(AiError):
        await ai.analyze_response({}, 200, {}, "{}")
