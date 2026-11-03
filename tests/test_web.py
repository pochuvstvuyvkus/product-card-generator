import json

import pytest
from fastapi.testclient import TestClient

from card_gen.config import ConfigError
from card_gen.llm import LLMError
from card_gen.web import app, get_client_factory

from .conftest import EXAMPLES, FakeClient, manometer_draft


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(fake):
    app.dependency_overrides[get_client_factory] = lambda: lambda: fake


def test_index_and_examples(client):
    assert "Черновик карточки" in client.get("/").text
    assert set(client.get("/api/examples").json()) == {"manometer_tm510r_m2", "gas_detector_dz1_co"}


def test_card_ok(client):
    use(FakeClient(manometer_draft()))
    body = (EXAMPLES / "manometer_tm510r_m2.json").read_bytes()
    res = client.post("/api/card", content=body)
    assert res.status_code == 200
    data = res.json()
    assert data["card"]["status"] == "needs_data"
    assert data["markdown"].startswith("# Манометр")


def test_invalid_json(client):
    res = client.post("/api/card", content=b'{"name": ')
    assert res.status_code == 400
    assert "Некорректный JSON" in res.json()["error"]


def test_insufficient_data_returns_issues(client):
    res = client.post("/api/card", content=json.dumps({"name": "Манометр"}))
    assert res.status_code == 422
    assert res.json()["issues"][0]["field"] == "specs, description"


def test_llm_error_is_502(client):
    use(FakeClient(LLMError("Нет связи с API")))
    res = client.post("/api/card", content=(EXAMPLES / "gas_detector_dz1_co.json").read_bytes())
    assert res.status_code == 502 and res.json()["error"] == "Нет связи с API"


def test_missing_key_is_503(client):
    def factory():
        raise ConfigError("Не задан ANTHROPIC_API_KEY")

    app.dependency_overrides[get_client_factory] = lambda: factory
    res = client.post("/api/card", content=(EXAMPLES / "gas_detector_dz1_co.json").read_bytes())
    assert res.status_code == 503


def test_check_endpoint(client):
    res = client.post("/api/check", content=(EXAMPLES / "manometer_tm510r_m2.json").read_bytes())
    assert res.status_code == 200
    assert res.json()["issues"][0]["field"] == "specs.Диапазон измерений"
