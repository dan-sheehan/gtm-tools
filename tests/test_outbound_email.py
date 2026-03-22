"""Tests for Outbound Email — personas and route checks."""
from __future__ import annotations

import pytest

import app_outbound_email


@pytest.fixture
def app(tmp_path):
    app_outbound_email.DB_PATH = tmp_path / "test.db"
    app_outbound_email.DATA_DIR = tmp_path
    app_outbound_email.ensure_db()
    flask_app = app_outbound_email.create_app(prefix="")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_sequences_list_empty(client):
    resp = client.get("/api/sequences")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sequences"] == []


def test_sequences_empty(client):
    resp = client.get("/api/sequences")
    assert resp.status_code == 200
    assert resp.get_json()["sequences"] == []
