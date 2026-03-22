"""Shared fixtures for gtm-tools tests.

Apps use hyphenated directory names (e.g. competitive-intel) which aren't
valid Python package names. This conftest uses importlib to load them
as importable modules via a lazy finder so they are only imported when
a test actually needs them (avoiding side effects at collection time).
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Map importable module names to their file paths
_MODULES = {
    "app_gateway": "apps/gateway/gateway.py",
    "app_prompts": "apps/prompts/prompts.py",
    "app_morning_brief": "apps/morning-brief/brief.py",
    "app_playbook": "apps/playbook/playbook.py",
    "app_discovery": "apps/discovery/discovery.py",
    "app_competitive_intel": "apps/competitive-intel/competitive_intel.py",
    "app_prompt_builder": "apps/prompt-builder/prompt_builder.py",
    "app_outbound_email": "apps/outbound-email/outbound_email.py",
    "app_icp_scorer": "apps/icp-scorer/icp_scorer.py",
    "app_pipeline": "apps/pipeline/pipeline.py",
    "app_enrichment": "apps/enrichment/enrichment.py",
}


class _LazyAppFinder(importlib.abc.MetaPathFinder):
    """Meta-path finder that lazily loads app modules on first import."""

    def find_module(self, fullname, path=None):
        if fullname in _MODULES:
            return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        file_path = str(PROJECT_ROOT / _MODULES[fullname])
        spec = importlib.util.spec_from_file_location(fullname, file_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = mod
        spec.loader.exec_module(mod)
        return mod


sys.meta_path.insert(0, _LazyAppFinder())


def _ensure_app_dirs():
    """Create app data directories so module imports don't fail in CI."""
    app_dirs = [
        ".competitive-intel", ".discovery", ".outbound-email",
        ".playbook", ".prompt-builder", ".icp-scorer",
        ".pipeline", ".enrichment", ".morning-brief",
    ]
    home = Path.home()
    for d in app_dirs:
        (home / d).mkdir(exist_ok=True)


_ensure_app_dirs()
