"""Controlled runtime and collaboration layer for human-approved TITAN agents.

Only declarative specifications present in the permanent ACE registry can run.
Agents can invoke only pre-registered, allowlisted Python adapters. Generated code
is never imported or executed. Tasks are persisted, idempotent, auditable and
coordinated through explicit dependencies and an append-only message inbox.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .agent_creation import _ALLOWED_TOOLS, _PROTECTED_CAPABILITIES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _json_safe(value: Any) -> Any:
    """Round-trip bounded JSON data; reject objects, NaN/Infinity and oversized payloads."""
    encoded = _json(value)
    if len(encoded.encode("utf-8")) > 1_000_000:
        raise AgentRuntimeError("Task/tool JSON payload exceeds the 1 MB safety limit.")
    return json.loads(encoded)


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    handler: Callable[[Mapping[str, Any], "ToolExecutionContext"], Any]
    retry_safe: bool = False
    max_attempts: int = 1


@dataclass(frozen=True)
class ToolExecutionContext:
    task_id: str
    agent_id: str
    inputs: Mapping[str, Any]
    dependency_outputs: Mapping[str, Any]
    prior_tool_outputs: Mapping[str, Any]


@dataclass(frozen=True)
class RuntimeTaskResult:
    task_id: str
    agent_id: str
    status: str
    output: Mapping[str, Any]
    error: str | None
    attempts: int
    duration_ms: float
    created_at: str
    updated_at: str


class AgentRuntimeError(RuntimeError):
    """Raised for rejected or invalid runtime operations."""


class AgentRuntime:
    """Run approved ACE agents through trusted tool adapters only."""

    def __init__(self, db_path: str | Path = "data/titan_learning.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._tools: dict[str, RegisteredTool] = {}
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runtime_tasks (
                    task_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE,
                    workflow_id TEXT, agent_id TEXT NOT NULL,
                    input_json TEXT NOT NULL, calls_json TEXT NOT NULL,
                    status TEXT NOT NULL, output_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    duration_ms REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_agent_status
                    ON runtime_tasks(agent_id,status);
                CREATE TABLE IF NOT EXISTS runtime_task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL, event TEXT NOT NULL,
                    details_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_messages (
                    message_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL,
                    from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
                    task_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, consumed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox
                    ON agent_messages(to_agent,consumed_at,created_at);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=15000")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def register_tool(self, name: str,
                      handler: Callable[[Mapping[str, Any], ToolExecutionContext], Any],
                      *, retry_safe: bool = False, max_attempts: int = 1) -> None:
        """Register a trusted adapter. This registers host code, not agent code."""
        if name not in _ALLOWED_TOOLS or name in _PROTECTED_CAPABILITIES:
            raise AgentRuntimeError(f"Tool is not in the runtime allowlist: {name}")
        if not callable(handler):
            raise AgentRuntimeError("Tool handler must be callable.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
            raise AgentRuntimeError("max_attempts must be an integer from 1 to 3.")
        self._tools[name] = RegisteredTool(name, handler, bool(retry_safe), max_attempts)

    def _approved_spec(self, agent_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT specification_json FROM permanent_agent_registry WHERE agent_id=?",
                (agent_id,)).fetchone()
        if row is None:
            raise AgentRuntimeError("Agent is not present in the human-approved permanent registry.")
        try:
            spec = json.loads(row["specification_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentRuntimeError("Approved agent specification is invalid.") from exc
        if not isinstance(spec, dict) or spec.get("agent_id") != agent_id:
            raise AgentRuntimeError("Approved agent registry entry failed integrity validation.")
        if set(spec.get("capabilities", [])) & _PROTECTED_CAPABILITIES:
            raise AgentRuntimeError("Agent specification contains protected capabilities.")
        if not set(spec.get("tools", [])) <= _ALLOWED_TOOLS:
            raise AgentRuntimeError("Agent specification includes an unapproved tool.")
        return spec

    def submit_task(self, agent_id: str, inputs: Mapping[str, Any],
                    tool_calls: Sequence[Mapping[str, Any]], *,
                    idempotency_key: str | None = None,
                    workflow_id: str | None = None) -> str:
        """Persist a task. No tool is invoked until run_task is explicitly called."""
        if not isinstance(inputs, Mapping):
            raise AgentRuntimeError("Task inputs must be a mapping.")
        if not isinstance(tool_calls, (list, tuple)) or not tool_calls:
            raise AgentRuntimeError("At least one tool call is required.")
        if len(tool_calls) > 20:
            raise AgentRuntimeError("A task may contain at most 20 tool calls.")
        normalized_inputs = _json_safe(dict(inputs))
        spec = self._approved_spec(agent_id)
        calls: list[dict[str, Any]] = []
        permitted = set(spec.get("tools", []))
        for call in tool_calls:
            if not isinstance(call, Mapping) or set(call) - {"tool", "args"}:
                raise AgentRuntimeError("Each tool call must contain only 'tool' and 'args'.")
            tool = call.get("tool")
            args = call.get("args", {})
            if not isinstance(tool, str) or tool not in permitted:
                raise AgentRuntimeError(f"Agent did not receive permission for tool: {tool}")
            if tool not in self._tools:
                raise AgentRuntimeError(f"No trusted runtime adapter is registered for tool: {tool}")
            if not isinstance(args, Mapping):
                raise AgentRuntimeError("Tool arguments must be a mapping.")
            calls.append({"tool": tool, "args": _json_safe(dict(args))})
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
                raise AgentRuntimeError("idempotency_key must be a non-empty string up to 200 characters.")
        task_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as db:
            if idempotency_key:
                existing = db.execute("SELECT task_id FROM runtime_tasks WHERE idempotency_key=?",
                                       (idempotency_key,)).fetchone()
                if existing:
                    return str(existing["task_id"])
            db.execute("""INSERT INTO runtime_tasks
                (task_id,idempotency_key,workflow_id,agent_id,input_json,calls_json,status,
                 output_json,error,attempts,duration_ms,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'PENDING','{}',NULL,0,0,?,?)""",
                (task_id, idempotency_key, workflow_id, agent_id, _json(normalized_inputs),
                 _json(calls), now, now))
            self._event(db, task_id, "TASK_SUBMITTED", {"agent_id": agent_id, "call_count": len(calls)})
        return task_id

    @staticmethod
    def _event(db: sqlite3.Connection, task_id: str, event: str, details: Mapping[str, Any]) -> None:
        db.execute("INSERT INTO runtime_task_events(task_id,event,details_json,created_at) VALUES(?,?,?,?)",
                   (task_id, event, _json(dict(details)), _now()))

    def run_task(self, task_id: str,
                 dependency_outputs: Mapping[str, Any] | None = None) -> RuntimeTaskResult:
        """Run one task. Completed idempotent tasks are returned without re-execution."""
        with self._lock:
            with self._connect() as db:
                row = db.execute("SELECT * FROM runtime_tasks WHERE task_id=?", (task_id,)).fetchone()
                if row is None:
                    raise AgentRuntimeError("Unknown runtime task.")
                if row["status"] == "COMPLETED":
                    return self._to_result(row)
                if row["status"] in {"FAILED", "BLOCKED"}:
                    return self._to_result(row)
                if row["status"] == "RUNNING":
                    raise AgentRuntimeError("Task is already running; duplicate execution is blocked.")
                agent_id = row["agent_id"]
                inputs = json.loads(row["input_json"])
                calls = json.loads(row["calls_json"])
                db.execute("UPDATE runtime_tasks SET status='RUNNING',updated_at=? WHERE task_id=?",
                           (_now(), task_id))
                self._event(db, task_id, "TASK_STARTED", {"agent_id": agent_id})
            started = time.perf_counter()
            prior_outputs: dict[str, Any] = {}
            total_attempts = 0
            try:
                # Re-check approval at execution time; revocation blocks queued tasks.
                spec = self._approved_spec(agent_id)
                permitted = set(spec.get("tools", []))
                for index, call in enumerate(calls):
                    tool_def = self._tools.get(call["tool"])
                    if tool_def is None or call["tool"] not in permitted:
                        raise AgentRuntimeError("Runtime tool permission changed after task submission.")
                    context = ToolExecutionContext(task_id, agent_id, inputs,
                                                   _json_safe(dict(dependency_outputs or {})),
                                                   _json_safe(dict(prior_outputs)))
                    attempts = 0
                    while True:
                        attempts += 1
                        total_attempts += 1
                        try:
                            result = tool_def.handler(call["args"], context)
                            prior_outputs[f"{index}:{call['tool']}"] = _json_safe(result)
                            break
                        except Exception:
                            if not tool_def.retry_safe or attempts >= tool_def.max_attempts:
                                raise
                            time.sleep(min(0.05 * (2 ** (attempts - 1)), 0.2))
                output = {"tool_outputs": prior_outputs,
                          "dependency_outputs_received": sorted((dependency_outputs or {}).keys()),
                          "agent_id": agent_id}
                duration = round((time.perf_counter() - started) * 1000, 3)
                self._finish(task_id, "COMPLETED", output, None, total_attempts, duration)
            except Exception as exc:
                duration = round((time.perf_counter() - started) * 1000, 3)
                error = f"{type(exc).__name__}: {str(exc)[:500]}"
                self._finish(task_id, "FAILED", {}, error, total_attempts, duration)
            return self.get_task(task_id)

    def _finish(self, task_id: str, status: str, output: Mapping[str, Any],
                error: str | None, attempts: int, duration: float) -> None:
        with self._connect() as db:
            db.execute("""UPDATE runtime_tasks SET status=?,output_json=?,error=?,attempts=?,
                duration_ms=?,updated_at=? WHERE task_id=?""",
                (status, _json(dict(output)), error, attempts, duration, _now(), task_id))
            self._event(db, task_id, "TASK_" + status,
                        {"attempts": attempts, "duration_ms": duration, "error": error})

    @staticmethod
    def _to_result(row: sqlite3.Row) -> RuntimeTaskResult:
        return RuntimeTaskResult(row["task_id"], row["agent_id"], row["status"],
                                 json.loads(row["output_json"]), row["error"],
                                 int(row["attempts"]), float(row["duration_ms"]),
                                 row["created_at"], row["updated_at"])

    def get_task(self, task_id: str) -> RuntimeTaskResult:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runtime_tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise AgentRuntimeError("Unknown runtime task.")
        return self._to_result(row)

    def pending_task_ids(self, *, limit: int = 20) -> list[str]:
        """List durable PENDING tasks in FIFO order for a local worker loop."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise AgentRuntimeError("Pending-task limit must be between 1 and 100.")
        with self._connect() as db:
            rows = db.execute("SELECT task_id FROM runtime_tasks WHERE status='PENDING' "
                              "ORDER BY created_at,task_id LIMIT ?", (limit,)).fetchall()
        return [str(row["task_id"]) for row in rows]

    def run_pending(self, *, limit: int = 10) -> list[RuntimeTaskResult]:
        """Execute a bounded batch of queued tasks; crashed RUNNING tasks are not replayed."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise AgentRuntimeError("Worker batch limit must be between 1 and 50.")
        return [self.run_task(task_id) for task_id in self.pending_task_ids(limit=limit)]

    def metrics(self) -> dict[str, Any]:
        """Return measured task success/failure and latency per approved agent."""
        with self._connect() as db:
            rows = db.execute("""SELECT agent_id,COUNT(*) AS total,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed,
                AVG(CASE WHEN status IN ('COMPLETED','FAILED') THEN duration_ms END) AS avg_ms,
                SUM(attempts) AS attempts FROM runtime_tasks GROUP BY agent_id ORDER BY agent_id""").fetchall()
        agents = {}
        for row in rows:
            total, completed, failed = int(row["total"]), int(row["completed"] or 0), int(row["failed"] or 0)
            agents[row["agent_id"]] = {
                "total_tasks": total, "completed": completed, "failed": failed,
                "success_rate_pct": round(completed / (completed + failed) * 100, 2) if completed + failed else None,
                "average_duration_ms": round(float(row["avg_ms"] or 0), 3),
                "tool_attempts": int(row["attempts"] or 0),
            }
        return {"agents": agents, "overall": {
            "total_tasks": sum(v["total_tasks"] for v in agents.values()),
            "completed": sum(v["completed"] for v in agents.values()),
            "failed": sum(v["failed"] for v in agents.values()),
        }}

    def inbox(self, agent_id: str, *, limit: int = 100, consume: bool = False) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise AgentRuntimeError("Inbox limit must be between 1 and 500.")
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM agent_messages WHERE to_agent=? AND consumed_at IS NULL
                ORDER BY created_at,message_id LIMIT ?""", (agent_id, limit)).fetchall()
            messages = [{"message_id": r["message_id"], "workflow_id": r["workflow_id"],
                         "from_agent": r["from_agent"], "to_agent": r["to_agent"],
                         "task_id": r["task_id"], "payload": json.loads(r["payload_json"]),
                         "created_at": r["created_at"]} for r in rows]
            if consume and messages:
                db.executemany("UPDATE agent_messages SET consumed_at=? WHERE message_id=?",
                               [(_now(), m["message_id"]) for m in messages])
        return messages

    def task_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT event,details_json,created_at FROM runtime_task_events "
                              "WHERE task_id=? ORDER BY event_id", (task_id,)).fetchall()
        return [{"event": r["event"], "details": json.loads(r["details_json"]),
                 "created_at": r["created_at"]} for r in rows]

    def recover_interrupted_tasks(self) -> int:
        """Fail stale RUNNING tasks closed; never replay possibly non-idempotent calls."""
        with self._connect() as db:
            rows = db.execute("SELECT task_id FROM runtime_tasks WHERE status='RUNNING'").fetchall()
            for row in rows:
                db.execute("UPDATE runtime_tasks SET status='FAILED',error=?,updated_at=? WHERE task_id=?",
                           ("AgentRuntimeError: Interrupted task not auto-replayed; manual review required.",
                            _now(), row["task_id"]))
                self._event(db, row["task_id"], "TASK_INTERRUPTED_FAIL_CLOSED", {})
        return len(rows)


