import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "run_agent_runtime.py",
    "run_backtest.py",
    "run_evolve_agents.py",
    "run_evolve_scheduler.py",
    "run_project_validation.py",
)


class Phase6CliSmokeTests(unittest.TestCase):
    def test_cli_help_loads_without_network_or_side_effects(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / script), "--help"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
