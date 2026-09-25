import pytest

from app.app import app, safe_color, DEFAULT_COLOR


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_healthz(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_readyz(client):
    assert client.get("/readyz").status_code == 200


def test_info_has_expected_fields(client):
    data = client.get("/api/info").get_json()
    for key in ["app", "version", "message", "color", "pod", "node", "requests_served"]:
        assert key in data


def test_version_comes_from_env(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "42")
    assert client.get("/api/info").get_json()["version"] == "42"


def test_home_page_renders(client, monkeypatch):
    monkeypatch.setenv("APP_MESSAGE", "Practice makes perfect")
    res = client.get("/")
    assert res.status_code == 200
    assert b"Practice makes perfect" in res.data


@pytest.mark.parametrize("value,expected", [
    ("#ff0000", "#ff0000"),
    ("red", DEFAULT_COLOR),
    ("#fff", DEFAULT_COLOR),
    ("#123456; }</style>", DEFAULT_COLOR),
    (None, DEFAULT_COLOR),
])
def test_color_is_validated(value, expected):
    assert safe_color(value) == expected
