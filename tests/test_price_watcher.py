import pytest

import database
import price_watcher

WATCHLIST = [{"origin": "KRK", "destination": "PMI", "date": "2026-09-01"}]


@pytest.fixture
def captured_store(monkeypatch, tmp_path):
    """Run run_once() with the scraper stubbed out; return the store it chose."""
    captured = {}

    async def fake_check_once(watchlist, price_store):
        captured["store"] = price_store

    monkeypatch.setattr(price_watcher, "load_watchlist", lambda: WATCHLIST)
    monkeypatch.setattr(price_watcher, "check_once", fake_check_once)
    monkeypatch.setattr(price_watcher, "PRICE_HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(database, "init_db", lambda: None)
    return captured


def test_once_defaults_to_json_store(monkeypatch, captured_store):
    monkeypatch.setattr(price_watcher, "PRICE_STORE", "json")
    price_watcher.run_once()
    assert isinstance(captured_store["store"], price_watcher.JsonFilePriceStore)


def test_once_uses_postgres_store_when_configured(monkeypatch, captured_store):
    monkeypatch.setattr(price_watcher, "PRICE_STORE", "postgres")
    price_watcher.run_once()
    assert isinstance(captured_store["store"], price_watcher.PostgresPriceStore)


def test_json_store_round_trip(tmp_path):
    path = tmp_path / "history.json"
    store = price_watcher.JsonFilePriceStore(str(path))
    store.save_price({"origin": "KRK", "destination": "PMI", "date": "2026-09-01", "price": 199.0})
    store.flush()

    reloaded = price_watcher.JsonFilePriceStore(str(path))
    assert reloaded.get_last_price("KRK", "PMI", "2026-09-01") == 199.0
    assert "KRK" not in path.read_text()  # keys are hashed, not plaintext
