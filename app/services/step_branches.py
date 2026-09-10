"""Personalized micro-branches per main roadmap step (main map unchanged)."""

from __future__ import annotations

import json
from typing import Any

from .roadmap import steps_for_startup


def parse_step_branches(startup) -> dict[str, list[dict[str, str]]]:
    if not startup:
        return {}
    raw = getattr(startup, "step_branches_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[dict[str, str]]] = {}
    for key, items in data.items():
        if not isinstance(items, list):
            continue
        branch_items = []
        for item in items:
            if isinstance(item, str) and item.strip():
                branch_items.append({"label": item.strip()[:90]})
            elif isinstance(item, dict) and (item.get("label") or "").strip():
                branch_items.append({"label": str(item["label"]).strip()[:90]})
        if branch_items:
            out[str(key)] = branch_items[:5]
    return out


def dump_step_branches(branches: dict[str, list[dict[str, str]]]) -> str:
    return json.dumps(branches, ensure_ascii=False)


def branches_for_step(startup, step_index: int) -> list[dict[str, str]]:
    data = parse_step_branches(startup)
    return list(data.get(str(step_index), data.get(step_index, [])))


def micro_branch_state(
    startup,
    step_index: int,
    current_step_index: int,
    *,
    goals_done: int = 0,
) -> list[dict[str, Any]]:
    """Status for micro-branches: done / active / pending."""
    labels = branches_for_step(startup, step_index)
    if not labels:
        return []
    result = []
    for j, item in enumerate(labels):
        if step_index < current_step_index:
            status = "done"
        elif step_index > current_step_index:
            status = "pending"
        else:
            if j < goals_done:
                status = "done"
            elif j == goals_done:
                status = "active"
            else:
                status = "pending"
        result.append({**item, "status": status, "index": j})
    return result


def attach_micro_branches_to_map(
    nodes: list[dict[str, Any]],
    startup,
    current_step_index: int,
    *,
    goals_done: int = 0,
) -> list[dict[str, Any]]:
    for node in nodes:
        idx = node.get("index", 0)
        node["micro_branches"] = micro_branch_state(
            startup,
            idx,
            current_step_index,
            goals_done=goals_done if idx == current_step_index else 0,
        )
    return nodes


def ensure_branch_keys(steps: list[dict], branches: dict[str, list]) -> dict[str, list[dict[str, str]]]:
    """Align branch dict to step count; fill gaps with empty lists."""
    out: dict[str, list[dict[str, str]]] = {}
    for i in range(len(steps)):
        key = str(i)
        items = branches.get(key) or branches.get(i) or []
        normalized = []
        for item in items[:5]:
            if isinstance(item, dict) and item.get("label"):
                normalized.append({"label": str(item["label"]).strip()[:90]})
            elif isinstance(item, str) and item.strip():
                normalized.append({"label": item.strip()[:90]})
        out[key] = normalized
    return out
