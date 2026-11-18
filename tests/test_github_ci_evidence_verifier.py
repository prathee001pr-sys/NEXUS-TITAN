"""Read-only GitHub CI evidence: mocked HTTPS transport, no network or token leak."""
from dataclasses import replace
import copy
import json

import pytest

import nexus_titan.dashboard.github_ci_evidence as proof
from nexus_titan.dashboard.github_ci_evidence import (
    GitHubEvidenceBlocked, verify_github_draft_pr_ci,
)

REPO = "prathee001pr-sys/NEXUS-TITAN"
SHA = "889e9c251cebfc255c4bec9c4408a66a6c314cdd"
TOKEN = "SYNTHETIC_TEST_ONLY_NOT_A_REAL_TOKEN"
PR = 152


def make_pr():
    return {
        "number": PR,
        "state": "open",
        "draft": True,
        "merged_at": None,
        "head": {"sha": SHA, "ref": "feature/pwa-private-snapshot-atomic-bridge-2026-11-17", "repo": {"full_name": REPO}},
        "base": {"ref": "feature/pwa-readonly-research-evidence-contract-2026-11-17",
                 "sha": "a"*40, "repo": {"full_name": REPO}},
    }


def make_runs():
    names = [
        "offline-validation (3.11)", "offline-validation (3.12)",
        "offline-validation (3.13)", "Full-history credential scan",
    ]
    runs = [{"name": name, "head_sha": SHA, "status": "completed",
             "conclusion": "success", "app": {"slug": "github-actions"},
             "details_url": (f"https://github.com/{REPO}/actions/runs/"
                             f"{44111903333 if name == 'Full-history credential scan' else 44111903255}/job/{i+134139470082}")}
            for i,name in enumerate(names)]
    return {"total_count": len(runs), "check_runs": runs}


def install(monkeypatch, pr=None, runs=None, workflow_overrides=None,
            run_overrides=None, final_pr=None):
    raw_pr = make_pr() if pr is None else pr
    raw_runs = make_runs() if runs is None else runs
    workflow_overrides = workflow_overrides or {}
    run_overrides = run_overrides or {}
    pinned = dict(proof._WORKFLOW_BLOBS)
    requests = []
    pr_reads = 0

    def github(path, token):
        nonlocal pr_reads
        assert token == TOKEN
        assert path.startswith("/repos/" + REPO + "/")
        requests.append(path)
        if "/actions/runs/" in path:
            run_id = int(path.rsplit("/", 1)[1])
            target = (".github/workflows/secret-scan.yml"
                      if run_id == 44111903333 else ".github/workflows/ci.yml")
            payload = {
                "id": run_id,
                "name": ("NEXUS TITAN Secret Scan" if target.endswith("secret-scan.yml") else "NEXUS TITAN CI"),
                "path": target, "head_sha": SHA,
                "head_branch": "feature/pwa-private-snapshot-atomic-bridge-2026-11-17",
                "event": "pull_request", "status": "completed", "conclusion": "success",
                "repository": {"full_name": REPO},
                "head_repository": {"full_name": REPO},
            }
            payload.update(run_overrides.get(run_id, {}))
            return payload
        if "/check-runs?" in path:
            return copy.deepcopy(raw_runs)
        if "/contents/" in path:
            name=path.split("/contents/", 1)[1].split("?", 1)[0]
            return {"path": name, "type": "file",
                    "sha": workflow_overrides.get(name,pinned[name])}
        pr_reads += 1
        if pr_reads > 1 and final_pr is not None:
            return copy.deepcopy(final_pr)
        return copy.deepcopy(raw_pr)
    monkeypatch.setattr(proof, "_get_github_json", github)
    return requests


def verify():
    return verify_github_draft_pr_ci(
        pr_number=PR, head_sha=SHA, backend_github_token=TOKEN,
    )


