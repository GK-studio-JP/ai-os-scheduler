import json
from pathlib import Path
import unittest

from scheduler import (
    BUDGET_POLICY_SCHEMA,
    EXECUTION_BUDGET_SCHEMA,
    build_plan,
    normalize_budget_policy,
)


def view(rows):
    return {
        "schema": "ai-os-scheduler-view:v1",
        "authoritative": False,
        "repository": "owner/board",
        "generated_at": "2026-09-19T00:00:00Z",
        "runnable": rows,
    }


def row(task, priority, process="PROC-A"):
    return {
        "task": task,
        "title": task,
        "issue_url": f"https://example.invalid/{task}",
        "state": "open",
        "process": process,
        "routing_ready": True,
        "target_repository": None,
        "priority": priority,
        "owner": None,
        "blocked_by": [],
        "capabilities": [],
        "next_action": None,
        "history_safe": True,
    }


def execution_budget(**limits):
    return {
        "schema": EXECUTION_BUDGET_SCHEMA,
        "authoritative": False,
        **limits,
    }


def budget_policy(default=None, processes=None):
    return {
        "schema": BUDGET_POLICY_SCHEMA,
        "authoritative": False,
        "default": default,
        "processes": processes or {},
    }


class SchedulerTests(unittest.TestCase):
    def test_priority_then_task_order(self):
        plan = build_plan(
            view([row("#3", 50), row("#2", 90), row("#1", 90)]),
            limit=2,
        )
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#1", "#2"])
        self.assertEqual(plan["policy"], "priority-desc/task-asc")

    def test_process_filter(self):
        plan = build_plan(
            view([row("#1", 90, "PROC-A"), row("#2", 100, "PROC-B")]),
            process="PROC-A",
        )
        self.assertEqual(plan["dispatches"][0]["task"], "#1")

    def test_browser_worker_requires_trusted_admission(self):
        trusted = row("#1", 100, "PROC-RUNTIME-BROWSER-WORKER")
        trusted["admission"] = {
            "author_login": "trusted-owner",
            "author_association": "OWNER",
            "trusted": True,
        }
        untrusted = row("#2", 200, "PROC-RUNTIME-BROWSER-WORKER")
        untrusted["admission"] = {
            "author_login": "outside-user",
            "author_association": "NONE",
            "trusted": False,
        }
        missing = row("#3", 300, "PROC-RUNTIME-BROWSER-WORKER")

        plan = build_plan(
            view([missing, untrusted, trusted]),
            process="PROC-RUNTIME-BROWSER-WORKER",
            limit=3,
        )

        self.assertEqual(plan["dispatch_count"], 1)
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#1"])
        self.assertTrue(plan["dispatches"][0]["admission"]["trusted"])

    def test_manifest_adds_capsule_reference(self):
        v = view([row("#7", 10)])
        manifest = {
            "schema": "ai-os-projection-manifest:v1",
            "authoritative": False,
            "repository": "owner/board",
            "generated_at": "2026-09-19T00:00:00Z",
            "tasks": [
                {
                    "task": "#7",
                    "capsule": "capsules/issue-7.json",
                    "fingerprint": "sha256:x",
                    "through_comment_id": 9,
                }
            ],
        }
        plan = build_plan(v, manifest)
        self.assertEqual(
            plan["dispatches"][0]["context"]["capsule"],
            "capsules/issue-7.json",
        )

    def test_corrupt_runnable_fails_closed(self):
        bad = row("#1", 1)
        bad["history_safe"] = False
        with self.assertRaises(ValueError):
            build_plan(view([bad]))

    def test_manifest_generation_must_match(self):
        v = view([row("#1", 1)])
        manifest = {
            "schema": "ai-os-projection-manifest:v1",
            "authoritative": False,
            "repository": "owner/board",
            "generated_at": "2026-09-18T00:00:00Z",
            "tasks": [],
        }
        with self.assertRaises(ValueError):
            build_plan(v, manifest)

    def test_no_budget_policy_preserves_existing_dispatch_shape(self):
        plan = build_plan(view([row("#1", 10)]))
        self.assertNotIn("execution_budget", plan["dispatches"][0])
        self.assertNotIn(
            "execution_budget_policy_fingerprint",
            plan["source"],
        )

    def test_default_budget_is_attached_as_non_authoritative(self):
        policy = budget_policy(
            default=execution_budget(
                deadline_seconds=1800,
                max_steps=100,
            )
        )
        plan = build_plan(
            view([row("#1", 10)]),
            budget_policy=policy,
        )
        dispatch = plan["dispatches"][0]

        self.assertFalse(dispatch["execution_budget"]["authoritative"])
        self.assertEqual(dispatch["execution_budget"]["deadline_seconds"], 1800)
        self.assertEqual(dispatch["execution_budget"]["max_steps"], 100)
        self.assertTrue(
            plan["source"]["execution_budget_policy_fingerprint"].startswith(
                "sha256:"
            )
        )

    def test_process_override_wins_and_null_disables_default(self):
        policy = budget_policy(
            default=execution_budget(deadline_seconds=1800),
            processes={
                "PROC-B": execution_budget(
                    deadline_seconds=900,
                    max_tool_calls=20,
                ),
                "PROC-C": None,
            },
        )
        plan = build_plan(
            view(
                [
                    row("#1", 30, "PROC-A"),
                    row("#2", 20, "PROC-B"),
                    row("#3", 10, "PROC-C"),
                ]
            ),
            budget_policy=policy,
            limit=3,
        )
        by_process = {d["process"]: d for d in plan["dispatches"]}

        self.assertEqual(
            by_process["PROC-A"]["execution_budget"]["deadline_seconds"],
            1800,
        )
        self.assertEqual(
            by_process["PROC-B"]["execution_budget"]["deadline_seconds"],
            900,
        )
        self.assertEqual(
            by_process["PROC-B"]["execution_budget"]["max_tool_calls"],
            20,
        )
        self.assertNotIn("execution_budget", by_process["PROC-C"])

    def test_budget_policy_is_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "non-authoritative"):
            normalize_budget_policy(
                {
                    "schema": BUDGET_POLICY_SCHEMA,
                    "authoritative": True,
                    "default": execution_budget(deadline_seconds=30),
                    "processes": {},
                }
            )
        with self.assertRaisesRegex(ValueError, "positive integer"):
            normalize_budget_policy(
                budget_policy(
                    default=execution_budget(deadline_seconds=0),
                )
            )

    def test_budget_policy_changes_plan_fingerprint(self):
        v = view([row("#1", 10)])
        first = build_plan(
            v,
            budget_policy=budget_policy(
                default=execution_budget(deadline_seconds=1800)
            ),
        )
        second = build_plan(
            v,
            budget_policy=budget_policy(
                default=execution_budget(deadline_seconds=900)
            ),
        )
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotEqual(
            first["source"]["execution_budget_policy_fingerprint"],
            second["source"]["execution_budget_policy_fingerprint"],
        )

    def test_repository_policy_uses_runtime_compatible_deadline_only(self):
        policy = json.loads(
            Path("execution_budget_policy.json").read_text(encoding="utf-8")
        )
        plan = build_plan(
            view([row("#1", 10)]),
            budget_policy=policy,
        )
        budget = plan["dispatches"][0]["execution_budget"]

        self.assertEqual(budget["schema"], EXECUTION_BUDGET_SCHEMA)
        self.assertFalse(budget["authoritative"])
        self.assertEqual(budget["deadline_seconds"], 1800)
        self.assertIsNone(budget["max_steps"])
        self.assertIsNone(budget["max_tool_calls"])
        self.assertIsNone(budget["max_tokens"])


if __name__ == "__main__":
    unittest.main()
