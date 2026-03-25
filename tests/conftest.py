"""Shared fixtures for gtm-tools tests.

Apps use hyphenated directory names (e.g. competitive-intel) which aren't
valid Python package names. This conftest uses importlib to load them
as importable modules and provides convenience accessors.

App data directories are pre-created so module-level initialization
doesn't fail in CI environments.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Pre-create app data directories so module imports don't fail in CI
_APP_DIRS = [
    ".competitive-intel", ".discovery", ".outbound-email",
    ".playbook", ".prompt-builder", ".icp-scorer",
    ".pipeline", ".enrichment", ".morning-brief",
    ".gtm-trends",
]
for _d in _APP_DIRS:
    (Path.home() / _d).mkdir(exist_ok=True)

# Map importable module names to their file paths
_MODULES = {
    "app_gateway": "apps/gateway/gateway.py",
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


def _register_module(module_name: str, file_path: str) -> None:
    full_path = PROJECT_ROOT / file_path
    if not full_path.exists():
        return
    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


for _name, _path in _MODULES.items():
    _register_module(_name, _path)