def test_exact_head_authenticated_api_checks_allow_display_only(monkeypatch):
    requests = install(monkeypatch)
    result = verify()
    assert requests == [
        f"/repos/{REPO}/pulls/{PR}",
        f"/repos/{REPO}/contents/.github/workflows/ci.yml?ref={SHA}",
        f"/repos/{REPO}/contents/.github/workflows/secret-scan.yml?ref={SHA}",
        f"/repos/{REPO}/commits/{SHA}/check-runs?per_page=100",
        f"/repos/{REPO}/actions/runs/44111903255",
        f"/repos/{REPO}/actions/runs/44111903333",
        f"/repos/{REPO}/pulls/{PR}",
    ]
    assert result.repository == REPO
    assert result.head_sha == SHA and result.pr_number == PR
    assert result.github_actions_check_count == 4
    assert result.workflow_run_count == 2
    assert len(result.checks_verified) == 4
    assert result.github_api_source_checked is True
    assert result.status == "VERIFIED_GITHUB_CI_ONLY_NOT_PRODUCTION"
    assert result.production_ready is False
    assert result.live_trading_authorized is False
    assert result.owner_pwa_session_authenticated is False
    assert result.global_independent_risk_veto_verified is False
    assert TOKEN not in repr(result)


@pytest.mark.parametrize("pr,sha", [
    (True, SHA), (0, SHA), (10_000_001, SHA), ("152", SHA),
    (PR, "a"*39), (PR, "A"*40), (PR, "../evil"), (PR, None),
])
def test_injection_and_invalid_identifiers_refused_before_network(pr, sha, monkeypatch):
    def never(*args):
        raise AssertionError("No network for bad identifier")
    monkeypatch.setattr(proof, "_get_github_json", never)
    with pytest.raises(GitHubEvidenceBlocked):
        verify_github_draft_pr_ci(
            pr_number=pr, head_sha=sha, backend_github_token=TOKEN,
        )


@pytest.mark.parametrize("field,value", [
    ("state", "closed"),
    ("draft", False),
    ("merged_at", "2026-11-17T00:00:00Z"),
    ("number", True),
    ("head", {}),
    ("base", {}),
])
def test_closed_merged_wrong_type_or_missing_pr_metadata_fails_closed(monkeypatch,field,value):
    p=make_pr()
    p[field]=value
    install(monkeypatch,pr=p)
    with pytest.raises(GitHubEvidenceBlocked):
        verify()


@pytest.mark.parametrize("target", ["head_repo", "base_repo", "head_sha"])
def test_wrong_repository_or_head_ancestry_cannot_reuse_green_checks(monkeypatch,target):
    p=make_pr()
    if target=="head_repo":
        p["head"]["repo"]["full_name"]="attacker/evil"
    elif target=="base_repo":
        p["base"]["repo"]["full_name"]="attacker/evil"
    else:
        p["head"]["sha"]="f"*40
    install(monkeypatch,pr=p)
    with pytest.raises(GitHubEvidenceBlocked,match="exact-head"):
        verify()


@pytest.mark.parametrize("status,conclusion", [
    ("in_progress", None), ("completed", "failure"),
    ("completed", "cancelled"), ("queued", None),
])
def test_pending_failing_cancelled_ci_never_green(monkeypatch,status,conclusion):
    data=make_runs()
    data["check_runs"][1].update(status=status,conclusion=conclusion)
    install(monkeypatch,runs=data)
    with pytest.raises(GitHubEvidenceBlocked,match="pending or failing"):
        verify()


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml", ".github/workflows/secret-scan.yml",
])
def test_edited_green_workflow_rejected_even_with_successful_checks(monkeypatch,path):
    install(monkeypatch, workflow_overrides={path:"0"*40})
    with pytest.raises(GitHubEvidenceBlocked,match="workflow content"):
        verify()


def test_missing_secret_scan_is_not_ci_approval(monkeypatch):
    runs=make_runs()
    runs["check_runs"].pop()
    runs["total_count"]=3
    install(monkeypatch,runs=runs)
    with pytest.raises(GitHubEvidenceBlocked):
        verify()


@pytest.mark.parametrize("damage", ["app", "sha", "missing", "number", "truncated", "extra_failed"])
def test_check_run_provider_pagination_and_unknown_failure_denied(monkeypatch,damage):
    runs=make_runs()
    if damage=="app":
        runs["check_runs"][0]["app"]={"slug":"untrusted"}
    elif damage=="sha":
        runs["check_runs"][0]["head_sha"]="0"*40
    elif damage=="missing":
        runs["check_runs"][0].pop("app")
    elif damage=="number":
        runs["total_count"]=True
    elif damage=="truncated":
        runs["total_count"]=101
    else:
        runs["check_runs"].append({
            "name":"security-review","head_sha":SHA,"status":"completed",
            "conclusion":"failure","app":{"slug":"github-actions"}
        })
        runs["total_count"]=5
    install(monkeypatch,runs=runs)
    with pytest.raises(GitHubEvidenceBlocked):
        verify()


