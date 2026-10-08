"""Evaluation recovery must preserve failures and reject mixed scenarios."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

from nino_rl.evaluation import METRICS, TRUTH_METRICS, benchmark_id
from nino_rl.trajectory_metrics import write_csv

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('merge_chunks', SCRIPTS / 'merge_evaluation_chunks.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def source(path, seed, success, speed=.78):
    path.mkdir()
    config = {'reward_pose_source': 'ground_truth', 'goal_tolerance_m': .2}
    metadata = {'benchmark_id': benchmark_id(config), 'evaluation_seeds': [seed],
                'seed': seed, 'baseline_speed_scale': speed, 'controller': 'straight_pi_baseline'}
    (path / 'config.yaml').write_text(yaml.safe_dump(config))
    (path / 'metadata.json').write_text(json.dumps(metadata))
    row = {key: 1. for key in METRICS + TRUTH_METRICS}
    row.update(seed=seed, episode=1, success=success, finished_within_target_time=success,
               termination='success' if success else 'timeout')
    write_csv(path / 'episodes.csv', [row])
    (path / 'episode-001/ground_truth').mkdir(parents=True)
    for name in ('trajectory.csv', 'ground_truth/trajectory.csv'):
        (path / 'episode-001' / name).write_text('original samples\n')
    return path


def test_complete_chunks_keep_failure_and_source_provenance(tmp_path):
    runs = [source(tmp_path / 'a', 1, True), source(tmp_path / 'b', 2, False)]
    result = module.merge(runs, [1, 2], tmp_path / 'merged')
    assert result['complete'] and result['episodes'] == 2
    assert result['success_rate'] == .5
    assert result['termination_counts'] == {'success': 1, 'timeout': 1}
    assert len(result['source_chunks']) == 2
    assert (runs[1] / 'episodes.csv').is_file()


def test_duplicate_missing_and_changed_controller_chunks_are_rejected(tmp_path):
    a = source(tmp_path / 'a', 1, True)
    b = source(tmp_path / 'b', 2, True, speed=1.)
    for runs, seeds, error in [([a, a], [1], 'duplicated'),
                              ([a], [1, 2], 'incomplete'),
                              ([a, b], [1, 2], 'Incompatible')]:
        with pytest.raises(ValueError, match=error):
            module.merge(runs, seeds, tmp_path / 'invalid')
    assert not (tmp_path / 'invalid').exists()
