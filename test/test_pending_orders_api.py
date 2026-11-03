"""Read-only /api/v1/pendingorders: an API client can see what became of the orders it
queued in the Action Center (Semi-Auto), and never anyone else's.

Run with: uv run pytest test/test_pending_orders_api.py -v
"""

import json

import pytest
from flask import Flask
from flask_restx import Api
from marshmallow import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

import database.action_center_db as action_center_db
import database.auth_db as auth_db
from database.action_center_db import (
    approve_pending_order,
    create_pending_order,
    reject_pending_order,
    update_broker_status,
)
from database.auth_db import upsert_api_key
from restx_api.account_schema import PendingOrdersSchema
from services.pending_orders_service import get_pending_orders_for_api

USER, KEY = "pending_api_user", "pending-api-test-key"
OTHER, OTHER_KEY = "pending_api_other", "pending-api-other-key"


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Run every test against a temporary database, never db/openalgo.db."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pending.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    ac_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    auth_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
    ac_query = action_center_db.Base.__dict__["query"]
    auth_query = auth_db.Base.__dict__["query"]
    monkeypatch.setattr(action_center_db, "engine", engine)
    monkeypatch.setattr(action_center_db, "db_session", ac_session)
    monkeypatch.setattr(auth_db, "engine", engine)
    monkeypatch.setattr(auth_db, "db_session", auth_session)
    action_center_db.Base.query = ac_session.query_property()
    auth_db.Base.query = auth_session.query_property()
    action_center_db.Base.metadata.create_all(bind=engine)
    auth_db.Base.metadata.create_all(bind=engine)
    auth_db.verified_api_key_cache.clear()
    auth_db.invalid_api_key_cache.clear()
    upsert_api_key(USER, KEY)
    upsert_api_key(OTHER, OTHER_KEY)
    try:
        yield
    finally:
        ac_session.remove()
        auth_session.remove()
        engine.dispose()
        action_center_db.Base.query = ac_query
        auth_db.Base.query = auth_query
        auth_db.verified_api_key_cache.clear()
        auth_db.invalid_api_key_cache.clear()


def _order(symbol, **extra):
    return {"symbol": symbol, "exchange": "NSE", "action": "BUY", "quantity": "10", **extra}


def test_lists_the_callers_orders_with_their_outcome():
    pending = create_pending_order(USER, "placeorder", _order("SBIN", apikey="leaked"))
    approved = create_pending_order(USER, "placeorder", _order("INFY"))
    rejected = create_pending_order(USER, "placeorder", _order("TCS"))
    create_pending_order(OTHER, "placeorder", _order("WIPRO"))
    approve_pending_order(approved, approved_by=USER, user_id=USER)
    update_broker_status(approved, "251103000123456", "complete")
    reject_pending_order(rejected, reason="not today", rejected_by=USER, user_id=USER)

    success, response, status = get_pending_orders_for_api(KEY)
    assert (success, status) == (True, 200)
    rows = {row["pending_order_id"]: row for row in response["data"]["orders"]}
    assert set(rows) == {pending, approved, rejected}  # never another user's
    assert rows[pending]["status"] == "pending"
    assert rows[pending]["order"]["symbol"] == "SBIN"
    assert "apikey" not in rows[pending]["order"]
    assert rows[approved]["broker_order_id"] == "251103000123456"
    assert rows[approved]["broker_status"] == "complete"
    assert rows[rejected]["status"] == "rejected"
    assert rows[rejected]["rejected_reason"] == "not today"


def test_status_filter_and_limit():
    first = create_pending_order(USER, "placeorder", _order("SBIN"))
    second = create_pending_order(USER, "placeorder", _order("INFY"))
    approve_pending_order(first, approved_by=USER, user_id=USER)
    _, response, _ = get_pending_orders_for_api(KEY, status="pending")
    assert [row["pending_order_id"] for row in response["data"]["orders"]] == [second]
    _, response, _ = get_pending_orders_for_api(KEY, limit=1)
    assert len(response["data"]["orders"]) == 1


def test_an_unknown_key_is_refused():
    success, response, status = get_pending_orders_for_api("not-a-key")
    assert (success, status) == (False, 403)


def test_schema_validates_status_and_limit():
    schema = PendingOrdersSchema()
    assert schema.load({"apikey": "k"}) == {"apikey": "k", "status": None, "limit": 100}
    with pytest.raises(ValidationError):
        schema.load({"apikey": "k", "status": "deleted"})
    with pytest.raises(ValidationError):
        schema.load({"apikey": "k", "limit": 0})


def test_route_returns_json():
    from limiter import limiter
    from restx_api import pending_orders

    app = Flask(__name__)
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    Api(app).add_namespace(pending_orders.api, path="/api/v1/pendingorders")
    create_pending_order(USER, "placeorder", _order("SBIN"))
    client = app.test_client()
    response = client.post("/api/v1/pendingorders", json={"apikey": KEY})
    assert response.status_code == 200
    assert json.loads(response.data)["data"]["orders"][0]["order"]["symbol"] == "SBIN"
    assert client.post("/api/v1/pendingorders", json={"apikey": KEY, "limit": 0}).status_code == 400
