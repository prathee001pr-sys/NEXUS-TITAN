"""Safe backend-only GitHub verification CLI: never echo credentials."""
from pathlib import Path
import json
import runpy

from nexus_titan.dashboard.github_ci_evidence import (
    GitHubEvidenceBlocked, GitHubPRCIEvidence,
)

PATH = Path(__file__).resolve().parents[1] / "scripts/verify_pwa_github_ci_evidence.py"
SHA = "889e9c251cebfc255c4bec9c4408a66a6c314cdd"
TOKEN = "LOCAL_TEST_TOKEN_NOT_REAL"


def loader():
    return runpy.run_path(str(PATH))["main"]


def test_cli_returns_no_go_without_private_backend_token(monkeypatch, capsys):
    monkeypatch.delenv("TITAN_GITHUB_READ_TOKEN", raising=False)
    main=loader()
    assert main(["--pr","152","--head-sha",SHA]) == 2
    captured=capsys.readouterr()
    assert captured.out == ""
    assert "NO-GO" in captured.err


def test_cli_prints_only_bounded_research_status_not_token(monkeypatch, capsys):
    monkeypatch.setenv("TITAN_GITHUB_READ_TOKEN", TOKEN)
    main=loader()
    observed=[]

    def verify(**kwargs):
        observed.append(kwargs)
        return GitHubPRCIEvidence(
            repository="prathee001pr-sys/NEXUS-TITAN",
            pr_number=152, head_sha=SHA,
            checks_verified=("offline-validation (3.11)",
                             "offline-validation (3.12)",
                             "offline-validation (3.13)",
                             "Full-history credential scan"),
            github_actions_check_count=8,
        )
    monkeypatch.setitem(main.__globals__, "verify_github_draft_pr_ci", verify)
    assert main(["--pr","152","--head-sha",SHA]) == 0
    output=capsys.readouterr()
    assert TOKEN not in output.out and TOKEN not in output.err
    assert observed[0]["backend_github_token"] == TOKEN
    payload=json.loads(output.out)
    assert payload["head_sha"]==SHA
    assert payload["production_ready"] is False
    assert payload["live_trading_authorized"] is False
    assert payload["owner_pwa_session_authenticated"] is False


def test_cli_cannot_reveal_credential_when_backend_denies(monkeypatch, capsys):
    monkeypatch.setenv("TITAN_GITHUB_READ_TOKEN", TOKEN)
    main=loader()

    def blocked(**kwargs):
        raise GitHubEvidenceBlocked("private_failure")
    monkeypatch.setitem(main.__globals__, "verify_github_draft_pr_ci", blocked)
    assert main(["--pr","152","--head-sha",SHA]) == 2
    output=capsys.readouterr()
    assert output.out == ""
    assert "private_failure" not in output.err
    assert TOKEN not in output.err
