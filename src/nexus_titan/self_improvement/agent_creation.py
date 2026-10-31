"""Governed Agent Creation Engine (ACE).

Creates declarative agent specifications and non-executable sandbox prototypes.
It deliberately does not import, execute, or dynamically register generated code.
Permanent registry promotion requires passing checks and explicit human approval.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


_ALLOWED_CAPABILITIES = {
    "research", "knowledge_ingestion", "memory_retrieval", "analysis",
    "proposal_generation", "code_review", "skill_drafting", "backtesting",
    "quality_assurance", "security_review", "coordination", "reporting",
    "market_data_analysis", "options_analysis", "crypto_analysis",
}
_ALLOWED_TOOLS = {
    "approved_research_sources", "knowledge_base_read", "learning_memory_read",
    "learning_memory_propose", "backtest_runner", "walk_forward_runner",
    "static_ast_checker", "test_runner", "red_team_policy_checker",
    "proposal_store", "report_writer", "agent_status_read",
}
_PROTECTED_CAPABILITIES = {
    "broker_order", "live_trading", "risk_limit_write", "permission_admin",
    "credential_access", "arbitrary_network", "shell_execution", "filesystem_write",
    "dynamic_code_execution", "self_deploy",
}
_AGENT_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


@dataclass(frozen=True)
class AgentSpecification:
    agent_id: str
    name: str
    purpose: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    coordination_with: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    version: int = 1


@dataclass(frozen=True)
class AgentCreationRecord:
    creation_id: str
    agent_id: str
    specification: Mapping[str, Any]
    prototype: Mapping[str, Any]
    status: str
    checks: Mapping[str, Any]
    created_at: str
    reviewed_by: str | None = None


class AgentCreationEngine:
    """Builds, tests, and governs declarative specialist-agent prototypes."""

    def __init__(self, db_path: str | Path = "data/titan_learning.db",
                 existing_agent_ids: tuple[str, ...] = ()) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.existing_agent_ids = set(existing_agent_ids)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_creation_records (
                creation_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL,
                specification_json TEXT NOT NULL, prototype_json TEXT NOT NULL,
                status TEXT NOT NULL, checks_json TEXT NOT NULL,
                created_at TEXT NOT NULL, reviewed_by TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS permanent_agent_registry (
                agent_id TEXT PRIMARY KEY, specification_json TEXT NOT NULL,
                version INTEGER NOT NULL, approved_by TEXT NOT NULL,
                approved_at TEXT NOT NULL, creation_id TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                details_json TEXT NOT NULL, created_at TEXT NOT NULL)""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _normalize(raw: Mapping[str, Any]) -> AgentSpecification:
        required = ("agent_id", "name", "purpose", "capabilities", "tools",
                    "inputs", "outputs", "coordination_with", "acceptance_criteria")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError("Missing agent specification fields: " + ", ".join(missing))
        def strings(key: str) -> tuple[str, ...]:
            value = raw[key]
            if not isinstance(value, (list, tuple)) or not value:
                raise ValueError(f"{key} must be a non-empty list.")
            items = tuple(str(x).strip() for x in value)
            if any(not x or len(x) > 160 for x in items) or len(set(items)) != len(items):
                raise ValueError(f"{key} contains blank, oversized, or duplicate values.")
            return items
        spec = AgentSpecification(
            agent_id=str(raw["agent_id"]).strip().upper(),
            name=str(raw["name"]).strip(), purpose=str(raw["purpose"]).strip(),
            capabilities=strings("capabilities"), tools=strings("tools"),
            inputs=strings("inputs"), outputs=strings("outputs"),
            coordination_with=tuple(str(x).strip().upper() for x in raw["coordination_with"]),
            acceptance_criteria=strings("acceptance_criteria"),
            version=int(raw.get("version", 1)),
        )
        if not _AGENT_ID.fullmatch(spec.agent_id):
            raise ValueError("agent_id must be 3-64 uppercase letters, digits, or underscores.")
        if not spec.name or len(spec.name) > 100 or not spec.purpose or len(spec.purpose) > 1000:
            raise ValueError("Agent name/purpose is blank or exceeds its size limit.")
        if spec.version < 1:
            raise ValueError("version must be positive.")
        forbidden = set(spec.capabilities) & _PROTECTED_CAPABILITIES
        if forbidden:
            raise PermissionError("Protected capabilities are never grantable: " + ", ".join(sorted(forbidden)))
        unknown_caps = set(spec.capabilities) - _ALLOWED_CAPABILITIES
        unknown_tools = set(spec.tools) - _ALLOWED_TOOLS
        if unknown_caps or unknown_tools:
            raise PermissionError(
                "Unapproved capability/tool: " + ", ".join(sorted(unknown_caps | unknown_tools)))
        return spec

    def create_prototype(self, raw_spec: Mapping[str, Any]) -> AgentCreationRecord:
        spec = self._normalize(raw_spec)
        if spec.agent_id in self.existing_agent_ids:
            raise ValueError("Agent ID already exists in the active specialist roster.")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM permanent_agent_registry WHERE agent_id=?",
                          (spec.agent_id,)).fetchone():
                raise ValueError("Agent ID already exists in the permanent registry.")
            if db.execute("SELECT 1 FROM agent_creation_records WHERE agent_id=? AND status <> 'REJECTED'",
                          (spec.agent_id,)).fetchone():
                raise ValueError("An active proposal already uses this agent ID.")
        prototype = {
            "kind": "declarative_non_executable_prototype",
            "agent_id": spec.agent_id,
            "workflow": ["validate_input", "invoke_allowlisted_tools", "validate_output", "emit_audit_event"],
            "tool_calls_are_simulated": True,
            "code_generated_or_executed": False,
            "runtime_registration": False,
        }
        with self._connect() as db:
            registered_ids = {row[0] for row in db.execute(
                "SELECT agent_id FROM permanent_agent_registry").fetchall()}
        known_agents = self.existing_agent_ids | registered_ids
        checks = self._run_checks(spec, prototype, known_agents)
        status = "SANDBOX_PASSED" if checks["all_passed"] else "SANDBOX_FAILED"
        now = datetime.now(timezone.utc).isoformat()
        record = AgentCreationRecord(str(uuid.uuid4()), spec.agent_id, asdict(spec),
                                     prototype, status, checks, now)
        with self._connect() as db:
            db.execute("INSERT INTO agent_creation_records VALUES(?,?,?,?,?,?,?,?)", (
                record.creation_id, record.agent_id,
                json.dumps(record.specification, sort_keys=True),
                json.dumps(record.prototype, sort_keys=True), record.status,
                json.dumps(record.checks, sort_keys=True), record.created_at, None))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                ("AGENT_PROTOTYPE_CREATED", "agent", record.agent_id,
                 json.dumps({"creation_id": record.creation_id, "status": status}, sort_keys=True), now))
        return record

    def _run_checks(self, spec: AgentSpecification, prototype: Mapping[str, Any],
                    known_agent_ids: set[str] | None = None) -> dict[str, Any]:
        checks = {
            "specification_schema": bool(spec.agent_id and spec.name and spec.purpose),
            "capabilities_allowlisted": set(spec.capabilities) <= _ALLOWED_CAPABILITIES,
            "tools_allowlisted": set(spec.tools) <= _ALLOWED_TOOLS,
            "coordination_targets_known": all(
                target in (known_agent_ids if known_agent_ids is not None else self.existing_agent_ids)
                or target == "EVOLUTION_MANAGER" for target in spec.coordination_with),
            "acceptance_criteria_defined": len(spec.acceptance_criteria) >= 1,
            "prototype_non_executable": prototype.get("code_generated_or_executed") is False,
            "no_runtime_registration": prototype.get("runtime_registration") is False,
            "no_protected_permissions": not (set(spec.capabilities) & _PROTECTED_CAPABILITIES),
        }
        checks["all_passed"] = all(checks.values())
        return checks

    def get_record(self, creation_id: str) -> AgentCreationRecord:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_creation_records WHERE creation_id=?",
                             (creation_id,)).fetchone()
        if not row:
            raise ValueError("Unknown agent creation record.")
        return AgentCreationRecord(row[0], row[1], json.loads(row[2]), json.loads(row[3]),
                                   row[4], json.loads(row[5]), row[6], row[7])

    def review_and_register(self, creation_id: str, *, approved: bool,
                            approved_by: str) -> AgentCreationRecord:
        if not isinstance(approved, bool) or not approved_by.strip():
            raise ValueError("Explicit approval decision and named human approver are required.")
        record = self.get_record(creation_id)
        if record.status != "SANDBOX_PASSED":
            raise ValueError("Only sandbox-passed proposals can be reviewed for registration.")
        now = datetime.now(timezone.utc).isoformat()
        new_status = "APPROVED_REGISTERED" if approved else "REJECTED"
        with self._connect() as db:
            if approved:
                db.execute("INSERT INTO permanent_agent_registry VALUES(?,?,?,?,?,?)", (
                    record.agent_id, json.dumps(record.specification, sort_keys=True),
                    int(record.specification["version"]), approved_by.strip(), now, creation_id))
            db.execute("UPDATE agent_creation_records SET status=?, reviewed_by=? WHERE creation_id=?",
                       (new_status, approved_by.strip(), creation_id))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                ("AGENT_HUMAN_REVIEW", "agent", record.agent_id,
                 json.dumps({"status": new_status, "approved_by": approved_by.strip()}, sort_keys=True), now))
        return self.get_record(creation_id)

    def list_registry(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT agent_id,specification_json,version,approved_by,approved_at "
                              "FROM permanent_agent_registry ORDER BY agent_id").fetchall()
        return [{"agent_id": r[0], "specification": json.loads(r[1]), "version": r[2],
                 "approved_by": r[3], "approved_at": r[4]} for r in rows]
