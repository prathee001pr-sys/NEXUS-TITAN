"""Read-only GitHub API CI evidence for a specified NEXUS TITAN Draft PR.

Server-side research status only. This is NOT PWA owner authentication, a
signed trading permit, an execution gateway, or production readiness.
Call only from a trusted environment; NEVER send the GitHub token to a PWA.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

_REPO = "prathee001pr-sys/NEXUS-TITAN"
_ORIGIN = "https://api.github.com"
_REQUIRED = (
    "offline-validation (3.11)",
    "offline-validation (3.12)",
    "offline-validation (3.13)",
    "Full-history credential scan",
)
_MAX_RESPONSE = 512_000
# Exact independently reviewed Stage152 workflow file Git blob identities.
# A feature-branch PR that weakens its own CI or Secret Scan must fail closed.
_WORKFLOW_BLOBS = {
    ".github/workflows/ci.yml": "72233c01d390f62238bd723d4eb7a80c6547955e",
    ".github/workflows/secret-scan.yml": "6257dfd768f1d12c768982350c340568ad51c0d9",
}


class GitHubEvidenceBlocked(ValueError):
    """A remote result is missing, ambiguous, unsafe, or not verified."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitHubEvidenceBlocked("Redirected GitHub API evidence refused")


def _reject_duplicate_keys(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise GitHubEvidenceBlocked("Ambiguous GitHub API JSON")
        result[name] = value
    return result


def _get_github_json(path: str, token: str) -> dict:
    """Hard-coded HTTPS GitHub API host, bounded read and no redirect following."""
    if (type(token) is not str or not 8 <= len(token) <= 4096
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)):
        raise GitHubEvidenceBlocked("Backend-only GitHub credential required")
    if (not path.startswith("/repos/" + _REPO + "/")
            or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_?=&.-"
                   for c in path)):
        raise GitHubEvidenceBlocked("Unapproved GitHub API path")
    url = _ORIGIN + path
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nexus-titan-private-research-ci-verifier",
    }, method="GET")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=12) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if (final.scheme != "https" or final.hostname != "api.github.com"
                    or final.port not in (None, 443)
                    or response.status != 200):
                raise GitHubEvidenceBlocked("Untrusted GitHub API response origin")
            body = response.read(_MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Never include urllib exception text: proxies/errors may leak headers.
        raise GitHubEvidenceBlocked("GitHub API unavailable or refused") from None
    if len(body) > _MAX_RESPONSE:
        raise GitHubEvidenceBlocked("Oversized GitHub API response")
    try:
        payload = json.loads(body, object_pairs_hook=_reject_duplicate_keys)
    except (ValueError, UnicodeDecodeError, TypeError):
        raise GitHubEvidenceBlocked("Invalid GitHub API response JSON") from None
    if type(payload) is not dict:
        raise GitHubEvidenceBlocked("GitHub API object required")
    return payload


@dataclass(frozen=True, slots=True)
class GitHubPRCIEvidence:
    repository: str
    pr_number: int
    head_sha: str
    checks_verified: tuple[str, ...]
    github_actions_check_count: int
    workflow_run_count: int = 0
    status: str = "VERIFIED_GITHUB_CI_ONLY_NOT_PRODUCTION"
    github_api_source_checked: bool = True
    owner_pwa_session_authenticated: bool = False
    production_ready: bool = False
    live_trading_authorized: bool = False
    global_independent_risk_veto_verified: bool = False

    def __post_init__(self):
        # This is a DISPLAY-ONLY record. Constructing a Python object is never
        # proof of a GitHub API call; consumers must use the verifier function.
        if (self.production_ready is not False
                or self.live_trading_authorized is not False
                or self.owner_pwa_session_authenticated is not False
                or self.global_independent_risk_veto_verified is not False):
            raise GitHubEvidenceBlocked("CI evidence never authorizes production")


def verify_github_draft_pr_ci(*, pr_number: int, head_sha: str,
                              backend_github_token: str) -> GitHubPRCIEvidence:
    """Check trusted GitHub REST PR+Actions evidence, fail closed on ambiguity.

    A token must be supplied only in a trusted backend process, never through
    user-submitted PWA JSON. No token is stored, returned, or printed.
    """
    if type(pr_number) is not int or not 1 <= pr_number <= 10_000_000:
        raise GitHubEvidenceBlocked("Invalid PR number")
    if type(head_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
        raise GitHubEvidenceBlocked("Exact lowercase Git commit SHA required")
    pr = _get_github_json(f"/repos/{_REPO}/pulls/{pr_number}", backend_github_token)
    h = pr.get("head")
    b = pr.get("base")
    if (pr.get("number") != pr_number or type(pr.get("number")) is not int
            or pr.get("state") != "open" or pr.get("draft") is not True
            or pr.get("merged_at") is not None
            or type(h) is not dict or type(b) is not dict
            or h.get("sha") != head_sha
            or type(h.get("repo")) is not dict
            or h["repo"].get("full_name") != _REPO
            or type(b.get("repo")) is not dict
            or b["repo"].get("full_name") != _REPO):
        raise GitHubEvidenceBlocked("PR is not an exact-head open internal Draft")
    # Pin the workflow content at the PR's exact commit before trusting
    # GitHub Actions green labels; callers may not replace a workflow with
    # an empty 'success' job on their feature branch.
    for path, approved_sha in _WORKFLOW_BLOBS.items():
        file = _get_github_json(
            f"/repos/{_REPO}/contents/{path}?ref={head_sha}",
            backend_github_token,
        )
        if (file.get("path") != path or file.get("type") != "file"
                or file.get("sha") != approved_sha):
            raise GitHubEvidenceBlocked("CI workflow content differs from reviewed baseline")
    runs = _get_github_json(
        f"/repos/{_REPO}/commits/{head_sha}/check-runs?per_page=100",
        backend_github_token,
    )
    result = runs.get("check_runs")
    total = runs.get("total_count")
    if (type(total) is not int or not 4 <= total <= 100
            or type(result) is not list or len(result) != total):
        raise GitHubEvidenceBlocked("Incomplete or paginated GitHub check run evidence")
    names: list[str] = []
    expected_runs: dict[int, str] = {}
    for run in result:
        if (type(run) is not dict or type(run.get("app")) is not dict
                or run["app"].get("slug") != "github-actions"
                or run.get("head_sha") != head_sha
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or type(run.get("name")) is not str):
            raise GitHubEvidenceBlocked("Untrusted, pending or failing GitHub check")
        name = run["name"]
        if name not in _REQUIRED:
            raise GitHubEvidenceBlocked("Unreviewed GitHub check name")
        # Check names alone can be spoofed by additional workflows. Link
        # each job to the actual GitHub Actions workflow run and its file.
        detail = run.get("details_url")
        job_url_pattern = (
            r"https://github\.com/" + re.escape(_REPO)
            + r"/actions/runs/([1-9][0-9]{0,18})/job/[1-9][0-9]{0,18}"
        )
        match = re.fullmatch(job_url_pattern, detail) if type(detail) is str else None
        if match is None:
            raise GitHubEvidenceBlocked("Invalid workflow job provenance")
        run_id = int(match.group(1))
        workflow = (".github/workflows/secret-scan.yml"
                    if name == "Full-history credential scan"
                    else ".github/workflows/ci.yml")
        existing = expected_runs.get(run_id)
        if existing is not None and existing != workflow:
            raise GitHubEvidenceBlocked("Mixed workflows in one check run")
        expected_runs[run_id] = workflow
        names.append(name)
    if not all(name in names for name in _REQUIRED):
        raise GitHubEvidenceBlocked("Required 3-version CI or Secret Scan absent")
    if not 2 <= len(expected_runs) <= 12:
        raise GitHubEvidenceBlocked("Unexpected GitHub workflow run count")
    for run_id, expected_path in sorted(expected_runs.items()):
        workflow_data = _get_github_json(
            f"/repos/{_REPO}/actions/runs/{run_id}",
            backend_github_token,
        )
        expected_name = ("NEXUS TITAN Secret Scan"
                         if expected_path.endswith("secret-scan.yml")
                         else "NEXUS TITAN CI")
        if (type(workflow_data.get("id")) is not int
                or workflow_data.get("id") != run_id
                or workflow_data.get("path") != expected_path
                or workflow_data.get("name") != expected_name
                or workflow_data.get("head_sha") != head_sha
                or workflow_data.get("head_branch") != h.get("ref")
                or workflow_data.get("event") not in ("push", "pull_request")
                or workflow_data.get("status") != "completed"
                or workflow_data.get("conclusion") != "success"
                or type(workflow_data.get("repository")) is not dict
                or workflow_data["repository"].get("full_name") != _REPO
                or type(workflow_data.get("head_repository")) is not dict
                or workflow_data["head_repository"].get("full_name") != _REPO):
            raise GitHubEvidenceBlocked("Unverified GitHub workflow run identity")
    return GitHubPRCIEvidence(
        repository=_REPO, pr_number=pr_number, head_sha=head_sha,
        checks_verified=_REQUIRED, github_actions_check_count=len(result),
        workflow_run_count=len(expected_runs),
    )
