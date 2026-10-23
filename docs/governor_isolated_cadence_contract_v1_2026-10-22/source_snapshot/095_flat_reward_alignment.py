"""Opt-in flat reward units/impact costs; loaded only by a new snapshot."""
from math import isfinite

REVISION = 'vertical_energy_peak_v1'


def impact_terms(imu, config):
    """Dense energy plus one-shot episode peak increases, without saturation.

    Energy is the numerator of the evaluator's timestamped RMS statistic.
    Sum(cost) = weight * coverage_seconds/reference_dt * (episode_RMS/sigma)^2.
    This is NOT the entire evaluation objective or a duration-normalized RMS.
    Peak increments telescope to weight * final_episode_peak/peak_sigma.
    """
    if config.get('impact_mode') != REVISION:
        raise ValueError('Explicit vertical_energy_peak_v1 reward contract required')
    energy = float(imu['square_integral'])
    peak = float(imu['peak'])
    previous_peak = float(imu['previous_episode_peak'])
    weight = float(config['impact_weight'])
    peak_weight = float(config['peak_impact_weight'])
    sigma = float(config['impact_acceleration_sigma_m_s2'])
    peak_sigma = float(config['peak_acceleration_sigma_m_s2'])
    reference_dt = float(config['impact_reference_seconds'])
    values = (energy, peak, previous_peak, weight, peak_weight, sigma, peak_sigma, reference_dt)
    if not all(isfinite(x) for x in values) or min(energy, peak, previous_peak, weight, peak_weight) < 0:
        raise ValueError('Impact costs require finite nonnegative energy, peaks and weights')
    if min(sigma, peak_sigma, reference_dt) <= 0:
        raise ValueError('Impact normalization scales must be positive')
    return {'impact': -weight * energy / (sigma * sigma * reference_dt),
            'peak_impact': -peak_weight * max(0., peak - previous_peak) / peak_sigma}


def aligned_reward(legacy_terms, imu, config):
    terms = dict(legacy_terms)
    terms.update(impact_terms(imu, config))
    result = float(sum(terms.values()))
    if not isfinite(result):
        raise ValueError('Non-finite aligned reward')
    return result, terms


def validate_scale(value):
    scale = float(value)
    if not isfinite(scale) or scale <= 0:
        raise ValueError('Training reward scale must be positive and finite')
    return scale


def scaled_environment(environment, scale):
    """Wrap AFTER Monitor: raw task records remain raw; PPO receives scaled units.

    No running normalization statistics, observation changes, or reward clipping.
    Evaluation scoring and the actor's action interface are unaffected.
    """
    import gymnasium as gym
    scale = validate_scale(scale)

    class FixedRewardScale(gym.RewardWrapper):
        def reward(self, reward):
            if not isfinite(float(reward)):
                raise ValueError('Non-finite raw training reward')
            return float(reward) * scale

    return FixedRewardScale(environment)


def record_value_diagnostics(callback):
    """Record pre-update rollout targets/predictions, in PPO reward units."""
    import numpy as np
    from stable_baselines3.common.utils import explained_variance
    values = callback.model.rollout_buffer.values.flatten()
    targets = callback.model.rollout_buffer.returns.flatten()
    for name, data in (('prediction', values), ('target', targets)):
        callback.logger.record(f'critic/{name}_mean', float(np.mean(data)))
        callback.logger.record(f'critic/{name}_std', float(np.std(data)))
        callback.logger.record(f'critic/{name}_min', float(np.min(data)))
        callback.logger.record(f'critic/{name}_max', float(np.max(data)))
    callback.logger.record('critic/pre_update_explained_variance', float(explained_variance(values, targets)))
    callback.logger.record('critic/pre_update_mse', float(np.mean((values - targets) ** 2)))
