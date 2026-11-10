"""TITAN ADVISOR: transparent, evidence-gated, non-executing 'best use of me' suggestions.

Provides actionable suggestions only; no autonomous browsing, broker routing, spend,
security control edits or unverified statements about available capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3


@dataclass(frozen=True, slots=True)
class AdvisorContext:
    goal: str = "improve_trading_research"
    guardian_tested: bool = False
    ci_verified: bool = False
    market_data_verified: bool = False
    fo_engine_verified: bool = False
    oos_verified: bool = False
    risk_veto_verified: bool = False
    learning_evidence_count: int = 0
    champion_challenger_verified: bool = False
    phone_first: bool = True

    def __post_init__(self) -> None:
        if self.goal != "improve_trading_research":
            raise ValueError("only the existing trading-research scope is supported")
        if isinstance(self.learning_evidence_count, bool) or not isinstance(self.learning_evidence_count, int) or not 0 <= self.learning_evidence_count <= 1_000_000:
            raise ValueError("invalid evidence count")
        for key in ("guardian_tested", "ci_verified", "market_data_verified", "fo_engine_verified",
                    "oos_verified", "risk_veto_verified", "champion_challenger_verified", "phone_first"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be explicit bool")


@dataclass(frozen=True, slots=True)
class AdvisorSuggestion:
    suggestion_id: str
    title: str
    i_can_help_by: str
    improvement_goal: str
    why_now: str
    next_step: str
    urgency: str
    needs_user_approval: bool = True
    estimated_gain_verified: bool = False
    order_or_code_executed: bool = False


def _suggest(key: str, title: str, help_text: str, outcome: str, reason: str, action: str, urgency: str) -> AdvisorSuggestion:
    return AdvisorSuggestion(hashlib.sha256(key.encode()).hexdigest()[:16], title, help_text, outcome, reason, action, urgency)


def recommend_best_use(context: AdvisorContext, *, max_items: int = 5) -> tuple[AdvisorSuggestion, ...]:
    """Explains what to do next, with meaningful user action; never claims ROI."""
    if not isinstance(context, AdvisorContext):
        raise TypeError("AdvisorContext required")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or not 1 <= max_items <= 8:
        raise ValueError("max_items must be 1..8")
    ideas: list[AdvisorSuggestion] = []
    if not context.guardian_tested:
        ideas.append(_suggest("guardian", "Crash recovery test", "मैं offline research job के crash/restart checkpoints को test कर सकता हूँ।",
            "Data loss और unsafe recovery के खतरे पहचानना", "Guardian की end-to-end crash proof उपलब्ध नहीं है।",
            "Replit की अलग test copy में forced-crash और SQLite recovery tests चलाने की अनुमति दें।", "P0"))
    if not context.ci_verified:
        ideas.append(_suggest("ci", "Verify latest code & CI", "मैं latest offline archive और GitHub feature branch का diff तथा tests audit करने में मदद कर सकता हूँ।",
            "Broken updates और hidden regression रोकना", "Latest offline stages की remote CI verification pending है।",
            "Exact feature branch पर 3-version CI, secret scan और full tests verify करें।", "P0"))
    if not context.risk_veto_verified:
        ideas.append(_suggest("risk", "Independent Risk & Veto audit", "मैं bad-data, unauthorized promotion और crash scenarios पर risk tests तैयार कर सकता हूँ।",
            "Unexpected trading authority रोकना", "Risk gateway की runtime independence को प्रमाणित करना बाकी है।",
            "Safe paper-only sandbox में veto/restart failure tests की approval दें।", "P0"))
    if not context.market_data_verified:
        ideas.append(_suggest("data", "Authenticate F&O market data", "मैं NSE contract dates, data provenance, missing bars और lookahead checks का QA कर सकता हूँ।",
            "Backtest की evidence quality बढ़ाना", "Source authenticity और licensed data coverage verified नहीं है।",
            "Licensed historical sample या official contract specification दें; पहले read-only validation करेंगे।", "P0"))
    if not context.fo_engine_verified:
        ideas.append(_suggest("fo", "Test multi-leg F&O lifecycle", "मैं partial fills, margin stress और expiry settlement के offline regression scenarios बना सकता हूँ।",
            "F&O accounting और risk correctness बेहतर करना", "Complete exchange-specific options lifecycle proof अधूरा है।",
            "Verified contract specs के बाद isolated scenarios पर run करें।", "P1"))
    if context.learning_evidence_count == 0:
        ideas.append(_suggest("learn", "Teach TITAN from authorized material", "आप transcript/PDF excerpt देंगे तो मैं source citations के साथ research notes organize कर सकता हूँ।",
            "नई trading hypotheses का documented research pool बनाना", "अभी source-linked educational evidence दर्ज नहीं है।",
            "कोई अपना PDF summary, permitted video transcript या authorized course notes दें।", "P1"))
    elif not context.oos_verified:
        ideas.append(_suggest("oos", "Test learned ideas fairly", "मैं source-linked strategy ideas को baseline के मुकाबले OOS evaluation के लिए structure कर सकता हूँ।",
            "Misleading win rates और overfitting पहचानना", "Learning sources हैं, लेकिन true out-of-sample evidence verified नहीं।",
            "Hypothesis rules स्पष्ट करके licensed data पर purged walk-forward test करें।", "P1"))
    if not context.champion_challenger_verified:
        ideas.append(_suggest("evolve", "Controlled strategy evolution", "मैं मौजूदा strategy और challengers की evaluation checklist व्यवस्थित कर सकता हूँ।",
            "कमजोर variants reject करने के लिए traceable evidence", "Unsupervised promotion की अनुमति नहीं है।",
            "Champion/Challenger को separate research sandbox में evidence-gated रखें।", "P1"))
    if context.phone_first:
        ideas.append(_suggest("phone", "Phone-friendly research workload", "मैं heavy backtests को bounded offline batches में व्यवस्थित कर सकता हूँ।",
            "Dashboard response और device resources सुरक्षित रखना", "Phone/Replit-first workflow में always-on heavy workloads risky हैं।",
            "Research worker के RAM/time limits तय करके batch jobs schedule करें।", "P2"))
    urgency_order = {"P0": 0, "P1": 1, "P2": 2}
    return tuple(sorted(ideas, key=lambda item: urgency_order[item.urgency])[:max_items])


class AdvisorFeedbackLedger:
    """Stores operator decisions, without changing AI models or trading permissions."""

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(str(path), timeout=5)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("""CREATE TABLE IF NOT EXISTS titan_advice_feedback (
                suggestion_id TEXT PRIMARY KEY, decision TEXT NOT NULL, note TEXT NOT NULL,
                CHECK(decision IN ('INTERESTED','DISMISSED','COMPLETED'))
            )""")
            self.db.commit()
        except BaseException:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def record(self, suggestion: AdvisorSuggestion, *, decision: str, note: str = "") -> None:
        if not isinstance(suggestion, AdvisorSuggestion):
            raise TypeError("suggestion required")
        if decision not in {"INTERESTED", "DISMISSED", "COMPLETED"}:
            raise ValueError("unknown decision")
        if not isinstance(note, str) or len(note) > 250:
            raise ValueError("note exceeds safe limit")
        with self.db:
            self.db.execute("""INSERT INTO titan_advice_feedback VALUES(?,?,?)
                ON CONFLICT(suggestion_id) DO UPDATE SET decision=excluded.decision, note=excluded.note""",
                (suggestion.suggestion_id, decision, note))

    def get(self, suggestion_id: str) -> tuple[str, str] | None:
        return self.db.execute("SELECT decision,note FROM titan_advice_feedback WHERE suggestion_id=?", (suggestion_id,)).fetchone()


def recommend_with_feedback(context: AdvisorContext, ledger: AdvisorFeedbackLedger, *,
                            max_items: int = 5) -> tuple[AdvisorSuggestion, ...]:
    """Prioritize accepted advice and avoid repeating dismissed advice (no AI mutation)."""
    if not isinstance(ledger, AdvisorFeedbackLedger):
        raise TypeError('AdvisorFeedbackLedger required')
    proposals = recommend_best_use(context, max_items=8)
    allowed = [x for x in proposals if (ledger.get(x.suggestion_id) or ('', ''))[0] != 'DISMISSED']
    allowed.sort(key=lambda x: (0 if (ledger.get(x.suggestion_id) or ('', ''))[0] == 'INTERESTED' else 1,
                                {'P0':0,'P1':1,'P2':2}[x.urgency]))
    if isinstance(max_items, bool) or not isinstance(max_items, int) or not 1 <= max_items <= 8:
        raise ValueError('invalid max_items')
    return tuple(allowed[:max_items])
