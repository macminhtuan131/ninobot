#!/usr/bin/env python3
"""Evidence-selected formulation proposal; no policy training or deployment."""
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(Path(__file__).parent))
from audit_rough_deterministic_actor import OUTPUT,SOURCE,distribution

def main():
    from inspect_flat_critic import gae_targets
    from prepare_rough_foundations import digest
    audit=json.loads((OUTPUT/'audit.json').read_text());probe=json.loads((OUTPUT/'gradient_probe.json').read_text())
    norms=probe['batches']
    balance=dict(median_critic_actor_norm_ratio=float(np.median([r['critic_gradient_norm']/r['actor_gradient_norm'] for r in norms])),
        median_global_clip_retained_fraction=float(np.median([r['clip_retained_fraction'] for r in norms])),
        explained_variance=probe['explained_variance'],critic_dominance_supported=False)
    sys.path.insert(0,str(SOURCE/'python'))
    import torch
    from stable_baselines3 import PPO
    torch.set_num_threads(2)
    model=PPO.load(audit['source_model'],device='cpu')
    with np.load(OUTPUT/'stochastic_probe.npz') as p:data={k:p[k] for k in p.files}
    means,std,values=distribution(model,data['observations'])
    returns=gae_targets(data['rewards'],data['values'],data['dones'],model.gamma,model.gae_lambda)
    advantage=returns-data['values'];advantage=(advantage-advantage.mean())/(advantage.std()+1e-8)
    score=advantage*(data['actions'].flatten()-means)/(std**2)
    frames=data['observations'].reshape(-1,5,72)[:,-1]
    masks={'holding':frames[:,62]>.5,'recovering':frames[:,63]>.5,'cooldown':frames[:,64]>.5}
    masks['ready']=~np.logical_or.reduce(list(masks.values()))
    signal={k:dict(samples=int(mask.sum()),mean_signed_mean_action_score=float(score[mask].mean()),
        note='Positive score favors increasing raw Gaussian mean at fixed variance; on-policy probe association, not causal reward decomposition')
        for k,mask in masks.items() if mask.any()}
    proposal=dict(revision='rough_incremental_speed_formulation_proposal_v1',status='selected proposal; not integrated or trained',
        starting_model_preserved=audit['source_model'],source_sha256=digest(audit['source_model']),
        action_space='Discrete(3): BRAKE, HOLD, RECOVER',
        action_mapping=dict(brake_scale_rate_per_s=-.4,hold_scale_rate_per_s=0.,recover_scale_rate_per_s=.4,
            control_dt_s=.1,minimum_scale=.55,maximum_scale=1.,
            update='s_next = clip(s_previous + selected_rate * dt, .55, 1.)'),
        policy='Categorical PPO head, not clipped Gaussian/gSDE. Actor freely chooses every action; cue does not force actions.',
        exploration='Categorical probabilities/entropy replace gSDE; no Gaussian std or raw action clipping',
        observations='Same 360 hardware-only causal history, including previous executed speed and cue state',
        reward='Existing revision-49 weights and executed-command reward; no penalty increase',
        fixed='Same physical speed-rate limit, unscaled PI yaw, terrain, estimator, timing and physical scoring',
        initialization='Fresh categorical actor, fresh critic and optimizer; old Gaussian checkpoint cannot be resumed as this policy',
        evidence=dict(deterministic_clip_fraction=audit['all']['deterministic_clip_fraction'],
            stochastic_clip_fraction=probe['raw_action_clipped_fraction'],ramp_limited_fraction=probe['speed_ramp_limited_fraction'],
            holding_executed_scale=audit['phases']['holding']['executed_scale_mean'],gradient_balance=balance,
            sustained_training_exposure=json.loads((SOURCE/'failed_exposure_audit.json').read_text())['attempts_with_sustained_slowdown_recovery']),
        hypothesis='Separate explicit speed changes from absolute noisy targets: each interior action has distinct execution; deterministic decisions can sustain braking and recovery.',
        limitations=['This proposal is not evidence that the categorical policy will learn or outperform PI.',
            'State saturation at .55/1 remains a physical constraint; HOLD and outward commands can coincide there.',
            'Six .1 s braking actions can only reach .76 from 1 under the unchanged .4/s ramp, not the .70 holding target.',
            'Holding and recovery rewards still compete with progress/comfort; no causal optimum claimed.',
            'Changing action meanings requires a new training contract and new likelihood/rollout verification.'],
        next_gate='Verify all action executions and exploration sequences offline/live; then one bounded fresh pilot, comparing reactive reference and full/time-matched PI',
        optuna_held=True,training_started=False)
    # Exercise the proposed execution algebra only. No learned actor update.
    s=1.;sequence=[]
    for action in [-.4]*6+[.4]*6:
        s=float(np.clip(s+action*.1,.55,1.));sequence.append(s)
    if not np.isclose(min(sequence),.76) or not np.isclose(sequence[-1],1):raise ValueError('Rate algebra failed')
    proposal['offline_execution_example']=sequence
    # Verify the proposed likelihood family with the installed PPO and exact
    # existing history extractor, without constructing ROS or optimizing weights.
    import gymnasium as gym
    import yaml
    from stable_baselines3.common.policies import ActorCriticPolicy
    from nino_rl.policies import policy_spec
    class SpacesOnly(gym.Env):
        observation_space=model.observation_space
        action_space=gym.spaces.Discrete(3)
    config=yaml.safe_load((SOURCE/'config.yaml').read_text())
    _,kwargs=policy_spec(config)
    kwargs.pop('initial_speed_scale');kwargs.pop('initial_action_std',None)
    fresh=PPO(ActorCriticPolicy,SpacesOnly(),policy_kwargs=kwargs,device='cpu',seed=17000,
        n_steps=1024,batch_size=256,use_sde=False)
    obs=torch.as_tensor(data['observations'][:32],dtype=torch.float32)
    with torch.no_grad():
        d=fresh.policy.get_distribution(obs).distribution
        probabilities=d.probs;actions,values,logp=fresh.policy(obs)
        _,replayed,_=fresh.policy.evaluate_actions(obs,actions)
    if probabilities.shape!=(32,3) or not torch.allclose(probabilities.sum(1),torch.ones(32)):
        raise ValueError('Categorical action probabilities invalid')
    if not torch.allclose(logp,replayed,atol=1e-6) or fresh.policy.optimizer.state or fresh.num_timesteps:
        raise ValueError('Categorical likelihood or no-update invariant failed')
    proposal['offline_categorical_verification']=dict(samples=32,three_probabilities_normalized=True,
        likelihood_replay_matched=True,optimizer_empty=True,training_steps=0,
        initialization='Fresh categorical actor and critic; original hardware HistoryFeatures extractor',
        limitation='Space-only construction; ROS action decoding, contract enforcement and live exploration still need integration/verification')
    result=dict(gradient_balance=balance,phase_likelihood_signal=signal,selected_correction=proposal,
        analysis_limit='Original training gradients unavailable. Probe backward passes made no optimizer updates.')
    (OUTPUT/'formulation_decision.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUTPUT/'proposed_contract.json').write_text(json.dumps(proposal,indent=2)+'\n')
    a=audit['phases'];cost=audit['mean_raw_reward_contributions_per_episode']['holding']
    lines=['# Rough deterministic actor and formulation audit','',
        'Revision-49 final checkpoint preserved. Exact saved inputs replayed; three frozen stochastic episodes '
        '(17100–17102), backward passes only. **No PPO update, extension or Optuna.**','',
        '| Actor phase | Samples | Raw mean | Deterministic clipping | Requested scale | Executed scale |',
        '|---|---:|---:|---:|---:|---:|']
    for name,p in a.items():lines.append(f"| {name} | {p['samples']} | {p['raw_mean']:.3f} | {100*p['deterministic_clip_fraction']:.1f}% | {p['requested_scale_mean']:.3f} | {p['executed_scale_mean']:.3f} |")
    lines+=['','## Findings','',
        f"- {100*audit['all']['deterministic_clip_fraction']:.1f}% of deterministic means exceed the upper bound. "
          'Holding itself is mostly unsaturated, so clipping is not the sole explanation.',
        f"- Frozen stochastic probe: {100*probe['raw_action_clipped_fraction']:.1f}% clipped; "
          f"{100*probe['speed_ramp_limited_fraction']:.1f}% additionally limited by the physical speed ramp. "
          'Raw gSDE matrix std 0.064 does not mean action std 0.064: mean observed marginal std is 0.611.',
        '- Latest-frame holding-flag edits change requested scale by only about −0.001; coherent five-frame '
          'holding edits change it by about −0.023. These are network sensitivity tests, not physical counterfactuals.',
        f"- Final training explained variance ~0.95; frozen-probe explained variance {balance['explained_variance']:.3f}. "
          f"Median critic/actor gradient ratio {balance['median_critic_actor_norm_ratio']:.3f}; retained fraction "
          f"{balance['median_global_clip_retained_fraction']:.3f}. **Weak critic/critic dominance is not supported here.**",
        '- Actual training included 66/72 attempts with sustained slowdown followed by recovery. '
          'The deterministic final actor failed to retain sufficient response despite exposure.',
        f"- Frozen likelihood score favors lower raw actions during holding ({signal['holding']['mean_signed_mean_action_score']:.3f}) "
          f"and higher ones during recovery ({signal['recovering']['mean_signed_mean_action_score']:.3f}). "
          'This does not support automatically increasing the holding penalty. It is a local stochastic-probe signal, not proof of a global reward optimum.',
        '- The holding window is 0.6 s, but a 1→0.70 ramp requires 0.75 s. A new action formulation alone '
          'does not resolve this target-duration mismatch; do not credit reaching an unreachable holding target.','',
        '## Holding reward contributions (raw mean per episode)','',
        '| Term | Contribution |','|---|---:|',
        *[f'| {k} | {v:.5f} |' for k,v in cost.items()],
        '', 'The holding-reference term is present and nonzero. Return summation is not an attribution '
        'of how the physical trajectory would change under another action. No reward weights changed.','',
        '## Selected formulation correction','',
        '**Replace absolute Gaussian speed targets with categorical BRAKE / HOLD / RECOVER speed-rate actions.** '
        'Keep the 0.4/s rate, .55–1 bounds, hardware observations and current reward/scoring. '
        'The policy selects actions freely; no cue-driven inference override or teacher-forced slowdown. '
        'This removes Gaussian action clipping and gives distinct executed changes inside the speed bounds. '
        'It requires a fresh categorical actor/critic/optimizer under a new contract.','',
        'Prepared: proposed_contract.json. **Not integrated or trained.** First validate categorical likelihoods, '
        'rate execution and sustained exploratory brake/recovery sequences, then run one short pilot. '
        'Compare with the validated reactive controller as well as full/time-matched PI. Keep Optuna held.','',
        *proposal['limitations'],'']
    (OUTPUT/'REPORT.md').write_text('\n'.join(lines));print(json.dumps(balance,indent=2))

if __name__=='__main__':main()
