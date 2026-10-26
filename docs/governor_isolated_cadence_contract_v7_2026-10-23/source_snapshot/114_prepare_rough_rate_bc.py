#!/usr/bin/env python3
"""New actor-imitation contract; keep the failed categorical checkpoint immutable."""
import json,shutil
from copy import deepcopy
from pathlib import Path
import yaml
from prepare_rough_foundations import ROOT,digest,immutable
from run_disturbance_reference_comparisons import replace,verify
SOURCE=ROOT/'rl_runs/rough_rate_action_pilot_v2'
OUTPUT=ROOT/'rl_runs/rough_rate_bc_pilot_v1'

def prepare():
    if (OUTPUT/'pilot_contract.json').exists():
        p=json.loads((OUTPUT/'pilot_contract.json').read_text());verify(p)
        return yaml.safe_load((OUTPUT/'config.yaml').read_text()),p
    source=json.loads((SOURCE/'pilot_contract.json').read_text());verify(source)
    old=next((SOURCE/'train').glob('*/nino_ppo_final.zip'))
    OUTPUT.mkdir(parents=True,exist_ok=True);package=OUTPUT/'python/nino_rl'
    shutil.copytree(SOURCE/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    config=yaml.safe_load((SOURCE/'config.yaml').read_text());original=deepcopy(config)
    config['behavior_cloning']=dict(revision='reactive_rate_actor_v1',
        teacher='Causal holding cue and last executed scale only; nearest discrete ramp approximation of .70',
        train_seeds=[17200,17201,17202],validation_seeds=[17203],test_seeds=[17204],
        actor='Fresh seed-17000 actor trained by supervised balanced categorical cross entropy',
        ppo_initialization='BC actor only; new critic, new optimizer, zero PPO training counter',
        physical_observations='Existing 360 hardware-only inputs; no added teacher state or physical-pose input')
    restored=deepcopy(config);restored.pop('behavior_cloning');assert restored==original
    path=package/'training_contract.py'
    code=replace(path.read_text(),'    contract["revision"] = 52',
        '    contract["revision"] = 54\n    contract["behavior_cloning"] = deepcopy(config["behavior_cloning"])')
    path.write_text(code)
    path=package/'train.py'
    code=replace(path.read_text(),
        '    if args.resume or args.init_model or args.init_speed_model:\n        raise SystemExit("This bounded pilot requires fresh actor, critic and optimizer")',
        '    if args.resume or args.init_speed_model or not args.init_model:\n        raise SystemExit("BC pilot requires actor-only --init-model; critic/optimizer and PPO counter must be fresh")')
    code=replace(code,'                source = PPO.load(args.init_model, device=device)',
        '''                source = PPO.load(args.init_model, device=device)
                if not getattr(source, 'nino_bc_completed', False) or source.num_timesteps != 0 or source.policy.optimizer.state:
                    raise ValueError('Expected verified BC actor with zero PPO counter and no imported optimizer state')
                from nino_rl.training_contract import validate_resume
                validate_resume(source, config)
                import hashlib
                expected_bc = Path(config['behavior_cloning']['verified_actor_path'])
                if args.init_model.resolve() != expected_bc.resolve():
                    raise ValueError("Initialization must use this contract's verified BC actor")
                verification = json.loads(expected_bc.with_name('bc_verification.json').read_text())
                if not verification['passed'] or verification['actor_sha256'] != hashlib.sha256(args.init_model.read_bytes()).hexdigest():
                    raise ValueError('BC actor failed verification or changed')''')
    # The path has no model hash cycle: verification freezes the saved actor hash.
    config['behavior_cloning']['verified_actor_path']=str(OUTPUT/'bc_actor.zip')
    path.write_text(code)
    for p in package.glob('*.py'):
        compile(p.read_text(),str(p),'exec')
        if p.name not in ('train.py','training_contract.py'):assert p.read_bytes()==(SOURCE/'python/nino_rl'/p.name).read_bytes()
    immutable(OUTPUT/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets=dict(source['assets']);assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in (Path(__file__),Path(__file__).with_name('rough_rate_behavior_cloning.py'),OUTPUT/'config.yaml',old,SOURCE/'acceptance.json'):
        assets[str(p)]=digest(p)
    plan=dict(revision='rough_rate_bc_pilot_v1',training_contract_revision=54,assets=assets,steps=20480,
        training_seed=17000,evaluation_seeds=list(range(17400,17405)),probe_seeds=[17300,17301,17302],
        preserved_checkpoint=str(old),preserved_checkpoint_sha256=digest(old),initialization=config['behavior_cloning'],
        unchanged=['Terrain','controller','360 causal observations','categorical actions','bounds/ramp','all reward weights and terms','physical scoring'],
        quality_gate=source['quality_gate'],scoring=source['scoring'],optuna_held=True)
    immutable(OUTPUT/'pilot_contract.json',json.dumps(plan,indent=2)+'\n');return config,plan
