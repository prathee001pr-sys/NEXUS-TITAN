"""Stage 205: Indian F&O dataset intake checkpoint, fail-closed for real-world use.

Structural QA is not exchange, provider, licence or production backtest proof.
This function never authorizes real-market performance claims or any trades.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re
from datetime import datetime

from .stage201_fo_catalog_inventory import FOCatalogInventoryReceipt
from .stage202_fo_contract_master_review import FOContractMasterReceipt
from .stage203_fo_source_integrity import FOSourceIntegrityReceipt
from .stage204_fo_temporal_embargo import FOTemporalEmbargoReceipt
from .stage200_synthetic_no_go_gate import SyntheticNoGoReceipt

_HEX = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class FODataReadinessReceipt:
    eligible_for_internal_manual_dataset_review: bool
    linked_evidence_sha256: str
    blockers: tuple[str, ...]
    independent_vendor_authenticated: bool = False
    source_licence_authenticated: bool = False
    exchange_metadata_authenticated: bool = False
    exchange_calendar_authenticated: bool = False
    real_historical_data_verified: bool = False
    real_market_backtest_verified: bool = False
    live_trading_authorized: bool = False
    autonomous_execution_authorized: bool = False
    strategy_promotion_authorized: bool = False


def evaluate_fo_data_readiness(
    *, inventory: FOCatalogInventoryReceipt, contracts: FOContractMasterReceipt,
    sources: FOSourceIntegrityReceipt, temporal: FOTemporalEmbargoReceipt,
    synthetic_baseline: SyntheticNoGoReceipt,
    live_requested: bool = False, autonomous_requested: bool = False,
    promotion_requested: bool = False,
) -> FODataReadinessReceipt:
    def digest(s: object) -> bool:
        return isinstance(s, str) and bool(_HEX.fullmatch(s))

    checks = {
        'linked Stage201 catalog': type(inventory) is FOCatalogInventoryReceipt
            and inventory.accepted_structurally is True and not inventory.blockers
            and digest(inventory.inventory_sha256) and inventory.snapshot_count > 0
            and bool(inventory.dataset_ids) and inventory.live_trading_authorized is False
            and digest(inventory.source_manifest_sha256) and bool(inventory.underlyings)
            and len(inventory.observation_windows) == len(inventory.dataset_ids),
        'Stage202 contract metadata': type(contracts) is FOContractMasterReceipt
            and contracts.accepted_structurally is True and not contracts.blockers
            and digest(contracts.contract_master_sha256) and bool(contracts.underlyings)
            and contracts.live_trading_authorized is False,
        'contract underlying matches catalog': type(inventory) is FOCatalogInventoryReceipt
            and type(contracts) is FOContractMasterReceipt
            and type(inventory.underlyings) is tuple and type(contracts.underlyings) is tuple
            and bool(inventory.underlyings) and set(inventory.underlyings).issubset(set(contracts.underlyings)),
        'Stage203 on-disk source bytes': type(sources) is FOSourceIntegrityReceipt
            and sources.accepted_byte_integrity is True and not sources.blockers
            and digest(sources.source_sha256) and sources.file_count > 0
            and sources.live_trading_authorized is False and digest(sources.source_manifest_sha256),
        'Stage201/203 source hashes agree': type(inventory) is FOCatalogInventoryReceipt
            and type(sources) is FOSourceIntegrityReceipt
            and bool(inventory.source_manifest_sha256)
            and inventory.source_manifest_sha256 == sources.source_manifest_sha256,
        'Stage204 holdout and embargo': type(temporal) is FOTemporalEmbargoReceipt
            and temporal.accepted_structurally is True and not temporal.blockers
            and digest(temporal.temporal_sha256) and temporal.train_count >= 2
            and temporal.holdout_count >= 2 and temporal.live_trading_authorized is False
            and len(temporal.observation_windows) == len(temporal.dataset_ids),
        'same dataset IDs across checks': type(inventory) is FOCatalogInventoryReceipt
            and type(sources) is FOSourceIntegrityReceipt and type(temporal) is FOTemporalEmbargoReceipt
            and bool(inventory.dataset_ids) and inventory.dataset_ids == sources.dataset_ids == temporal.dataset_ids,
        'Stage200 synthetic-only NO-GO baseline': type(synthetic_baseline) is SyntheticNoGoReceipt
            and synthetic_baseline.eligible_for_offline_synthetic_review is True
            and not synthetic_baseline.blockers and digest(synthetic_baseline.synthetic_evidence_sha256)
            and synthetic_baseline.live_trading_authorized is False
            and synthetic_baseline.autonomous_execution_authorized is False
            and synthetic_baseline.strategy_promotion_authorized is False,
        'live trading prohibited': live_requested is False,
        'autonomous execution prohibited': autonomous_requested is False,
        'strategy promotion prohibited': promotion_requested is False,
    }
    # Compare timezone-aware ISO UTC windows only after typed receipts exist.
    bounds_ok = False
    if (type(inventory) is FOCatalogInventoryReceipt and type(temporal) is FOTemporalEmbargoReceipt
            and inventory.observation_windows and temporal.observation_windows):
        try:
            catalog_bounds = {ds: (datetime.fromisoformat(start),datetime.fromisoformat(end))
                              for ds,start,end in inventory.observation_windows}
            test_bounds = {ds: (datetime.fromisoformat(start),datetime.fromisoformat(end))
                           for ds,start,end in temporal.observation_windows}
            bounds_ok = (set(catalog_bounds)==set(test_bounds)
                         and all(catalog_bounds[ds][0].utcoffset() is not None
                                 and test_bounds[ds][0].utcoffset() is not None
                                 and catalog_bounds[ds][1].utcoffset() is not None
                                 and test_bounds[ds][1].utcoffset() is not None
                                 and catalog_bounds[ds][0] <= test_bounds[ds][0] <= test_bounds[ds][1] <= catalog_bounds[ds][1]
                                 for ds in catalog_bounds))
        except (ValueError, TypeError, KeyError):
            pass
    checks['holdout timestamps inside catalog windows'] = bounds_ok
    blockers = tuple(name for name, valid in checks.items() if not valid)
    evidence = ''
    if not blockers:
        body = {'stage201':inventory.inventory_sha256, 'stage202':contracts.contract_master_sha256,
                'stage203':sources.source_sha256, 'stage204':temporal.temporal_sha256,
                'stage200':synthetic_baseline.synthetic_evidence_sha256,
                'scope':'manual_internal_structural_qa_only'}
        evidence = hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return FODataReadinessReceipt(not blockers, evidence, blockers)
