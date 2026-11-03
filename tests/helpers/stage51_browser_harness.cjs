/* Browser-like deterministic Stage51 DOM tests, no external dependencies. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const file = path.resolve(__dirname, "../../src/nexus_titan/dashboard/static/stage51.js");
const code = fs.readFileSync(file, "utf8");
const elements = new Map();
const created = [];

function element(tag = "div") {
  return {
    tag, textContent: "", value: "", hidden: false, files: null,
    children: [], handlers: {},
    addEventListener(name, fn) { this.handlers[name] = fn; },
    replaceChildren() { this.children = []; },
    appendChild(child) { this.children.push(child); },
  };
}
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  },
  createElement(tag) {
    created.push(tag);
    return element(tag);
  },
};
const e = (id) => document.getElementById(id);
vm.runInNewContext(code, { document, Intl, Date, Error }, { timeout: 1500 });

function baseline() {
  return {
    schema_version: 1, component: "TITAN_PAPER_SAFETY",
    status: "LOCAL_REVIEW_REQUIRED",
    data_source: "LOCAL_SYNTHETIC_PAPER_SQLITE_ONLY",
    checked_at_utc: "2026-11-03T07:00:00+00:00",
    theme: { theme_id: "NEXUS_TITAN_BLACK_SILVER_LOCKED" },
    account: {
      account_id: "QA-STAGE51", initial_paper_capital_cents: 5000000,
      virtual_cash_cents: 5000000, research_cash_cents: 5000000,
      combined_cash_cents: null, two_book_cash_match_observed: true,
    },
    paper_orders: { total: 1, pending_manual_approval: 1,
      approved_unfilled: 0, fill_fragments: 0, open_position_symbols: 0 },
    paper_session: {
      paper_orders_enabled_in_config: true,
      strict_manual_account: true, pretrade_risk_enabled: true,
      kill_switch_active: false,
    },
    admission_fence: {
      attempt_count: 1, latest_attempt_state: "PENDING",
      first_synthetic_buy_preflight_passed: false,
    },
    risk_veto: {configured_limits: { daily_loss_limit_pct: 3,
      max_drawdown_limit_pct: 10 }},
    signed_approval: {
      external_identity_authenticated: false,
      external_signer_verified: false,
      configured_local_verifier: true,
    },
    safety: {
      paper_order_actions_enabled: false,
      approval_actions_enabled: false,
      broker_connected: false, live_trading_enabled: false,
      production_ready: false, combined_capital_authority_verified: false,
      global_legacy_entrypoints_fenced: false,
      independent_human_identity_verified: false,
    },
    market: {
      india_fo_live_data: false, crypto_live_data: false,
      provider_identity_verified: false, latest_price: null,
    },
    blockers: ["Coordinator has a prior BUY attempt"],
  };
}

async function load(payload) {
  const raw = JSON.stringify(payload);
  e("snapshotFile").files = [{ size: Buffer.byteLength(raw), text: async () => raw }];
  await e("snapshotFile").handlers.change();
}
function blocked() {
  assert.equal(e("initialCapital").textContent, "—");
  assert.equal(e("error").hidden, false);
  assert.match(e("error").textContent, /Snapshot rejected/);
}
async function main() {
  assert.equal(e("snapshotStatus").textContent, "NO SNAPSHOT ATTACHED");
  assert.equal(e("initialCapital").textContent, "—");

  const good = baseline();
  await load(good);
  assert.equal(e("error").hidden, true);
  assert.equal(e("initialCapital").textContent, "₹50,000.00");
  assert.equal(e("virtualCash").textContent, "₹50,000.00");
  assert.equal(e("researchCash").textContent, "₹50,000.00");
  assert.equal(e("cashMatch").textContent, "LOCAL MATCH / NOT ATOMIC");
  assert.equal(e("pending").textContent, "1");
  assert.equal(e("accepted").textContent, "0");
  assert.equal(e("dailyLossLimit").textContent, "3%");
  assert.equal(e("attemptState").textContent, "PENDING");
  assert.match(e("snapshotStatus").textContent, /REVIEW REQUIRED/);

  const xss = baseline();
  const payload = '<img src=x onerror=alert(1)>';
  xss.account.account_id = payload;
  xss.blockers = [payload];
  await load(xss);
  assert.equal(e("accountId").textContent, payload);
  assert.equal(e("blockers").children[0].textContent, payload);
  assert(created.every(tag => tag === "li"));

  for (const mutate of [
    d => { d.safety.production_ready = true; },
    d => { d.safety.broker_connected = true; },
    d => { d.signed_approval.external_identity_authenticated = true; },
    d => { d.market.latest_price = 12345; },
    d => { d.market.provider_identity_verified = true; },
    d => { d.account.combined_cash_cents = 10000000; },
    d => { d.theme.theme_id = "EVIL"; },
    d => { d.data_source = "EXTERNAL_BROKER"; },
    d => { d.paper_orders.total = -1; },
    d => { d.schema_version = 2; },
    // Stage52 adversarial semantic assertions: source untrusted, reject
    // dangerous contradictions rather than creating a reassuring UI.
    d => { d.status = "LOCAL_SYNTHETIC_REVIEW_ONLY"; },
    d => { d.blockers = []; },
    d => { d.account.two_book_cash_match_observed = false; },
    d => { d.account.research_cash_cents = 5000100; },
    d => { d.admission_fence.latest_attempt_state = null; },
    d => { d.admission_fence.latest_attempt_state = "SUCCESS"; },
    d => { d.admission_fence.attempt_count = 0; },
    d => { d.admission_fence.attempt_count = true; },
    d => { d.admission_fence.first_synthetic_buy_preflight_passed = true; },
    d => { d.paper_orders.pending_manual_approval = 99; },
    d => { d.paper_orders.approved_unfilled = -1; },
    d => { d.paper_orders.fill_fragments = 1.5; },
  ]) {
    const item = baseline();
    mutate(item);
    await load(item);
    blocked();
  }
  const oversized = e("snapshotFile");
  oversized.files = [{ size: 256 * 1024 + 1, text: async () => "{}" }];
  await oversized.handlers.change();
  blocked();

  await load(good);
  e("clearSnapshot").handlers.click();
  assert.equal(e("snapshotStatus").textContent, "NO SNAPSHOT ATTACHED");
  assert.equal(e("virtualCash").textContent, "—");
  assert.equal(e("error").hidden, true);
  assert.equal(e("snapshotFile").value, "");
  // A stale async File.text response cannot restore cleared screen.
  let finishStale = null;
  const slowText = new Promise(resolve => { finishStale = resolve; });
  const slowJSON = JSON.stringify(good);
  e("snapshotFile").files = [{ size: Buffer.byteLength(slowJSON),
    text: () => slowText }];
  const obsoleteRead = e("snapshotFile").handlers.change();
  e("clearSnapshot").handlers.click();
  finishStale(slowJSON);
  await obsoleteRead;
  assert.equal(e("snapshotStatus").textContent, "NO SNAPSHOT ATTACHED");
  assert.equal(e("virtualCash").textContent, "—");

  // A newer selection wins, even if the earlier File.text() completes later.
  let resolveEarlier = null;
  const pendingEarlier = new Promise(resolve => { resolveEarlier = resolve; });
  e("snapshotFile").files = [{ size: Buffer.byteLength(slowJSON),
    text: () => pendingEarlier }];
  const oldSelection = e("snapshotFile").handlers.change();
  await load(good);
  assert.equal(e("virtualCash").textContent, "₹50,000.00");
  resolveEarlier(JSON.stringify({ schema_version: 2 }));
  await oldSelection;
  assert.equal(e("virtualCash").textContent, "₹50,000.00");
  assert.equal(e("error").hidden, true);

  process.stdout.write("STAGE51_NODE_BROWSER_SECURITY_CHECKS_PASSED\n");
}
main().catch(error => {
  process.stderr.write(error.stack + "\n");
  process.exitCode = 2;
});
