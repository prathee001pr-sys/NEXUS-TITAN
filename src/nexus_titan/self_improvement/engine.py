"""Governed, local-first continuous learning and self-improvement foundation.

This module stores knowledge, research proposals, experiment evidence and versioned
skill metadata. It deliberately does NOT execute generated code, alter risk limits,
change permissions, or deploy changes without explicit human approval.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    return value.strip()


def _confidence(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("confidence must be a finite number between 0 and 1.")
    return float(value)


@dataclass(frozen=True)
class LearningRecord:
    learning_id: str
    topic: str
    content: str
    source: str
    learned_at: str
    confidence: float
    evidence: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImprovementProposal:
    proposal_id: str
    title: str
    description: str
    rationale: str
    expected_benefit: str
    risk_level: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    proposal_id: str
    baseline_metric: float
    candidate_metric: float
    metric_name: str
    sample_size: int
    out_of_sample: bool
    safety_checks_passed: bool
    result: str
    recorded_at: str


@dataclass(frozen=True)
class SkillVersion:
    skill_id: str
    name: str
    version: int
    description: str
    instructions: str
    status: str
    approved_by: str
    created_at: str


class LearningStore:
    """SQLite persistence for learning artefacts and an append-only audit trail."""

    def __init__(self, db_path: str | Path = "data/titan_learning.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS learnings (
                    learning_id TEXT PRIMARY KEY, topic TEXT NOT NULL, content TEXT NOT NULL,
                    source TEXT NOT NULL, learned_at TEXT NOT NULL, confidence REAL NOT NULL,
                    evidence TEXT NOT NULL, tags_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    rationale TEXT NOT NULL, expected_benefit TEXT NOT NULL, risk_level TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, approved_by TEXT
                );
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(proposal_id),
                    baseline_metric REAL NOT NULL, candidate_metric REAL NOT NULL, metric_name TEXT NOT NULL,
                    sample_size INTEGER NOT NULL, out_of_sample INTEGER NOT NULL,
                    safety_checks_passed INTEGER NOT NULL, result TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL,
                    description TEXT NOT NULL, instructions TEXT NOT NULL, status TEXT NOT NULL,
                    approved_by TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(skill_id, version)
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_regime_evidence (
                    observation_id TEXT PRIMARY KEY, strategy_key TEXT NOT NULL, regime TEXT NOT NULL,
                    observations INTEGER NOT NULL, net_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL, sharpe_ratio REAL, source TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS code_change_proposals (
                    change_id TEXT PRIMARY KEY, relative_path TEXT NOT NULL, rationale TEXT NOT NULL,
                    base_sha256 TEXT NOT NULL, candidate_sha256 TEXT NOT NULL, candidate_source TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, reviewed_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_learnings_topic ON learnings(topic);
                CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
                CREATE INDEX IF NOT EXISTS idx_strategy_regime ON strategy_regime_evidence(strategy_key, regime);
                CREATE INDEX IF NOT EXISTS idx_code_proposal_status ON code_change_proposals(status);
            """)

    def audit(self, event: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       (event, entity_type, entity_id, json.dumps(details, sort_keys=True), _now()))

    def add_learning(self, record: LearningRecord) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO learnings VALUES(?,?,?,?,?,?,?,?)", (
                record.learning_id, record.topic, record.content, record.source, record.learned_at,
                record.confidence, record.evidence, json.dumps(record.tags)))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       ("LEARNING_RECORDED", "learning", record.learning_id,
                        json.dumps({"topic": record.topic, "confidence": record.confidence}), _now()))

    def list_learnings(self, topic: str | None = None, limit: int = 100) -> list[LearningRecord]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer.")
        with self._connect() as db:
            if topic:
                rows = db.execute("SELECT * FROM learnings WHERE topic=? ORDER BY learned_at DESC LIMIT ?", (topic, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM learnings ORDER BY learned_at DESC LIMIT ?", (limit,)).fetchall()
        return [LearningRecord(r["learning_id"], r["topic"], r["content"], r["source"], r["learned_at"],
                               r["confidence"], r["evidence"], tuple(json.loads(r["tags_json"]))) for r in rows]

    def search_learnings(self, query: str, limit: int = 25) -> list[LearningRecord]:
        """Simple local text retrieval across topic, content, source and tags."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer.")
        term = _required_text(query, "query").casefold()
        records = self.list_learnings(limit=max(limit, 100))
        matches = [r for r in records if term in " ".join((r.topic, r.content, r.source, *r.tags)).casefold()]
        return matches[:limit]


class TitanEvolveEngine:
    """Orchestrates evidence-based learning, experiments and human-gated promotion."""

    def __init__(self, store: LearningStore | None = None):
        self.store = store or LearningStore()

    def learn(self, topic: str, content: str, source: str, evidence: str,
              confidence: float, tags: list[str] | tuple[str, ...] = ()) -> LearningRecord:
        record = LearningRecord(str(uuid.uuid4()), _required_text(topic, "topic"),
                                _required_text(content, "content"), _required_text(source, "source"),
                                _now(), _confidence(confidence), _required_text(evidence, "evidence"),
                                tuple(_required_text(t, "tag") for t in tags))
        self.store.add_learning(record)
        return record

    def capture_post_mortem(self, report: Any) -> LearningRecord:
        """Convert an existing trade post-mortem into a traceable learning memory.

        The source report remains the evidence; the generated insight is explicitly
        labelled heuristic and is not treated as a proven trading rule.
        """
        required = ("strategy_name", "total_trades", "net_realized_pnl",
                    "primary_leakage_source", "actionable_recommendation")
        if any(not hasattr(report, field) for field in required):
            raise ValueError("report is not a compatible post-mortem report.")
        evidence = (f"Heuristic post-mortem; trades={report.total_trades}; "
                    f"net_pnl={report.net_realized_pnl}; leakage={report.primary_leakage_source}")
        return self.learn(
            topic="trade-review",
            content=(f"Strategy {report.strategy_name}: {report.actionable_recommendation}"),
            source=f"post_mortem:{report.strategy_name}",
            evidence=evidence,
            confidence=0.60,
            tags=("post-mortem", str(report.primary_leakage_source)),
        )

    def propose_improvement(self, title: str, description: str, rationale: str,
                            expected_benefit: str, risk_level: str = "MEDIUM") -> ImprovementProposal:
        risk = _required_text(risk_level, "risk_level").upper()
        if risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValueError("risk_level must be LOW, MEDIUM, HIGH, or CRITICAL.")
        proposal = ImprovementProposal(str(uuid.uuid4()), _required_text(title, "title"),
            _required_text(description, "description"), _required_text(rationale, "rationale"),
            _required_text(expected_benefit, "expected_benefit"), risk, "PROPOSED", _now())
        with self.store._connect() as db:
            db.execute("INSERT INTO proposals(proposal_id,title,description,rationale,expected_benefit,risk_level,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                       (proposal.proposal_id, proposal.title, proposal.description, proposal.rationale,
                        proposal.expected_benefit, proposal.risk_level, proposal.status, proposal.created_at))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       ("IMPROVEMENT_PROPOSED", "proposal", proposal.proposal_id,
                        json.dumps({"risk_level": risk}), _now()))
        return proposal

    def record_experiment(self, proposal_id: str, baseline_metric: float, candidate_metric: float,
                          metric_name: str, sample_size: int, out_of_sample: bool,
                          safety_checks_passed: bool, metric_direction: str = "higher") -> ExperimentResult:
        for name, value in (("baseline_metric", baseline_metric), ("candidate_metric", candidate_metric)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite.")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 1:
            raise ValueError("sample_size must be a positive integer.")
        if sample_size < 30:
            raise ValueError("At least 30 observations are required before an experiment can qualify for promotion.")
        if metric_direction not in {"higher", "lower"}:
            raise ValueError("metric_direction must be higher or lower.")
        if not isinstance(out_of_sample, bool) or not isinstance(safety_checks_passed, bool):
            raise ValueError("Validation flags must be booleans.")
        metric = _required_text(metric_name, "metric_name")
        with self.store._connect() as db:
            proposal = db.execute("SELECT status FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not proposal:
                raise ValueError("Unknown proposal_id.")
            if proposal["status"] in {"REJECTED", "PROMOTED"}:
                raise ValueError("Cannot experiment on a rejected or already promoted proposal.")
        # Direction is explicit so lower-is-better metrics (e.g. drawdown) are handled correctly.
        improved = candidate_metric > baseline_metric if metric_direction == "higher" else candidate_metric < baseline_metric
        result = "PASS" if improved and out_of_sample and safety_checks_passed else "FAIL"
        exp = ExperimentResult(str(uuid.uuid4()), proposal_id, float(baseline_metric), float(candidate_metric),
                               metric, sample_size, out_of_sample, safety_checks_passed, result, _now())
        with self.store._connect() as db:
            db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?,?)", (exp.experiment_id, exp.proposal_id,
                exp.baseline_metric, exp.candidate_metric, exp.metric_name, exp.sample_size, int(exp.out_of_sample),
                int(exp.safety_checks_passed), exp.result, exp.recorded_at))
            db.execute("UPDATE proposals SET status=? WHERE proposal_id=?", ("VALIDATED" if result == "PASS" else "EXPERIMENT_FAILED", proposal_id))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       ("EXPERIMENT_" + result, "experiment", exp.experiment_id,
                        json.dumps(asdict(exp)), _now()))
        return exp

    def approve_and_promote_skill(self, proposal_id: str, name: str, description: str,
                                  instructions: str, approved_by: str) -> SkillVersion:
        """Promote validated skill metadata only; this method never executes code."""
        approver = _required_text(approved_by, "approved_by")
        with self.store._connect() as db:
            proposal = db.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not proposal:
                raise ValueError("Unknown proposal_id.")
            if proposal["status"] != "VALIDATED":
                raise PermissionError("Promotion requires a passing out-of-sample experiment and safety checks.")
            latest = db.execute("SELECT MAX(version) AS version FROM skills WHERE skill_id=?", (proposal_id,)).fetchone()
            version = (latest["version"] or 0) + 1
            skill = SkillVersion(proposal_id, _required_text(name, "name"), version,
                                 _required_text(description, "description"),
                                 _required_text(instructions, "instructions"), "ACTIVE", approver, _now())
            db.execute("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?)", (skill.skill_id, skill.version,
                skill.name, skill.description, skill.instructions, skill.status, skill.approved_by, skill.created_at))
            db.execute("UPDATE proposals SET status='PROMOTED', approved_by=? WHERE proposal_id=?", (approver, proposal_id))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       ("SKILL_PROMOTED", "skill", skill.skill_id,
                        json.dumps({"version": version, "approved_by": approver}), _now()))
        return skill

    def rollback_skill(self, skill_id: str, target_version: int, approved_by: str) -> SkillVersion:
        """Reactivate an existing version with an explicit human operator recorded."""
        approver = _required_text(approved_by, "approved_by")
        with self.store._connect() as db:
            target = db.execute("SELECT * FROM skills WHERE skill_id=? AND version=?", (skill_id, target_version)).fetchone()
            if not target:
                raise ValueError("Target skill version does not exist.")
            db.execute("UPDATE skills SET status='ROLLED_BACK' WHERE skill_id=? AND status='ACTIVE'", (skill_id,))
            db.execute("UPDATE skills SET status='ACTIVE', approved_by=? WHERE skill_id=? AND version=?",
                       (approver, skill_id, target_version))
            db.execute("INSERT INTO audit_log(event,entity_type,entity_id,details_json,created_at) VALUES(?,?,?,?,?)",
                       ("SKILL_ROLLBACK", "skill", skill_id,
                        json.dumps({"target_version": target_version, "approved_by": approver}), _now()))
            row = db.execute("SELECT * FROM skills WHERE skill_id=? AND version=?", (skill_id, target_version)).fetchone()
        return SkillVersion(row["skill_id"], row["name"], row["version"], row["description"],
                            row["instructions"], row["status"], row["approved_by"], row["created_at"])

    def list_active_skills(self) -> list[SkillVersion]:
        with self.store._connect() as db:
            rows = db.execute("SELECT * FROM skills WHERE status='ACTIVE' ORDER BY name, version DESC").fetchall()
        return [SkillVersion(r["skill_id"], r["name"], r["version"], r["description"],
                             r["instructions"], r["status"], r["approved_by"], r["created_at"]) for r in rows]

    def create_agent_coordinator(self):
        """Return the allow-listed TITAN EVOLVE specialist-agent coordinator.

        Imported lazily to keep the core learning engine lightweight and avoid
        a module-import cycle. Agent execution remains local and supervised.
        """
        from .agents import EvolutionAgentCoordinator
        return EvolutionAgentCoordinator(self)

    def get_status(self) -> dict[str, int]:
        with self.store._connect() as db:
            return {
                "learnings": db.execute("SELECT COUNT(*) FROM learnings").fetchone()[0],
                "proposals": db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0],
                "experiments": db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0],
                "active_skills": db.execute("SELECT COUNT(*) FROM skills WHERE status='ACTIVE'").fetchone()[0],
                "pending_code_reviews": db.execute("SELECT COUNT(*) FROM code_change_proposals WHERE status='PROPOSED_FOR_REVIEW'").fetchone()[0],
                "accepted_code_proposals": db.execute("SELECT COUNT(*) FROM code_change_proposals WHERE status='ACCEPTED_FOR_MANUAL_MERGE'").fetchone()[0],
                "regime_observations": db.execute("SELECT COALESCE(SUM(observations),0) FROM strategy_regime_evidence").fetchone()[0],
            }
