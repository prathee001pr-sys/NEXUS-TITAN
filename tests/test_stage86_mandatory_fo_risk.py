"""Runtime bypass, stale evidence, risk veto and durable boundary tests."""
from dataclasses import replace
from pathlib import Path
import hashlib
import hmac
import json
import runpy
import sqlite3

import pytest

from nexus_titan.operations.fo_risk_boundary import (
    SyntheticFOOperation, SyntheticFORiskBlocked,
)
from nexus_titan.operations.isolated_atomic_execution_book import Stage55SyntheticBookBlocked

helper = runpy.run_path(str(Path(__file__).parent / 'helpers/fo_synthetic_fixture.py'))
environment, opening, issue, execute, reopen = (helper[k] for k in ('environment','opening','issue','execute','reopen'))


def resign(env, permit, **changes):
    value = replace(permit, **changes, signature_hex='')
    payload = json.dumps(value.payload(), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return replace(value, signature_hex=hmac.new(env['key'], payload.encode(), hashlib.sha256).hexdigest())


def test_raw_reserve_and_fill_cannot_skip_risk_boundary(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    with pytest.raises(Stage55SyntheticBookBlocked, match='permit missing'):
        execute(env, op)
    assert env['book'].inspect().revision == 0
    execute(env, op, issue(env, op))
    fill = SyntheticFOOperation('FILL', 'fill-a', op.order_id, quantity=5, price_cents=550)
    with pytest.raises(Stage55SyntheticBookBlocked, match='permit missing'):
        execute(env, fill)
    assert execute(env, fill, issue(env, fill)).filled_quantity == 5


@pytest.mark.parametrize('mode', ['no-boundary', 'wrong-key', 'changed-policy'])
def test_persistent_scope_cannot_be_downgraded_on_reopen(tmp_path, mode):
    env = environment(tmp_path)
    boundary = env['boundary']
    if mode == 'no-boundary':
        boundary = None
    elif mode == 'wrong-key':
        boundary = replace(boundary, verification_key=b'x'*32)
    else:
        boundary = replace(boundary, permit_ttl_seconds=9)
    with pytest.raises(Stage55SyntheticBookBlocked):
        reopen(env, fo_boundary=boundary)
    assert reopen(env).inspect().revision == 0


@pytest.mark.parametrize('offset', [-1, 10, 31])
def test_future_expired_and_stale_permits_never_acquire_a_hold(tmp_path, offset):
    env = environment(tmp_path)
    op = opening(env)
    permit = issue(env, op)
    env['clock'][0] += offset
    with pytest.raises(Stage55SyntheticBookBlocked, match='Stale or mismatched'):
        execute(env, op, permit)
    assert env['book'].inspect().open_reserved_cents == 0


def test_intervening_book_mutation_invalidates_signed_risk_snapshot(tmp_path):
    env = environment(tmp_path)
    first, second = opening(env), opening(env, 'order-b', 'BANKNIFTY')
    stale = issue(env, second)
    execute(env, first, issue(env, first))
    with pytest.raises(Stage55SyntheticBookBlocked, match='Stale or mismatched'):
        execute(env, second, stale)
    assert env['book'].inspect().total_orders == 1


@pytest.mark.parametrize('changed', ['signature', 'quantity', 'fee', 'operation-id', 'risk-revision'])
def test_permit_is_bound_to_exact_operation_and_risk_revision(tmp_path, changed):
    env = environment(tmp_path)
    op, permit = opening(env), issue(env, opening(env))
    if changed == 'signature':
        permit = replace(permit, signature_hex='0'*64)
    elif changed == 'quantity':
        op = replace(op, quantity=op.quantity+1)
    elif changed == 'fee':
        op = replace(op, fee_buffer_cents=op.fee_buffer_cents+1)
    elif changed == 'operation-id':
        op = replace(op, operation_id='different', order_id='different')
    else:
        permit = replace(permit, risk_revision=permit.risk_revision+1)
    with pytest.raises(Stage55SyntheticBookBlocked):
        execute(env, op, permit)
    assert env['book'].inspect().revision == 0


@pytest.mark.parametrize('changes', [
    {'daily_realized_loss_bps': 300}, {'drawdown_bps': 1000},
    {'consecutive_losses': 3}, {'risk_engine_healthy': False}, {'kill_switch_active': True},
])
def test_risk_is_recomputed_inside_transaction_even_for_a_valid_mac(tmp_path, changes):
    env = environment(tmp_path)
    op = opening(env)
    with pytest.raises(SyntheticFORiskBlocked, match='Risk & Veto'):
        issue(env, op, **changes)
    valid = issue(env, op)
    forged_by_faulty_control_plane = resign(env, valid, telemetry=replace(env['telemetry'], **changes))
    with pytest.raises(Stage55SyntheticBookBlocked, match='Risk & Veto'):
        execute(env, op, forged_by_faulty_control_plane)
    assert env['book'].inspect().revision == 0


def test_kill_switch_wins_over_expired_permit_and_legacy_rearm_is_denied(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    permit = issue(env, op)
    env['book'].set_local_synthetic_kill_switch(active=True, operation_id='kill-now')
    env['clock'][0] += 11
    with pytest.raises(Stage55SyntheticBookBlocked, match='kill switch'):
        execute(env, op, permit)
    with pytest.raises(Stage55SyntheticBookBlocked, match='cannot be rearmed'):
        env['book'].set_local_synthetic_kill_switch(active=False, operation_id='bypass')
    assert reopen(env).inspect_local_synthetic_risk_state().kill_switch_active


def test_signed_request_cannot_be_replayed_or_reused_for_another_db(tmp_path):
    a, b = environment(tmp_path/'a'), environment(tmp_path/'b')
    op = opening(a)
    same_boundary_other_book = reopen(b, fo_boundary=b['boundary'])
    assert same_boundary_other_book.inspect().revision == 0
    permit = issue(a, op)
    # Re-sign to isolate ledger-scope binding from the different key/configuration.
    wrong_scope = resign(a, permit, ledger_scope_sha256=b['book'].snapshot_local_synthetic_portfolio().ledger_scope_sha256)
    with pytest.raises(Stage55SyntheticBookBlocked, match='mismatched'):
        execute(a, op, wrong_scope)
    execute(a, op, permit)
    replay = execute(a, op, permit)
    assert replay.replayed and replay.revision == 1
    assert a['book'].inspect().total_orders == 1


def test_cancellation_releases_only_unfilled_hold_under_kill_and_expired_data(tmp_path):
    env = environment(tmp_path)
    op = opening(env)
    execute(env, op, issue(env, op))
    env['book'].set_local_synthetic_kill_switch(active=True, operation_id='kill')
    env['clock'][0] += 300
    cancel = SyntheticFOOperation('CANCEL', 'cancel-a', op.order_id)
    receipt = execute(env, cancel)
    assert receipt.available_cents == env['book'].starting_cents
    assert receipt.trading_authority is False
    assert receipt.live_orders_transmitted == 0


@pytest.mark.parametrize('damage', ['delete-proof', 'change-signature', 'delete-marker'])
def test_missing_or_corrupted_risk_journal_fails_closed(tmp_path, damage):
    env = environment(tmp_path)
    op = opening(env)
    execute(env, op, issue(env, op))
    with sqlite3.connect(env['path']) as db:
        if damage == 'delete-proof':
            db.execute('DELETE FROM execution_fo_permits')
        elif damage == 'delete-marker':
            db.execute('DELETE FROM execution_fo_boundary')
        else:
            raw = db.execute('SELECT permit_json FROM execution_fo_permits').fetchone()[0]
            body = json.loads(raw); body['signature_hex'] = '0'*64
            db.execute('UPDATE execution_fo_permits SET permit_json=?', (json.dumps(body,sort_keys=True,separators=(',',':')),))
    assert not env['book'].inspect().local_integrity_verified
    with pytest.raises(Stage55SyntheticBookBlocked):
        reopen(env)


def test_stale_data_and_false_authority_cannot_be_configured_or_signed(tmp_path):
    env = environment(tmp_path)
    env['clock'][0] += 31
    with pytest.raises(SyntheticFORiskBlocked, match='Stale'):
        issue(env, opening(env))
    bad = replace(env['boundary'].packets[0], live_trading_enabled=True)
    with pytest.raises(ValueError, match='authority'):
        replace(env['boundary'], packets=(bad, env['boundary'].packets[1]))


@pytest.mark.parametrize('changes', [
    {'quantity': 26}, {'price_cents': 551}, {'symbol': 'BTCUSDT'}, {'fee_buffer_cents': 999},
])
def test_faulty_signer_cannot_permit_invalid_contract_economics(tmp_path, changes):
    env = environment(tmp_path)
    valid = opening(env)
    invalid = replace(valid, **changes)
    with pytest.raises(SyntheticFORiskBlocked):
        issue(env, invalid)
    signed = resign(env, issue(env, valid), operation_sha256=invalid.digest)
    with pytest.raises(Stage55SyntheticBookBlocked):
        execute(env, invalid, signed)
    assert env['book'].inspect().open_reserved_cents == 0


def test_legacy_stage77_gateway_cannot_bypass_selected_account_boundary(tmp_path):
    from nexus_titan.operations.stage77_brokerless_fo_sandbox import (
        Stage77BrokerlessFOSyntheticGateway, Stage77SyntheticGatewayBlocked,
    )
    env = environment(tmp_path)
    gate = Stage77BrokerlessFOSyntheticGateway(
        book=env['book'], research_packets=env['boundary'].packets,
        policy=env['boundary'].policy,
    )
    spec = env['boundary'].instruments[0]
    with pytest.raises(Stage77SyntheticGatewayBlocked, match='reserve rejected'):
        gate.reserve_synthetic_long_option(
            research_packet_sha256=spec.research_packet_sha256, request_id='legacy-bypass',
            symbol=spec.symbol, lots=1, lot_size=spec.lot_size,
            limit_price_cents=spec.limit_price_cents, fee_buffer_cents=spec.fee_buffer_cents,
            telemetry=env['telemetry'],
        )
    assert env['book'].inspect().revision == 0
