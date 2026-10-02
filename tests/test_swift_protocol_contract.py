from pathlib import Path
import importlib.util


def test_swift_contract_matches_python_and_shared_fixtures():
    path = Path(__file__).resolve().parents[1] / 'scripts/check_backend_protocol.py'
    assert path.exists(), 'Phase 2 compatibility checker is missing'
    spec = importlib.util.spec_from_file_location('check_backend_protocol', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check()
