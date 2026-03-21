import json
from pathlib import Path

import pytest


def _read_path(payload: dict, json_path: str):
    current = payload
    for part in json_path.split("."):
        if not part:
            continue
        current = current[part]
    return current


@pytest.mark.parametrize(
    "case",
    json.loads(
        Path(__file__).with_name("fixtures").joinpath("golden_cases.json").read_text(encoding="utf-8")
    ),
    ids=lambda case: case["name"],
)
def test_golden_cases(case: dict):
    repo_root = Path(__file__).resolve().parents[2]
    payload = json.loads((repo_root / case["file"]).read_text(encoding="utf-8"))
    value = _read_path(payload, case["json_path"])

    if "contains_all" in case:
        text = str(value)
        for expected in case["contains_all"]:
            assert expected in text

    if "not_contains" in case:
        text = str(value)
        for forbidden in case["not_contains"]:
            assert forbidden not in text

    if "min_length" in case:
        assert len(value) >= int(case["min_length"])

    if "required_keys" in case:
        for key in case["required_keys"]:
            assert key in value
