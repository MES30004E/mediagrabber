"""The diagnostic must really drive the native queue with synthetic jobs."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_isolated_queue_probe_exercises_bounded_workers_and_persisted_operations():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-B", str(project / "scripts/benchmark_queue.py"), "--items", "100"],
        cwd=project, env=dict(os.environ, PYTHONPATH=str(project / "src"), PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["items"] == 100 and report["result"] == "passed"
    stages = {item["operation"]: item for item in report["measurements"]}
    assert set(stages) == {"analyse", "enqueue", "start", "progress-two-active", "pause-all", "resume-all",
                           "cancel-selected", "reload", "remove-selected-keep-files"}
    assert stages["start"]["active_tasks"] == 2
    assert all(stage["active_tasks"] <= 2 for stage in stages.values())
    assert stages["enqueue"]["sql"]["writes"] == 100
    assert stages["reload"]["sql"]["writes"] == 0
    assert stages["remove-selected-keep-files"]["active_tasks"] == 0
    assert report["confirmation_requests"] > 0
