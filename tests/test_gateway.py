"""Tests for the gateway hub page."""
from __future__ import annotations

import app_gateway


def test_hub_page_contains_all_apps():
    assert "/discovery/" in app_gateway.HUB_PAGE
    assert "/competitive-intel/" in app_gateway.HUB_PAGE
    assert "/outbound-email/" in app_gateway.HUB_PAGE
    assert "/playbook/" in app_gateway.HUB_PAGE
    assert "/brief/" in app_gateway.HUB_PAGE
    assert "/gtm-trends/" in app_gateway.HUB_PAGE
    assert "/prompt-builder/" in app_gateway.HUB_PAGE


def test_hub_page_is_valid_html():
    assert "<!doctype html>" in app_gateway.HUB_PAGE.lower()
    assert "</html>" in app_gateway.HUB_PAGE
