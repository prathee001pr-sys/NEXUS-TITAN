"""Stage97: separate brokerless crypto *synthetic* spot account.

Only long spot, no external exchange, no network, no API secrets and no real
orders. HMAC authenticates a *local test issuer*, NOT a human or market venue.
Every read replays a tamper-evident local journal; no external rollback anchor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z', re.ASCII)
_SCOPE = re.compile(r'[a-f0-9]{64}\Z', re.ASCII)
_BASE_QUANTA = 1_000_000  # 1 unit = one micro-coin; prices are quote cents / coin.
_MAX = 10**15


class CryptoPaperBlocked(ValueError):
    pass


def _int(x, positive=False):
    if type(x) is not int or x < (1 if positive else 0) or x > _MAX:
        raise CryptoPaperBlocked('Invalid bounded integer')
    return x


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _id(value):
    if not isinstance(value,str) or not _ID.fullmatch(value):
        raise CryptoPaperBlocked('Invalid account or command identifier')
    return value


@dataclass(frozen=True,slots=True)
class CryptoPaperLimits:
    initial_cash_cents: int
    max_order_cents: int
    max_exposure_cents: int
    max_session_loss_cents: int
    fee_bps: int = 10
    max_quote_age_seconds: int = 30
    mode: str = 'SAFE'
    autonomy_enabled: bool = False
    paper_enabled: bool = False

    def __post_init__(self):
        for x in (self.initial_cash_cents,self.max_order_cents,self.max_exposure_cents,
                  self.max_session_loss_cents): _int(x,True)
        for x in (self.fee_bps,self.max_quote_age_seconds): _int(x)
        if (self.max_order_cents > self.max_exposure_cents or
                self.max_exposure_cents > self.initial_cash_cents or
                self.fee_bps > 1000 or not 1 <= self.max_quote_age_seconds <= 300 or
                self.mode not in ('SAFE','RISKY') or
                type(self.autonomy_enabled) is not bool or
                type(self.paper_enabled) is not bool):
            raise CryptoPaperBlocked('Invalid conservative crypto risk policy')


@dataclass(frozen=True,slots=True)
class CryptoPaperIntent:
    operation_id: str
    side: str
    quantity_microcoin: int
    price_cents_per_coin: int
    observed_epoch: int
    source: str = 'LOCAL_SYNTHETIC_TEST_ONLY'
    symbol: str = 'BTC-USDT'

    def __post_init__(self):
        _id(self.operation_id)
        for x in (self.quantity_microcoin,self.price_cents_per_coin):_int(x,True)
        _int(self.observed_epoch)
        if (self.side not in ('BUY','SELL') or self.source != 'LOCAL_SYNTHETIC_TEST_ONLY'
                or self.symbol != 'BTC-USDT'):
            raise CryptoPaperBlocked('Only explicitly supported brokerless crypto spot intents')


@dataclass(frozen=True,slots=True)
class CryptoPaperPermit:
    account_id: str
    expected_revision: int
    expected_tip: str
    intent_sha256: str
    expires_epoch: int
    signature_hex: str


def seal_crypto_paper_permit(secret: bytes, *, account_id: str, revision: int,
                             tip: str, intent: CryptoPaperIntent, expires_epoch: int) -> CryptoPaperPermit:
    """Test-harness issuer ONLY; possession of secret is not human approval."""
    if not isinstance(secret,bytes) or len(secret)<32:
        raise CryptoPaperBlocked('Test issuer needs a 256-bit local key')
    _id(account_id);_int(revision);_int(expires_epoch)
    digest=_hash(asdict(intent))
    payload=[account_id,revision,tip,digest,expires_epoch]
    sig=hmac.new(secret,_json(['CRYPTO_TEST_PERMIT_V1',payload]).encode(),hashlib.sha256).hexdigest()
    return CryptoPaperPermit(account_id,revision,tip,digest,expires_epoch,sig)


@dataclass(frozen=True,slots=True)
class CryptoPaperState:
    account_id: str
    currency: str
    market: str
    journal_revision: int
    journal_tip: str
    initial_cents: int
    cash_cents: int
    position_microcoin: int
    remaining_cost_basis_cents: int
    realized_net_pnl_cents: int
    total_fees_cents: int
    kill_active: bool
    last_observed_epoch: int
    live_trading_enabled: bool = False
    exchange_orders_transmitted: int = 0
    real_market_evidence_verified: bool = False


def _notional(intent):
    n=intent.quantity_microcoin * intent.price_cents_per_coin
    if n>_MAX * _BASE_QUANTA: raise CryptoPaperBlocked('Notional overflow')
    # Round toward a conservative execution price: buys up, sells down.
    return (n + _BASE_QUANTA-1)//_BASE_QUANTA if intent.side=='BUY' else n//_BASE_QUANTA


class CryptoPaperBook:
    def __init__(self, *, path, account_id, limits: CryptoPaperLimits,
                 verification_key:bytes, indian_book_path=None):
        _id(account_id)
        if not isinstance(limits,CryptoPaperLimits) or not isinstance(verification_key,bytes) or len(verification_key)<32:
            raise CryptoPaperBlocked('Explicit config and local verifier key required')
        if indian_book_path is not None and Path(indian_book_path).resolve()==Path(path).resolve():
            raise CryptoPaperBlocked('Crypto and Indian books must use separate physical ledgers')
        self.path=Path(path).resolve()
        self.account_id=account_id
        self.limits=limits
        self._key=verification_key
        if not self.path.parent.exists():raise CryptoPaperBlocked('Ledger parent directory must already exist')
        with self._connect() as db:
            existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if existing and existing!={'crypto_meta','crypto_events'}:
                raise CryptoPaperBlocked('Non-crypto or unexpected schema in proposed ledger')
            db.execute('CREATE TABLE IF NOT EXISTS crypto_meta (account TEXT PRIMARY KEY, settings_sha TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS crypto_events (seq INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, prior_tip TEXT NOT NULL, tip TEXT NOT NULL)')
            setting=_hash([account_id,asdict(limits),'CRYPTO_PAPER_SCHEMA_V1'])
            row=db.execute('SELECT account,settings_sha FROM crypto_meta').fetchall()
            if not row:
                db.execute('INSERT INTO crypto_meta VALUES (?,?)',(account_id,setting))
            elif row!=[(account_id,setting)]:
                raise CryptoPaperBlocked('Account scope, risk policy or ledger mismatch')
            self._replay(db)

    @contextmanager
    def _connect(self):
        conn=sqlite3.connect(str(self.path),timeout=15,isolation_level=None)
        try:
            conn.execute('PRAGMA busy_timeout=15000')
            conn.execute('PRAGMA journal_mode=WAL')
            yield conn
        finally:
            conn.close()

    def _initial(self):
        return CryptoPaperState(self.account_id,'USDT','CRYPTO_PAPER',0,'0'*64,
                                self.limits.initial_cash_cents,self.limits.initial_cash_cents,
                                0,0,0,0,False,0)

    def _replay(self,db):
        settings=_hash([self.account_id,asdict(self.limits),'CRYPTO_PAPER_SCHEMA_V1'])
        if db.execute('SELECT account,settings_sha FROM crypto_meta').fetchall()!=[(self.account_id,settings)]:
            raise CryptoPaperBlocked('Crypto account metadata changed')
        s=self._initial()
        seen=set()
        rows=db.execute('SELECT seq,operation_id,payload,prior_tip,tip FROM crypto_events ORDER BY seq').fetchall()
        for seq,oid,payload,prior,tip in rows:
            try:
                p=json.loads(payload)
                if (type(seq) is not int or seq!=s.journal_revision+1 or oid in seen
                        or oid != p['operation_id'] or prior != s.journal_tip
                        or _hash(['CRYPTO_PAPER_EVENT_V1',seq,oid,p,prior])!=tip
                        or payload!=_json(p)):
                    raise CryptoPaperBlocked('Journal sequence, integrity or idempotency tampered')
                s=self._transition(s,p,validate_limits=False)
                s=CryptoPaperState(**{**asdict(s),'journal_revision':seq,'journal_tip':tip})
                seen.add(oid)
            except (KeyError,TypeError,ValueError,OverflowError,AttributeError) as e:
                raise CryptoPaperBlocked('Malformed or tampered crypto journal') from e
        if (s.cash_cents+s.remaining_cost_basis_cents != s.initial_cents+s.realized_net_pnl_cents
                or s.cash_cents<0 or s.position_microcoin<0 or s.remaining_cost_basis_cents<0):
            raise CryptoPaperBlocked('Crypto journal conservation or negative balance failed')
        return s

    def _transition(self,s,p,*,validate_limits=True):
        if p['kind']=='KILL':
            if s.kill_active: raise CryptoPaperBlocked('Kill already active')
            return CryptoPaperState(**{**asdict(s),'kill_active':True})
        if p['kind']!='TRADE':raise CryptoPaperBlocked('Unsupported event kind')
        intent=CryptoPaperIntent(**p['intent'])
        qty=intent.quantity_microcoin
        notional=_notional(intent)
        fee=(notional*self.limits.fee_bps+9999)//10000
        if notional < 100:
            raise CryptoPaperBlocked('Dust trade below one USDT not allowed')
        if fee!=p['fee_cents'] or notional!=p['notional_cents']:
            raise CryptoPaperBlocked('Signed economics mismatch')
        if intent.observed_epoch<s.last_observed_epoch:
            raise CryptoPaperBlocked('Out-of-sequence quote timestamp')
        if intent.side=='BUY':
            if s.kill_active or s.realized_net_pnl_cents<=-self.limits.max_session_loss_cents:
                raise CryptoPaperBlocked('Kill/loss veto prevents new entry')
            if (notional>self.limits.max_order_cents or
                    s.remaining_cost_basis_cents+notional+fee>self.limits.max_exposure_cents or
                    s.cash_cents<notional+fee):
                raise CryptoPaperBlocked('Cash, order or exposure cap exceeded')
            cash=s.cash_cents-notional-fee
            basis=s.remaining_cost_basis_cents+notional+fee
            quantity=s.position_microcoin+qty
            pnl=s.realized_net_pnl_cents
        else:
            if qty>s.position_microcoin:
                raise CryptoPaperBlocked('Short/over-close blocked')
            allocated=s.remaining_cost_basis_cents*qty//s.position_microcoin
            cash=s.cash_cents+notional-fee
            basis=s.remaining_cost_basis_cents-allocated
            quantity=s.position_microcoin-qty
            pnl=s.realized_net_pnl_cents+notional-fee-allocated
            if cash<0:raise CryptoPaperBlocked('No negative cash on protective close')
        for amount in (cash,basis,quantity,abs(pnl)):_int(amount)
        if cash+basis != s.initial_cents+pnl: raise CryptoPaperBlocked('Atomic cash/cost ledger mismatch')
        return CryptoPaperState(**{**asdict(s),'cash_cents':cash,'remaining_cost_basis_cents':basis,
                                   'position_microcoin':quantity,'realized_net_pnl_cents':pnl,
                                   'total_fees_cents':s.total_fees_cents+fee,
                                   'last_observed_epoch':intent.observed_epoch})

    def snapshot(self):
        with self._connect() as db:
            return self._replay(db)

    def _apply(self,operation_id,payload,*,permit=None):
        _id(operation_id)
        with self._connect() as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                before=self._replay(db)
                old=db.execute('SELECT payload FROM crypto_events WHERE operation_id=?',(operation_id,)).fetchone()
                if old:
                    if old[0]!=_json(payload):raise CryptoPaperBlocked('Conflicting reused operation id')
                    db.execute('COMMIT')
                    return before,True
                if permit is not None and (permit.expected_revision!=before.journal_revision
                                           or permit.expected_tip!=before.journal_tip):
                    raise CryptoPaperBlocked('Stale signed risk permit at atomic commit boundary')
                after=self._transition(before,payload)
                seq=before.journal_revision+1
                tip=_hash(['CRYPTO_PAPER_EVENT_V1',seq,operation_id,payload,before.journal_tip])
                db.execute('INSERT INTO crypto_events VALUES (?,?,?,?,?)',
                           (seq,operation_id,_json(payload),before.journal_tip,tip))
                verified=self._replay(db)
                if verified.journal_revision!=seq or verified.journal_tip!=tip:
                    raise CryptoPaperBlocked('Journal replay failed after append')
                db.execute('COMMIT')
                return verified,False
            except Exception:
                if db.in_transaction:db.execute('ROLLBACK')
                raise

    def apply(self,intent:CryptoPaperIntent,permit:CryptoPaperPermit,*,now_epoch,
              human_approved=False,autonomous=False):
        if not isinstance(intent,CryptoPaperIntent) or not isinstance(permit,CryptoPaperPermit):
            raise CryptoPaperBlocked('Typed intent and independent permit required')
        _int(now_epoch)
        if intent.observed_epoch>now_epoch:
            raise CryptoPaperBlocked('Future synthetic quote')
        if (not self.limits.paper_enabled or type(human_approved) is not bool or
                type(autonomous) is not bool or (autonomous and
                 (self.limits.mode!='RISKY' or not self.limits.autonomy_enabled)) or
                (intent.side=='BUY' and not autonomous and human_approved is not True)):
            raise CryptoPaperBlocked('Paper access requires explicit approved local policy')
        # Independently signed SELL remains allowed as a protective exit after kill.
        with self._connect() as db:
            state=self._replay(db)
        with self._connect() as db:
            prior=db.execute('SELECT seq,payload,prior_tip FROM crypto_events WHERE operation_id=?',
                             (intent.operation_id,)).fetchone()
        if prior is not None:
            seq, prior_json, prior_tip = prior
            if (prior_json != _json({'kind':'TRADE','operation_id':intent.operation_id,
                                   'intent':asdict(intent),'notional_cents':_notional(intent),
                                   'fee_cents':(_notional(intent)*self.limits.fee_bps+9999)//10000})
                    or permit.expected_revision!=seq-1 or permit.expected_tip!=prior_tip):
                raise CryptoPaperBlocked('Conflicting replay or mismatched original permit')
        elif permit.expected_revision!=state.journal_revision or permit.expected_tip!=state.journal_tip:
            raise CryptoPaperBlocked('Stale permit at account head')
        if prior is None and now_epoch-intent.observed_epoch>self.limits.max_quote_age_seconds:
            raise CryptoPaperBlocked('Stale synthetic quote')
        if (permit.account_id!=self.account_id or permit.intent_sha256!=_hash(asdict(intent))
                or type(permit.expires_epoch) is not int
                or (prior is None and (now_epoch>permit.expires_epoch or permit.expires_epoch>now_epoch+300))):
            raise CryptoPaperBlocked('Missing, expired or stale risk permit')
        payload=[permit.account_id,permit.expected_revision,permit.expected_tip,
                 permit.intent_sha256,permit.expires_epoch]
        expected=hmac.new(self._key,_json(['CRYPTO_TEST_PERMIT_V1',payload]).encode(),hashlib.sha256).hexdigest()
        if not isinstance(permit.signature_hex,str) or not hmac.compare_digest(permit.signature_hex,expected):
            raise CryptoPaperBlocked('Invalid risk permit signature')
        notional=_notional(intent)
        fee=(notional*self.limits.fee_bps+9999)//10000
        event={'kind':'TRADE','operation_id':intent.operation_id,
               'intent':asdict(intent),'notional_cents':notional,'fee_cents':fee}
        return self._apply(intent.operation_id,event,permit=permit)

    def stop(self,operation_id:str):
        """One-way emergency stop. No silent rearm API exists."""
        return self._apply(operation_id,{'kind':'KILL','operation_id':operation_id})

    def equity_at_synthetic_bid(self,*,price_cents_per_coin:int,observed_epoch:int,now_epoch:int):
        _int(price_cents_per_coin,True);_int(observed_epoch);_int(now_epoch)
        if observed_epoch>now_epoch or now_epoch-observed_epoch>self.limits.max_quote_age_seconds:
            raise CryptoPaperBlocked('Stale or future synthetic mark')
        s=self.snapshot()
        if observed_epoch<s.last_observed_epoch: raise CryptoPaperBlocked('Old mark predates latest execution')
        # Synthetic mark is explicitly exploratory; charge an estimated future sell fee.
        value=s.position_microcoin*price_cents_per_coin//_BASE_QUANTA
        fee=(value*self.limits.fee_bps+9999)//10000
        equity=s.cash_cents+value-fee
        return {'market':'CRYPTO_PAPER','currency':'USDT','account_id':s.account_id,
                'journal_revision':s.journal_revision,'journal_tip':s.journal_tip,
                'synthetic_equity_cents':equity,
                'synthetic_unrealized_pnl_cents':equity-s.initial_cents-s.realized_net_pnl_cents,
                'real_market_evidence_verified':False,'live_trading_enabled':False}
