/* Stage63 browser-like tests on REAL Stage62 CLI and Stage61 smoke JSON.
 * No node modules beyond built-ins, no web server or browser network.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const cp = require("node:child_process");

const ROOT = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(ROOT,
  "src/nexus_titan/dashboard/static/stage63.js"), "utf8");
const elements = new Map();
const created = [];
function element(tag = "div") {
  return {
    tag, value: "", textContent: "", hidden: false, files: null,
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
vm.runInNewContext(source, { document, Error, Set }, { timeout: 2500 });

const py = process.env.PYTHON || "python";
function fixture(script) {
  const raw = cp.execFileSync(py, [path.join(ROOT, "scripts", script)], {
    cwd: ROOT, timeout: 45000, encoding: "utf8",
  });
  return JSON.parse(raw);
}
function deep(value) { return JSON.parse(JSON.stringify(value)); }
async function load(id, data) {
  const raw = typeof data === "string" ? data : JSON.stringify(data);
  e(id).files = [{
    size: Buffer.byteLength(raw), text: async () => raw,
  }];
  await e(id).handlers.change();
}
function invalid(id, other) {
  const targetError = id === "auditFile" ? "auditError" : "researchError";
  const status = id === "auditFile" ? "auditStatus" : "researchStatus";
  const untouched = other === "researchFile" ? "researchStatus" : "auditStatus";
  assert.equal(e(targetError).hidden, false);
  assert.match(e(targetError).textContent, /Local JSON rejected:/);
  assert.equal(e(status).textContent, "NOT ATTACHED");
  if (other) assert.notEqual(e(untouched).textContent, "");
}
function noRelease() {
  assert.notEqual(e("overallStatus").textContent.includes("NO-GO"), false);
  assert.notEqual(e("mainProtection").textContent, "PROTECTED · VERIFIED");
}

async function main() {
  const audit = fixture("run_stage62_integration_audit.py");
  const research = fixture("run_stage61_fo_evidence_smoke.py");
  assert.equal(audit.frozen_pr_count, 52);
  assert.equal(audit.merge_authorized, false);
  assert.equal(research.nifty.candles, 46);
  assert.equal(research.nifty.production_ready, false);

  assert.equal(e("overallStatus").textContent, "NO REPORTS ATTACHED · NOT VERIFIED");
  await load("auditFile", audit);
  assert.equal(e("auditError").hidden, true);
  assert.match(e("auditStatus").textContent, /LOCAL STRUCTURE/);
  assert.match(e("prCount").textContent, /52/);
  assert.match(e("prRoots").textContent, /1, 3/);
  assert.match(e("mainProtection").textContent, /REPORTED NO/);
  assert.match(e("diffCoverage").textContent, /UNKNOWN/);
  assert.match(e("overallStatus").textContent, /ONE LOCAL FILE/);
  assert.ok(e("auditBlockers").children.length >= 8);
  noRelease();

  await load("researchFile", research);
  assert.equal(e("researchError").hidden, true);
  assert.match(e("researchStatus").textContent, /SYNTHETIC/);
  assert.equal(e("niftyCandles").textContent, "46");
  assert.equal(e("bankniftyCandles").textContent, "46");
  assert.equal(e("niftyFolds").textContent, "3");
  assert.equal(e("bankniftyFolds").textContent, "3");
  assert.match(e("overallStatus").textContent, /TWO LOCAL FILES/);
  assert.ok(e("researchBlockers").children.length >= 8);
  assert.ok(created.every(tag => tag === "li"));
  noRelease();

  // Source-provided dangerous text must stay literal, without HTML parsing.
  const injection = "<img src=x onerror=alert(1)>";
  const xss = deep(audit);
  xss.blockers[0] = injection;
  await load("auditFile", xss);
  assert.equal(e("auditBlockers").children[0].textContent, injection);
  assert.ok(created.every(tag => tag === "li"));
  assert.match(e("mainProtection").textContent, /UNVERIFIED/);
  noRelease();

  // Wrong/forged authority is rejected, even if other fields appear valid.
  for (const mutation of [
    d => { d.production_ready = true; },
    d => { d.merge_authorized = true; },
    d => { d.independent_risk_and_execution_fenced = true; },
    d => { d.broker_orders_transmitted = 1; },
    d => { d.schema_version = 2; },
    d => { d.frozen_pr_count = -1; },
    d => { d.frozen_root_prs = []; },
    d => { d.frozen_changed_paths_complete = "yes"; },
    d => { d.blockers = []; },
    d => { d.checks = []; },
    d => { d.local_static_review_passed = true; d.local_ci_workflow_contracts_passed = false; },
    d => { d.frozen_main_sha = "not-a-sha"; },
  ]) {
    const value = deep(audit);
    mutation(value);
    await load("auditFile", value);
    invalid("auditFile", "researchFile");
    assert.equal(e("niftyCandles").textContent, "46");
  }
  await load("auditFile", audit);
  assert.equal(e("auditError").hidden, true);

  for (const mutation of [
    d => { d.production_ready = true; },
    d => { d.real_vendor_data_present = true; },
    d => { d.actual_fo_pnl_verified = true; },
    d => { d.broker_orders_transmitted = 1; },
    d => { d.nifty.production_ready = true; },
    d => { d.nifty.execution_scenario_bound_to_holdout = true; },
    d => { d.nifty.genuine_futures_options_backtest_verified = true; },
    d => { d.banknifty.strategy_promotion_authorized = true; },
    d => { d.nifty.missing_evidence = []; },
    d => { d.nifty.mandatory_release_blockers = []; },
    d => { d.nifty.candles = -1; },
    d => { d.nifty.local_evidence_sha256 = "false-digest"; },
    d => { d.nifty.synthetic_execution_fee_reserve = -0.01; },
  ]) {
    const value = deep(research);
    mutation(value);
    await load("researchFile", value);
    invalid("researchFile", "auditFile");
    assert.match(e("prCount").textContent, /52/);
  }

  const oversized = e("auditFile");
  oversized.files = [{ size: 256 * 1024 + 1, text: async () => "{}" }];
  await oversized.handlers.change();
  invalid("auditFile", "researchFile");
  await load("researchFile", research);
  await load("auditFile", audit);

  e("clearAudit").handlers.click();
  assert.equal(e("prCount").textContent, "—");
  assert.equal(e("auditFile").value, "");
  assert.match(e("overallStatus").textContent, /ONE LOCAL FILE/);
  e("clearResearch").handlers.click();
  assert.equal(e("researchStatus").textContent, "NOT ATTACHED");
  assert.equal(e("researchFile").value, "");
  assert.equal(e("overallStatus").textContent, "NO REPORTS ATTACHED · NOT VERIFIED");

  // A delayed File.text resolution after clear must not render stale data.
  let completeAudit;
  const pending = new Promise(resolve => { completeAudit = resolve; });
  e("auditFile").files = [{ size: 4096, text: () => pending }];
  const old = e("auditFile").handlers.change();
  e("clearAll").handlers.click();
  completeAudit(JSON.stringify(audit));
  await old;
  assert.equal(e("prCount").textContent, "—");
  assert.equal(e("auditError").hidden, true);

  // A newer selection must win over an older malicious response.
  let completeResearch;
  const earlier = new Promise(resolve => { completeResearch = resolve; });
  e("researchFile").files = [{ size: 4096, text: () => earlier }];
  const olderRequest = e("researchFile").handlers.change();
  await load("researchFile", research);
  completeResearch(JSON.stringify({ production_ready: true }));
  await olderRequest;
  assert.equal(e("niftyCandles").textContent, "46");
  assert.equal(e("researchError").hidden, true);
  noRelease();

  process.stdout.write("STAGE63_NODE_OFFLINE_OPERATOR_SECURITY_CHECKS_PASSED\n");
}
main().catch(error => {
  process.stderr.write(error.stack + "\n");
  process.exitCode = 2;
});
