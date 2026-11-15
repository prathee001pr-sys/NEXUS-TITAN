"""Read-only dashboard backend for NEXUS TITAN V2 + Phase 6 modules."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus_titan.dashboard.paper_read_model import (
    Stage50ReadOnlyPaperDashboard, unattached_stage50_dashboard,
)
from nexus_titan.derivatives.options_engine import calculate_option_greeks
from nexus_titan.research.backtest import compute_file_sha256, load_candles, run_backtest
from nexus_titan.research.post_mortem import generate_post_mortem
from nexus_titan.research.v6_strategies import AVAILABLE_STRATEGIES, BollingerBreakoutStrategy
from nexus_titan.research.v6_validation import rolling_walk_forward_validation, run_monte_carlo_simulation
from nexus_titan.self_improvement import TitanEvolveEngine
from nexus_titan.virtual.order_manager import VirtualAccount


class DashboardBackendService:
    """Builds dashboard views from actual local V2 account and research data."""

    def __init__(
        self, account: VirtualAccount | None = None,
        default_csv: str | Path = "data/nifty_daily_sample.csv",
        evolve_engine: TitanEvolveEngine | None = None,
        starting_capital: float | None = None,
        options_spot_price: float | None = None,
        master_orchestrator: Any | None = None,
        stage50_paper_dashboard: Stage50ReadOnlyPaperDashboard | None = None,
    ) -> None:
        if account is None:
            if starting_capital is None:
                raise ValueError("Provide an explicit VirtualAccount or starting_capital.")
            account = VirtualAccount("TITAN-MAIN-ACCOUNT", starting_capital=starting_capital)
        if options_spot_price is not None and (
            isinstance(options_spot_price, bool) or not isinstance(options_spot_price, (int, float))
            or options_spot_price <= 0
        ):
            raise ValueError("options_spot_price must be positive.")
        self.account = account
        self.default_csv = Path(default_csv)
        self.evolve_engine = evolve_engine or TitanEvolveEngine(
            # The dashboard shares the same database as the durable account only when
            # explicitly configured; default storage is local EVOLVE research state.
        )
        self.options_spot_price = float(options_spot_price) if options_spot_price is not None else None
        self.master_orchestrator = master_orchestrator
        if stage50_paper_dashboard is not None and (
            not isinstance(stage50_paper_dashboard, Stage50ReadOnlyPaperDashboard)
            or stage50_paper_dashboard.account is not account
        ):
            raise ValueError(
                "Stage50 paper read model must use the same explicit VirtualAccount instance"
            )
        self.stage50_paper_dashboard = stage50_paper_dashboard

    def get_stage50_paper_safety(self) -> dict[str, Any]:
        """Read-only optional Stage50 data contract, never a command endpoint."""
        if self.stage50_paper_dashboard is None:
            return unattached_stage50_dashboard()
        return self.stage50_paper_dashboard.snapshot()

    def get_system_telemetry(self) -> dict[str, Any]:
        reconcile = self.account.reconcile()
        module_names = [
            ("Canonical data and quality gate", "Data"),
            ("Technical indicators", "Research"),
            ("Multi-strategy engine", "Research"),
            ("Advanced backtest", "Research"),
            ("Rolling walk-forward validation", "Validation"),
            ("Monte Carlo stress testing", "Validation"),
            ("Post-mortem attribution", "Validation"),
            ("Portfolio risk sizing and circuit breakers", "Risk"),
            ("Indian statutory charge estimates", "Costs"),
            ("Options theoretical Greeks", "Derivatives"),
            ("Crypto virtual account", "Crypto"),
            ("Durable virtual account", "Execution"),
            ("AI analyst and deterministic risk veto", "Intelligence"),
            ("EVOLVE learning and governance", "Self-Improvement"),
            ("ACE and controlled Agent Runtime", "Self-Improvement"),
        ]
        modules = [{"name": name, "category": category, "status": "CODE_PRESENT_NOT_HEALTHCHECKED"}
                   for name, category in module_names]
        if self.options_spot_price is None:
            options = {"status": "WAITING_FOR_MARKET_DATA", "spot": None}
        else:
            spot = self.options_spot_price
            strike = round(spot / 50) * 50
            options = {
                "status": "INDICATIVE_INPUT_ONLY", "spot": spot, "atm_strike": strike,
                "call": asdict(calculate_option_greeks(spot, strike, 7, 0.14, option_type="CE")),
                "put": asdict(calculate_option_greeks(spot, strike, 7, 0.14, option_type="PE")),
            }
        coordinator = self.evolve_engine.create_agent_coordinator()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_mode": self.account.trading_mode.value,
            "kill_switched": self.account.kill_switched,
            "modules_online": 0, "modules_available": len(modules), "modules_total": len(modules),
            "modules": modules,
            "self_improvement": self.evolve_engine.get_status(),
            "self_improvement_agents": coordinator.status(),
            "self_improvement_capabilities": [
                {"name": "Provenance-backed learning memory", "status": "AVAILABLE"},
                {"name": "Allow-listed research ingestion", "status": "AVAILABLE", "network_enabled": False},
                {"name": "Three-fold strategy experiment runner", "status": "AVAILABLE"},
                {"name": "Market regime evidence registry", "status": "AVAILABLE", "mode": "recommendation_only"},
                {"name": "Versioned skill registry", "status": "AVAILABLE"},
                {"name": "Code-change proposal review", "status": "AVAILABLE", "mode": "manual_merge_only"},
                {"name": "12 specialist-agent runtime", "status": "AVAILABLE", "mode": "deterministic_local_supervised"},
                {"name": "Agent creation proposals", "status": "AVAILABLE", "mode": "human_review_before_registration"},
            ],
            "account": asdict(reconcile),
            "open_positions": [asdict(p) for p in self.account.positions.values()],
            "recent_orders": [o.to_dict() for o in list(self.account.orders.values())[-10:]],
            "options_analytics": options,
            "master_integration": self.get_master_integration_status(),
            "paper_safety": self.get_stage50_paper_safety(),
            "market_data": {"status": "NO_PROVIDER_CONNECTED", "live_prices": False},
            "safety": {"broker_connected": False, "live_trading_enabled": False,
                       "generated_code_execution_enabled": False},
        }


    def get_master_integration_status(self) -> dict[str, Any]:
        """Return read-only master-orchestrator health; never starts a trading cycle."""
        if self.master_orchestrator is None:
            return {
                "connected": False, "status": "NOT_ATTACHED",
                "order_submitted": False, "live_trading_enabled": False,
            }
        report = self.master_orchestrator.health_report()
        return {
            "connected": True, "status": report.status,
            "checked_at": report.checked_at,
            "components": [asdict(item) for item in report.components],
            "order_submitted": False, "live_trading_enabled": False,
        }

    def run_evolve_agent_cycle(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary.")
        outcomes = self.evolve_engine.create_agent_coordinator().run_cycle(payload or {})
        return {
            "agent_count": len(outcomes),
            "results": [item.to_dict() for item in outcomes],
            "safety": {"real_orders_placed": False, "live_trading_enabled": False,
                       "generated_code_executed": False, "production_changes_applied": False},
        }

    def run_backtest_suite(self, strategy_key: str = "bollinger") -> dict[str, Any]:
        """Run research only; dataset and options must be supplied/verified by operator."""
        if not self.default_csv.exists():
            return {"status": "DATASET_NOT_FOUND", "dataset": str(self.default_csv)}
        if strategy_key not in AVAILABLE_STRATEGIES:
            raise ValueError(f"Unknown strategy key: {strategy_key}")
        candles = load_candles(self.default_csv)
        strategy = AVAILABLE_STRATEGIES[strategy_key]()
        result = run_backtest(
            candles, starting_capital=self.account.current_capital,
            fee_per_side=20, slippage_per_side=2, signal=strategy.get_signal,
            stop_loss_pct=2, target_pct=5, use_indian_statutory_costs=True,
            instrument_type="EQUITY_DELIVERY",
        )
        _, walk = rolling_walk_forward_validation(
            candles, lambda _: (lambda i, rows: AVAILABLE_STRATEGIES[strategy_key]().get_signal(i, rows)),
            num_folds=3, min_trades_gate=5, starting_capital=self.account.current_capital,
        )
        monte = run_monte_carlo_simulation(
            [trade["pnl"] for trade in result.trade_log],
            starting_capital=self.account.current_capital, iterations=500,
        )
        post = generate_post_mortem(strategy.name, result, slippage_per_side=2)
        return {
            "status": "RESEARCH_ONLY", "strategy": strategy.name,
            "dataset_sha256": compute_file_sha256(self.default_csv),
            "candles_count": len(candles), "backtest": asdict(result),
            "walk_forward": asdict(walk), "monte_carlo": asdict(monte),
            "post_mortem": asdict(post),
            "warning": "Results are not proof of profitability; verify dataset provenance and tradability.",
        }


    def run_live_backtest_suite(self, strategy_key: str = "bollinger") -> dict[str, Any]:
        """Backward-compatible name for the historical-only backtest suite."""
        return self.run_backtest_suite(strategy_key)
