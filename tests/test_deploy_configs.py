"""Deployed bot configs must not override strategy attributes the fixes rely on.

freqtrade gives config keys precedence over strategy class attributes, so a
`minimal_roi` in any config mounted by a docker-compose*.yml would silently
re-enable ROI exits that the strategies disable with `minimal_roi = {}`.
Only key names are inspected; config values are never printed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _deployed_configs() -> list[str]:
    names: set[str] = set()
    for yml in REPO.glob("docker-compose*.yml"):
        names.update(re.findall(r"\./(config[^\s:]*\.json):", yml.read_text(encoding="utf-8")))
    return sorted(names)


def test_compose_files_reference_configs():
    assert len(_deployed_configs()) >= 10


@pytest.mark.parametrize("name", _deployed_configs())
def test_deployed_config_does_not_override_roi(name):
    path = REPO / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    assert "minimal_roi" not in cfg, f"{name} overrides the strategy's minimal_roi"
