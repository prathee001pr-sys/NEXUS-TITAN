"""Shared, explicitly fabricated data for the selected Stage86+ account tests."""
from dataclasses import replace
from pathlib import Path
import runpy
import secrets

from nexus_titan.operations.fo_risk_boundary import (
    SyntheticFOInstrument, SyntheticFOOperation,
    SyntheticFORiskAuthority, SyntheticFORiskBoundary,
)
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticPolicy,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import Stage76FOResearchPolicy

ROOT = Path(__file__).resolve().parents[2]
chain_fixture = runpy.run_path(str(ROOT / "tests/test_full_chain_fo_data_to_sandbox_e2e.py"))["integrated_chain"]


def environment(tmp_path, *, capital=10_000_000, policy=None, history_bars=4, option_start_minute=1):
    chains = {name: chain_fixture(tmp_path / name, name, capital, history_bars, option_start_minute)
              for name in ("NIFTY", "BANKNIFTY")}
    key = secrets.token_bytes(32)
    specs = []
    for name, c in chains.items():
        price = int(round(next(r.ask for r in c['72'].rows if r.option_type == 'CE') * 100))
        qty = c['contract'].lot_size
        specs.append(SyntheticFOInstrument(
            name, c['75'].option_symbol, qty, qty, 5, price,
            c['75'].long_option_entry_debit_cents - qty*price,
            int(c['72'].observation_time.timestamp()),
            int(c['72'].declared_expiry_cutoff.timestamp()),
            c['75'].research_packet_sha256,
        ))
    boundary = SyntheticFORiskBoundary(
        tuple(c['75'] for c in chains.values()), tuple(specs),
        policy or Stage76FOResearchPolicy(), key,
    )
    clock = [specs[0].observed_epoch]
    book_policy = Stage55SyntheticPolicy(2000, boundary.policy.max_portfolio_debit_bps)
    path = tmp_path / 'selected-fo.sqlite'
    book = Stage55IsolatedSyntheticExecutionBook(
        db_path=path, account_id='qa-fo-portfolio', starting_cents=capital,
        policy=book_policy, fo_boundary=boundary, clock=lambda: clock[0],
    )
    return dict(chains=chains, key=key, boundary=boundary, clock=clock, book=book,
                authority=SyntheticFORiskAuthority(key), policy=book_policy, path=path,
                telemetry=chains['NIFTY']['pulse'])


def opening(env, request='order-a', underlying='NIFTY'):
    spec = next(s for s in env['boundary'].instruments if s.underlying == underlying)
    return SyntheticFOOperation('OPEN', request, request, spec.symbol, spec.quantity,
                                spec.limit_price_cents, 0, spec.fee_buffer_cents)


def issue(env, op, **changes):
    return env['authority'].issue(
        env['boundary'], operation=op,
        snapshot=env['book'].snapshot_local_synthetic_portfolio(),
        telemetry=replace(env['telemetry'], **changes), now_epoch=env['clock'][0],
    )


def execute(env, op, permit=None):
    b = env['book']
    if op.kind == 'OPEN':
        return b.reserve_synthetic_buy(
            request_id=op.operation_id, symbol=op.symbol, quantity=op.quantity,
            limit_price_cents=op.price_cents, fee_buffer_cents=op.fee_buffer_cents,
            risk_permit=permit,
        )
    if op.kind == 'FILL':
        return b.record_simulated_fill(
            order_id=op.order_id, fill_id=op.operation_id, quantity=op.quantity,
            price_cents=op.price_cents, fee_cents=op.fee_cents,
            evidence_source='LOCAL_SYNTHETIC_TEST_ONLY', risk_permit=permit,
        )
    return b.cancel_unfilled(order_id=op.order_id, cancel_id=op.operation_id,
                             evidence_source='LOCAL_SYNTHETIC_TEST_ONLY')


def reopen(env, **changes):
    arguments = dict(db_path=env['path'], account_id='qa-fo-portfolio',
                     starting_cents=env['book'].starting_cents, policy=env['policy'],
                     fo_boundary=env['boundary'], clock=lambda: env['clock'][0])
    arguments.update(changes)
    return Stage55IsolatedSyntheticExecutionBook(**arguments)
