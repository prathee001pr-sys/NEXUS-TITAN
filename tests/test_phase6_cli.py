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

    def test_backtest_cli_runs_on_illustrative_csv(self):
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "scripts" / "run_backtest.py"),
                "--csv", str(ROOT / "data" / "market_sample.csv"),
                "--strategy", "sma",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("HISTORICAL_RESEARCH_ONLY", result.stdout)

    def test_evolve_cli_runs_locally_without_llm_or_network(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "evolve-test.sqlite"
            result = subprocess.run(
                [
                    sys.executable, str(ROOT / "scripts" / "run_evolve_agents.py"),
                    "--csv", str(ROOT / "data" / "market_sample.csv"),
                    "--db", str(db_path), "--llm-disabled",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            self.assertIn('"agent_count": 12', result.stdout)
            self.assertTrue(db_path.exists())


if __name__ == "__main__":
    unittest.main()
