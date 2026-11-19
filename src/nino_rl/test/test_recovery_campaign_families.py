import pytest

from nino_rl import recovery_campaign as campaign
from nino_rl.recovery_campaign_contract import CampaignRequest, ReadyBank
from nino_rl.recovery_curriculum import FAMILIES
from test_recovery_campaign import PhysicalFixture
from test_recovery_training import FakeLifecycle, qualified


@pytest.mark.parametrize('family', ['clean', 'short_obstacle'])
def test_separate_50k_campaign_keeps_its_family_on_every_reset(tmp_path, family):
    request = CampaignRequest.parse(dict(prepared_root=str(tmp_path/'prepared'),
        families=[family], transitions=50000, checkpoint_keep=12))
    assert CampaignRequest.parse(request.state()) == request
    bank = qualified(tmp_path, FAMILIES)
    ready = ReadyBank(bank.root, bank.bank, tmp_path/'readiness', {family: {}})
    out = tmp_path/'campaign'
    out.mkdir()
    backend = FakeLifecycle(out)
    env = campaign.CampaignEnv(out, request, ready, lifecycle=backend,
        environment_factory=PhysicalFixture,
        episode_qc=lambda episode: dict(valid=True, episodes={episode: dict(valid=True)}))
    try:
        for _ in range(2):
            _, info = env.reset()
            assert info['recovery_assignment']['family'] == family
            assert set(env.curricula) == {family}
            for _ in range(400):
                _, _, term, trunc, _ = env.step([0.])
                if term or trunc:
                    break
            env.finish_stored_episode()
        assert [row['family'] for row in env.assignments] == [family, family]
    finally:
        env.close()


def test_campaign_preserves_requested_family_order_and_default(tmp_path):
    assert CampaignRequest.parse(dict(prepared_root=str(tmp_path))).families == FAMILIES
    request = CampaignRequest.parse(dict(prepared_root=str(tmp_path),
        families=['short_obstacle', 'clean']))
    assert request.families == ('short_obstacle', 'clean')


@pytest.mark.parametrize('families', [[], ['clean', 'clean'], ['unknown'],
    ['clean', 'unknown'], [True], 'clean', {'clean': True}, None])
def test_campaign_rejects_invalid_family_subsets(tmp_path, families):
    with pytest.raises(ValueError, match='nonempty unique subset'):
        CampaignRequest.parse(dict(prepared_root=str(tmp_path), families=families))
