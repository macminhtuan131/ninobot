"""Preparation gates cannot launch legacy training or silently change its ABI."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from nino_rl.core import load_config
from nino_rl.residual_experiment import experiment_contract, reward_terms, build_model, make_environment, prepare_main


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.path=Path(__file__).parents[1]/'config/residual_velocity_td3.yaml'
        self.config=load_config(self.path)

    def test_td3_and_ppo_share_abi_without_inherited_td3_parameters(self):
        ppo=load_config(self.path.with_name('residual_velocity_ppo.yaml'))
        a,b=experiment_contract(self.config),experiment_contract(ppo)
        self.assertEqual(a['observation_size'],100)
        for key in ('features','normalization_scales','history_frames','action'):
            self.assertEqual(a[key],b[key])
        self.assertNotIn('buffer_size',ppo['algorithm_parameters']['PPO'])
        self.assertNotIn('policy_delay',ppo['algorithm_parameters']['PPO'])
        self.assertIn('policy_proposal',a['replay_action'])

    def test_legacy_privileged_backend_and_training_fail_before_importing_sb3(self):
        bad=deepcopy(self.config);bad['experiment_contract']='old_torque'
        with self.assertRaises(ValueError):experiment_contract(bad)
        bad=deepcopy(self.config);bad['actor']['privileged_inputs']=['contact']
        with self.assertRaises(ValueError):experiment_contract(bad)
        with self.assertRaises(ValueError):make_environment(self.config,object())
        with self.assertRaisesRegex(ValueError,'disabled'):build_model(self.config,None,0)
        bad=deepcopy(self.config);bad['training']['allowed']=True
        with self.assertRaisesRegex(ValueError,'budget'):build_model(bad,None,0)

    def test_enabled_missing_reward_label_is_unknown_not_zero(self):
        with self.assertRaises(ValueError):reward_terms({},dict(lateral_m=.1),(0.,0.),(0.,0.),.1)
        v,terms=reward_terms(dict(progress_m=.01,lateral_m=.02),dict(progress_m=10.,lateral_m=1.),(0.,0.),(0.,0.),.1)
        self.assertAlmostEqual(v,.1-.00004)
        self.assertIn('lateral_m',terms)

    def test_prepare_writes_only_contract_and_unreleased_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'contract'
            prepare_main(['--config',str(self.path),'--output',str(out)])
            self.assertEqual({p.name for p in out.iterdir()},{'contract.json','readiness.json'})
            status=json.loads((out/'readiness.json').read_text())
            self.assertFalse(status['training_released']);self.assertFalse(status['backend_integration_verified'])
