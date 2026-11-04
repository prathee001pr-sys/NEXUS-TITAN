"""Real selected-book lifecycle, accounting, concurrency and recovery tests."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import runpy
import sqlite3
from threading import Barrier

import pytest

from nexus_titan.crypto.crypto_engine import CryptoVirtualAccount
from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskBlocked
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticBookBlocked,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import Stage76FOResearchPolicy
from nexus_titan.operations.synthetic_fo_execution import SyntheticFOExecutionGateway

helper = runpy.run_path(str(Path(__file__).parent / 'helpers/fo_synthetic_fixture.py'))
environment, opening, issue, reopen = (helper[k] for k in ('environment','opening','issue','reopen'))


def gate(env):
    return SyntheticFOExecutionGateway(env['book'])


def admit(env, op):
    return gate(env).apply(op, risk_permit=issue(env, op))


def check_cash(snapshot):
    assert snapshot.initial_cents == snapshot.cash_cents + snapshot.paid_notional_cents + snapshot.paid_fees_cents
    assert 0 <= snapshot.reserved_cents <= snapshot.cash_cents
    assert snapshot.available_cents == snapshot.cash_cents - snapshot.reserved_cents
    assert sum(o.open_hold_cents for o in snapshot.orders) == snapshot.reserved_cents
    assert sum(o.paid_notional_cents for o in snapshot.orders) == snapshot.paid_notional_cents
    assert sum(o.paid_fees_cents for o in snapshot.orders) == snapshot.paid_fees_cents


def test_two_markets_partial_fill_cancel_and_costs_use_one_cash_balance(tmp_path):
    env = environment(tmp_path)
    n, b = opening(env), opening(env, 'bank', 'BANKNIFTY')
    admit(env, n); admit(env, b)
    fill = SyntheticFOOperation('FILL', 'n-part', n.order_id, quantity=10, price_cents=540, fee_cents=5)
    receipt = admit(env, fill)
    assert receipt.order_state == 'PARTIAL_SYNTHETIC'
    snapshot = gate(env).snapshot()
    check_cash(snapshot)
    assert snapshot.paid_notional_cents == 5400 and snapshot.paid_fees_cents == 5
    assert snapshot.reserved_cents == 15*550 + 6 + 13761
    cancel = SyntheticFOOperation('CANCEL', 'n-cancel', n.order_id)
    gate(env).apply(cancel)
    snapshot = gate(env).snapshot()
    check_cash(snapshot)
    assert snapshot.reserved_cents == 13761
    assert snapshot.cash_cents == snapshot.initial_cents - 5405
    assert receipt.trading_authority is False and receipt.live_orders_transmitted == 0


@pytest.mark.parametrize('kind', ['OPEN','FILL','CANCEL'])
def test_exact_retry_is_read_only_after_restart_and_evidence_expiry(tmp_path, kind):
    env = environment(tmp_path)
    op = opening(env)
    admit(env, op)
    if kind == 'FILL':
        op = SyntheticFOOperation('FILL','part',op.order_id,quantity=5,price_cents=550,fee_cents=1)
        admit(env, op)
    elif kind == 'CANCEL':
        op = SyntheticFOOperation('CANCEL','cancel',op.order_id)
        gate(env).apply(op)
    before = gate(env).snapshot()
    env['clock'][0] += 11
    env['book'] = reopen(env)
    replay = gate(env).apply(op)
    assert replay.replayed and replay.revision == before.journal_revision
    assert gate(env).snapshot() == before
    assert not replay.trading_authority


def test_duplicate_id_with_changed_economics_is_not_an_idempotent_retry(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    admit(env, op)
    with pytest.raises(Stage55SyntheticBookBlocked, match='Idempotency ID conflicts'):
        gate(env).apply(replace(op, quantity=op.quantity+1))
    assert gate(env).snapshot().journal_revision == 1


def test_full_fills_do_not_reset_committed_capital_for_new_reservations(tmp_path):
    env = environment(tmp_path, capital=80000,
                      policy=replace(Stage76FOResearchPolicy(),max_stressed_loss_bps=5000))
    for name in ('NIFTY','BANKNIFTY'):
        op = opening(env, 'open-'+name, name)
        admit(env, op)
        fill = SyntheticFOOperation('FILL','fill-'+name,op.order_id,quantity=op.quantity,
                                    price_cents=op.price_cents,fee_cents=op.fee_buffer_cents)
        admit(env, fill)
    assert gate(env).snapshot().reserved_cents == 0
    extra = opening(env,'third-filled-allocation')
    with pytest.raises(Stage55SyntheticBookBlocked, match='committed-capital limit'):
        admit(env, extra)
    check_cash(gate(env).snapshot())
    assert gate(env).snapshot().journal_revision == 4


def test_partial_cancel_does_not_restore_already_filled_research_allocation(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    admit(env,op)
    admit(env,SyntheticFOOperation('FILL','part',op.order_id,quantity=5,price_cents=550))
    gate(env).apply(SyntheticFOOperation('CANCEL','cancel',op.order_id))
    with pytest.raises(Stage55SyntheticBookBlocked, match='allocation already committed'):
        admit(env,opening(env,'duplicate-idea'))
    assert gate(env).snapshot().orders[0].filled_quantity == 5


def test_cancelled_unfilled_allocation_can_be_reserved_again_without_creating_cash(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    admit(env,op)
    gate(env).apply(SyntheticFOOperation('CANCEL','cancel',op.order_id))
    admit(env,opening(env,'retry-after-cancel'))
    check_cash(gate(env).snapshot())
    assert gate(env).snapshot().cash_cents == env['book'].starting_cents
    assert gate(env).snapshot().reserved_cents == 13761


def test_concurrent_identical_requests_allocate_capital_once(tmp_path):
    env = environment(tmp_path)
    op, permit = opening(env), issue(env,opening(env))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: gate(env).apply(op,risk_permit=permit),range(2)))
    assert sorted(r.replayed for r in results) == [False,True]
    assert gate(env).snapshot().journal_revision == 1
    assert gate(env).snapshot().reserved_cents == 13761


def test_concurrent_distinct_requests_cannot_overspend_or_duplicate_allocations(tmp_path):
    env = environment(tmp_path)
    ops = [opening(env,'request-'+str(i),name) for i,name in enumerate(('NIFTY','BANKNIFTY','NIFTY','BANKNIFTY'))]
    barrier = Barrier(4)
    def submit(op):
        permit = issue(env,op)
        barrier.wait(timeout=5)
        try:
            return gate(env).apply(op,risk_permit=permit)
        except Stage55SyntheticBookBlocked:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(submit,ops))
    assert sum(r is not None for r in results) == 1
    # Fresh explicit risk review may retry a stale request; quota/cash still
    # prevent a second allocation of the same reviewed instrument.
    for op in ops:
        try:
            admit(env,op)
        except Stage55SyntheticBookBlocked:
            pass
    snapshot = gate(env).snapshot()
    check_cash(snapshot)
    assert snapshot.reserved_cents == 2*13761
    assert sum(o.unfilled_quantity for o in snapshot.orders) == 50


def test_restart_reads_partial_order_but_needs_fresh_permit_for_next_fill(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    admit(env,op)
    admit(env,SyntheticFOOperation('FILL','part',op.order_id,quantity=10,price_cents=545,fee_cents=3))
    env['clock'][0] += 11
    env['book'] = reopen(env)
    final = SyntheticFOOperation('FILL','rest',op.order_id,quantity=15,price_cents=540,fee_cents=5)
    with pytest.raises(Stage55SyntheticBookBlocked,match='permit missing'):
        gate(env).apply(final)
    result = admit(env,final)
    assert result.order_state == 'FILLED_SYNTHETIC'
    snapshot = gate(env).snapshot()
    assert snapshot.reserved_cents == 0
    assert snapshot.paid_notional_cents == 13550 and snapshot.paid_fees_cents == 8
    check_cash(snapshot)


@pytest.mark.parametrize('point', ['before-event','after-event-before-head'])
def test_crash_rolls_back_capital_event_and_risk_proof_together(tmp_path,monkeypatch,point):
    env = environment(tmp_path)
    op, permit = opening(env), issue(env,opening(env))
    gateway = gate(env)
    if point == 'before-event':
        def fail(*_): raise RuntimeError('injected-crash')
        monkeypatch.setattr(env['book'],'_write_event',fail)
    else:
        original, count = env['book']._derive, [0]
        def fail(db):
            count[0] += 1
            if count[0] == 2: raise RuntimeError('injected-crash')
            return original(db)
        monkeypatch.setattr(env['book'],'_derive',fail)
    with pytest.raises(RuntimeError,match='injected-crash'):
        gateway.apply(op,risk_permit=permit)
    monkeypatch.undo()
    env['book'] = reopen(env)
    snapshot = gate(env).snapshot()
    check_cash(snapshot)
    assert snapshot.journal_revision == 0 and snapshot.reserved_cents == 0
    with sqlite3.connect(env['path']) as db:
        assert db.execute('SELECT count(*) FROM execution_fo_permits').fetchone()[0] == 0
    assert not gate(env).apply(op,risk_permit=permit).replayed


@pytest.mark.parametrize('kind', ['FILL','CANCEL'])
def test_crash_during_settlement_or_release_keeps_the_original_hold(tmp_path,monkeypatch,kind):
    env = environment(tmp_path)
    op = opening(env)
    admit(env,op)
    before = gate(env).snapshot()
    action = (SyntheticFOOperation('FILL','part',op.order_id,quantity=5,price_cents=550)
              if kind == 'FILL' else SyntheticFOOperation('CANCEL','cancel',op.order_id))
    permit = issue(env,action) if kind == 'FILL' else None
    def fail(*_): raise RuntimeError('crash-settle')
    monkeypatch.setattr(env['book'],'_write_event',fail)
    with pytest.raises(RuntimeError):
        gate(env).apply(action,risk_permit=permit)
    monkeypatch.undo()
    env['book'] = reopen(env)
    assert gate(env).snapshot() == before


@pytest.mark.parametrize('excess', ['fee','quantity'])
def test_excess_fees_or_overfill_never_debit_cash(tmp_path,excess):
    env = environment(tmp_path)
    op = opening(env)
    admit(env,op)
    before = gate(env).snapshot()
    fill = SyntheticFOOperation('FILL','excess',op.order_id,
                                quantity=26 if excess=='quantity' else 5,
                                price_cents=550,fee_cents=12 if excess=='fee' else 0)
    with pytest.raises(Stage55SyntheticBookBlocked,match='remaining limits'):
        admit(env,fill)
    assert gate(env).snapshot() == before


def test_crypto_uses_separate_cash_and_cannot_enter_selected_fo_book(tmp_path):
    env = environment(tmp_path)
    before = gate(env).snapshot()
    crypto = CryptoVirtualAccount(starting_capital=1000)
    crypto.execute_crypto_order('BTCUSDT','BUY',50000,0.001)
    assert crypto.cash_balance < 1000
    assert gate(env).snapshot() == before
    with pytest.raises(SyntheticFORiskBlocked,match='Instrument'):
        issue(env,replace(opening(env),symbol='BTCUSDT'))


def test_public_gateway_rejects_legacy_unprotected_book(tmp_path):
    book = Stage55IsolatedSyntheticExecutionBook(db_path=tmp_path/'legacy.sqlite',
                                                account_id='legacy',starting_cents=100000)
    with pytest.raises(Stage55SyntheticBookBlocked,match='mandatory F&O account'):
        SyntheticFOExecutionGateway(book)
