"""Bounded research training and measurement readiness for recovery100 TD3."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import math
from tempfile import TemporaryDirectory

from .recovery_curriculum import FAMILIES
from .recovery_training_contract import digest, read_json, require_manifest, sha


CAMPAIGN_KIND = 'nino_recovery100_campaign_v1'
CHECKPOINT_KIND = 'nino_recovery100_campaign_checkpoint_v1'
PROFILE = 'nino_recovery100_td3_research_v1'
PHYSICAL_TERMINALS = frozenset(('task_success', 'stall', 'path_violation',
    'physical_envelope_failure', 'recovery_timeout', 'motion_quality_violation',
    'task_timeout', 'incomplete_recovery'))
CHECKPOINT_FILES = frozenset(('model.zip', 'replay_buffer.pkl', 'identity.json',
    'checkpoint.json', 'state.json', 'rng.pkl', 'source_qc.json', 'replay_audit.json'))


@dataclass(frozen=True)
class CampaignRequest:
    prepared_root: Path
    transitions: int = 20000
    seed: int = 1511
    schema_version: int = 1
    mode: str = 'recovery-research'
    profile: str = PROFILE
    families: tuple[str, ...] = FAMILIES
    maximum_launches: int = 200
    episode_transition_limit: int = 400
    checkpoint_every: int = 5000
    wall_seconds: int = 86400
    minimum_free_bytes: int = 2147483648
    raw_retention_bytes: int = 4294967296
    successful_raw_keep: int = 5
    checkpoint_keep: int = 6
    resume: Path | None = None

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict) or 'prepared_root' not in raw:
            raise ValueError('Campaign request requires prepared_root')
        if set(raw)-set(cls.__dataclass_fields__):
            raise ValueError('Unknown recovery campaign request fields')
        value = dict(raw)
        for name in ('prepared_root', 'resume'):
            item = value.get(name)
            if item is not None:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError('Campaign path must be a nonempty string')
                value[name] = Path(item).expanduser().resolve()
        families = value.get('families', list(FAMILIES))
        if (not isinstance(families, list) or not families
                or any(type(f) is not str for f in families)
                or len(set(families)) != len(families) or not set(families) <= set(FAMILIES)):
            raise ValueError('Research campaign requires a nonempty unique subset of recovery families')
        value['families'] = tuple(families)
        request = cls(**value)
        for name, low, high in (('transitions', 1001, 100000), ('seed', 0, 2**31-1),
                ('maximum_launches', 5, 1000), ('checkpoint_every', 100, 100000),
                ('wall_seconds', 60, 86400), ('minimum_free_bytes', 2**31, 2**50),
                ('raw_retention_bytes', 2**28, 2**40), ('successful_raw_keep', 0, 20),
                ('checkpoint_keep', 2, 32)):
            n = getattr(request, name)
            if type(n) is not int or not low <= n <= high:
                raise ValueError('Invalid campaign resource limit: '+name)
        if (type(request.schema_version) is not int or request.schema_version != 1
                or request.mode != 'recovery-research' or request.profile != PROFILE
                or type(request.episode_transition_limit) is not int
                or request.episode_transition_limit != 400):
            raise ValueError('Unsupported recovery campaign contract')
        if request.maximum_launches*400 < request.transitions:
            raise ValueError('Launch budget cannot supply the requested transition budget')
        if request.checkpoint_keep < math.ceil(request.transitions/request.checkpoint_every)+2:
            raise ValueError('Checkpoint retention must cover milestones and two latest boundaries')
        return request

    def state(self):
        value = asdict(self)
        value.update(prepared_root=str(self.prepared_root), families=list(self.families),
                     resume=None if self.resume is None else str(self.resume))
        return value


def algorithm(request):
    return dict(name='TD3', actor_lr=.0003, critic_lr=.0003, gamma=.99, tau=.005,
        batch_size=256, buffer_size=request.transitions, learning_starts=1000,
        policy_delay=2, target_policy_noise=.2, target_noise_clip=.5,
        exploration_noise=.1, train_freq=1, gradient_steps=1, network_arch=[256, 256],
        warmup_rationale='1000 transitions, 5 percent of the initial 20000 budget; not tuned')


@dataclass(frozen=True)
class ReadyBank:
    root: Path
    bank: dict
    readiness: Path
    receipts: dict

    def layout(self, family, stage=0):
        if stage != 0 or family not in self.receipts:
            raise ValueError('Campaign only releases measurement-ready stage zero')
        rows = [r for r in self.bank['layouts'] if
                (r['family'], r['stage'], r['split']) == (family, stage, 'development')]
        if len(rows) != 1:
            raise ValueError('Campaign requires one development layout per family')
        return rows[0]


def require_ready(request, root):
    from . import recovery_runner as runner
    root = Path(root).expanduser().resolve()
    bank = runner.require_bank(request.prepared_root)
    pins = runner.sources()
    receipts = {}
    for family in request.families:
        probe = root/'readiness'/f'{family}_s0'
        manifest = require_manifest(probe, ('job.json', 'result.json', 'source_qc.json',
            'episode_0_reset.json', 'environment_trace.jsonl'))
        job, result, qc, reset = (read_json(probe/name) for name in
            ('job.json', 'result.json', 'source_qc.json', 'episode_0_reset.json'))
        layouts = [r for r in bank['layouts'] if
                   (r['family'], r['stage'], r['split']) == (family, 0, 'development')]
        if len(layouts) != 1:
            raise ValueError('Missing unique readiness layout')
        with TemporaryDirectory(prefix='nino_campaign_readiness_') as temporary:
            audit = Path(temporary)
            (audit/'episodes').symlink_to(probe/'episodes', target_is_directory=True)
            for artifact in probe.glob('episode_*_reset.json'):
                (audit/artifact.name).symlink_to(artifact)
            (audit/'environment_trace.jsonl').symlink_to(probe/'environment_trace.jsonl')
            retained = runner.raw_qc(audit)
        outcome = result.get('outcome') or {}
        if (job.get('kind') != CAMPAIGN_KIND or job.get('action') != 'readiness-probe'
                or job.get('status') != 'completed' or job.get('source_pins') != pins
                or job.get('clean_closure') is not True
                or (result.get('family'), result.get('stage')) != (family, 0)
                or result.get('layout_id') != layouts[0]['id']
                or result.get('world_sha256') != layouts[0]['world_sha256']
                or result.get('bank_sha256') != sha(request.prepared_root/'inputs/bank.json')
                or reset.get('private_layout') != layouts[0]
                or qc.get('valid') is not True or result.get('source_qc') != qc
                or retained.get('valid') is not True
                or set(retained.get('episodes', {})) != {'episode_0'}
                or retained['episodes']['episode_0'].get('boundary_coverage_checked') is not True
                or outcome.get('measurement_valid') is not True
                or outcome.get('terminated') is not True or outcome.get('truncated') is not False
                or outcome.get('termination_reason') not in PHYSICAL_TERMINALS):
            raise ValueError('Recovery measurement/backend readiness failed: '+family)
        receipts[family] = dict(manifest_sha256=sha(probe/'manifest.json'),
                                result_sha256=manifest['result.json'])
    return ReadyBank(request.prepared_root, bank, root, receipts)


def campaign_identity(request, ready):
    from . import recovery_runner as runner
    from .recovery_contract import CONTRACT_ID, RecoveryAdapter
    from .residual_workflow import runtime_versions
    controller, _, _, _ = runner.runtime_configuration(ready.bank['config'],
                                                      ready.layout(request.families[0]))
    plan = request.state()
    plan.pop('resume')
    return dict(kind=CAMPAIGN_KIND, checkpoint_kind=CHECKPOINT_KIND, contract_id=CONTRACT_ID,
        request=plan, profile=algorithm(request), source_pins=runner.sources(),
        bank_sha256=sha(request.prepared_root/'inputs/bank.json'), readiness=ready.receipts,
        runtime=runtime_versions(), controller_abi=RecoveryAdapter(controller).identity,
        stages={family: [0] for family in request.families}, hardware_authorized=False,
        classical_success_required=False, learned_benefit_verified=False)


def inspect_checkpoint(path, *, expected_identity=None, require_resumable=True):
    root = Path(path).expanduser().resolve()
    manifest = require_manifest(root, CHECKPOINT_FILES)
    if set(manifest) != CHECKPOINT_FILES:
        raise ValueError('Unexpected campaign checkpoint files')
    identity, metadata, state, qc, replay = (read_json(root/name) for name in
        ('identity.json', 'checkpoint.json', 'state.json', 'source_qc.json', 'replay_audit.json'))
    if (identity.get('kind') != CAMPAIGN_KIND or metadata.get('kind') != CHECKPOINT_KIND
            or identity.get('checkpoint_kind') != CHECKPOINT_KIND
            or expected_identity is not None and identity != expected_identity):
        raise ValueError('Campaign checkpoint identity mismatch')
    request = CampaignRequest.parse(identity['request'])
    n, launches = state.get('transitions'), state.get('launch_attempts')
    if (type(n) is not int or not 0 <= n <= request.transitions
            or type(launches) is not int or not 0 <= launches <= request.maximum_launches
            or metadata.get('global_steps') != n or metadata.get('replay_size') != n
            or replay.get('rows_verified') != n or replay.get('valid') is not True):
        raise ValueError('Campaign checkpoint replay/counters mismatch')
    eligible = (metadata.get('episode_boundary') is True and metadata.get('optimizer_boundary') is True
                and metadata.get('qualified') is True and qc.get('valid') is True
                and len(state.get('completed', []))+len(state.get('censored', [])) == launches)
    if metadata.get('resumable') is not eligible or require_resumable and not eligible:
        raise ValueError('Campaign diagnostic checkpoint cannot resume')
    return dict(path=str(root), identity=identity, checkpoint=metadata, state=state,
                source_qc=qc, replay_audit=replay, manifest_sha256=sha(root/'manifest.json'))
