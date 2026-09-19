from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

VIEW_SCHEMA = "ai-os-scheduler-view:v1"
MANIFEST_SCHEMA = "ai-os-projection-manifest:v1"
PLAN_SCHEMA = "ai-os-dispatch-plan:v1"
DISPATCH_SCHEMA = "ai-os-dispatch:v1"
POLICY = "priority-desc/task-asc"


def _read(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | None, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def _task_number(task: Any) -> int:
    match = re.search(r"(\d+)$", str(task))
    if not match:
        raise ValueError(f"task has no numeric suffix: {task!r}")
    return int(match.group(1))


def _priority(row: dict[str, Any]) -> int:
    value = row.get("priority")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return (-_priority(row), _task_number(row.get("task")), str(row.get("task")))


def validate_view(view: dict[str, Any]) -> None:
    if view.get("schema") != VIEW_SCHEMA:
        raise ValueError(f"unsupported scheduler view schema: {view.get('schema')!r}")
    if view.get("authoritative") is not False:
        raise ValueError("scheduler view must be explicitly non-authoritative")
    if not isinstance(view.get("repository"), str) or not view["repository"]:
        raise ValueError("scheduler view repository is required")
    if not isinstance(view.get("generated_at"), str) or not view["generated_at"]:
        raise ValueError("scheduler view generated_at is required")
    runnable = view.get("runnable")
    if not isinstance(runnable, list):
        raise ValueError("scheduler view runnable must be a list")
    for row in runnable:
        if not isinstance(row, dict):
            raise ValueError("runnable row must be an object")
        if row.get("state") != "open":
            raise ValueError(f"runnable row is not open: {row.get('task')}")
        if row.get("history_safe") is not True:
            raise ValueError(f"runnable row is not history-safe: {row.get('task')}")
        if row.get("blocked_by"):
            raise ValueError(f"runnable row is blocked: {row.get('task')}")
        if row.get("routing_ready") is not True or not row.get("process"):
            raise ValueError(f"runnable row is not routed: {row.get('task')}")
        _task_number(row.get("task"))


def validate_manifest(view: dict[str, Any], manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema: {manifest.get('schema')!r}")
    if manifest.get("authoritative") is not False:
        raise ValueError("projection manifest must be explicitly non-authoritative")
    if manifest.get("repository") != view.get("repository"):
        raise ValueError("manifest repository does not match scheduler view")
    if manifest.get("generated_at") != view.get("generated_at"):
        raise ValueError("manifest generation does not match scheduler view")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("manifest tasks must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in tasks:
        if not isinstance(item, dict) or not item.get("task"):
            raise ValueError("manifest task entry is invalid")
        task = str(item["task"])
        if task in result:
            raise ValueError(f"duplicate manifest task: {task}")
        result[task] = item
    return result


def build_plan(
    view: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    *,
    limit: int = 1,
    process: str | None = None,
) -> dict[str, Any]:
    validate_view(view)
    if limit < 1:
        raise ValueError("limit must be >= 1")

    manifest_by_task: dict[str, dict[str, Any]] = {}
    if manifest is not None:
        manifest_by_task = validate_manifest(view, manifest)

    candidates = list(view["runnable"])
    if process:
        candidates = [row for row in candidates if row.get("process") == process]
    candidates.sort(key=_sort_key)
    selected = candidates[:limit]

    dispatches: list[dict[str, Any]] = []
    for row in selected:
        task = str(row["task"])
        context = None
        if manifest is not None:
            item = manifest_by_task.get(task)
            if item is None:
                raise ValueError(f"selected task missing from manifest: {task}")
            if not item.get("capsule") or not item.get("fingerprint"):
                raise ValueError(f"selected task has incomplete context reference: {task}")
            context = {
                "capsule": item["capsule"],
                "fingerprint": item["fingerprint"],
                "through_comment_id": item.get("through_comment_id"),
            }

        dispatches.append(
            {
                "schema": DISPATCH_SCHEMA,
                "authoritative": False,
                "task": task,
                "title": row.get("title") or "",
                "process": row["process"],
                "target_repository": row.get("target_repository"),
                "priority": _priority(row),
                "capabilities": list(row.get("capabilities") or []),
                "next_action": row.get("next_action"),
                "context": context,
                "source": {
                    "repository": view["repository"],
                    "issue_url": row.get("issue_url"),
                    "projection_generated_at": view["generated_at"],
                },
            }
        )

    plan = {
        "schema": PLAN_SCHEMA,
        "authoritative": False,
        "policy": POLICY,
        "source": {
            "repository": view["repository"],
            "projection_generated_at": view["generated_at"],
        },
        "filters": {"process": process},
        "candidate_count": len(candidates),
        "dispatch_count": len(dispatches),
        "dispatches": dispatches,
    }
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    plan["fingerprint"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return plan


def command_plan(args: argparse.Namespace) -> None:
    view = _read(args.view)
    manifest = _read(args.manifest) if args.manifest else None
    plan = build_plan(view, manifest, limit=args.limit, process=args.process)
    _write(args.output, plan)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aios-scheduler")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="build a bounded deterministic dispatch plan")
    p.add_argument("--view", required=True)
    p.add_argument("--manifest")
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--process")
    p.add_argument("--output")
    p.set_defaults(func=command_plan)
    return root


def main() -> None:
    args = parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
