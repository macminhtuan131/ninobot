"""Per-family RNG and outcome windows. Rewards alone never promote a stage."""
from collections import deque
from copy import deepcopy

import numpy as np

FAMILIES = ('clean', 'short_obstacle', 'pothole', 'mixed')


class FamilyCurriculum:
    def __init__(self, family, seed, settings):
        if family not in FAMILIES:
            raise ValueError('Unknown family')
        self.family, self.settings = family, deepcopy(settings)
        c = self.settings
        if (not 1 <= c['minimum_episodes'] <= c['window'] or c['maximum_stage'] < 0
                or not 0 < c['success_fraction'] <= 1
                or not 0 <= c['earlier_stage_probability'] <= 1):
            raise ValueError('Invalid curriculum gate')
        self.stage, self.total = 0, 0
        self.results = deque(maxlen=c['window'])
        self.recorded = set()
        self.rng = np.random.default_rng(np.random.SeedSequence([seed, FAMILIES.index(family)]))

    def sample_stage(self, fixed=None):
        if fixed is not None:
            if type(fixed) is not int or not 0 <= fixed <= self.settings['maximum_stage']:
                raise ValueError('Invalid fixed evaluation stage')
            return fixed
        if self.stage and self.rng.random() < self.settings['earlier_stage_probability']:
            return int(self.rng.integers(self.stage))
        return self.stage

    def record(self, episode_id, sampled_stage, outcome):
        if episode_id in self.recorded:
            raise ValueError('Episode outcome already consumed')
        self.recorded.add(episode_id)
        self.total += 1
        if sampled_stage != self.stage:
            return False
        success = (outcome.get('measurement_valid') is True
                   and outcome.get('task_success') is True
                   and outcome.get('all_obstacles_recovered') is True
                   and outcome.get('terminated') is True
                   and outcome.get('truncated') is False)
        self.results.append(success)
        enough = len(self.results) >= self.settings['minimum_episodes']
        if (enough and sum(self.results)/len(self.results) >= self.settings['success_fraction']
                and self.stage < self.settings['maximum_stage']):
            self.stage += 1
            self.results.clear()
            return True
        return False

    def state(self):
        return dict(family=self.family, settings=self.settings, stage=self.stage, total=self.total,
                    results=list(self.results), recorded=sorted(self.recorded),
                    rng=deepcopy(self.rng.bit_generator.state))

    def restore(self, state):
        if state['family'] != self.family or state['settings'] != self.settings:
            raise ValueError('Curriculum family/config mismatch')
        if (type(state['stage']) is not int or not 0 <= state['stage'] <= self.settings['maximum_stage']
                or len(state['results']) > self.settings['window']
                or any(type(v) is not bool for v in state['results'])
                or len(state['recorded']) != len(set(state['recorded']))
                or state['total'] != len(state['recorded'])):
            raise ValueError('Invalid curriculum state')
        self.stage, self.total = state['stage'], state['total']
        self.results.clear()
        self.results.extend(state['results'])
        self.recorded = set(state['recorded'])
        self.rng.bit_generator.state = deepcopy(state['rng'])
