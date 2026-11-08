"""Causal probe cadence, independent RNG streams and real SB3 replay semantics."""
from copy import deepcopy
import numpy as np
import pytest
from nino_rl.coverage_sampling import CoverageSampler


def packet(open=True):
    o=np.zeros(103,np.float32);o[101]=float(open);return o


def test_warmup_shared_then_one_probe_per_four_open_and_balanced_cycles():
    a,c=CoverageSampler(11,'A_gaussian'),CoverageSampler(11,'C_stratified_probes')
    audits=[]
    for t in range(64+96):
        obs=packet(t%3!=0)
        x,ax=a.choose(obs,np.array([-.9],np.float32),t)
        y,cx=c.choose(obs,np.array([-.9],np.float32),t)
        if t<64:np.testing.assert_array_equal(x,y)
        else:
            assert ax['gaussian_noise']==cx['gaussian_noise']
            if not cx['probe']:np.testing.assert_array_equal(x,y)
        if cx['probe']:
            assert obs[101]==1 and cx['eligible_open_decisions']%4==0
            assert -.999999<=float(y[0])<=1.
            assert int(np.clip(np.floor((float(y[0])+1.)*2),0,3))==cx['probe_bin']
            audits.append(cx)
    assert c.probes==c.eligible//4 and a.probes==0
    for i in range(0,len(audits)-3,4):assert sorted(x['probe_bin'] for x in audits[i:i+4])==[0,1,2,3]


def test_sampler_does_not_mutate_global_random_or_reset_counter_between_episodes():
    np.random.seed(123);before=deepcopy(np.random.get_state())
    s=CoverageSampler(22,'C_stratified_probes')
    for i in range(100):s.choose(packet(),np.zeros(1,np.float32),i)
    after=np.random.get_state()
    assert before[0]==after[0] and np.array_equal(before[1],after[1]) and before[2:]==after[2:]
    assert s.eligible==36 and s.probes==9
    # A new episode does not construct a new sampler; next decision remains100.
    _,audit=s.choose(packet(False),np.zeros(1,np.float32),100)
    assert audit['eligible_open_decisions']==36


@pytest.mark.parametrize('fault',['window','shape','nan','sequence','mean'])
def test_invalid_packet_fails_without_advancing(fault):
    s=CoverageSampler(11,'C_stratified_probes');obs=packet();mean=np.zeros(1,np.float32);t=0
    if fault=='window':obs[101]=.5
    if fault=='shape':obs=obs[:-1]
    if fault=='nan':obs[0]=np.nan
    if fault=='sequence':t=1
    if fault=='mean':mean[0]=np.inf
    with pytest.raises(ValueError):s.choose(obs,mean,t)
    assert s.decisions==0


def test_independent_replay_keeps_timeout_semantics_and_global_rng():
    import gymnasium as gym
    from nino_rl.coverage_td3 import IndependentReplayBuffer
    b=IndependentReplayBuffer(8,gym.spaces.Box(-5.,5.,(103,),np.float32),gym.spaces.Box(-1.,1.,(1,),np.float32),device='cpu')
    for timeout in (True,False):
        b.add(packet(),packet(),np.array([float(timeout)],np.float32),np.array([0.]),np.array([1.]),[{'TimeLimit.truncated':timeout}])
    before=deepcopy(np.random.get_state());sample=b.sample(80);after=np.random.get_state()
    assert np.array_equal(before[1],after[1]) and before[2:]==after[2:]
    assert set(sample.actions.flatten().tolist())=={0.,1.}
    np.testing.assert_array_equal(sample.dones.flatten().numpy(),1-sample.actions.flatten().numpy())
