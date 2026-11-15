"""Protect single-variable flat correction using independent test fixtures."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import pytest
import yaml
ROOT = Path(__file__).parents[3]
FIXTURES = Path(__file__).parent / 'fixtures/legacy_flat'
spec = importlib.util.spec_from_file_location('targeted_courses', ROOT / 'src/nino_rl/scripts/experiment_assets.py')
targeted = importlib.util.module_from_spec(spec)
spec.loader.exec_module(targeted)

def test_flat_only_slip_weight_changes():
    original = yaml.safe_load((FIXTURES / 'pilot.yaml').read_text())
    candidate = deepcopy(original)
    candidate['reward_v2']['slip_weight'] *= 1.5
    assert targeted.flat_change(original, candidate) == candidate
    assert original['reward_v2']['slip_weight'] != candidate['reward_v2']['slip_weight']
    candidate['ppo']['learning_rate'] *= 2
    with pytest.raises(ValueError, match='only increase slip'):
        targeted.flat_change(original, candidate)

def test_new_flat_contract_rejects_original_optimizer_resume():
    import sys
    sys.path.insert(0, str(ROOT / 'src/nino_rl'))
    original_path = FIXTURES / 'training_contract.py'
    spec = importlib.util.spec_from_file_location('old_flat_contract', original_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    config = yaml.safe_load((FIXTURES / 'pilot.yaml').read_text())
    candidate = deepcopy(config)
    candidate['reward_v2']['slip_weight'] *= 1.5
    namespace = {}
    exec(original_path.read_text().replace('contract["revision"] = 38', 'contract["revision"] = 40'), namespace)
    model = type('Saved', (), {'nino_training_contract': old.training_contract(config)})()
    assert namespace['training_contract'](candidate)['revision'] == 40
    with pytest.raises(ValueError, match='differs'):
        namespace['validate_resume'](model, candidate)
