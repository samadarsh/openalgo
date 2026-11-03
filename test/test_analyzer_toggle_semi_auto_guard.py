"""The Semi-Auto block on the analyzer toggle must look the order mode up by user.

toggle_analyzer_mode() refuses an API toggle while the user is in Semi-Auto, because
mode switching is a client-only decision there. It used to pass the API key to
get_order_mode(), which looks rows up by user id, so it always read "auto" and the
block never fired.

Run with: uv run pytest test/test_analyzer_toggle_semi_auto_guard.py -v
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

import database.auth_db as auth_db
import services.analyzer_service as analyzer_service
from database.auth_db import update_order_mode, upsert_api_key

USER = "analyzer_guard_user"
API_KEY = "analyzer-guard-test-api-key"


@pytest.fixture(autouse=True)
def isolated_auth_database(tmp_path, monkeypatch):
    """Run every test against a temporary database, never db/openalgo.db."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    original_query = auth_db.Base.__dict__["query"]
    monkeypatch.setattr(auth_db, "engine", engine)
    monkeypatch.setattr(auth_db, "db_session", session)
    auth_db.Base.query = session.query_property()
    auth_db.Base.metadata.create_all(bind=engine)
    auth_db.order_mode_cache.clear()
    auth_db.verified_api_key_cache.clear()
    auth_db.invalid_api_key_cache.clear()
    try:
        yield
    finally:
        session.remove()
        engine.dispose()
        auth_db.Base.query = original_query
        auth_db.order_mode_cache.clear()
        auth_db.verified_api_key_cache.clear()
        auth_db.invalid_api_key_cache.clear()


@pytest.fixture
def toggle_calls(monkeypatch):
    """Stub the broker lookup, the toggle itself and the order log."""
    calls = []

    def fake_toggle(analyzer_data, auth_token, broker, original_data):
        calls.append(analyzer_data)
        return True, {"status": "success"}, 200

    class NoLog:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(analyzer_service, "get_auth_token_broker", lambda key: ("token", "angel"))
    monkeypatch.setattr(analyzer_service, "toggle_analyzer_mode_with_auth", fake_toggle)
    monkeypatch.setattr(analyzer_service, "log_executor", NoLog())
    upsert_api_key(USER, API_KEY)
    return calls


def test_api_toggle_is_refused_in_semi_auto(toggle_calls):
    update_order_mode(USER, "semi_auto")
    success, response, status = analyzer_service.toggle_analyzer_mode(
        {"mode": True}, api_key=API_KEY
    )
    assert (success, status) == (False, 403)
    assert "Semi-Auto" in response["message"]
    assert toggle_calls == []


def test_api_toggle_still_works_in_auto(toggle_calls):
    update_order_mode(USER, "auto")
    success, _, status = analyzer_service.toggle_analyzer_mode({"mode": True}, api_key=API_KEY)
    assert (success, status) == (True, 200)
    assert len(toggle_calls) == 1


def test_internal_toggle_is_not_affected_by_the_api_guard(toggle_calls):
    update_order_mode(USER, "semi_auto")
    success, _, status = analyzer_service.toggle_analyzer_mode(
        {"mode": True}, auth_token="token", broker="angel"
    )
    assert (success, status) == (True, 200)
