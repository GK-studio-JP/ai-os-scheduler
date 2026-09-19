import unittest

from scheduler import build_plan


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


class SchedulerTests(unittest.TestCase):
    def test_priority_then_task_order(self):
        plan = build_plan(view([row("#3", 50), row("#2", 90), row("#1", 90)]), limit=2)
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#1", "#2"])
        self.assertEqual(plan["policy"], "priority-desc/task-asc")

    def test_process_filter(self):
        plan = build_plan(view([row("#1", 90, "PROC-A"), row("#2", 100, "PROC-B")]), process="PROC-A")
        self.assertEqual(plan["dispatches"][0]["task"], "#1")

    def test_manifest_adds_capsule_reference(self):
        v = view([row("#7", 10)])
        manifest = {
            "schema": "ai-os-projection-manifest:v1",
            "authoritative": False,
            "repository": "owner/board",
            "generated_at": "2026-09-19T00:00:00Z",
            "tasks": [{"task": "#7", "capsule": "capsules/issue-7.json", "fingerprint": "sha256:x", "through_comment_id": 9}],
        }
        plan = build_plan(v, manifest)
        self.assertEqual(plan["dispatches"][0]["context"]["capsule"], "capsules/issue-7.json")

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


if __name__ == "__main__":
    unittest.main()
