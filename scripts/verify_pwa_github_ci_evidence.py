"""Local backend-only CLI for trusted GitHub Draft PR CI evidence.

Reads a GitHub token from the current process environment, never logs it,
never offers HTTP/PWA endpoints, and never authorizes any paper/live order.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys

from nexus_titan.dashboard.github_ci_evidence import (
    GitHubEvidenceBlocked, verify_github_draft_pr_ci,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify exact-head NEXUS TITAN GitHub CI as research-only evidence"
    )
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args(argv)
    # Backend-only secret. Never include it in the CLI output or exception text.
    token = os.environ.get("TITAN_GITHUB_READ_TOKEN", "")
    try:
        receipt = verify_github_draft_pr_ci(
            pr_number=args.pr, head_sha=args.head_sha,
            backend_github_token=token,
        )
    except GitHubEvidenceBlocked:
        print("NO-GO: exact-head GitHub evidence was not verified", file=sys.stderr)
        return 2
    print(json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
