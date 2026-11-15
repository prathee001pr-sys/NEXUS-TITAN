"""Evidence-aware offline release preflight; never grants production approval."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("COMMON_API_TOKEN", re.compile(r"(?i)\b(?:api[_-]?key|secret|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{20,}['\"]")),
]
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "build", "dist"}


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src").rglob("*.py")):
        if EXCLUDED_PARTS.intersection(path.parts):
            continue
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def scan_secrets() -> list[dict[str, object]]:
    findings = []
    roots = [ROOT / "src", ROOT / "scripts"]
    for base in roots:
        for path in base.rglob("*"):
            if not path.is_file() or EXCLUDED_PARTS.intersection(path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for label, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(content):
                    findings.append({"rule": label, "path": path.relative_to(ROOT).as_posix(),
                                     "line": content.count("\n", 0, match.start()) + 1})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    tests = {"attempted": not args.skip_tests, "success": False, "output": "Skipped"}
    if not args.skip_tests:
        env = os.environ.copy()
        src = str(ROOT / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run([sys.executable, "scripts/run_project_validation.py"], cwd=ROOT,
                              env=env, text=True, capture_output=True, check=False)
        tests = {"attempted": True, "success": proc.returncode == 0,
                 "return_code": proc.returncode, "output": (proc.stdout + proc.stderr)[-5000:]}
    findings = scan_secrets()
    result = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_fingerprint(),
        "test_validation": tests,
        "secret_scan": {"finding_count": len(findings), "findings": findings},
        "external_release_evidence": {
            "licensed_market_data": "NOT_VERIFIED",
            "independent_security_assessment": "NOT_VERIFIED",
            "operations_recovery_drill": "NOT_VERIFIED",
            "multi_day_shadow_evidence": "NOT_VERIFIED",
            "owner_signoff": "NOT_VERIFIED",
        },
        "release_decision": "BLOCKED_EXTERNAL_EVIDENCE" if tests["success"] and not findings else "BLOCKED",
        "live_trading_enabled": False,
        "note": "This preflight is not a penetration test, data licence check, or production authorization.",
    }
    output = json.dumps(result, indent=2)
    print(output)
    if args.json_out:
        target = (ROOT / args.json_out).resolve()
        if ROOT.resolve() not in target.parents:
            raise SystemExit("--json-out must stay inside the repository")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
    return 0 if tests["success"] and not findings else 1

if __name__ == "__main__":
    raise SystemExit(main())
