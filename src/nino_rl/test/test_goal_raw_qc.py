import json

import pytest

from nino_rl.unknown_step_runner import raw_qc


def write_episode(root, index, *, channels=('imu', 'wheel', 'truth', 'drive'), stamps=(1., 1.02)):
    name = f'episode_{index}'
    (root / (name + '_reset.json')).write_text(json.dumps({
        'reset': {'physical_sample': {'stamp_s': 1.}}
    }))
    directory = root / 'episodes' / name / 'backend' / 'episode_0'
    directory.mkdir(parents=True)
    rows = [dict(channel=channel, stamp_s=stamp) for stamp in stamps for channel in channels]
    (directory / 'raw_samples.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_another_episode_cannot_supply_a_missing_channel(tmp_path):
    write_episode(tmp_path, 0, channels=('wheel', 'truth', 'drive'))
    write_episode(tmp_path, 1)
    assert raw_qc(tmp_path)['valid'] is False


def test_missing_whole_raw_file_cannot_disappear_from_quality_check(tmp_path):
    write_episode(tmp_path, 0)
    write_episode(tmp_path, 1)
    (tmp_path / 'episodes/episode_0/backend/episode_0/raw_samples.jsonl').unlink()
    assert raw_qc(tmp_path)['valid'] is False


def test_large_gap_in_one_episode_invalidates_the_dataset(tmp_path):
    write_episode(tmp_path, 0, stamps=(1., 1.06))
    write_episode(tmp_path, 1)
    assert raw_qc(tmp_path)['valid'] is False


def test_complete_independent_episodes_pass(tmp_path):
    write_episode(tmp_path, 0)
    write_episode(tmp_path, 1)
    assert raw_qc(tmp_path)['valid'] is True


def test_retained_samples_must_cover_declared_final_boundary(tmp_path):
    write_episode(tmp_path, 0)
    (tmp_path/'environment_trace.jsonl').write_text(json.dumps(dict(
        episode=0, physical_sample=dict(stamp_s=1.2)))+'\n')
    result = raw_qc(tmp_path)
    assert not result['valid']
    episode = result['episodes']['episode_0']
    assert episode['boundary_coverage_checked']
    assert {r['channel'] for r in episode['reasons'] if r['reason'] == 'missing_tail_support'} == {
        'imu', 'wheel', 'truth', 'drive'}


def test_retained_samples_must_cover_declared_start_boundary(tmp_path):
    write_episode(tmp_path, 0, stamps=(1.1, 1.12))
    assert not raw_qc(tmp_path)['valid']


def test_one_sample_per_channel_does_not_establish_source_cadence(tmp_path):
    write_episode(tmp_path, 0, stamps=(1.,))
    write_episode(tmp_path, 1)
    assert raw_qc(tmp_path)['valid'] is False


def test_duplicate_headers_are_explicit_quality_failures(tmp_path):
    write_episode(tmp_path, 0, stamps=(1., 1., 1.02))
    assert raw_qc(tmp_path)['valid'] is False


def test_episode_reasons_and_legacy_summaries_preserve_the_observed_evidence(tmp_path):
    write_episode(tmp_path, 0, channels=('wheel', 'truth', 'drive'))
    write_episode(tmp_path, 1)
    result = raw_qc(tmp_path)
    assert result['counts'] == dict(imu=2, wheel=4, truth=4, drive=4)
    assert result['maximum_source_gap_s'] == pytest.approx(dict(imu=.02, wheel=.02, truth=.02, drive=.02))
    assert len(result['final_stamps']) == 2
    assert result['episodes']['episode_0']['valid'] is False
    assert result['episodes']['episode_0']['reasons'] == [dict(reason='missing_channel', channel='imu', count=0)]
    assert result['episodes']['episode_1']['valid'] is True
    assert json.loads((tmp_path / 'source_qc.json').read_text()) == result


def test_reset_without_an_episode_directory_still_requires_raw_evidence(tmp_path):
    write_episode(tmp_path, 0)
    (tmp_path / 'episode_1_reset.json').write_text(json.dumps({
        'reset': {'physical_sample': {'stamp_s': 1.}}
    }))
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['episodes']['episode_1']['reasons'][0]['reason'] == 'missing_raw_samples'


def test_episode_directory_without_reset_metadata_has_no_invented_epoch(tmp_path):
    write_episode(tmp_path, 0)
    (tmp_path / 'episode_0_reset.json').unlink()
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['episodes']['episode_0']['reasons'][0]['reason'] == 'invalid_reset_metadata'
    assert result['counts'] == result['maximum_source_gap_s'] == result['final_stamps'] == {}


@pytest.mark.parametrize('reset', [
    {}, {'reset': None}, {'reset': {'physical_sample': {}}},
    {'reset': {'physical_sample': {'stamp_s': True}}},
    {'reset': {'physical_sample': {'stamp_s': '1.0'}}},
    {'reset': {'physical_sample': {'stamp_s': float('nan')}}},
])
def test_unknown_or_malformed_reset_metadata_is_an_explicit_failure(tmp_path, reset):
    write_episode(tmp_path, 0)
    (tmp_path / 'episode_0_reset.json').write_text(json.dumps(reset))
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['episodes']['episode_0']['reasons'][0]['reason'] == 'invalid_reset_metadata'
    assert result['counts'] == result['maximum_source_gap_s'] == {}


def test_timestamp_reversal_is_reported_without_passing_the_dataset(tmp_path):
    write_episode(tmp_path, 0, stamps=(1., 1.02, 1.01))
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert {reason['channel'] for reason in result['episodes']['episode_0']['reasons']
            if reason['reason'] == 'source_timestamp_reversal'} == {'imu', 'wheel', 'truth', 'drive'}


@pytest.mark.parametrize('stamp', [None, True, '1.02', float('nan'), float('inf')])
def test_malformed_source_timestamps_are_not_silently_ignored(tmp_path, stamp):
    write_episode(tmp_path, 0)
    raw = tmp_path / 'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    with raw.open('a') as stream:
        stream.write(json.dumps(dict(channel='imu', stamp_s=stamp)) + '\n')
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['episodes']['episode_0']['reasons'][0]['reason'] == 'malformed_raw_record'


def test_malformed_raw_json_is_an_explicit_failure(tmp_path):
    write_episode(tmp_path, 0)
    raw = tmp_path / 'episodes/episode_0/backend/episode_0/raw_samples.jsonl'
    with raw.open('a') as stream:
        stream.write('{broken\n')
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['episodes']['episode_0']['reasons'][0]['reason'] == 'malformed_raw_record'


def test_only_samples_from_the_task_epoch_establish_cadence(tmp_path):
    write_episode(tmp_path, 0, stamps=(.8, .9, 1., 1.02))
    result = raw_qc(tmp_path)
    assert result['valid'] is True
    assert result['counts'] == dict(imu=2, wheel=2, truth=2, drive=2)
    assert result['maximum_source_gap_s'] == pytest.approx(dict(imu=.02, wheel=.02, truth=.02, drive=.02))


def test_no_expected_episodes_is_an_explicit_failure(tmp_path):
    result = raw_qc(tmp_path)
    assert result['valid'] is False
    assert result['reasons'] == [dict(reason='no_expected_episodes')]
    assert result['counts'] == result['maximum_source_gap_s'] == result['final_stamps'] == {}
