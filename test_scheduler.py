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


def row(task, priority, process="PROC-A", trusted=True):
    value = {
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
    if trusted is not None:
        value["admission"] = {
            "author_login": "trusted-owner" if trusted else "outside-user",
            "author_association": "OWNER" if trusted else "NONE",
            "trusted": trusted,
        }
    return value


class SchedulerTests(unittest.TestCase):
    def test_priority_then_task_order(self):
        plan = build_plan(view([row("#3", 50), row("#2", 90), row("#1", 90)]), limit=2)
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#1", "#2"])
        self.assertEqual(plan["policy"], "priority-desc/task-asc")

    def test_process_filter(self):
        plan = build_plan(view([row("#1", 90, "PROC-A"), row("#2", 100, "PROC-B")]), process="PROC-A")
        self.assertEqual(plan["dispatches"][0]["task"], "#1")

    def test_all_processes_require_trusted_admission(self):
        trusted = row("#1", 100, "PROC-A", trusted=True)
        untrusted = row("#2", 300, "PROC-A", trusted=False)
        missing = row("#3", 400, "PROC-A", trusted=None)
        browser_untrusted = row("#4", 500, "PROC-RUNTIME-BROWSER-WORKER", trusted=False)
        browser_trusted = row("#5", 90, "PROC-RUNTIME-BROWSER-WORKER", trusted=True)

        plan = build_plan(
            view([missing, untrusted, trusted, browser_untrusted, browser_trusted]),
            limit=10,
        )

        self.assertEqual(plan["candidate_count"], 2)
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#1", "#5"])
        self.assertTrue(all(d["admission"]["trusted"] for d in plan["dispatches"]))

    def test_process_filter_fails_closed_on_untrusted_rows(self):
        plan = build_plan(
            view([
                row("#1", 300, "PROC-B", trusted=False),
                row("#2", 200, "PROC-B", trusted=None),
                row("#3", 100, "PROC-B", trusted=True),
            ]),
            process="PROC-B",
            limit=3,
        )
        self.assertEqual(plan["candidate_count"], 1)
        self.assertEqual([d["task"] for d in plan["dispatches"]], ["#3"])

    def test_manifest_adds_capsule_reference(self):
        v = view([row("#7", 10)])
        manifest = {
            "schema": "ai-os-projection-manifest:v1",
            "authoritative": False,
            "repository": "owner/board",
            "generated_at": "2026-09-19T00:00:00Z",
            "tasks": [{"task": "#7", "capsule": "capsules/issue-7.json", "fingerprint": "sha256:x", "content_digest": "sha256:" + "a" * 64, "through_comment_id": 9}],
        }
        plan = build_plan(v, manifest)
        self.assertEqual(plan["dispatches"][0]["context"]["capsule"], "capsules/issue-7.json")
        self.assertEqual(plan["dispatches"][0]["context"]["content_digest"], "sha256:" + "a" * 64)

    def test_manifest_requires_content_digest(self):
        v = view([row("#7", 10)])
        manifest = {
            "schema": "ai-os-projection-manifest:v1",
            "authoritative": False,
            "repository": "owner/board",
            "generated_at": "2026-09-19T00:00:00Z",
            "tasks": [{"task": "#7", "capsule": "capsules/issue-7.json", "fingerprint": "sha256:x", "through_comment_id": 9}],
        }
        with self.assertRaisesRegex(ValueError, "incomplete context reference"):
            build_plan(v, manifest)

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