@pytest.mark.parametrize("damage", [
    {"path": ".github/workflows/evil.yml"},
    {"name": "NEXUS TITAN CI but forged"},
    {"head_sha": "0"*40},
    {"head_branch": "main"},
    {"status": "in_progress", "conclusion": None},
    {"conclusion": "failure"},
    {"event": "workflow_dispatch"},
    {"head_repository": {"full_name": "other/repo"}},
])
def test_workflow_run_must_match_exact_path_commit_branch_and_source(monkeypatch,damage):
    install(monkeypatch, run_overrides={44111903255: damage})
    with pytest.raises(GitHubEvidenceBlocked,match="workflow run identity"):
        verify()


def test_forged_green_check_name_from_unreviewed_workflow_denied(monkeypatch):
    raw=make_runs()
    raw["check_runs"][0]["details_url"] = (
        f"https://github.com/{REPO}/actions/runs/999999/job/123456"
    )
    install(monkeypatch,runs=raw,run_overrides={999999:{
        "path": ".github/workflows/attacker.yml", "name": "Fake CI",
    }})
    with pytest.raises(GitHubEvidenceBlocked,match="workflow run identity"):
        verify()


def test_duplicate_workflow_checks_accepted_only_when_all_succeed(monkeypatch):
    runs=make_runs()
    runs["check_runs"]+=copy.deepcopy(runs["check_runs"])
    runs["total_count"]=8
    install(monkeypatch,runs=runs)
    assert verify().github_actions_check_count==8
    runs["check_runs"][-1]["conclusion"]="failure"
    install(monkeypatch,runs=runs)
    with pytest.raises(GitHubEvidenceBlocked):
        verify()


def test_missing_private_token_is_rejected_and_never_written(monkeypatch):
    monkeypatch.setattr(proof.urllib.request,"build_opener",
                        lambda *args: (_ for _ in ()).throw(AssertionError("Network called")))
    for token in ("", "contains spaces", "contains\nnewline", None):
        with pytest.raises(GitHubEvidenceBlocked) as error:
            proof._get_github_json(f"/repos/{REPO}/pulls/{PR}",token)
        assert not token or str(token) not in str(error.value)


def test_fixed_host_https_transport_and_no_redirect_policy(monkeypatch):
    actual={}
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*args): return None
        def geturl(self): return actual["url"]
        def read(self,max_bytes):
            assert max_bytes==512001
            return json.dumps(make_pr()).encode()
    class Opener:
        def open(self,request,timeout):
            actual["url"]=request.full_url
            actual["method"]=request.get_method()
            actual["timeout"]=timeout
            actual["accept"]=request.get_header("Accept")
            actual["auth"]=request.get_header("Authorization")
            return Response()
    monkeypatch.setattr(proof.urllib.request,"build_opener",
                        lambda *args: Opener())
    output=proof._get_github_json(f"/repos/{REPO}/pulls/{PR}",TOKEN)
    assert output["head"]["sha"]==SHA
    assert actual["url"]==f"https://api.github.com/repos/{REPO}/pulls/{PR}"
    assert actual["method"]=="GET" and actual["timeout"]==12
    assert actual["auth"]=="Bearer "+TOKEN


def test_deny_redirect_and_arbitrary_resource_paths():
    blocker=proof._NoRedirect()
    with pytest.raises(GitHubEvidenceBlocked):
        blocker.redirect_request(None,None,302,"Found",{},"https://evil.example/")
    with pytest.raises(GitHubEvidenceBlocked):
        proof._get_github_json("/repos/other/repo/pulls/1",TOKEN)


def test_evidence_dataclass_cannot_be_used_to_assert_live_permissions(monkeypatch):
    install(monkeypatch)
    evidence=verify()
    for attr in ("live_trading_authorized","production_ready",
                 "owner_pwa_session_authenticated","global_independent_risk_veto_verified"):
        with pytest.raises(GitHubEvidenceBlocked):
            replace(evidence,**{attr:True})


