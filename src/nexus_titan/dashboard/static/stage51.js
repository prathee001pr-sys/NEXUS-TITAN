/* Stage51 offline local Stage50 JSON renderer.
 * This script is a VISUALIZER, not a market or broker client.
 * Only local JSON file input is accepted. No network APIs, HTML injection,
 * trade/approval commands, credentials, image downloads or telemetry calls.
 */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const path = (obj, ...parts) => {
    let value = obj;
    for (const key of parts) {
      if (!record(value)) return undefined;
      value = Object.hasOwn(value, key) ? value[key] : undefined;
    }
    return value;
  };
  const cents = (v) => v === null ? null :
    (Number.isSafeInteger(v) && v >= 0 ? v : null);
  const count = (v) => Number.isSafeInteger(v) && v >= 0 ? String(v) : "—";
  const currency = (v) => {
    const amount = cents(v);
    if (amount === null) return "—";
    return "₹" + new Intl.NumberFormat("en-IN", {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(amount / 100);
  };
  const fmtPercent = (v) =>
    (typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 100)
      ? String(v) + "%" : "—";
  const formatTime = (v) => {
    if (typeof v !== "string" || v.length > 60) return "—";
    const date = new Date(v);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("en-IN");
  };
  const put = (id, text) => { byId(id).textContent = String(text); };
  const flags = [
    ["safety", "paper_order_actions_enabled"],
    ["safety", "approval_actions_enabled"],
    ["safety", "broker_connected"],
    ["safety", "live_trading_enabled"],
    ["safety", "production_ready"],
    ["safety", "combined_capital_authority_verified"],
    ["safety", "global_legacy_entrypoints_fenced"],
    ["safety", "independent_human_identity_verified"],
    ["signed_approval", "external_identity_authenticated"],
    ["signed_approval", "external_signer_verified"],
    ["market", "india_fo_live_data"],
    ["market", "crypto_live_data"],
    ["market", "provider_identity_verified"],
  ];
  const validate = (d) => {
    assert(record(d), "Snapshot must be a JSON object.");
    assert(d.schema_version === 1 && d.component === "TITAN_PAPER_SAFETY",
      "Only Stage50 paper-safety schema v1 is supported.");
    assert(d.data_source === "LOCAL_SYNTHETIC_PAPER_SQLITE_ONLY",
      "No trusted local Stage50 data source declared.");
    assert(["LOCAL_REVIEW_REQUIRED", "LOCAL_SYNTHETIC_REVIEW_ONLY"].includes(d.status),
      "Snapshot has an unknown review state.");
    assert(path(d, "theme", "theme_id") === "NEXUS_TITAN_BLACK_SILVER_LOCKED",
      "Snapshot does not match the approved TITAN theme.");
    for (const [section, field] of flags) {
      assert(path(d, section, field) === false,
        "Snapshot claims unsupported real trading or external security authority.");
    }
    assert(path(d, "market", "latest_price") === null,
      "External market quotes are not accepted by the offline reader.");
    assert(path(d, "account", "combined_cash_cents") === null,
      "Combined independent-book cash is not supported.");
    for (const section of ["account", "paper_orders", "paper_session",
      "admission_fence", "risk_veto", "signed_approval", "safety", "market"]) {
      assert(record(d[section]), "A required paper safety section is missing.");
    }
    assert(Array.isArray(d.blockers) && d.blockers.length <= 100,
      "Blocker list must be a bounded array.");
    for (const field of ["initial_paper_capital_cents", "virtual_cash_cents",
      "research_cash_cents"]) {
      const v = d.account[field];
      assert(v === null || cents(v) !== null, "Invalid account capital value.");
    }
    assert(
      d.paper_orders.total === null ||
      (Number.isSafeInteger(d.paper_orders.total) && d.paper_orders.total >= 0),
      "Invalid paper-order count."
    );
    assert(path(d, "paper_session", "paper_orders_enabled_in_config") === true ||
      path(d, "paper_session", "paper_orders_enabled_in_config") === false,
      "Paper session status missing.");
    // Stage52: reject internally inconsistent *presentation* assertions.
    // All values still come from an UNAUTHENTICATED local JSON file. These
    // checks are NOT a cryptographic source-authenticity or trade admission.
    const a = d.account, po = d.paper_orders, ps = d.paper_session;
    const fence = d.admission_fence;
    for (const field of ["total", "pending_manual_approval", "approved_unfilled",
        "fill_fragments", "open_position_symbols"]) {
      const v = po[field];
      assert(v === null || (Number.isSafeInteger(v) && v >= 0),
        "Paper order/position counts must be non-negative integers or unknown.");
    }
    if (po.total !== null && po.pending_manual_approval !== null &&
        po.approved_unfilled !== null) {
      assert(po.pending_manual_approval + po.approved_unfilled <= po.total,
        "Paper order counts contradict reported totals.");
    }
    assert(Number.isSafeInteger(fence.attempt_count) && fence.attempt_count >= 0,
      "Coordinator attempt count missing or invalid.");
    assert(fence.attempt_count === 0
      ? fence.latest_attempt_state === null
      : ["PREPARING", "PENDING", "UNKNOWN"].includes(fence.latest_attempt_state),
      "Coordinator marker state is inconsistent.");
    assert(fence.first_synthetic_buy_preflight_passed !== true ||
      fence.attempt_count === 0,
      "Cannot claim first-entry preflight after durable attempted admission.");
    const cashMatch = cents(a.virtual_cash_cents) !== null &&
      cents(a.research_cash_cents) !== null &&
      cents(a.initial_paper_capital_cents) !== null &&
      a.virtual_cash_cents === a.research_cash_cents &&
      a.virtual_cash_cents === a.initial_paper_capital_cents;
    assert(a.two_book_cash_match_observed === cashMatch,
      "Cash-match claim contradicts displayed separate balances.");
    if (d.status === "LOCAL_SYNTHETIC_REVIEW_ONLY") {
      assert(d.blockers.length === 0 && cashMatch &&
        fence.attempt_count === 0 && fence.coordinator_bound === true &&
        ps.paper_orders_enabled_in_config === true &&
        ps.kill_switch_active === false &&
        ps.strict_manual_account === true && ps.gateway_only === true &&
        ps.pretrade_risk_enabled === true &&
        d.signed_approval.configured_local_verifier === true,
        "Green local presentation contradicts unresolved paper safety blockers.");
    } else {
      assert(d.blockers.length > 0,
        "Local review warning must disclose an outstanding blocker.");
    }
    return d;
  };
  const showBlockers = (items) => {
    const list = byId("blockers");
    list.replaceChildren();
    const safe = items.slice(0, 18).filter(item => typeof item === "string");
    if (safe.length === 0) {
      safe.push("No local blockers reported. External identity, real feeds and global risk remain UNVERIFIED.");
    }
    for (const message of safe) {
      const li = document.createElement("li");
      li.textContent = message.slice(0, 200);
      list.appendChild(li);
    }
    if (items.length > safe.length) {
      const li = document.createElement("li");
      li.textContent = "More local blockers omitted from visual summary.";
      list.appendChild(li);
    }
  };
  const reset = () => {
    byId("error").hidden = true;
    put("snapshotStatus", "NO SNAPSHOT ATTACHED");
    put("observedAt", "Last observed: —");
    for (const id of ["initialCapital", "virtualCash", "researchCash", "accountId",
      "pending", "accepted", "fills", "riskGuard", "dailyLossLimit",
      "drawdownLimit", "killSwitch", "signedGate", "attemptCount",
      "attemptState", "firstEntry"]) put(id, "—");
    put("cashMatch", "NOT VERIFIED");
    showBlockers(["No snapshot attached. Nothing has been verified."]);
    byId("snapshotFile").value = "";
  };
  const render = (input) => {
    const d = validate(input);
    const a = d.account;
    const po = d.paper_orders;
    const ps = d.paper_session;
    const adm = d.admission_fence;
    const risk = d.risk_veto;
    put("snapshotStatus", d.status === "LOCAL_REVIEW_REQUIRED"
      ? "LOCAL REVIEW REQUIRED · NO TRADE AUTHORITY"
      : "LOCAL SNAPSHOT LOADED · NOT EXTERNALLY VERIFIED");
    put("observedAt", "File timestamp (untrusted): " + formatTime(d.checked_at_utc));
    put("initialCapital", currency(a.initial_paper_capital_cents));
    put("virtualCash", currency(a.virtual_cash_cents));
    put("researchCash", currency(a.research_cash_cents));
    put("accountId", typeof a.account_id === "string" ? a.account_id.slice(0, 72) : "—");
    put("cashMatch", a.two_book_cash_match_observed === true ?
      "LOCAL MATCH / NOT ATOMIC" : "MISMATCH / UNVERIFIED");
    put("pending", count(po.pending_manual_approval));
    put("accepted", count(po.approved_unfilled));
    put("fills", count(po.fill_fragments));
    put("riskGuard", ps.pretrade_risk_enabled === true && ps.strict_manual_account === true
      ? "CONFIGURED LOCALLY" : "NOT VERIFIED");
    put("dailyLossLimit", fmtPercent(path(risk, "configured_limits", "daily_loss_limit_pct")));
    put("drawdownLimit", fmtPercent(path(risk, "configured_limits", "max_drawdown_limit_pct")));
    put("killSwitch", ps.kill_switch_active === true ? "ACTIVE" :
      ps.kill_switch_active === false ? "NOT ACTIVE (LOCAL)" : "UNKNOWN");
    put("signedGate", d.signed_approval.configured_local_verifier === true
      ? "LOCAL CALLBACK ONLY" : "NOT VERIFIED");
    put("attemptCount", count(adm.attempt_count));
    put("attemptState", typeof adm.latest_attempt_state === "string" ?
      adm.latest_attempt_state.slice(0, 40) : "NONE / UNKNOWN");
    put("firstEntry", adm.first_synthetic_buy_preflight_passed === true ?
      "LOCAL PREFLIGHT ONLY" : "BLOCKED / NOT VERIFIED");
    showBlockers(d.blockers);
    byId("error").hidden = true;
  };
  const fileInput = byId("snapshotFile");
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    try {
      assert(file.size > 0 && file.size <= 256 * 1024,
        "Only nonempty Stage50 JSON files up to 256 KiB are accepted.");
      const data = JSON.parse(await file.text());
      render(data);
    } catch (err) {
      reset();
      put("error", "Snapshot rejected: " + (err instanceof Error ? err.message : "Invalid file"));
      byId("error").hidden = false;
    }
  });
  byId("clearSnapshot").addEventListener("click", reset);
  reset();
})();
