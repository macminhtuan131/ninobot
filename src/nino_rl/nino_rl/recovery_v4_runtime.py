"""Simulator factories for the v4 actor ABI. Construction never starts Gazebo."""
from . import recovery_runner as prior
from .recovery_v4_contract import load_config
from .recovery_v4_environment import CONTRACT_ID, V4Env
from .recovery_contract import StartBudget
from .recovery_task import RecoveryBands
from .unknown_step_runtime import TaskSettings
from .residual_factory_workflow import repo

CONFIG = repo()/'src/nino_rl/config/recovery_v4.yaml'


def runtime_configuration(config, layout):
    controller, guidance, protocol, condition = prior.runtime_configuration(config, layout)
    controller['purpose'] = CONTRACT_ID
    controller['backend']['scenario_id'] = CONTRACT_ID
    guidance['baseline_id'] = CONTRACT_ID+'_causal_follower'
    protocol['protocol_id'] = CONTRACT_ID
    condition['scenario'] = CONTRACT_ID
    # Reset consumes four real frames outside the finite learner mission.
    for block in (controller['backend'], controller['task'], protocol):
        block['horizon_s'] = config['horizon_s']+1.
        block['command_until_s'] = config['horizon_s']+1.
    return controller, guidance, protocol, condition


def make_environment(config, layout, envelope, backend, controller=None, *, v4_config=None):
    c, g, protocol, condition = runtime_configuration(config, layout)
    return V4Env(v4_config or load_config(CONFIG), controller or c, backend,
        TaskSettings(**layout['task_settings']), layout['obstacles'],
        RecoveryBands(**config['recovery_bands']), StartBudget(**config['start_budget']),
        runtime_identity=dict(guidance=g, protocol=protocol, condition=condition),
        macro_ramp=layout.get('macro_ramp'), motion_quality=config['motion_quality'])


def make_backend(config, layout, envelope, output, *, maximum_launches):
    from .recovery_startup import RecoveryBackend
    from .reliable_episode import EpisodeLifecycle
    c, g, protocol, condition = runtime_configuration(config, layout)
    limits = dict(training_episodes_per_seed_maximum=maximum_launches,
        observer_start_deadline_s=15., feedback_deadline_s=5., observer_ipc_grace_s=1.,
        maximum_support_age_ns=40_000_000)
    return EpisodeLifecycle(c, output/'episodes', layout['world'], g, protocol, condition,
        limits, backend_factory=lambda *args: RecoveryBackend(*args, expected_envelope=envelope))
