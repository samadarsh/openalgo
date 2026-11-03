"""/api/v1/analyzer reports the caller's order mode, so an API client can confirm Semi-Auto
(orders queued for the Action Center) before it sends anything.

Run with: uv run pytest test/test_analyzer_status_order_mode.py -v
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

import database.auth_db as auth_db
import services.analyzer_service as analyzer_service
from database.auth_db import update_order_mode, upsert_api_key

USER = "analyzer_status_user"
API_KEY = "analyzer-status-test-api-key"


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


@pytest.fixture(autouse=True)
def stub_platform(monkeypatch):
    """Analyzer flag, analyzer log count, broker lookup and the order log are stubbed."""

    class Count:
        def query(self, model):
            return self

        def count(self):
            return 3

    class NoLog:
        def submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(analyzer_service, "get_analyze_mode", lambda: False)
    monkeypatch.setattr(analyzer_service, "db_session", Count())
    monkeypatch.setattr(analyzer_service, "log_executor", NoLog())
    monkeypatch.setattr(analyzer_service, "get_auth_token_broker", lambda key: ("token", "angel"))
    upsert_api_key(USER, API_KEY)


@pytest.mark.parametrize("mode", ["auto", "semi_auto"])
def test_status_reports_the_callers_order_mode(mode):
    update_order_mode(USER, mode)
    success, response, status = analyzer_service.get_analyzer_status({}, api_key=API_KEY)
    assert (success, status) == (True, 200)
    assert response["data"] == {
        "mode": "live",
        "analyze_mode": False,
        "total_logs": 3,
        "order_mode": mode,
    }


def test_internal_callers_get_the_unchanged_shape():
    success, response, _ = analyzer_service.get_analyzer_status(
        {}, auth_token="token", broker="angel"
    )
    assert success and "order_mode" not in response["data"]
