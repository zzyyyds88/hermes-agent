"""Owner-poll completion suppression.

A spawning session that polls a process AFTER it exited already has the completion
inline. The gateway watcher must not inject a second completion turn for it (the
a duplicate "old receipt" turn). A poll from any other session
only observes and must stay non-consuming.
"""

import time
import unittest

from tools.process_registry import ProcessRegistry, ProcessSession


def _exited_session(session_id: str, parent_session_id: str) -> ProcessSession:
    return ProcessSession(
        id=session_id,
        command="echo done",
        task_id="t1",
        started_at=time.time(),
        exited=True,
        exit_code=0,
        output_buffer="done\n",
        parent_session_id=parent_session_id,
    )


class OwnerPollCompletionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ProcessRegistry()

    def test_owner_poll_marks_completion_observed(self) -> None:
        session = _exited_session("proc_owner", "sess-parent")
        self.registry._finished[session.id] = session

        self.assertFalse(self.registry.is_completion_observed(session.id))
        self.registry.poll(session.id, observer_session_id="sess-parent")

        self.assertTrue(self.registry.is_completion_observed(session.id))
        self.assertIn(session.id, self.registry._poll_observed)
        self.assertIn(session.id, self.registry._poll_observed_by_parent)

    def test_foreign_poll_stays_non_consuming(self) -> None:
        session = _exited_session("proc_foreign", "sess-parent")
        self.registry._finished[session.id] = session

        self.registry.poll(session.id, observer_session_id="sess-other")

        self.assertFalse(self.registry.is_completion_observed(session.id))
        self.assertIn(session.id, self.registry._poll_observed)
        self.assertNotIn(session.id, self.registry._poll_observed_by_parent)

    def test_poll_without_observer_stays_non_consuming(self) -> None:
        session = _exited_session("proc_anonymous", "sess-parent")
        self.registry._finished[session.id] = session

        self.registry.poll(session.id)

        self.assertFalse(self.registry.is_completion_observed(session.id))

    def test_wait_log_consumption_still_observed(self) -> None:
        session = _exited_session("proc_waited", "sess-parent")
        self.registry._finished[session.id] = session
        self.registry._completion_consumed.add(session.id)

        self.assertTrue(self.registry.is_completion_observed(session.id))

    def test_prune_drops_owner_poll_marks(self) -> None:
        self.registry._poll_observed_by_parent.add("proc_gone")

        self.registry._prune_if_needed()

        self.assertNotIn("proc_gone", self.registry._poll_observed_by_parent)

    def test_process_manage_forwards_caller_session(self) -> None:
        from unittest.mock import patch
        from tools import process_registry as pr_mod

        captured: dict[str, str] = {}

        def fake_poll(session_id: str, *, observer_session_id: str = "") -> dict:
            captured["session_id"] = session_id
            captured["observer_session_id"] = observer_session_id
            return {"status": "exited", "session_id": session_id}

        with patch.object(pr_mod.process_registry, "poll", side_effect=fake_poll):
            pr_mod._handle_process(
                {"action": "poll", "session_id": "proc_x"},
                session_id="sess-parent",
                task_id="t1",
            )

        self.assertEqual(captured, {"session_id": "proc_x", "observer_session_id": "sess-parent"})


if __name__ == "__main__":
    unittest.main()
