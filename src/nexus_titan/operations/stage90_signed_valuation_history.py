"""Stage90 read-only, locally attested SYNTHETIC option MTM history.

No journal write, new account/position balance, real-market evidence, independent
signer, live order, or approved performance promotion is provided here.
The local test issuer can attest a historical snapshot; only a full independent
journal replay could prove historical source completeness to a third party.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import re

from nexus_titan.operations.fo_risk_boundary import SyntheticFORiskBoundary, _json
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage83LocalSyntheticLedgerSnapshot,
)
from nexus_titan.operations.synthetic_option_positions import (
    SyntheticMTMReport, SyntheticOptionQuote, value_positions,
)

_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ZERO = "0" * 64
_DOMAIN = "STAGE90_LOCAL_SYNTHETIC_MTM_HISTORY_V1"


class Stage90HistoryBlocked(PermissionError):
    """A read-only history does not satisfy conservative synthetic QA."""


def _hex(value):
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _int(value, *, positive=False):
    return type(value) is int and (value > 0 if positive else value >= 0)


def _payload(snapshot, valuation, quotes, preceding_sha256):
    return _json([
        _DOMAIN, asdict(snapshot), asdict(valuation),
        [asdict(q) for q in quotes], preceding_sha256,
    ]).encode("utf-8")


@dataclass(frozen=True, slots=True)
class Stage90ValuationCheckpoint:
    snapshot: Stage83LocalSyntheticLedgerSnapshot
    valuation: SyntheticMTMReport
    quotes: tuple[SyntheticOptionQuote, ...]
    preceding_sha256: str
    record_sha256: str
    signature_hex: str
    synthetic_only: bool = True
    independent_market_evidence: bool = False


@dataclass(frozen=True, slots=True)
class Stage90ValuationHistoryAudit:
    account_id: str
    ledger_scope_sha256: str
    checkpoint_count: int
    first_epoch: int | None
    last_epoch: int | None
    last_journal_revision: int | None
    last_journal_tip: str | None
    last_checkpoint_sha256: str
    exploratory_synthetic_drawdown_percent: float | None
    eligible_for_exploratory_synthetic_drawdown: bool
    profit_factor: None = None
    expectancy_cents: None = None
    real_market_evidence_verified: bool = False
    independently_replayed_historical_journal: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "SYNTHETIC_HISTORY_ONLY_REAL_FO_SHADOW_NO_GO"


def _verify_single(boundary, checkpoint):
    if not isinstance(boundary, SyntheticFORiskBoundary) or not isinstance(checkpoint, Stage90ValuationCheckpoint):
        raise Stage90HistoryBlocked("Typed local history checkpoint and boundary required")
    c = checkpoint
    if (c.synthetic_only is not True or c.independent_market_evidence is not False
            or not all(_hex(x) for x in (c.preceding_sha256,c.record_sha256,c.signature_hex))
            or not isinstance(c.snapshot, Stage83LocalSyntheticLedgerSnapshot)
            or not isinstance(c.valuation,SyntheticMTMReport)
            or type(c.quotes) is not tuple or len(c.quotes)>500):
        raise Stage90HistoryBlocked("Invalid or misleading history attestation")
    s,v = c.snapshot,c.valuation
    if (s.local_integrity_verified is not True
            or s.cross_ledger_authority_verified is not False
            or s.real_market_data_authenticated is not False
            or s.live_trading_enabled is not False or s.paper_order_authorized is not False
            or s.broker_orders_transmitted != 0
            or v.synthetic_only is not True or v.market_evidence_verified is not False
            or v.live_trading_enabled is not False
            or not _hex(s.ledger_scope_sha256) or not _hex(s.journal_tip)
            or not _int(s.journal_revision) or not _int(s.risk_revision)
            or not _int(s.initial_cents,positive=True) or not _int(s.cash_cents)
            or not _int(s.reserved_cents) or s.reserved_cents>s.cash_cents
            or s.available_cents != s.cash_cents-s.reserved_cents
            or s.initial_cents+s.exit_proceeds_cents != s.cash_cents+s.paid_notional_cents+s.paid_fees_cents
            or s.cash_cents+s.remaining_cost_basis_cents != s.initial_cents+s.realized_net_pnl_cents
            or s.account_id != v.account_id or s.journal_revision != v.journal_revision
            or s.journal_tip != v.journal_sha256):
        raise Stage90HistoryBlocked("Historical ledger provenance or accounting mismatch")
    try:
        expected=value_positions(boundary,s,c.quotes,now_epoch=v.valuation_epoch)
        if asdict(expected)!=asdict(v):
            raise Stage90HistoryBlocked("Historical valuation is not reproducible from signed quotes")
        payload=_payload(s,v,c.quotes,c.preceding_sha256)
        digest=hashlib.sha256(payload).hexdigest()
        signature=hmac.new(boundary.verification_key,
                           _DOMAIN.encode()+b":" + bytes.fromhex(digest),hashlib.sha256).hexdigest()
    except (ValueError,TypeError,OverflowError) as exc:
        raise Stage90HistoryBlocked("Invalid historical valuation payload") from exc
    if (not hmac.compare_digest(digest,c.record_sha256)
            or not hmac.compare_digest(signature,c.signature_hex)):
        raise Stage90HistoryBlocked("Historical snapshot/quote chain signature mismatch")
    return s,v


def capture_stage90_checkpoint(book, boundary, *, issuer_key, quotes, previous=None):
    """Attest a single coherent live *synthetic* ledger read; never persist it.

    The caller must separately protect/checkpoint these objects. Same-process
    HMAC possession is not an operator signature or proof of actual NSE data.
    """
    if (not isinstance(book,Stage55IsolatedSyntheticExecutionBook)
            or not isinstance(boundary,SyntheticFORiskBoundary)
            or not isinstance(issuer_key,bytes) or len(issuer_key)<32
            or not hmac.compare_digest(issuer_key,boundary.verification_key)
            or book.selected_fo_boundary_sha256!=boundary.digest):
        raise Stage90HistoryBlocked("Selected book and matching local test issuer required")
    prior=_ZERO
    if previous is not None:
        ps,pv=_verify_single(boundary,previous)
        prior=previous.record_sha256
    snapshot,valuation=book.synthetic_valued_snapshot(quotes)
    if previous is not None:
        if (snapshot.account_id!=ps.account_id or snapshot.ledger_scope_sha256!=ps.ledger_scope_sha256
                or snapshot.initial_cents!=ps.initial_cents
                or valuation.valuation_epoch<=pv.valuation_epoch
                or snapshot.journal_revision<ps.journal_revision
                or snapshot.risk_revision<ps.risk_revision
                or (snapshot.journal_revision==ps.journal_revision
                    and snapshot.journal_tip!=ps.journal_tip)):
            raise Stage90HistoryBlocked("Nonmonotone or cross-account checkpoint")
    body=_payload(snapshot,valuation,quotes,prior)
    digest=hashlib.sha256(body).hexdigest()
    signature=hmac.new(issuer_key,_DOMAIN.encode()+b":" + bytes.fromhex(digest),hashlib.sha256).hexdigest()
    mark=Stage90ValuationCheckpoint(snapshot,valuation,quotes,prior,digest,signature)
    _verify_single(boundary,mark)
    return mark


def inspect_stage90_history(boundary, checkpoints, *, current_snapshot=None,
                            max_gap_seconds=300, min_marks=3, min_span_seconds=2):
    """Fail closed on holes/forgery; only exploratory *synthetic* drawdown is eligible.

    History is locally attested, not proof of a complete historical event chain.
    If a current snapshot is passed the final mark must be its exact journal head.
    """
    if (type(checkpoints) is not tuple or len(checkpoints)>512
            or not _int(max_gap_seconds,positive=True)
            or not _int(min_marks,positive=True)
            or not _int(min_span_seconds,positive=True)
            or min_marks>512 or not isinstance(boundary,SyntheticFORiskBoundary)):
        raise Stage90HistoryBlocked("Bounded explicit signed valuation history required")
    if not checkpoints:
        return Stage90ValuationHistoryAudit("", "", 0, None, None, None, None,
                                            _ZERO,None,False)
    head=_ZERO
    account=scope=None
    first_epoch=last_epoch=None
    old_revision=old_tip=old_risk=old_quote_epoch=None
    capital=None
    peak=None
    max_dd=0.0
    for c in checkpoints:
        s,v=_verify_single(boundary,c)
        if c.preceding_sha256!=head:
            raise Stage90HistoryBlocked("Missing, reordered or forked attestation")
        if account is None:
            account,scope,capital=s.account_id,s.ledger_scope_sha256,s.initial_cents
            first_epoch=v.valuation_epoch
        elif account!=s.account_id or scope!=s.ledger_scope_sha256 or capital!=s.initial_cents:
            raise Stage90HistoryBlocked("Mixed account, scope or initial capital in history")
        if old_revision is not None:
            if (v.valuation_epoch<=last_epoch or v.valuation_epoch-last_epoch>max_gap_seconds
                    or s.journal_revision<old_revision or s.risk_revision<old_risk
                    or (s.journal_revision==old_revision and s.journal_tip!=old_tip)):
                raise Stage90HistoryBlocked("History time gap, reversal or journal fork")
        if v.quote_epoch is not None:
            if old_quote_epoch is not None and v.quote_epoch<=old_quote_epoch:
                raise Stage90HistoryBlocked("Repeated/backdated synthetic market quote")
            old_quote_epoch=v.quote_epoch
        if not _int(v.total_hypothetical_equity_cents,positive=True):
            raise Stage90HistoryBlocked("Nonpositive synthetic valuation equity")
        peak=v.total_hypothetical_equity_cents if peak is None else max(peak,v.total_hypothetical_equity_cents)
        max_dd=max(max_dd,100.0*(peak-v.total_hypothetical_equity_cents)/peak)
        head=c.record_sha256
        last_epoch=v.valuation_epoch
        old_revision,old_tip,old_risk=s.journal_revision,s.journal_tip,s.risk_revision
    if current_snapshot is not None:
        if (not isinstance(current_snapshot,Stage83LocalSyntheticLedgerSnapshot)
                or current_snapshot.local_integrity_verified is not True
                or current_snapshot.account_id!=account
                or current_snapshot.ledger_scope_sha256!=scope
                or current_snapshot.journal_revision!=old_revision
                or current_snapshot.journal_tip!=old_tip
                or current_snapshot.risk_revision!=old_risk):
            raise Stage90HistoryBlocked("Final synthetic valuation not anchored to current ledger head")
    eligible=len(checkpoints)>=min_marks and last_epoch-first_epoch>=min_span_seconds
    return Stage90ValuationHistoryAudit(
        account,scope,len(checkpoints),first_epoch,last_epoch,old_revision,old_tip,
        head,round(max_dd,8) if eligible else None,eligible,
    )
