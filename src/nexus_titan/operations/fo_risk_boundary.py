"""Mandatory risk checks for a selected local synthetic F&O SQLite account.

The test control plane owns the HMAC key. Key possession is not human identity
or process isolation. No permission here applies to real markets or other books.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import hmac
import json
import re

from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76UntrustedRiskTelemetry,
    inspect_stage76_fo_portfolio_risk,
)
from nexus_titan.shadow.stage75_fo_shadow_readiness import Stage75FOShadowReadinessPacket

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)


class SyntheticFORiskBlocked(PermissionError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticFOOperation:
    kind: str
    operation_id: str
    order_id: str
    symbol: str = ""
    quantity: int = 0
    price_cents: int = 0
    fee_cents: int = 0
    fee_buffer_cents: int = 0

    def __post_init__(self):
        if self.kind not in ("OPEN", "FILL", "CANCEL") or any(
            not isinstance(x, str) or not _ID.fullmatch(x)
            for x in (self.operation_id, self.order_id)
        ):
            raise SyntheticFORiskBlocked("Invalid synthetic operation identity")
        values = (self.quantity, self.price_cents, self.fee_cents, self.fee_buffer_cents)
        if any(type(x) is not int or not 0 <= x <= 10**14 for x in values):
            raise SyntheticFORiskBlocked("Invalid operation amounts")
        if self.kind == "OPEN":
            if (self.operation_id != self.order_id or self.quantity < 1
                    or self.price_cents < 1 or self.fee_cents != 0
                    or not isinstance(self.symbol, str) or not self.symbol):
                raise SyntheticFORiskBlocked("Invalid synthetic opening declaration")
        elif self.symbol or self.fee_buffer_cents or (
            self.kind == "FILL" and (self.quantity < 1 or self.price_cents < 1)
        ) or (self.kind == "CANCEL" and any(values)):
            raise SyntheticFORiskBlocked("Invalid synthetic lifecycle declaration")

    @property
    def digest(self):
        return _sha(asdict(self))


@dataclass(frozen=True, slots=True)
class SyntheticFOInstrument:
    underlying: str
    symbol: str
    quantity: int
    lot_size: int
    tick_cents: int
    limit_price_cents: int
    fee_buffer_cents: int
    observed_epoch: int
    expiry_epoch: int
    research_packet_sha256: str


@dataclass(frozen=True, slots=True)
class SyntheticFORiskPermit:
    boundary_sha256: str
    ledger_scope_sha256: str
    operation_sha256: str
    book_revision: int
    journal_tip: str
    risk_revision: int
    issued_epoch: int
    expires_epoch: int
    telemetry: Stage76UntrustedRiskTelemetry
    signature_hex: str = ""

    def payload(self):
        result = asdict(self)
        result.pop("signature_hex")
        return result

    def encode(self):
        return _json(asdict(self))

    @classmethod
    def decode(cls, raw):
        if not isinstance(raw, str) or len(raw) > 8192:
            raise SyntheticFORiskBlocked("Invalid persisted risk permit")
        try:
            body = json.loads(raw)
            body["telemetry"] = Stage76UntrustedRiskTelemetry(**body["telemetry"])
            value = cls(**body)
            if value.encode() != raw:
                raise ValueError("Noncanonical risk permit")
            return value
        except (TypeError, KeyError, ValueError) as exc:
            raise SyntheticFORiskBlocked("Malformed persisted risk permit") from exc


@dataclass(frozen=True, slots=True)
class SyntheticFORiskBoundary:
    packets: tuple[Stage75FOShadowReadinessPacket, ...]
    instruments: tuple[SyntheticFOInstrument, ...]
    policy: Stage76FOResearchPolicy
    verification_key: bytes = field(repr=False)
    max_data_age_seconds: int = 30
    permit_ttl_seconds: int = 10

    def __post_init__(self):
        if (type(self.verification_key) is not bytes or len(self.verification_key) < 32
                or not isinstance(self.policy, Stage76FOResearchPolicy)
                or type(self.max_data_age_seconds) is not int
                or not 1 <= self.max_data_age_seconds <= 300
                or type(self.permit_ttl_seconds) is not int
                or not 1 <= self.permit_ttl_seconds <= 30
                or not isinstance(self.packets, tuple) or not self.packets
                or not isinstance(self.instruments, tuple)
                or len(self.instruments) != len(self.packets)):
            raise SyntheticFORiskBlocked("Explicit bounded synthetic risk configuration required")
        accounts = {p.account_id for p in self.packets if isinstance(p, Stage75FOShadowReadinessPacket)}
        if len(accounts) != 1 or any(not isinstance(p, Stage75FOShadowReadinessPacket) for p in self.packets):
            raise SyntheticFORiskBlocked("One F&O account required")
        seen = set()
        for spec in self.instruments:
            if not isinstance(spec, SyntheticFOInstrument):
                raise SyntheticFORiskBlocked("Typed synthetic contract required")
            packets = [p for p in self.packets if p.research_packet_sha256 == spec.research_packet_sha256]
            if len(packets) != 1:
                raise SyntheticFORiskBlocked("Unmatched or duplicate research binding")
            p = packets[0]
            numbers = (spec.quantity, spec.lot_size, spec.tick_cents, spec.limit_price_cents,
                       spec.observed_epoch, spec.expiry_epoch)
            if (spec.symbol in seen or spec.underlying not in ("NIFTY", "BANKNIFTY")
                    or spec.symbol != p.option_symbol or spec.underlying != p.underlying
                    or any(type(x) is not int or not 1 <= x <= 10**12 for x in numbers)
                    or not 1 <= spec.lot_size <= 500 or spec.quantity > 10000
                    or spec.quantity % spec.lot_size or spec.limit_price_cents % spec.tick_cents
                    or type(spec.fee_buffer_cents) is not int or spec.fee_buffer_cents < 0
                    or spec.expiry_epoch <= spec.observed_epoch
                    or spec.quantity * spec.limit_price_cents + spec.fee_buffer_cents
                       != p.long_option_entry_debit_cents):
                raise SyntheticFORiskBlocked("Invalid synthetic contract/lot/tick/debit binding")
            seen.add(spec.symbol)
        # Validate all packet arithmetic and no-authority flags at configuration.
        telemetry = Stage76UntrustedRiskTelemetry(next(iter(accounts)), 0, 0, 0, False, True)
        if not inspect_stage76_fo_portfolio_risk(
            packets=self.packets, policy=self.policy, telemetry=telemetry,
        ).local_research_fence_passed:
            raise SyntheticFORiskBlocked("Research configuration fails Risk & Veto")

    @property
    def digest(self):
        return _sha({"schema": "SYNTHETIC_FO_BOUNDARY_V1",
                     "packets": [asdict(p) for p in self.packets],
                     "instruments": [asdict(s) for s in self.instruments],
                     "policy": asdict(self.policy),
                     "key_sha256": hashlib.sha256(self.verification_key).hexdigest(),
                     "data_age": self.max_data_age_seconds, "ttl": self.permit_ttl_seconds})

    def review(self, operation, telemetry, now_epoch, stopped, order_symbols):
        if stopped:
            raise SyntheticFORiskBlocked("Local kill switch veto")
        if type(now_epoch) is not int or now_epoch < 1:
            raise SyntheticFORiskBlocked("Trusted synthetic clock unavailable")
        review = inspect_stage76_fo_portfolio_risk(
            packets=self.packets, policy=self.policy, telemetry=telemetry,
        )
        if not review.local_research_fence_passed:
            raise SyntheticFORiskBlocked("Risk & Veto denied synthetic action")
        if operation.kind not in ("OPEN", "FILL"):
            raise SyntheticFORiskBlocked("Risk permits only cover synthetic OPEN/FILL")
        symbol = operation.symbol if operation.kind == "OPEN" else order_symbols.get(operation.order_id)
        specs = [s for s in self.instruments if s.symbol == symbol]
        if len(specs) != 1:
            raise SyntheticFORiskBlocked("Instrument outside selected F&O boundary")
        spec = specs[0]
        if not spec.observed_epoch <= now_epoch <= spec.observed_epoch + self.max_data_age_seconds:
            raise SyntheticFORiskBlocked("Stale or future F&O data")
        if now_epoch >= spec.expiry_epoch - 1800:
            raise SyntheticFORiskBlocked("Expiry risk veto")
        if operation.kind == "OPEN" and (
            operation.quantity != spec.quantity or operation.price_cents != spec.limit_price_cents
            or operation.fee_buffer_cents != spec.fee_buffer_cents
        ):
            raise SyntheticFORiskBlocked("Synthetic order differs from reviewed contract/debit")
        if operation.price_cents > spec.limit_price_cents or operation.price_cents % spec.tick_cents:
            raise SyntheticFORiskBlocked("Synthetic fill price or tick veto")

    def verify(self, permit, operation, *, scope, revision, tip, risk_revision, now_epoch):
        if not isinstance(permit, SyntheticFORiskPermit):
            raise SyntheticFORiskBlocked("Mandatory signed synthetic risk permit missing")
        ints = (permit.book_revision, permit.risk_revision, permit.issued_epoch, permit.expires_epoch)
        if (any(type(x) is not int or x < 0 for x in ints)
                or permit.boundary_sha256 != self.digest or permit.ledger_scope_sha256 != scope
                or permit.operation_sha256 != operation.digest
                or permit.book_revision != revision or permit.journal_tip != tip
                or permit.risk_revision != risk_revision
                or not permit.issued_epoch <= now_epoch < permit.expires_epoch
                or permit.expires_epoch - permit.issued_epoch != self.permit_ttl_seconds):
            raise SyntheticFORiskBlocked("Stale or mismatched synthetic risk permit")
        expected = hmac.new(self.verification_key, _json(permit.payload()).encode(), hashlib.sha256).hexdigest()
        if not isinstance(permit.signature_hex, str) or not hmac.compare_digest(expected, permit.signature_hex):
            raise SyntheticFORiskBlocked("Invalid synthetic risk signature")

    def position_contract(self, symbol):
        """Full identity for the pinned long CE/PE, not just a display symbol."""
        specs=[s for s in self.instruments if s.symbol==symbol]
        packets=[p for p in self.packets if p.option_symbol==symbol]
        if len(specs)!=1 or len(packets)!=1 or packets[0].selected_option_type not in ('CE','PE'):
            raise SyntheticFORiskBlocked('Unknown selected long-option contract')
        s,p=specs[0],packets[0]
        identity={'underlying':s.underlying,'symbol':symbol,'option_type':p.selected_option_type,
                  'strike':p.selected_strike,'expiry_epoch':s.expiry_epoch,'lot_size':s.lot_size,
                  'tick_cents':s.tick_cents,'research_packet_sha256':s.research_packet_sha256}
        return {**identity,'contract_sha256':_sha(['STAGE89_CONTRACT_V1',identity])}


class SyntheticFORiskAuthority:
    """Privileged LOCAL TEST harness; never inject this into order clients/EVOLVE."""

    def __init__(self, signing_key: bytes):
        if type(signing_key) is not bytes or len(signing_key) < 32:
            raise SyntheticFORiskBlocked("Independent synthetic test signing key required")
        self._key = signing_key

    def issue(self, boundary, *, operation, snapshot, telemetry, now_epoch):
        if not isinstance(boundary, SyntheticFORiskBoundary) or not isinstance(operation, SyntheticFOOperation):
            raise SyntheticFORiskBlocked("Typed boundary and operation required")
        if not hmac.compare_digest(self._key, boundary.verification_key):
            raise SyntheticFORiskBlocked("Risk signer does not match pinned boundary")
        boundary.review(operation, telemetry, now_epoch, snapshot.kill_switch_active,
                        {o.order_id: o.symbol for o in snapshot.orders})
        permit = SyntheticFORiskPermit(
            boundary.digest, snapshot.ledger_scope_sha256, operation.digest,
            snapshot.journal_revision, snapshot.journal_tip, snapshot.risk_revision,
            now_epoch, now_epoch + boundary.permit_ttl_seconds, telemetry,
        )
        return replace(permit, signature_hex=hmac.new(
            self._key, _json(permit.payload()).encode(), hashlib.sha256,
        ).hexdigest())

    def issue_quote(self, boundary, **kwargs):
        from nexus_titan.operations.synthetic_option_positions import issue_quote
        return issue_quote(self._key,boundary,**kwargs)

    def issue_close(self, boundary, **kwargs):
        from nexus_titan.operations.synthetic_option_positions import issue_close
        return issue_close(self._key,boundary,**kwargs)
