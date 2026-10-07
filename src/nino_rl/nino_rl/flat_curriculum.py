"""Success-gated cable and adaptive-item curriculum for the flat course."""

from collections import deque
from math import radians

class FlatCourseCurriculum:
    def __init__(self, config: dict, cables: list[dict], max_features: int):
        self.stages = list(config["stages"])
        self.cables = cables
        self.window_size = int(config.get("window_episodes", 30))
        self.advance_rate = float(config.get("advance_success_rate", 0.75))
        self.replay_probability = float(config.get("replay_probability", 0.0))
        self.fixed_stage = config.get("fixed_stage")
        if (not self.stages or self.window_size < 1 or not 0 < self.advance_rate <= 1 or
                not 0 <= self.replay_probability < 1):
            raise ValueError("Flat curriculum needs stages, a positive window, and a success rate in (0,1]")
        if self.fixed_stage is not None:
            self.fixed_stage = int(self.fixed_stage)
            if not 0 <= self.fixed_stage < len(self.stages):
                raise ValueError("flat_curriculum.fixed_stage is out of range")
        for stage in self.stages:
            indices = stage["cable_indices"]
            angles = stage["angle_range_deg"]
            features = int(stage["adaptive_features"])
            if (len(indices) != len(set(indices)) or
                    any(not isinstance(index, int) or not 0 <= index < len(cables) for index in indices) or
                    len(angles) != 2 or not -89 < float(angles[0]) <= float(angles[1]) < 89 or
                    not 0 <= features <= max_features):
                raise ValueError("Invalid flat curriculum stage")
        self.stage_index = self.fixed_stage if self.fixed_stage is not None else 0
        self.outcomes = deque(maxlen=self.window_size)

    @property
    def stage(self) -> dict:
        return self.stages[self.stage_index]

    def sample_stage(self, rng) -> int:
        if (self.fixed_stage is None and self.stage_index > 0 and
                rng.random() < self.replay_probability):
            return self.stage_index - 1
        return self.stage_index

    def sample_cables(self, rng, stage_index: int) -> list[tuple[float, float, float]]:
        stage = self.stages[stage_index]
        low, high = (float(value) for value in stage["angle_range_deg"])
        return [
            (float(self.cables[index]["x"]), float(self.cables[index]["radius"]),
             radians(float(rng.uniform(low, high))))
            for index in stage["cable_indices"]
        ]

    def record(self, succeeded: bool, episode_stage: int) -> tuple[float, int, bool]:
        if self.fixed_stage is not None or episode_stage != self.stage_index:
            return 0.0, 0, False
        self.outcomes.append(bool(succeeded))
        count = len(self.outcomes)
        rate = sum(self.outcomes) / count
        advanced = (count == self.window_size and rate >= self.advance_rate and
                    self.stage_index < len(self.stages) - 1)
        if advanced:
            self.stage_index += 1
            self.outcomes.clear()
        return rate, count, advanced

    def state(self) -> dict:
        return {"stage_index": self.stage_index,
                "outcomes": [int(value) for value in self.outcomes]}

    def restore(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise ValueError("Missing flat curriculum checkpoint state")
        index = state.get("stage_index")
        outcomes = state.get("outcomes")
        if (not isinstance(index, int) or not 0 <= index < len(self.stages) or
                not isinstance(outcomes, list) or len(outcomes) > self.window_size or
                any(value not in (0, 1) for value in outcomes)):
            raise ValueError("Invalid flat curriculum checkpoint state")
        if self.fixed_stage is not None and index != self.fixed_stage:
            raise ValueError("Flat curriculum checkpoint stage conflicts with fixed_stage")
        self.stage_index = index
        self.outcomes.clear()
        self.outcomes.extend(bool(value) for value in outcomes)
