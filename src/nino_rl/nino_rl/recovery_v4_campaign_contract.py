"""Versioned v4 resource, replay and simulator qualification boundary."""
from dataclasses import asdict, dataclass
import math
from pathlib import Path

from . import recovery_runner as runner
from .recovery_v4_bank import FAMILIES, require_bank, sample_layout
from .recovery_v4_runtime import runtime_configuration, CONFIG
from .recovery_v4_contract import load_config
from .recovery_v4_environment import CONTRACT_ID, V4Adapter
from .recovery_training_contract import read_json, sha, require_manifest
from .recovery_campaign_contract import CHECKPOINT_FILES, PHYSICAL_TERMINALS as PRIOR_TERMINALS

CAMPAIGN_KIND = 'nino_recovery_v4_campaign'
CHECKPOINT_KIND = 'nino_recovery_v4_checkpoint'
PHYSICAL_TERMINALS = PRIOR_TERMINALS | {'intrinsic_deadline', 'reference_intervention'}


@dataclass(frozen=True)
class CampaignRequest:
    prepared_root: Path
    families: tuple = ('clean',)
    transitions: int = 200000
    seed: int = 1511
    checkpoint_every: int = 25000
    checkpoint_keep: int = 10
    wall_seconds: int = 345600
    maximum_launches: int = 2000
    minimum_free_bytes: int = 4294967296
    raw_retention_bytes: int = 536870912
    successful_raw_keep: int = 2
    resume: Path | None = None
    qualification_root: Path | None = None
    software_fixture: bool = False
    learning_starts: int = 1000
    evaluation_split: str = 'heldout'
    episode_transition_limit: int = 400

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict) or 'prepared_root' not in raw or set(raw)-set(cls.__dataclass_fields__):
            raise ValueError('Unknown or missing v4 request fields')
        value = dict(raw)
        for key in ('prepared_root', 'resume', 'qualification_root'):
            if value.get(key) is not None:
                if not isinstance(value[key], str) or not value[key].strip():
                    raise ValueError('Nonempty v4 path required')
                value[key] = Path(value[key]).expanduser().resolve()
        families = value.get('families', ['clean'])
        if (not isinstance(families, list) or not families or len(set(families)) != len(families)
                or not set(families) <= set(FAMILIES)):
            raise ValueError('V4 releases clean and short_obstacle families only')
        value['families'] = tuple(families)
        request = cls(**value)
        for key, low, high in (('transitions', 64, 200000), ('seed', 0, 2**31-1),
                ('checkpoint_every', 1, 200000), ('checkpoint_keep', 2, 32),
                ('wall_seconds', 60, 604800), ('maximum_launches', 1, 4000),
                ('minimum_free_bytes', 2**31, 2**50), ('raw_retention_bytes', 2**28, 2**40),
                ('successful_raw_keep', 0, 20), ('learning_starts', 1, 10000)):
            if type(getattr(request, key)) is not int or not low <= getattr(request, key) <= high:
                raise ValueError('Invalid v4 limit '+key)
        if type(request.software_fixture) is not bool or request.episode_transition_limit != 400:
            raise ValueError('Explicit fixture flag and 400-step finite task required')
        if request.evaluation_split not in ('tune', 'heldout'):
            raise ValueError('Evaluation must use tune or heldout split')
        if (not request.software_fixture and request.learning_starts != 1000
                or request.software_fixture and request.learning_starts != 32):
            raise ValueError('Fixture warmup is 32; physical campaign warmup is 1000')
        if request.checkpoint_keep < math.ceil(request.transitions/request.checkpoint_every)+2:
            raise ValueError('Checkpoint retention must cover milestones and latest two')
        if request.maximum_launches*400 < request.transitions:
            raise ValueError('Insufficient launch budget')
        return request

    def state(self):
        value = asdict(self)
        value['families'] = list(self.families)
        for key in ('prepared_root', 'resume', 'qualification_root'):
            value[key] = None if value[key] is None else str(value[key])
        return value


def algorithm(request):
    return dict(name='TD3', actor_lr=load_config(CONFIG).learning_rate,
        critic_lr=load_config(CONFIG).learning_rate, gamma=.99, tau=.005,
        batch_size=256, buffer_size=max(1000, request.transitions), learning_starts=request.learning_starts,
        policy_delay=2, target_policy_noise=.2, target_noise_clip=.5, exploration_noise=.1,
        train_freq=1, gradient_steps=1, network_arch=[256, 256],
        learning_rate_semantics='one_shared_SB3_schedule')


