"""Tests for Competitive Intel — prompt dispatch and route checks."""
from __future__ import annotations

import pytest

import app_competitive_intel


@pytest.fixture
def app(tmp_path):
    app_competitive_intel.DB_PATH = tmp_path / "test.db"
    app_competitive_intel.DATA_DIR = tmp_path
    app_competitive_intel.ensure_db()
    flask_app = app_competitive_intel.create_app(prefix="")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_build_prompt_general():
    prompt = app_competitive_intel.build_prompt({"company_name": "Acme", "analysis_type": "general"})
    assert "Acme" in prompt


def test_build_prompt_battlecard():
    prompt = app_competitive_intel.build_prompt({"company_name": "Acme", "analysis_type": "battlecard"})
    assert "Acme" in prompt
    assert "battlecard" in prompt.lower() or "feature_matrix" in prompt


def test_analyses_list_empty(client):
    resp = client.get("/api/analyses")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["analyses"] == []
