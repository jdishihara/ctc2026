from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_existing_experiment_directory_is_not_overwritten(tmp_path):
    sentinel = tmp_path / "baseline-deep.json"
    sentinel.write_text("previous experiment\n")
    result = subprocess.run([sys.executable, "scripts/experiment_execution.py",
        "--configs", "baseline", "--seasons", "451", "--workers", "1",
        "--out", str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert sentinel.read_text() == "previous experiment\n"
