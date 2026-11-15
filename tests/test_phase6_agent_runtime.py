"""Focused integration tests for Phase 6 ACE and Agent Runtime."""
import tempfile
import unittest
from pathlib import Path

from nexus_titan.self_improvement import (
    AgentCreationEngine,
    AgentRuntime,
    AgentRuntimeError,
    AgentWorkflowCoordinator,
)


class Phase6AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "phase6.db"
        self.ace = AgentCreationEngine(
            self.db_path,
            existing_agent_ids=("EVOLUTION_MANAGER", "QUALITY_ASSURANCE"),
        )
        self.runtime = AgentRuntime(self.db_path)

    def tearDown(self):
        self.temp.cleanup()

    def _approve(self, agent_id="RESEARCH_SPECIALIST", tools=None):
        tools = tools or ["approved_research_sources", "report_writer"]
        record = self.ace.create_prototype({
            "agent_id": agent_id,
            "name": agent_id.replace("_", " ").title(),
            "purpose": "Run an approved specialist workflow and return evidence.",
            "capabilities": ["research", "analysis", "reporting"],
            "tools": tools,
            "inputs": ["approved_input"],
            "outputs": ["verified_report"],
            "coordination_with": ["EVOLUTION_MANAGER"],
            "acceptance_criteria": ["Output is JSON-safe and traceable."],
        })
        self.assertEqual(record.status, "SANDBOX_PASSED")
        self.ace.review_and_register(
            record.creation_id, approved=True, approved_by="Test Owner"
        )

    def test_ace_creates_non_executable_prototype(self):
        record = self.ace.create_prototype({
            "agent_id": "VOLATILITY_RESEARCH",
            "name": "Volatility Research",
            "purpose": "Research market regimes.",
            "capabilities": ["research", "analysis"],
            "tools": ["approved_research_sources"],
            "inputs": ["market_data"],
            "outputs": ["research_report"],
            "coordination_with": ["EVOLUTION_MANAGER"],
            "acceptance_criteria": ["Findings are evidence-backed."],
        })
        self.assertTrue(record.checks["all_passed"])
        self.assertFalse(record.prototype["code_generated_or_executed"])
        self.assertFalse(record.prototype["runtime_registration"])
        self.assertEqual(self.ace.list_registry(), [])

    def test_ace_rejects_protected_capability(self):
        with self.assertRaises(PermissionError):
            self.ace.create_prototype({
                "agent_id": "UNSAFE_AGENT",
                "name": "Unsafe Agent",
                "purpose": "Attempt unsafe capability.",
                "capabilities": ["analysis", "live_trading"],
                "tools": ["report_writer"],
                "inputs": ["input"],
                "outputs": ["output"],
                "coordination_with": ["EVOLUTION_MANAGER"],
                "acceptance_criteria": ["Must not pass."],
            })

    def test_ace_requires_human_approval_before_registry(self):
        record = self.ace.create_prototype({
            "agent_id": "HUMAN_REVIEW_AGENT",
            "name": "Human Review Agent",
            "purpose": "Wait for explicit approval.",
            "capabilities": ["analysis"],
            "tools": ["report_writer"],
            "inputs": ["input"],
            "outputs": ["output"],
            "coordination_with": ["EVOLUTION_MANAGER"],
            "acceptance_criteria": ["Approval is explicit."],
        })
        self.assertEqual(self.ace.list_registry(), [])
        approved = self.ace.review_and_register(
            record.creation_id, approved=True, approved_by="Test Owner"
        )
        self.assertEqual(approved.status, "APPROVED_REGISTERED")
        self.assertEqual(self.ace.list_registry()[0]["approved_by"], "Test Owner")

    def test_runtime_executes_only_registered_adapter(self):
        self._approve()
        self.runtime.register_tool(
            "approved_research_sources",
            lambda args, ctx: {"query": args["query"], "agent": ctx.agent_id},
        )
        task_id = self.runtime.submit_task(
            "RESEARCH_SPECIALIST",
            {"topic": "volatility"},
            [{"tool": "approved_research_sources", "args": {"query": "volatility"}}],
        )
        result = self.runtime.run_task(task_id)
        self.assertEqual(result.status, "COMPLETED")
        output = result.output["tool_outputs"]["0:approved_research_sources"]
        self.assertEqual(output["agent"], "RESEARCH_SPECIALIST")

    def test_runtime_rejects_unapproved_agent_and_tool_escalation(self):
        with self.assertRaises(AgentRuntimeError):
            self.runtime.submit_task(
                "UNKNOWN_AGENT", {}, [{"tool": "report_writer", "args": {}}]
            )
        self._approve(tools=["approved_research_sources"])
        self.runtime.register_tool("report_writer", lambda args, ctx: {"ok": True})
        with self.assertRaises(AgentRuntimeError):
            self.runtime.submit_task(
                "RESEARCH_SPECIALIST", {},
                [{"tool": "report_writer", "args": {}}],
            )

    def test_runtime_blocks_protected_tool_registration(self):
        with self.assertRaises(AgentRuntimeError):
            self.runtime.register_tool("shell_execution", lambda args, ctx: {})

    def test_idempotency_prevents_duplicate_execution(self):
        self._approve()
        calls = {"count": 0}

        def handler(args, ctx):
            calls["count"] += 1
            return {"count": calls["count"]}

        self.runtime.register_tool("report_writer", handler)
        payload = [{"tool": "report_writer", "args": {}}]
        first = self.runtime.submit_task(
            "RESEARCH_SPECIALIST", {}, payload, idempotency_key="same-key"
        )
        second = self.runtime.submit_task(
            "RESEARCH_SPECIALIST", {}, payload, idempotency_key="same-key"
        )
        self.assertEqual(first, second)
        self.runtime.run_task(first)
        self.runtime.run_task(second)
        self.assertEqual(calls["count"], 1)

    def test_workflow_passes_dependency_output_to_downstream_agent(self):
        self._approve("RESEARCH_SPECIALIST", ["approved_research_sources"])
        self._approve("QA_SPECIALIST", ["test_runner"])
        self.runtime.register_tool(
            "approved_research_sources", lambda args, ctx: {"evidence": "source-A"}
        )
        self.runtime.register_tool(
            "test_runner",
            lambda args, ctx: {
                "received": ctx.dependency_outputs["research"]["tool_outputs"]
                ["0:approved_research_sources"]["evidence"]
            },
        )
        result = AgentWorkflowCoordinator(self.runtime).execute_workflow(
            [
                {
                    "task_id": "research",
                    "agent_id": "RESEARCH_SPECIALIST",
                    "inputs": {},
                    "tool_calls": [
                        {"tool": "approved_research_sources", "args": {}}
                    ],
                },
                {
                    "task_id": "qa",
                    "agent_id": "QA_SPECIALIST",
                    "depends_on": ["research"],
                    "inputs": {},
                    "tool_calls": [{"tool": "test_runner", "args": {}}],
                },
            ],
            workflow_id="phase6-test-flow",
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(
            result["results"]["qa"]["output"]["tool_outputs"]
            ["0:test_runner"]["received"],
            "source-A",
        )
        self.assertEqual(len(self.runtime.inbox("QA_SPECIALIST")), 1)

    def test_workflow_rejects_dependency_cycles(self):
        with self.assertRaises(AgentRuntimeError):
            AgentWorkflowCoordinator._topological_order(
                [
                    {"task_id": "a", "depends_on": ["b"]},
                    {"task_id": "b", "depends_on": ["a"]},
                ]
            )

    def test_runtime_rejects_excessive_tool_calls_and_oversized_json(self):
        self._approve()
        self.runtime.register_tool("report_writer", lambda args, ctx: {"ok": True})
        many_calls = [
            {"tool": "report_writer", "args": {}} for _ in range(21)
        ]
        with self.assertRaises(AgentRuntimeError):
            self.runtime.submit_task("RESEARCH_SPECIALIST", {}, many_calls)
        with self.assertRaises(AgentRuntimeError):
            self.runtime.submit_task(
                "RESEARCH_SPECIALIST", {"payload": "x" * 1_000_001},
                [{"tool": "report_writer", "args": {}}],
            )

    def test_non_json_tool_output_fails_safely(self):
        self._approve()
        self.runtime.register_tool("report_writer", lambda args, ctx: object())
        task_id = self.runtime.submit_task(
            "RESEARCH_SPECIALIST", {},
            [{"tool": "report_writer", "args": {}}],
        )
        self.assertEqual(self.runtime.run_task(task_id).status, "FAILED")

    def test_interrupted_running_tasks_fail_closed(self):
        self._approve()
        self.runtime.register_tool("report_writer", lambda args, ctx: {"ok": True})
        task_id = self.runtime.submit_task(
            "RESEARCH_SPECIALIST", {},
            [{"tool": "report_writer", "args": {}}],
        )
        with self.runtime._connect() as db:
            db.execute(
                "UPDATE runtime_tasks SET status='RUNNING' WHERE task_id=?",
                (task_id,),
            )
        self.assertEqual(self.runtime.recover_interrupted_tasks(), 1)
        self.assertEqual(self.runtime.get_task(task_id).status, "FAILED")


if __name__ == "__main__":
    unittest.main()