@dataclass(frozen=True)
class ReadyBank:
    root: Path
    bank: dict
    receipts: dict

    def layout(self, family, stage=0):
        if stage != 0 or family not in FAMILIES:
            raise ValueError('Only qualified v4 stage zero')
        return sample_layout(self.bank, family, 'train', 0, 0)


def require_ready(request):
    bank = require_bank(request.prepared_root)
    receipts = {}
    if request.software_fixture:
        return ReadyBank(request.prepared_root, bank, dict(synthetic_fixture=True))
    root = request.qualification_root or request.prepared_root/'qualification'
    for family in request.families:
        for arm in ('classical', 'constant', 'governor'):
            directory = root/family/arm
            manifest = require_manifest(directory, ('job.json', 'result.json', 'source_qc.json',
                'episode_0_reset.json', 'environment_trace.jsonl'))
            job, result, qc = (read_json(directory/name) for name in ('job.json', 'result.json', 'source_qc.json'))
            outcome = result.get('outcome') or {}
            if (job.get('kind') != CAMPAIGN_KIND or job.get('status') != 'completed'
                    or job.get('source_pins') != runner.sources() or job.get('clean_closure') is not True
                    or result.get('bank_sha256') != sha(request.prepared_root/'inputs/bank.json')
                    or result.get('family') != family or result.get('arm') != arm
                    or qc.get('valid') is not True or outcome.get('measurement_valid') is not True
                    or outcome.get('terminated') is not True or outcome.get('truncated') is not False
                    or outcome.get('termination_reason') not in PHYSICAL_TERMINALS
                    or arm == 'classical' and outcome.get('task_success') is not True):
                raise ValueError('V4 simulator qualification failed '+family+'/'+arm)
            retained = runner.raw_qc(directory)
            if retained.get('valid') is not True:
                raise ValueError('Retained raw qualification failed')
            receipts[family+'/'+arm] = dict(manifest_sha256=sha(directory/'manifest.json'),
                result_sha256=manifest['result.json'])
    return ReadyBank(request.prepared_root, bank, receipts)


def campaign_identity(request, ready):
    from .residual_workflow import runtime_versions
    c, _, _, _ = runtime_configuration(ready.bank['config'], ready.layout(request.families[0]))
    plan = request.state()
    plan.pop('resume')
    return dict(kind=CAMPAIGN_KIND, checkpoint_kind=CHECKPOINT_KIND, contract_id=CONTRACT_ID,
        request=plan, families=list(request.families), profile=algorithm(request),
        source_pins=runner.sources(), bank_sha256=sha(request.prepared_root/'inputs/bank.json'),
        readiness=ready.receipts, controller_abi=V4Adapter(load_config(CONFIG), c).identity,
        runtime=runtime_versions(), hardware_authorized=False, learned_benefit_verified=False)


def inspect_checkpoint(path, *, expected_identity=None, require_resumable=True,
                       verify_files=True, check_runtime=True):
    root = Path(path).expanduser().resolve()
    if root.is_file():
        root = root.parent
    manifest = require_manifest(root, CHECKPOINT_FILES)
    if set(manifest) != CHECKPOINT_FILES:
        raise ValueError('V4 checkpoint file set differs')
    identity, meta, state, qc, replay = (read_json(root/name) for name in
        ('identity.json', 'checkpoint.json', 'state.json', 'source_qc.json', 'replay_audit.json'))
    if (identity.get('kind') != CAMPAIGN_KIND or meta.get('kind') != CHECKPOINT_KIND
            or expected_identity is not None and identity != expected_identity):
        raise ValueError('V4 checkpoint identity differs; v3 cannot resume')
    request = CampaignRequest.parse(identity['request'])
    n = state.get('transitions')
    if (type(n) is not int or not 0 <= n <= request.transitions or meta.get('global_steps') != n
            or meta.get('replay_size') != n or replay != dict(valid=True, rows_verified=n)):
        raise ValueError('V4 replay counters differ')
    eligible = (meta.get('qualified') is True and meta.get('episode_boundary') is True
        and meta.get('optimizer_boundary') is True and qc.get('valid') is True
        and len(state.get('completed', []))+len(state.get('censored', [])) == state.get('launch_attempts'))
    if meta.get('resumable') is not eligible or require_resumable and not eligible:
        raise ValueError('V4 diagnostic checkpoint is not resumable')
    if check_runtime and identity.get('source_pins') != runner.sources():
        raise ValueError('V4 checkpoint sources changed')
    return dict(path=str(root), identity=identity, checkpoint=meta, state=state,
        source_qc=qc, replay_audit=replay, manifest_sha256=sha(root/'manifest.json'),
        global_steps=n, replay_size=n, critic_updates=meta['critic_updates'],
        actor_updates=meta['actor_updates'], family=request.families[0] if len(request.families) == 1 else None)
