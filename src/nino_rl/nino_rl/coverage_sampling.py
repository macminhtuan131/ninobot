"""Causal exploration for the coverage study; no global RNG mutation."""
import numpy as np


ARMS = ("A_gaussian", "C_stratified_probes")


class CoverageSampler:
    def __init__(self, seed, arm):
        if arm not in ARMS:
            raise ValueError("Unknown coverage arm")
        self.seed, self.arm = int(seed), arm
        streams = np.random.SeedSequence(seed).spawn(6)
        self.warmup, self.gaussian, self.order, self.jitter = [
            np.random.default_rng(streams[i]) for i in (1, 2, 3, 4)]
        self.eligible = self.probes = self.decisions = 0
        self.permutation = []

    def choose(self, observation, actor_mean, timestep):
        obs = np.asarray(observation, dtype=np.float32)
        mean = np.asarray(actor_mean, dtype=np.float32)
        if (obs.shape != (103,) or not np.isfinite(obs).all() or obs[101] not in (0., 1.)
                or mean.shape != (1,) or not np.isfinite(mean).all()
                or abs(float(mean[0])) > 1. or timestep != self.decisions):
            raise ValueError("Finite causal103D/scalar packet and sequential decision required")
        self.decisions += 1
        probe, bin_index, noise = False, None, None
        warmup = timestep < 64
        if warmup:
            requested = float(self.warmup.uniform(-1., 1.))
        else:
            noise = float(self.gaussian.normal(0., .1))
            requested = float(np.clip(float(mean[0]) + noise, -1., 1.))
            if obs[101] == 1.:
                self.eligible += 1
                if self.arm == ARMS[1] and self.eligible % 4 == 0:
                    if not self.permutation:
                        self.permutation = self.order.permutation(4).tolist()
                    bin_index = self.permutation.pop(0)
                    low = -1. + .5 * bin_index
                    requested = float(self.jitter.uniform(low, low + .5))
                    self.probes += 1
                    probe = True
        request = np.array([requested], dtype=np.float32)
        audit = dict(timestep=timestep + 1, arm=self.arm, warmup=warmup,
            actor_mean=mean.tolist(), gaussian_noise=noise, window_open=bool(obs[101]),
            eligible_open_decisions=self.eligible, probe=probe, probe_bin=bin_index,
            probe_count=self.probes, requested_scalar=request.tolist(),
            replay_semantics="actual_request_after_probe_before_projection")
        return request, audit
