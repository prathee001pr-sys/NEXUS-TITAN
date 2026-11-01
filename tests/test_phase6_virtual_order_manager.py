import tempfile
import unittest
from pathlib import Path

from nexus_titan.virtual.order_manager import (
    OrderSide, OrderState, OrderType, TradingMode, VirtualAccount,
)


class VirtualOrderManagerTests(unittest.TestCase):
    def setUp(self):
        self.account = VirtualAccount(
            "TEST-ACC-50K", starting_capital=50000.0,
            require_pretrade_risk_check=False,
        )

    def test_account_initial_state(self):
        self.assertEqual(self.account.cash_balance, 50000.0)
        report = self.account.reconcile()
        self.assertTrue(report.is_reconciled)
        self.assertEqual(report.balance_discrepancy, 0.0)

    def test_configurable_starting_capital(self):
        self.assertEqual(VirtualAccount(starting_capital=10000).cash_balance, 10000)
        self.assertEqual(VirtualAccount(starting_capital=500000).cash_balance, 500000)
        for amount in (0.0, -5000.0, float("nan")):
            with self.assertRaises(ValueError):
                VirtualAccount(starting_capital=amount)
        with self.assertRaises(ValueError):
            VirtualAccount()

    def test_capital_top_up_withdrawal(self):
        account = VirtualAccount(starting_capital=25000.0, risk_per_trade_pct=1.0)
        top_up = account.adjust_capital(15000, "TOP_UP")
        self.assertEqual(account.current_capital, 40000)
        self.assertEqual(account.cash_balance, 40000)
        self.assertEqual(top_up.resulting_risk_budget, 400)
        withdrawal = account.adjust_capital(10000, "WITHDRAWAL")
        self.assertEqual(account.current_capital, 30000)
        self.assertEqual(account.cash_balance, 30000)
        self.assertEqual(withdrawal.resulting_risk_budget, 300)
        with self.assertRaises(ValueError):
            account.adjust_capital(50000, "WITHDRAWAL")

    def test_strict_enums_and_order_type(self):
        with self.assertRaises(ValueError):
            self.account.submit_order("NIFTY", "SHORT", 10)
        with self.assertRaises(ValueError):
            self.account.submit_order("NIFTY", "MAGIC", 10)
        with self.assertRaises(ValueError):
            self.account.submit_order("NIFTY", "BUY", 10, order_type="ICEBERG")

    def test_overfill_and_partial_fill_protection(self):
        order = self.account.submit_order("TCS", "BUY", 10)
        self.assertEqual(order.remaining_qty, 10)
        self.account.execute_fill(order.order_id, 3500, 4)
        self.assertEqual(order.filled_qty, 4)
        self.assertEqual(order.remaining_qty, 6)
        self.assertEqual(order.state, OrderState.PARTIALLY_FILLED)
        with self.assertRaises(ValueError):
            self.account.execute_fill(order.order_id, 3500, 7)
        self.account.execute_fill(order.order_id, 3500, 6)
        self.assertEqual(order.filled_qty, 10)
        self.assertEqual(order.remaining_qty, 0)
        self.assertEqual(order.state, OrderState.FILLED)

    def test_legal_state_machine_and_idempotent_cancel(self):
        order = self.account.submit_order("WIPRO", "BUY", 5)
        self.assertEqual(order.state, OrderState.ACCEPTED)
        self.assertEqual(self.account.cancel_order(order.order_id).state, OrderState.CANCELLED)
        self.assertEqual(self.account.cancel_order(order.order_id).state, OrderState.CANCELLED)
        with self.assertRaises(ValueError):
            self.account.execute_fill(order.order_id, 400)

    def test_order_submission_fill_and_reconciliation(self):
        order = self.account.submit_order("NIFTY", OrderSide.BUY, 2, stop_price=21500)
        self.assertEqual(order.state, OrderState.ACCEPTED)
        self.account.execute_fill(order.order_id, 22000)
        self.assertEqual(self.account.positions["NIFTY"].quantity, 2)
        self.assertTrue(self.account.reconcile().is_reconciled)

    def test_complete_trade_cycle(self):
        buy = self.account.submit_order("RELIANCE", OrderSide.BUY, 10)
        self.account.execute_fill(buy.order_id, 100)
        sell = self.account.submit_order("RELIANCE", OrderSide.SELL, 10)
        self.account.execute_fill(sell.order_id, 110)
        self.assertNotIn("RELIANCE", self.account.positions)
        self.assertGreater(self.account.realized_pnl, 90)
        report = self.account.reconcile()
        self.assertTrue(report.is_reconciled)
        self.assertAlmostEqual(report.balance_discrepancy, 0)

    def test_kill_switch_and_emergency_square_off(self):
        buy = self.account.submit_order("INFY", OrderSide.BUY, 10)
        self.account.execute_fill(buy.order_id, 1500)
        exits = self.account.emergency_square_off({"INFY": 1510})
        self.assertEqual(len(exits), 1)
        self.assertFalse(self.account.positions)
        self.assertTrue(self.account.kill_switched)
        rejected = self.account.submit_order("TCS", OrderSide.BUY, 5)
        self.assertEqual(rejected.state, OrderState.REJECTED)

    def test_buy_requires_entry_and_protective_stop_when_risk_enabled(self):
        account = VirtualAccount(starting_capital=5_000_000)
        with self.assertRaises(ValueError):
            account.submit_order("NIFTY", "BUY", 25)
        order = account.submit_order(
            "NIFTY", "BUY", 25, entry_price=22000, stop_price=21900, lot_size=25
        )
        self.assertEqual(order.state, OrderState.ACCEPTED)

    def test_manual_approval_requires_authenticated_callback(self):
        account = VirtualAccount(starting_capital=50000, trading_mode=TradingMode.MANUAL_APPROVAL,
                                 require_pretrade_risk_check=False)
        order = account.submit_order("TCS", "BUY", 1)
        self.assertEqual(order.state, OrderState.PENDING_APPROVAL)
        with self.assertRaises(PermissionError):
            account.approve_order(order.order_id)
        account.approval_authorizer = lambda actor, oid: actor == "OWNER" and oid == order.order_id
        self.assertEqual(account.approve_order(order.order_id, "OWNER").state, OrderState.ACCEPTED)

    def test_limit_orders_enforce_execution_price(self):
        order = self.account.submit_order("TCS", "BUY", 1, order_type=OrderType.LIMIT, limit_price=100)
        with self.assertRaises(ValueError):
            self.account.execute_fill(order.order_id, 101)
        self.assertEqual(self.account.execute_fill(order.order_id, 99).state, OrderState.FILLED)

    def test_mark_to_market_triggers_stop_loss(self):
        order = self.account.submit_order("TCS", "BUY", 1, stop_price=95)
        self.account.execute_fill(order.order_id, 100)
        exits = self.account.mark_to_market({"TCS": 94})
        self.assertEqual(len(exits), 1)
        self.assertFalse(self.account.positions)

    def test_durable_restart_restores_open_position_and_kill_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            first = VirtualAccount("DURABLE", 50000, require_pretrade_risk_check=False, state_dir=temp)
            buy = first.submit_order("TCS", "BUY", 2)
            first.execute_fill(buy.order_id, 100)
            first.activate_emergency_kill_switch("test")
            restored = VirtualAccount("DURABLE", 50000, require_pretrade_risk_check=False, state_dir=temp)
            self.assertEqual(restored.cash_balance, first.cash_balance)
            self.assertEqual(restored.positions["TCS"].quantity, 2)
            self.assertTrue(restored.kill_switched)
            self.assertIn(buy.order_id, restored.orders)

    def test_idempotent_fill_key_prevents_duplicate_processing(self):
        first = self.account.submit_order("TCS", "BUY", 1)
        self.account.execute_fill(first.order_id, 100, idempotency_key="fill-1")
        before = self.account.cash_balance
        self.account.execute_fill(first.order_id, 100, idempotency_key="fill-1")
        self.assertEqual(self.account.cash_balance, before)


if __name__ == "__main__":
    unittest.main()