def test_duplicate_json_keys_and_oversized_https_body_are_rejected(monkeypatch):
    replies = [b'{"state":"open","state":"closed"}', b"x" * 512001]
    class Response:
        status = 200
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def geturl(self): return f"https://api.github.com/repos/{REPO}/pulls/{PR}"
        def read(self, count): return self.data[:count]
    class Opener:
        def open(self, request, timeout): return Response(replies.pop(0))
    monkeypatch.setattr(proof.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(GitHubEvidenceBlocked):
        proof._get_github_json(f"/repos/{REPO}/pulls/{PR}", TOKEN)
    with pytest.raises(GitHubEvidenceBlocked, match="Oversized"):
        proof._get_github_json(f"/repos/{REPO}/pulls/{PR}", TOKEN)


def test_https_response_host_mismatch_does_not_consume_untrusted_json(monkeypatch):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def geturl(self): return "https://hostile.example/api"
        def read(self, count): raise AssertionError("Must reject host before reading")
    class Opener:
        def open(self, request, timeout): return Response()
    monkeypatch.setattr(proof.urllib.request,"build_opener",lambda *a: Opener())
    with pytest.raises(GitHubEvidenceBlocked, match="response origin"):
        proof._get_github_json(f"/repos/{REPO}/pulls/{PR}", TOKEN)


@pytest.mark.parametrize("change", [
    "head_sha", "head_ref", "base_sha", "base_ref",
    "head_repo", "base_repo", "closed", "merged", "not_draft", "pr_number",
])
def test_pr_changed_during_checks_is_rejected_at_final_read(monkeypatch, change):
    final=make_pr()
    if change=="head_sha":
        final["head"]["sha"]="f"*40
    elif change=="head_ref":
        final["head"]["ref"]="feature/replaced"
    elif change=="base_sha":
        final["base"]["sha"]="b"*40
    elif change=="base_ref":
        final["base"]["ref"]="feature/new-base"
    elif change=="head_repo":
        final["head"]["repo"]["full_name"]="unknown/fork"
    elif change=="base_repo":
        final["base"]["repo"]["full_name"]="unknown/fork"
    elif change=="closed":
        final["state"]="closed"
    elif change=="merged":
        final["merged_at"]="2026-11-17T20:00:00Z"
    elif change=="not_draft":
        final["draft"]=False
    elif change=="pr_number":
        final["number"]=153
    requests=install(monkeypatch,final_pr=final)
    with pytest.raises(GitHubEvidenceBlocked,match="PR revision changed"):
        verify()
    assert requests.count(f"/repos/{REPO}/pulls/{PR}") == 2


@pytest.mark.parametrize("change", [
    "missing_sha", "bad_sha", "bool_sha", "missing_head_ref",
    "missing_base_ref", "wrong_head_ref_type", "wrong_base_ref_type",
])
def test_initial_pr_revision_identity_must_be_complete(monkeypatch, change):
    initial=make_pr()
    if change=="missing_sha":
        initial["base"].pop("sha")
    elif change=="bad_sha":
        initial["base"]["sha"]="missing"
    elif change=="bool_sha":
        initial["base"]["sha"]=True
    elif change=="missing_head_ref":
        initial["head"]["ref"]=""
    elif change=="missing_base_ref":
        initial["base"]["ref"]=""
    elif change=="wrong_head_ref_type":
        initial["head"]["ref"]=4
    elif change=="wrong_base_ref_type":
        initial["base"]["ref"]=[]
    requests=install(monkeypatch,pr=initial)
    with pytest.raises(GitHubEvidenceBlocked,match="exact-head"):
        verify()
    assert len(requests)==1


def test_stable_pr_is_read_twice_and_result_is_still_display_only(monkeypatch):
    first=make_pr()
    last=copy.deepcopy(first)
    requests=install(monkeypatch, pr=first, final_pr=last)
    evidence=verify()
    assert requests[0]==requests[-1]==f"/repos/{REPO}/pulls/{PR}"
    assert evidence.head_sha==SHA
    assert evidence.owner_pwa_session_authenticated is False
    assert evidence.global_independent_risk_veto_verified is False
    assert evidence.production_ready is False
    assert evidence.live_trading_authorized is False
