/* Stage63: static/offline untrusted local JSON viewer ONLY.
 * Does NOT authenticate files, query GitHub, contact brokers, place orders,
 * load market data or give permissions. All DOM content is text-only.
 * This is a supplementary view; the approved Stage51 layout is untouched.
 */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const record = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
  const has = (obj, key) => record(obj) && Object.hasOwn(obj, key);
  const check = (good, msg) => {
    if (!good) throw new Error(msg);
  };
  const display = (id, value) => { $(id).textContent = String(value); };
  const integer = (x, min = 0, max = 10000000) =>
    Number.isSafeInteger(x) && x >= min && x <= max;
  const short = (x, max = 200) => typeof x === "string" && x.length > 0 &&
    x.length <= max && x.trim().length > 0;
  const sha = (x) => typeof x === "string" && /^[a-f0-9]{64}$/.test(x);
  const bool = (x) => x === true || x === false;
  const boundedStrings = (items, min = 0, max = 256) =>
    Array.isArray(items) && items.length >= min && items.length <= max &&
    items.every((x) => short(x, 512));
  const putList = (id, items, fallback) => {
    const node = $(id);
    node.replaceChildren();
    const entries = items.length > 0 ? items.slice(0, 16) : [fallback];
    for (const value of entries) {
      const li = document.createElement("li");
      li.textContent = String(value).slice(0, 220);
      node.appendChild(li);
    }
    if (items.length > entries.length) {
      const li = document.createElement("li");
      li.textContent = "Additional untrusted local findings omitted from this view.";
      node.appendChild(li);
    }
  };
  const STAGE62_FALSE = [
    "github_current_state_independently_verified",
    "main_branch_protection_independently_verified",
    "independent_root_stacks_reconciled",
    "complete_file_diff_conflicts_ruled_out",
    "prospective_merged_tree_ci_verified",
    "independent_risk_and_execution_fenced",
    "one_authoritative_cross_ledger_capital_verified",
    "authenticated_real_fo_history_and_licence_verified",
    "independently_verified_human_identity",
    "owner_merge_approval_verified",
    "merge_authorized",
    "real_money_trading_enabled",
    "strategy_promotion_authorized",
    "production_ready",
  ];
  const STAGE61_FALSE = [
    "execution_scenario_bound_to_holdout",
    "genuine_futures_options_backtest_verified",
    "strategy_promotion_authorized",
    "production_ready",
  ];
  const requireFalse = (obj, flags, context) => {
    for (const name of flags) {
      check(has(obj, name) && obj[name] === false,
        context + " claims unsupported live/merge/authenticated authority.");
    }
  };
  const auditValidate = (d) => {
    check(record(d) && d.schema_version === 1 &&
      d.mode === "STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY" &&
      d.scope === "NO_MERGE_FROZEN_PR_AND_SELECTED_SOURCE_AST_CI_REVIEW_ONLY",
    "Only Stage62 CLI schema v1 audit export is accepted.");
    requireFalse(d, STAGE62_FALSE, "Stage62 file");
    check(d.merges_performed === 0 && d.broker_orders_transmitted === 0,
      "Stage62 cannot claim any merge or broker order.");
    check(integer(d.frozen_pr_count, 1, 100) &&
      sha(d.frozen_main_sha) && sha(d.frozen_pr_snapshot_sha256),
    "Invalid frozen PR metadata.");
    check(Array.isArray(d.frozen_root_prs) &&
      d.frozen_root_prs.length >= 1 && d.frozen_root_prs.length <= 100 &&
      d.frozen_root_prs.every((n) => integer(n, 1, 1000000)) &&
      new Set(d.frozen_root_prs).size === d.frozen_root_prs.length,
    "Invalid frozen main-rooted branch list.");
    for (const name of [
      "frozen_main_protected_reported", "frozen_topology_consistent",
      "frozen_changed_paths_complete", "local_source_structure_passed",
      "local_cross_module_import_contracts_passed",
      "local_ci_workflow_contracts_passed", "local_static_review_passed",
    ]) {
      check(bool(d[name]), "Missing Stage62 local-review boolean: " + name);
    }
    check(boundedStrings(d.blockers, 12, 128) &&
      boundedStrings(d.local_reviewed_legacy_entrypoints, 1, 120),
    "Missing Stage62 release blockers or bypass inventory.");
    check(Array.isArray(d.checks) && d.checks.length >= 22 &&
      d.checks.length <= 100 && d.checks.every((item) =>
        record(item) && short(item.check_id, 180) &&
        bool(item.passed) && short(item.detail, 512)),
    "Missing Stage62 reviewed import and CI evidence.");
    if (d.local_static_review_passed) {
      check(d.local_source_structure_passed &&
        d.local_cross_module_import_contracts_passed &&
        d.local_ci_workflow_contracts_passed &&
        d.checks.every((item) => item.passed) &&
        sha(d.source_subset_sha256),
      "Stage62 local structural summary contradicts its source checks.");
    } else {
      check(d.source_subset_sha256 === null || sha(d.source_subset_sha256),
        "Invalid Stage62 subset source fingerprint.");
    }
    return d;
  };
  const researchValidate = (d) => {
    check(record(d) &&
      d.mode === "STAGE61_SYNTHETIC_EVIDENCE_NO_GO_SCORECARD_ONLY",
    "Only Stage61 synthetic smoke JSON output is accepted.");
    check(d.real_vendor_data_present === false &&
      d.actual_fo_pnl_verified === false &&
      d.global_risk_and_execution_ready === false &&
      d.production_ready === false &&
      d.broker_orders_transmitted === 0,
    "Research file claims unsupported market, profit or trading readiness.");
    for (const [key, underlying] of [
      ["nifty", "NIFTY"], ["banknifty", "BANKNIFTY"],
    ]) {
      const market = d[key];
      check(record(market) && market.underlying === underlying,
        "Missing or mislabeled synthetic " + underlying + " evidence.");
      requireFalse(market, STAGE61_FALSE, underlying);
      check(market.broker_orders_transmitted === 0,
        "Broker order counter is not allowed in local research.");
      for (const n of [
        "candles", "oos_folds", "oos_predictions", "synthetic_execution_fragments",
      ]) check(integer(market[n], n === "oos_folds" ? 1 : 0, 100000),
        "Invalid synthetic market observation count.");
      check(market.oos_predictions <= market.candles &&
        market.oos_folds <= market.candles,
        "Synthetic research summary counts are inconsistent.");
      check((market.synthetic_execution_fee_reserve === null ||
        (typeof market.synthetic_execution_fee_reserve === "number" &&
         Number.isFinite(market.synthetic_execution_fee_reserve) &&
         market.synthetic_execution_fee_reserve >= 0)),
        "Invalid indicative synthetic fee reserve.");
      check(bool(market.local_inputs_structurally_consistent),
        "Missing local evidence consistency status.");
      check(market.local_inputs_structurally_consistent
        ? sha(market.local_evidence_sha256)
        : market.local_evidence_sha256 === null,
      "Research fingerprint contradicts reported structural review.");
      check(boundedStrings(market.missing_evidence, 3, 80) &&
        boundedStrings(market.mandatory_release_blockers, 8, 80),
      "Mandatory research/release blockers are missing.");
      check(market.mandatory_release_blockers.includes(
        "NO_ACTUAL_FO_PNL_OR_REALISTIC_SHADOW_FILLS"),
      "Mandatory missing real fills/P&L blocker is absent.");
    }
    return d;
  };
  let auditGeneration = 0;
  let researchGeneration = 0;
  let auditLoaded = false;
  let researchLoaded = false;
  const summary = () => {
    display("overallStatus", auditLoaded && researchLoaded
      ? "TWO LOCAL FILES LOADED · RELEASE NO-GO"
      : auditLoaded || researchLoaded
        ? "ONE LOCAL FILE LOADED · RELEASE NO-GO"
        : "NO REPORTS ATTACHED · NOT VERIFIED");
  };
  const clearAudit = () => {
    ++auditGeneration;
    auditLoaded = false;
    $("auditFile").value = "";
    $("auditError").hidden = true;
    display("auditStatus", "NOT ATTACHED");
    display("prCount", "—");
    display("prRoots", "—");
    display("mainProtection", "UNKNOWN");
    display("diffCoverage", "UNKNOWN");
    display("staticChecks", "UNVERIFIED");
    display("sourceChecks", "—");
    display("importChecks", "—");
    display("ciChecks", "—");
    putList("auditBlockers", [], "No Stage62 audit attached. Branch review not verified.");
    summary();
  };
  const clearResearch = () => {
    ++researchGeneration;
    researchLoaded = false;
    $("researchFile").value = "";
    $("researchError").hidden = true;
    display("researchStatus", "NOT ATTACHED");
    for (const id of [
      "niftyCandles", "niftyFolds", "niftyPredictions", "niftyMissing",
      "bankniftyCandles", "bankniftyFolds", "bankniftyPredictions",
      "bankniftyMissing",
    ]) display(id, "—");
    putList("researchBlockers", [],
      "No Stage61 synthetic evidence attached. No market-performance claim.");
    summary();
  };
  const renderAudit = (d) => {
    display("auditStatus", d.local_static_review_passed
      ? "LOCAL STRUCTURE CHECKED · MERGE NO-GO"
      : "LOCAL SOURCE REVIEW FAILED · MERGE NO-GO");
    display("prCount", String(d.frozen_pr_count) + " (UNTRUSTED FILE)");
    display("prRoots", d.frozen_root_prs.map(String).join(", ").slice(0, 80));
    display("mainProtection", d.frozen_main_protected_reported
      ? "REPORTED YES · UNVERIFIED" : "REPORTED NO · UNVERIFIED");
    display("diffCoverage", d.frozen_changed_paths_complete
      ? "CLAIMED COMPLETE · UNVERIFIED" : "INCOMPLETE / UNKNOWN");
    display("staticChecks", d.local_static_review_passed
      ? "LOCAL AST ONLY" : "LOCAL CHECK FAILED");
    display("sourceChecks", d.local_source_structure_passed
      ? "SOURCE SHAPE ONLY" : "FAILED / UNKNOWN");
    display("importChecks", d.local_cross_module_import_contracts_passed
      ? "LOCAL IMPORT NAMES ONLY" : "FAILED / UNKNOWN");
    display("ciChecks", d.local_ci_workflow_contracts_passed
      ? "CI CONFIG TEXT ONLY" : "FAILED / UNKNOWN");
    putList("auditBlockers", d.blockers,
      "Local file reported no blockers; independent review still required.");
    auditLoaded = true;
    $("auditError").hidden = true;
    summary();
  };
  const renderResearch = (d) => {
    display("researchStatus", "FABRICATED/SYNTHETIC ONLY · NOT PROFIT");
    for (const key of ["nifty", "banknifty"]) {
      const m = d[key];
      display(key + "Candles", String(m.candles));
      display(key + "Folds", String(m.oos_folds));
      display(key + "Predictions", String(m.oos_predictions));
      display(key + "Missing", String(m.missing_evidence.length));
    }
    const lines = [];
    for (const key of ["nifty", "banknifty"]) {
      const m = d[key];
      for (const label of m.missing_evidence.slice(0, 6)) {
        lines.push(key.toUpperCase() + " · " + label);
      }
    }
    // These eight mandatory blockers can never disappear from
    // the underlying Stage61 report; show a selection of them too.
    for (const value of d.nifty.mandatory_release_blockers.slice(0, 8)) {
      lines.push("RELEASE NO-GO · " + value);
    }
    putList("researchBlockers", lines, "No independently verified real-market evidence.");
    researchLoaded = true;
    $("researchError").hidden = true;
    summary();
  };
  const MAX_FILE_BYTES = 256 * 1024;
  const hookFile = (name, validator, renderer, reset, errorId, generation) => {
    const field = $(name);
    field.addEventListener("change", async () => {
      const selected = generation.next();
      const file = field.files && field.files[0];
      if (!file) return;
      try {
        check(file.size > 0 && file.size <= MAX_FILE_BYTES,
          "Only nonempty local JSON files up to 256 KiB are allowed.");
        const raw = await file.text();
        if (selected !== generation.current()) return;
        check(typeof raw === "string" && raw.length > 0 &&
          raw.length <= MAX_FILE_BYTES, "Invalid or oversized local JSON text.");
        const parsed = JSON.parse(raw);
        const data = validator(parsed);
        renderer(data);
      } catch (error) {
        if (selected !== generation.current()) return;
        reset();
        display(errorId, "Local JSON rejected: " +
          (error instanceof Error ? error.message.slice(0, 160) : "invalid content"));
        $(errorId).hidden = false;
      }
    });
  };
  hookFile("auditFile", auditValidate, renderAudit, clearAudit, "auditError", {
    next: () => ++auditGeneration, current: () => auditGeneration,
  });
  hookFile("researchFile", researchValidate, renderResearch,
    clearResearch, "researchError", {
      next: () => ++researchGeneration, current: () => researchGeneration,
    });
  $("clearAudit").addEventListener("click", clearAudit);
  $("clearResearch").addEventListener("click", clearResearch);
  $("clearAll").addEventListener("click", () => {
    clearAudit();
    clearResearch();
  });
  clearAudit();
  clearResearch();
})();
