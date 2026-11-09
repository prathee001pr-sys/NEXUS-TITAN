"""Stage98: read-only combined assurance, never combined capital authority."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from .stage96_accounting_review import FOAccountingReview
from .stage97_crypto_paper import CryptoPaperBook, CryptoPaperBlocked


class DualMarketBlocked(ValueError):
    pass


@dataclass(frozen=True,slots=True)
class DualMarketReview:
    indian: dict
    crypto: dict
    combined_pnl_cents: None = None
    combined_cash_cents: None = None
    cross_currency_conversion_verified: bool = False
    live_trading_enabled: bool = False
    real_market_shadow_validated: bool = False
    verdict: str = 'SYNTHETIC_DUAL_MARKET_REVIEW_ONLY_NO_LIVE'


def read_only_dual_market_review(indian:FOAccountingReview, crypto:CryptoPaperBook)->DualMarketReview:
    """Fail closed on invalid provenance and never net INR with USDT."""
    if not isinstance(indian,FOAccountingReview) or not isinstance(crypto,CryptoPaperBook):
        raise DualMarketBlocked('Actual selected account views required')
    if (indian.market!='INDIAN_FO' or indian.currency!='INR' or
            indian.live_trading_enabled is not False or indian.market_evidence_verified is not False
            or indian.broker_orders_transmitted!=0 or indian.account_id==crypto.account_id):
        raise DualMarketBlocked('Invalid market identity, execution mode or authority boundary')
    if indian.cash_cents+indian.remaining_cost_basis_cents!=indian.initial_cents+indian.realized_net_pnl_cents:
        raise DualMarketBlocked('Indian cash conservation failed')
    c=crypto.snapshot()  # replay checked, no exchanges / no broker network
    if (c.market!='CRYPTO_PAPER' or c.currency!='USDT' or c.live_trading_enabled is not False
            or c.exchange_orders_transmitted!=0 or c.real_market_evidence_verified is not False
            or c.cash_cents+c.remaining_cost_basis_cents!=c.initial_cents+c.realized_net_pnl_cents):
        raise DualMarketBlocked('Crypto provenance or accounting failed')
    if (not isinstance(indian.journal_sha256,str) or len(indian.journal_sha256)!=64
            or not isinstance(c.journal_tip,str) or len(c.journal_tip)!=64):
        raise DualMarketBlocked('Independent checked journal heads required')
    return DualMarketReview(asdict(indian),asdict(c))
