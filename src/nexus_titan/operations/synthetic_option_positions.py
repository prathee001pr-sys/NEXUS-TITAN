"""Stage89 value objects, signed reduce-only evidence and read-only valuation.

There is no balance store here. The existing execution book owns all writes.
HMAC authenticates the local synthetic issuer, not a person or exchange feed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import json
import re

from nexus_titan.operations.fo_risk_boundary import SyntheticFORiskBlocked, _json

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_MAX = 900_000_000_000_000


class SyntheticPositionBlocked(SyntheticFORiskBlocked):
    """No synthetic position mutation or valuation may proceed."""


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SyntheticPositionBlocked('Invalid bounded position identifier')


def _hex(value):
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _integer(value, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= _MAX:
        raise SyntheticPositionBlocked('Invalid integer-cent amount or quantity')


def _mac(key, domain, payload):
    return hmac.new(key, _json([domain,payload]).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticCloseRequest:
    operation_id: str
    order_id: str
    symbol: str
    contract_sha256: str
    quantity: int
    price_cents: int
    fee_cents: int
    side: str = 'SELL_TO_CLOSE'

    def __post_init__(self):
        for value in (self.operation_id,self.order_id,self.symbol):
            _identifier(value)
        for value in (self.quantity,self.price_cents):
            _integer(value,positive=True)
        _integer(self.fee_cents)
        if (self.side != 'SELL_TO_CLOSE' or not _hex(self.contract_sha256)
                or self.quantity > 1_000_000 or self.quantity*self.price_cents > _MAX):
            raise SyntheticPositionBlocked('Only bounded synthetic SELL-to-close is permitted')

    @property
    def digest(self):
        return hashlib.sha256(_json(['SELL_TO_CLOSE_V1',asdict(self)]).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticOptionQuote:
    ledger_scope_sha256: str
    boundary_sha256: str
    order_id: str
    symbol: str
    contract_sha256: str
    quantity: int
    bid_cents: int
    ask_cents: int
    observed_epoch: int
    estimated_exit_fee_cents: int
    synthetic_only: bool = True
    market_evidence_verified: bool = False
    signature_hex: str = ''

    def __post_init__(self):
        for value in (self.order_id,self.symbol):
            _identifier(value)
        for value in (self.quantity,self.bid_cents,self.ask_cents,self.observed_epoch):
            _integer(value,positive=True)
        _integer(self.estimated_exit_fee_cents)
        if (not all(_hex(x) for x in (self.ledger_scope_sha256,self.boundary_sha256,self.contract_sha256))
                or self.quantity > 1_000_000 or self.bid_cents > self.ask_cents
                or self.quantity*self.ask_cents > _MAX
                or self.estimated_exit_fee_cents > self.quantity*self.bid_cents
                or self.synthetic_only is not True or self.market_evidence_verified is not False):
            raise SyntheticPositionBlocked('Invalid or falsely authenticated synthetic quote')

    def payload(self):
        body = asdict(self)
        body.pop('signature_hex')
        return body


@dataclass(frozen=True, slots=True)
class SyntheticCloseAuthorization:
    boundary_sha256: str
    ledger_scope_sha256: str
    request_sha256: str
    book_revision: int
    journal_tip: str
    risk_revision: int
    issued_epoch: int
    expires_epoch: int
    quote: SyntheticOptionQuote
    authorization_type: str = 'SYNTHETIC_REDUCE_ONLY_CLOSE_V1'
    signature_hex: str = ''

    def payload(self):
        body = asdict(self)
        body.pop('signature_hex')
        return body

    def encode(self):
        return _json(asdict(self))

    @classmethod
    def decode(cls, raw):
        if not isinstance(raw,str) or len(raw)>16384:
            raise SyntheticPositionBlocked('Invalid close authorization journal record')
        try:
            body=json.loads(raw)
            body['quote']=SyntheticOptionQuote(**body['quote'])
            value=cls(**body)
            if value.encode()!=raw:
                raise ValueError('Noncanonical authorization')
            return value
        except (TypeError,ValueError,KeyError) as exc:
            raise SyntheticPositionBlocked('Malformed close authorization journal record') from exc


def verify_quote(boundary,quote,*,scope,now_epoch):
    if not isinstance(quote,SyntheticOptionQuote):
        raise SyntheticPositionBlocked('Signed synthetic quote required')
    quote.__post_init__()
    _integer(now_epoch,positive=True)
    spec=boundary.position_contract(quote.symbol)
    if (quote.ledger_scope_sha256!=scope or quote.boundary_sha256!=boundary.digest
            or quote.contract_sha256!=spec['contract_sha256']
            or quote.bid_cents%spec['tick_cents'] or quote.ask_cents%spec['tick_cents']
            or not quote.observed_epoch<=now_epoch<=quote.observed_epoch+boundary.max_data_age_seconds
            or now_epoch>=spec['expiry_epoch']):
        raise SyntheticPositionBlocked('Stale, expired or mismatched synthetic quote/contract')
    expected=_mac(boundary.verification_key,'STAGE89_QUOTE_V1',quote.payload())
    if not _hex(quote.signature_hex) or not hmac.compare_digest(expected,quote.signature_hex):
        raise SyntheticPositionBlocked('Invalid synthetic quote signature')


def validate_close_position(boundary,request,positions):
    if not isinstance(request,SyntheticCloseRequest):
        raise SyntheticPositionBlocked('Typed SELL-to-close request required')
    request.__post_init__()
    spec=boundary.position_contract(request.symbol)
    matches=[p for p in positions if p.order_id==request.order_id]
    if len(matches)!=1:
        raise SyntheticPositionBlocked('No existing long position to close')
    p=matches[0]
    if (p.symbol!=request.symbol or p.contract_sha256!=request.contract_sha256
            or request.contract_sha256!=spec['contract_sha256']):
        raise SyntheticPositionBlocked('Cross-contract closing is forbidden')
    if not 0<request.quantity<=p.open_quantity:
        raise SyntheticPositionBlocked('Close quantity exceeds held long units')
    if any(row.symbol==request.symbol and row.open_hold_cents>0 for row in positions):
        raise SyntheticPositionBlocked('Cancel pending entries before reducing this position')
    if request.quantity%spec['lot_size'] and request.quantity!=p.open_quantity:
        raise SyntheticPositionBlocked('Partial close must use whole lots; full residual close only')
    if request.price_cents%spec['tick_cents']:
        raise SyntheticPositionBlocked('Close price violates contract tick')
    return p


def verify_close_authorization(boundary,authorization,request,*,scope,revision,tip,risk_revision,now_epoch):
    if not isinstance(authorization,SyntheticCloseAuthorization) or not isinstance(request,SyntheticCloseRequest):
        raise SyntheticPositionBlocked('Authenticated synthetic close authorization required')
    a=authorization
    for value in (a.book_revision,a.risk_revision,a.issued_epoch,a.expires_epoch):
        _integer(value)
    if (a.authorization_type!='SYNTHETIC_REDUCE_ONLY_CLOSE_V1'
            or a.boundary_sha256!=boundary.digest or a.ledger_scope_sha256!=scope
            or a.request_sha256!=request.digest or a.book_revision!=revision
            or a.journal_tip!=tip or a.risk_revision!=risk_revision
            or not a.issued_epoch<=now_epoch<a.expires_epoch
            or a.expires_epoch-a.issued_epoch!=boundary.permit_ttl_seconds):
        raise SyntheticPositionBlocked('Stale or mismatched close authorization')
    expected=_mac(boundary.verification_key,'STAGE89_CLOSE_V1',a.payload())
    if not _hex(a.signature_hex) or not hmac.compare_digest(expected,a.signature_hex):
        raise SyntheticPositionBlocked('Invalid close authorization signature')
    verify_quote(boundary,a.quote,scope=scope,now_epoch=now_epoch)
    q=a.quote
    if (q.order_id!=request.order_id or q.symbol!=request.symbol
            or q.contract_sha256!=request.contract_sha256 or q.quantity!=request.quantity
            or request.price_cents!=q.bid_cents or request.fee_cents>q.estimated_exit_fee_cents):
        raise SyntheticPositionBlocked('Close economics differ from the signed conservative bid/fee quote')


def issue_quote(key,boundary,*,snapshot,order_id,quantity,bid_cents,ask_cents,
                observed_epoch,estimated_exit_fee_cents,now_epoch):
    if not hmac.compare_digest(key,boundary.verification_key):
        raise SyntheticPositionBlocked('Quote signer does not match selected boundary')
    rows=[p for p in snapshot.orders if p.order_id==order_id and p.open_quantity>0]
    if len(rows)!=1 or type(quantity) is not int or not 0<quantity<=rows[0].open_quantity:
        raise SyntheticPositionBlocked('Quote must identify existing held long units')
    p=rows[0]
    q=SyntheticOptionQuote(snapshot.ledger_scope_sha256,boundary.digest,order_id,p.symbol,
                           p.contract_sha256,quantity,bid_cents,ask_cents,observed_epoch,
                           estimated_exit_fee_cents)
    q=replace(q,signature_hex=_mac(key,'STAGE89_QUOTE_V1',q.payload()))
    verify_quote(boundary,q,scope=snapshot.ledger_scope_sha256,now_epoch=now_epoch)
    if q.observed_epoch<p.last_fill_epoch:
        raise SyntheticPositionBlocked('Quote predates the position fill')
    return q


def issue_close(key,boundary,*,request,snapshot,quote,now_epoch):
    if not hmac.compare_digest(key,boundary.verification_key):
        raise SyntheticPositionBlocked('Close signer does not match selected boundary')
    p=validate_close_position(boundary,request,snapshot.orders)
    verify_quote(boundary,quote,scope=snapshot.ledger_scope_sha256,now_epoch=now_epoch)
    if quote.observed_epoch<p.last_fill_epoch:
        raise SyntheticPositionBlocked('Close quote predates the position fill')
    a=SyntheticCloseAuthorization(boundary.digest,snapshot.ledger_scope_sha256,request.digest,
        snapshot.journal_revision,snapshot.journal_tip,snapshot.risk_revision,now_epoch,
        now_epoch+boundary.permit_ttl_seconds,quote)
    a=replace(a,signature_hex=_mac(key,'STAGE89_CLOSE_V1',a.payload()))
    verify_close_authorization(boundary,a,request,scope=snapshot.ledger_scope_sha256,
        revision=snapshot.journal_revision,tip=snapshot.journal_tip,
        risk_revision=snapshot.risk_revision,now_epoch=now_epoch)
    return a


@dataclass(frozen=True, slots=True)
class SyntheticCloseAccounting:
    operation_id: str
    order_id: str
    quantity: int
    entry_premium_allocated_cents: int
    entry_fees_allocated_cents: int
    exit_proceeds_cents: int
    exit_fees_cents: int
    gross_realized_pnl_cents: int
    net_realized_pnl_cents: int
    remaining_open_quantity: int
    remaining_premium_cents: int
    remaining_entry_fees_cents: int


def allocate_entry_costs(premium,fees,held,quantity):
    """Moving weighted-average pools; floor allocation, remainder on final close."""
    for value in (premium,fees):
        _integer(value)
    for value in (held,quantity):
        _integer(value,positive=True)
    if quantity>held:
        raise SyntheticPositionBlocked('Cost allocation exceeds held units')
    return premium*quantity//held,fees*quantity//held


@dataclass(frozen=True, slots=True)
class SyntheticPositionValuation:
    order_id: str
    symbol: str
    contract_sha256: str
    open_quantity: int
    remaining_cost_basis_cents: int
    reference_price_cents: int
    market_value_cents: int
    unrealized_gross_pnl_cents: int
    estimated_exit_cost_cents: int
    unrealized_net_pnl_cents: int


@dataclass(frozen=True, slots=True)
class SyntheticMTMReport:
    account_id: str
    journal_revision: int
    journal_sha256: str
    valuation_epoch: int
    quote_epoch: int | None
    positions: tuple[SyntheticPositionValuation,...]
    open_quantity: int
    remaining_cost_basis_cents: int
    unrealized_gross_pnl_cents: int
    estimated_exit_cost_cents: int
    unrealized_net_pnl_cents: int
    realized_net_pnl_cents: int
    total_hypothetical_equity_cents: int
    available_cash_cents: int
    reserved_capital_cents: int
    portfolio_exposure_cents: int
    synthetic_only: bool = True
    market_evidence_verified: bool = False
    live_trading_enabled: bool = False


def value_positions(boundary,snapshot,quotes,*,now_epoch):
    if not isinstance(quotes,tuple) or len(quotes)>500:
        raise SyntheticPositionBlocked('Bounded explicit valuation quote tuple required')
    held={p.order_id:p for p in snapshot.orders if p.open_quantity>0}
    supplied={}
    for q in quotes:
        verify_quote(boundary,q,scope=snapshot.ledger_scope_sha256,now_epoch=now_epoch)
        if q.order_id in supplied or q.order_id not in held:
            raise SyntheticPositionBlocked('Duplicate or unknown valuation position')
        p=held[q.order_id]
        if (q.symbol!=p.symbol or q.contract_sha256!=p.contract_sha256
                or q.quantity!=p.open_quantity or q.observed_epoch<p.last_fill_epoch):
            raise SyntheticPositionBlocked('Valuation contract, quantity or timestamp mismatch')
        supplied[q.order_id]=q
    if set(supplied)!=set(held) or len({q.observed_epoch for q in quotes})>1:
        raise SyntheticPositionBlocked('Complete synchronized position quotes required')
    rows=[]
    for oid,p in sorted(held.items()):
        q=supplied[oid]
        value=p.open_quantity*q.bid_cents
        gross=value-p.remaining_premium_cents
        basis=p.remaining_premium_cents+p.remaining_entry_fees_cents
        rows.append(SyntheticPositionValuation(oid,p.symbol,p.contract_sha256,p.open_quantity,
            basis,q.bid_cents,value,gross,q.estimated_exit_fee_cents,
            gross-p.remaining_entry_fees_cents-q.estimated_exit_fee_cents))
    exposure=sum(r.market_value_cents for r in rows)
    estimated=sum(r.estimated_exit_cost_cents for r in rows)
    unrealized=sum(r.unrealized_net_pnl_cents for r in rows)
    equity=snapshot.cash_cents+exposure-estimated
    if equity!=snapshot.initial_cents+snapshot.realized_net_pnl_cents+unrealized:
        raise SyntheticPositionBlocked('MTM equity/cost conservation failed')
    return SyntheticMTMReport(snapshot.account_id,snapshot.journal_revision,snapshot.journal_tip,
        now_epoch,quotes[0].observed_epoch if quotes else None,tuple(rows),
        sum(r.open_quantity for r in rows),sum(r.remaining_cost_basis_cents for r in rows),
        sum(r.unrealized_gross_pnl_cents for r in rows),estimated,unrealized,
        snapshot.realized_net_pnl_cents,equity,snapshot.available_cents,snapshot.reserved_cents,exposure)
