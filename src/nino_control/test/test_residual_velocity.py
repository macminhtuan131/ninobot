"""Reference ABI invariants; no ROS or hardware commands."""
import math
import random
import unittest
from nino_control.residual_velocity import (FEATURES, FeatureHistory, ReferenceLimits,
    ResidualReference, body_to_wheels, wheels_to_body, feature_frame)


class ResidualTests(unittest.TestCase):
    def setUp(self):
        self.limits = ReferenceLimits(.345,.4,.4,.5,.1,.04,.2)
        self.core = ResidualReference(self.limits)
        self.flags = dict(permission=True,sensors_fresh=True,history_ready=True,command_age_s=.01)

    def test_geometry_and_observation_have_no_privileged_target(self):
        v,w=wheels_to_body(*body_to_wheels(.1,.2,.345),.345)
        self.assertAlmostEqual(v,.1);self.assertAlmostEqual(w,.2)
        sample=dict.fromkeys(FEATURES[:18],0.)
        sample['accel_z_m_s2']=9.81
        frame=feature_frame(sample,.06,.06,.345)
        self.assertEqual(len(frame),20)
        self.assertAlmostEqual(frame[9],.5)
        self.assertFalse(any('target' in k or 'ground' in k or 'terrain' in k for k in FEATURES))
        del sample['wheel_l_rad_s']
        with self.assertRaises(KeyError):feature_frame(sample,.06,.06,.345)

    def test_history_padding_is_not_readiness_and_gaps_reset(self):
        h=FeatureHistory(5,.15);frame=(0.,)*20
        self.assertEqual(len(h.append(0.,frame)),100)
        self.assertFalse(h.ready)
        for t in (.1,.2,.3,.4):h.append(t,frame)
        self.assertTrue(h.ready)
        for bad in (.4,-1.,1.):
            h.clear();h.append(.4,frame)
            with self.assertRaises(ValueError):h.append(bad,frame)
            self.assertFalse(h.ready)

    def test_common_diff_per_wheel_bounds_rate_and_reference_bounds(self):
        rng=random.Random(27)
        for _ in range(400):
            old=self.core.previous
            trace=self.core.compose((rng.uniform(-.8,.8),rng.uniform(-2,2)),
                (rng.uniform(-1,1),rng.uniform(-1,1)),.1,1.,**self.flags)
            self.assertLessEqual(max(map(abs,trace['proposed_residual_wheel_m_s'])),.04+1e-12)
            accepted=trace['accepted_reference_wheel_m_s']
            self.assertLessEqual(max(map(abs,accepted)),.4+1e-12)
            self.assertTrue(all(abs(a-b)<=.01+1e-12 for a,b in zip(old,accepted)))
            v,w=trace['body_reference'];self.assertLessEqual(abs(v),.4+1e-12);self.assertLessEqual(abs(w),.5+1e-12)
            self.assertIsNone(trace['actuator_target']);self.assertFalse(trace['motor_execution_verified'])

    def test_zero_and_warmup_cannot_create_residual_motion(self):
        trace=self.core.compose((0.,0.),(1.,1.),.1,1.,**self.flags)
        self.assertEqual(trace['body_reference'],(0.,0.))
        flags=dict(self.flags,history_ready=False)
        trace=self.core.compose((.05,0.),(1.,1.),.1,1.,**flags)
        self.assertEqual(trace['proposed_residual_wheel_m_s'],(0.,0.))

    def test_stale_unknown_fault_and_invalid_input_latch_stop(self):
        changes=[dict(command_age_s=.3),dict(permission='false'),dict(history_ready=None),
                 dict(sensors_fresh=False),dict(emergency_stop=True),dict(fault=True)]
        for change in changes:
            self.core.reset()
            trace=self.core.compose((.05,0.),(1.,0.),.1,1.,**dict(self.flags,**change))
            self.assertTrue(self.core.latched);self.assertEqual(trace['body_reference'],(0.,0.))
            trace=self.core.compose((.05,0.),(1.,0.),.1,1.,**self.flags)
            self.assertEqual(trace['body_reference'],(0.,0.))
        self.core.reset()
        self.assertEqual(self.core.compose((math.nan,0.),(0.,0.),.1,**self.flags)['body_reference'],(0.,0.))
