import pytest

import database
import webapp


@pytest.fixture
def client():
    webapp.app.config["TESTING"] = True
    with webapp.app.test_client() as client:
        yield client


class _FakeConnection:
    def cursor(self):
        return self

    def execute(self, sql):
        pass

    def close(self):
        pass


def _db_down():
    raise ConnectionError("connection refused")


def test_parse_codes():
    assert webapp.parse_codes(" krk, KTW\nwaw ,, ") == ["KRK", "KTW", "WAW"]


def test_parse_groups():
    assert webapp.parse_groups("bcn, gro\n\nPFO,LCA") == [["BCN", "GRO"], ["PFO", "LCA"]]


def test_healthz_ignores_database(client, monkeypatch):
    monkeypatch.setattr(database, "get_connection", _db_down)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_readyz_ok_when_database_reachable(client, monkeypatch):
    monkeypatch.setattr(database, "get_connection", lambda: _FakeConnection())
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.get_json()["db"] == "ok"


def test_readyz_unavailable_when_database_down(client, monkeypatch):
    monkeypatch.setattr(database, "get_connection", _db_down)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"


def test_index_renders(client):
    response = client.get("/")
    assert response.status_code == 200