class AgentWorkflowCoordinator:
    """Execute a dependency graph and pass verified outputs to downstream agents."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    @staticmethod
    def _topological_order(tasks: Sequence[Mapping[str, Any]]) -> list[str]:
        ids = [str(task.get("task_id", "")).strip() for task in tasks]
        if not ids or any(not item for item in ids) or len(set(ids)) != len(ids):
            raise AgentRuntimeError("Workflow must have unique, non-empty task_id values.")
        known = set(ids)
        if any(not isinstance(t.get("depends_on", []), (list, tuple, set))
               for t in tasks):
            raise AgentRuntimeError("depends_on must be a list of task IDs.")
        deps = {str(t["task_id"]): set(t.get("depends_on", [])) for t in tasks}
        if any(dep not in known for values in deps.values() for dep in values):
            raise AgentRuntimeError("Workflow references an unknown dependency.")
        ordered: list[str] = []
        pending = {key: set(value) for key, value in deps.items()}
        while pending:
            ready = sorted(key for key, value in pending.items() if not value)
            if not ready:
                raise AgentRuntimeError("Workflow contains a dependency cycle.")
            for key in ready:
                ordered.append(key)
                pending.pop(key)
            for value in pending.values():
                value.difference_update(ready)
        return ordered

    def execute_workflow(self, tasks: Sequence[Mapping[str, Any]], *,
                         workflow_id: str | None = None) -> dict[str, Any]:
        if len(tasks) > 100:
            raise AgentRuntimeError("A workflow may contain at most 100 tasks.")
        order = self._topological_order(tasks)
        workflow_id = workflow_id or str(uuid.uuid4())
        if not isinstance(workflow_id, str) or not workflow_id.strip() or len(workflow_id) > 200:
            raise AgentRuntimeError("workflow_id must be a non-empty string up to 200 characters.")
        by_id = {str(t["task_id"]): t for t in tasks}
        results: dict[str, RuntimeTaskResult] = {}
        blocked: list[str] = []
        for node_id in order:
            task = by_id[node_id]
            deps = list(task.get("depends_on", []))
            if any(d in blocked or d not in results or results[d].status != "COMPLETED" for d in deps):
                blocked.append(node_id)
                continue
            dependency_outputs = {d: dict(results[d].output) for d in deps}
            payload = dict(task.get("inputs", {}))
            payload["dependency_outputs"] = dependency_outputs
            task_id = self.runtime.submit_task(
                str(task["agent_id"]), payload, task.get("tool_calls", []),
                idempotency_key=f"{workflow_id}:{node_id}", workflow_id=workflow_id)
            result = self.runtime.run_task(task_id, dependency_outputs)
            results[node_id] = result
            for downstream in tasks:
                if node_id in downstream.get("depends_on", []):
                    with self.runtime._connect() as db:
                        db.execute("""INSERT INTO agent_messages
                            (message_id,workflow_id,from_agent,to_agent,task_id,payload_json,created_at)
                            VALUES(?,?,?,?,?,?,?)""",
                            (str(uuid.uuid4()), workflow_id, result.agent_id,
                             str(downstream["agent_id"]), task_id,
                             _json({"status": result.status, "output": result.output,
                                    "error": result.error}), _now()))
        return {"workflow_id": workflow_id, "order": order,
                "results": {key: asdict(value) for key, value in results.items()},
                "blocked_tasks": blocked,
                "status": "COMPLETED" if not blocked and all(r.status == "COMPLETED" for r in results.values()) else "PARTIAL_OR_FAILED"}


def register_core_local_tools(runtime: AgentRuntime, engine: Any) -> list[str]:
    """Register safe local adapters backed by TITAN's existing learning services.

    Network access, broker actions, shell execution, arbitrary file writes and
    test/backtest subprocesses are intentionally not registered by default.
    """
    from .agents import DEFAULT_SPECIALIST_AGENTS

    def _read_memory(args: Mapping[str, Any], context: ToolExecutionContext) -> Any:
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 10))
        if not query:
            raise ValueError("query is required")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        return [{"learning_id": item.learning_id, "topic": item.topic,
                 "content": item.content, "source": item.source,
                 "confidence": item.confidence, "evidence": item.evidence}
                for item in engine.store.search_learnings(query, limit=limit)]

    def _propose_learning(args: Mapping[str, Any], context: ToolExecutionContext) -> Any:
        required = ("topic", "content", "source", "evidence")
        if any(not str(args.get(key, "")).strip() for key in required):
            raise ValueError("topic, content, source and evidence are required")
        record = engine.learn(topic=str(args["topic"]), content=str(args["content"]),
            source=f"agent:{context.agent_id}:{args['source']}", evidence=str(args["evidence"]),
            confidence=float(args.get("confidence", 0.5)),
            tags=tuple(str(x) for x in args.get("tags", ["agent-runtime"])))
        return {"learning_id": record.learning_id, "status": "RECORDED", "topic": record.topic}

    def _proposal(args: Mapping[str, Any], context: ToolExecutionContext) -> Any:
        required = ("title", "description", "rationale", "expected_benefit")
        if any(not str(args.get(key, "")).strip() for key in required):
            raise ValueError("title, description, rationale and expected_benefit are required")
        proposal = engine.propose_improvement(
            title=str(args["title"]), description=str(args["description"]),
            rationale=str(args["rationale"]), expected_benefit=str(args["expected_benefit"]),
            risk_level=str(args.get("risk_level", "MEDIUM")))
        return {"proposal_id": proposal.proposal_id, "status": proposal.status,
                "risk_level": proposal.risk_level}

    def _agent_status(args: Mapping[str, Any], context: ToolExecutionContext) -> Any:
        return [{"agent_id": agent.agent_id, "purpose": agent.purpose}
                for agent in DEFAULT_SPECIALIST_AGENTS]

    def _report(args: Mapping[str, Any], context: ToolExecutionContext) -> Any:
        title = str(args.get("title", "")).strip()
        if not title:
            raise ValueError("report title is required")
        body = args.get("body", {})
        if not isinstance(body, Mapping):
            raise ValueError("report body must be a JSON object")
        # Returned in the task artefact only; never writes to an arbitrary path.
        return {"title": title, "body": _json_safe(dict(body)),
                "dependency_outputs": _json_safe(dict(context.dependency_outputs)),
                "created_by": context.agent_id, "task_id": context.task_id}

    adapters: dict[str, Callable[[Mapping[str, Any], ToolExecutionContext], Any]] = {
        "knowledge_base_read": _read_memory,
        "learning_memory_read": _read_memory,
        "learning_memory_propose": _propose_learning,
        "proposal_store": _proposal,
        "agent_status_read": _agent_status,
        "report_writer": _report,
    }
    for name, handler in adapters.items():
        runtime.register_tool(name, handler)
    return list(adapters)
