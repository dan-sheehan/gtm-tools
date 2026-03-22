"""Tests for Playbook Generator — routes and prompt building."""
from __future__ import annotations

import pytest

import app_playbook


@pytest.fixture
def app(tmp_path):
    app_playbook.DB_PATH = tmp_path / "test.db"
    app_playbook.DATA_DIR = tmp_path
    app_playbook.ensure_db()
    flask_app = app_playbook.create_app(prefix="")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_playbooks_list_empty(client):
    resp = client.get("/api/playbooks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["playbooks"] == []


def test_build_prompt():
    prompt = app_playbook.build_prompt({
        "company_name": "Acme Corp",
        "segment": "mid-market",
        "product": "CRM Platform",
    })
    assert "Acme Corp" in prompt
