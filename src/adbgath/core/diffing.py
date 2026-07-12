from __future__ import annotations

from typing import Any


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            output.update(_flatten(value[key], child))
        return output
    if isinstance(value, list):
        if all(isinstance(item, (str, int, float, bool, type(None))) for item in value):
            return {prefix: sorted(value, key=lambda item: str(item))}
        return {f"{prefix}[{index}]": item for index, item in enumerate(value)}
    return {prefix: value}


def diff_values(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    left = _flatten(before)
    right = _flatten(after)
    added = {key: right[key] for key in sorted(right.keys() - left.keys())}
    removed = {key: left[key] for key in sorted(left.keys() - right.keys())}
    changed = {
        key: {"before": left[key], "after": right[key]}
        for key in sorted(left.keys() & right.keys())
        if left[key] != right[key]
    }
    return {
        "summary": {"added": len(added), "removed": len(removed), "changed": len(changed)},
        "added": added,
        "removed": removed,
        "changed": changed,
    }
