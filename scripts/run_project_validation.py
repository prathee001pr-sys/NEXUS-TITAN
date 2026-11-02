"""Run repository-wide offline checks for NEXUS TITAN.

This command compiles the package and runs the project's pytest suite. It does not
contact a broker, fetch market data, or enable network access.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN offline project validation")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--tests-only", action="store_true")
    args = parser.parse_args()
    commands: list[list[str]] = []
    if not args.skip_compile and not args.tests_only:
        commands.append([sys.executable, "-m", "compileall", "-q", "src", "scripts"])
    commands.append([sys.executable, "-m", "pytest", "-q"])
    for command in commands:
        print("+", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    print("Offline validation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
