from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_acquisition_script():
    path = ROOT / "scripts" / "acquire_snapshot.py"
    spec = importlib.util.spec_from_file_location("acquire_snapshot", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_json_is_stable_and_strict() -> None:
    module = load_acquisition_script()
    first = module.canonical_json({"b": 2, "a": ["£", 1]})
    second = module.canonical_json({"a": ["£", 1], "b": 2})
    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == {"a": ["£", 1], "b": 2}
    assert module.sha256_text(first) == module.sha256_text(second)
