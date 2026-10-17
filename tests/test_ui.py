"""UI tests with NiceGUI's simulated user (no browser needed)."""

import pytest
from nicegui.testing import User

from apirunner.core.models import FieldSpec, RequestTemplate
from apirunner.services import services

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("APIRUNNER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    services.__dict__.pop("storage", None)  # reset cached_property
    yield
    services.__dict__.pop("storage", None)


@pytest.mark.parametrize("path,title", [("/", "Single Call"), ("/templates", "JSON Templates"),
                                        ("/bulk", "Excel Bulk"), ("/history", "History"),
                                        ("/settings", "Settings")])
async def test_every_page_renders(user: User, path, title):
    await user.open(path)
    await user.should_see(title)


async def test_single_call_detects_placeholders_as_params(user: User):
    await user.open("/")
    user.find("Request URL").type("https://api.test/orders/{{orderId}}/items/{{itemId}}")
    await user.should_see("orderId")
    await user.should_see("itemId")


async def test_ai_buttons_hidden_without_key(user: User):
    await user.open("/")
    await user.should_not_see("AI: describe the request")


async def test_bulk_page_asks_for_template_when_none(user: User):
    await user.open("/bulk")
    await user.should_see("Create a JSON template first")


async def test_bulk_page_lists_saved_templates(user: User):
    services.storage.save_template(RequestTemplate(name="Create user", url="https://x/{{name}}",
                                                   fields=[FieldSpec(name="name")]))
    await user.open("/bulk")
    user.find(marker="template-select").click()
    await user.should_see("Create user")
