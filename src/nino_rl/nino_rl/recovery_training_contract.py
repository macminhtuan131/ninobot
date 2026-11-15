"""Qualification and immutable bundles for the bounded recovery smoke."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .recovery_curriculum import FAMILIES

CHECKPOINT_KIND = 'nino_recovery_live_smoke_checkpoint_v1'
PROFILE = 'nino_td3_smoke_h5_v1'
REQUIRED_FILES = frozenset(('model.zip', 'replay_buffer.pkl', 'identity.json',
    'checkpoint.json', 'job_state.json', 'rng.pkl', 'source_qc.json', 'replay_audit.json'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


@dataclass(frozen=True)
class RecoverySmokeRequest:
    prepared_root: Path
    families: tuple[str, ...]
    seed: int = 1511
    schema_version: int = 1
    mode: str = 'live-smoke'
    transitions: int = 384
    maximum_launches: int = 4
    episode_transition_limit: int = 128
    profile: str = PROFILE
    wall_seconds: int = 1800
    minimum_free_bytes: int = 2147483648
    resume: Path | None = None

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError('Recovery request must be an object')
        allowed = set(cls.__dataclass_fields__)
        if set(raw)-allowed or not {'prepared_root', 'families'} <= set(raw):
            raise ValueError('Unknown or missing recovery request fields')
        value = dict(raw)
        for name in ('prepared_root', 'resume'):
            item = value.get(name)
            if item is not None:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError('Request path must be a nonempty string')
                value[name] = Path(item).expanduser().resolve()
        families = value['families']
        if (not isinstance(families, list) or not families
                or any(type(f) is not str or f not in FAMILIES for f in families)
                or len(set(families)) != len(families)):
            raise ValueError('Select distinct known recovery families')
        value['families'] = tuple(families)
        request = cls(**value)
        exact = dict(schema_version=1, transitions=384, maximum_launches=4,
                     episode_transition_limit=128)
        for name, expected in exact.items():
            if type(getattr(request, name)) is not int or getattr(request, name) != expected:
                raise ValueError('Unsupported fixed smoke budget: '+name)
        for name, lower, upper in (('seed', 0, 2**31-1), ('wall_seconds', 1, 3600),
                ('minimum_free_bytes', 2147483648, 2**50)):
            number = getattr(request, name)
            if type(number) is not int or not lower <= number <= upper:
                raise ValueError('Invalid recovery resource setting: '+name)
        if request.mode != 'live-smoke' or request.profile != PROFILE:
            raise ValueError('Only the explicit bounded recovery smoke is supported')
        return request

    def state(self):
        value = asdict(self)
        value['prepared_root'] = str(self.prepared_root)
        value['resume'] = None if self.resume is None else str(self.resume)
        value['families'] = list(self.families)
        return value


@dataclass(frozen=True)
class EpisodeAssignment:
    episode_id: str
    family: str
    sampled_stage: int
    layout_id: str
    world_sha256: str


@dataclass(frozen=True)
class QualifiedRecoveryBank:
    root: Path
    bank: dict
    bank_sha256: str
    source_pins_sha256: str
    baselines: dict

    def layout(self, family, stage):
        if (family, stage) not in self.baselines:
            raise ValueError('Unqualified recovery family/stage')
        rows = [r for r in self.bank['layouts'] if
                (r['family'], r['stage'], r['split']) == (family, stage, 'development')]
        if len(rows) != 1:
            raise ValueError('Recovery assignment needs one development layout')
        return rows[0]


def require_manifest(root, required):
    root = Path(root).resolve()
    manifest = read_json(root/'manifest.json')
    if not isinstance(manifest, dict) or not set(required) <= set(manifest):
        raise ValueError('Incomplete immutable manifest')
    actual = {str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and p != root/'manifest.json'}
    if actual != set(manifest):
        raise ValueError('Manifest does not cover the full artifact')
    for name, expected in manifest.items():
        path = (root/name).resolve()
        if (not path.is_relative_to(root) or path == root or not path.is_file()
                or sha(path) != expected):
            raise ValueError('Artifact manifest differs: '+name)
    return manifest


def require_live_qualification(request):
    from . import recovery_runner as runner
    bank = runner.require_bank(request.prepared_root)
    bank_hash = sha(request.prepared_root/'inputs/bank.json')
    pins_hash = sha(request.prepared_root/'inputs/source_pins.json')
    baselines = {}
    families = set(request.families)
    if 'mixed' in families:
        runner.require_components(request.prepared_root, 'mixed')
        families.update(('short_obstacle', 'pothole'))
    for family in sorted(families):
        root = request.prepared_root/f'baseline_{family}_s0'
        manifest = require_manifest(root, ('job.json', 'result.json', 'source_qc.json',
            'environment_trace.jsonl', 'episode_0_reset.json'))
        job, result, qc = (read_json(root/name) for name in
                           ('job.json', 'result.json', 'source_qc.json'))
        rows = [r for r in bank['layouts'] if
                (r['family'], r['stage'], r['split']) == (family, 0, 'development')]
        if len(rows) != 1:
            raise ValueError('Missing unique development baseline layout')
        layout = rows[0]
        reset = read_json(root/'episode_0_reset.json')
        with TemporaryDirectory(prefix='nino_recovery_qualification_') as temporary:
            audit_root = Path(temporary)
            (audit_root/'episodes').symlink_to(root/'episodes', target_is_directory=True)
            for artifact in root.glob('episode_*_reset.json'):
                (audit_root/artifact.name).symlink_to(artifact)
            (audit_root/'environment_trace.jsonl').symlink_to(root/'environment_trace.jsonl')
            retained_qc = runner.raw_qc(audit_root)
        outcome = result.get('outcome') or {}
        if (job.get('status') != 'completed' or job.get('action') != 'baseline'
                or job.get('family') != family or job.get('stage') != 0
                or job.get('source_pins') != runner.sources()
                or result.get('classical_baseline_only') is not True
                or result.get('optimizer_updates') != 0
                or result.get('physical_gate_pass') is not True
                or (result.get('family'), result.get('stage')) != (family, 0)
                or result.get('bank_sha256') != bank_hash
                or result.get('world_sha256') != layout['world_sha256']
                or result.get('layout_id') != layout['id']
                or reset.get('private_layout') != layout
                or qc.get('valid') is not True or result.get('source_qc') != qc
                or retained_qc.get('valid') is not True
                or set(retained_qc.get('episodes', {})) != {'episode_0'}
                or not qc.get('episodes')
                or any(e.get('valid') is not True for e in qc['episodes'].values())
                or any(outcome.get(k) is not True for k in ('measurement_valid',
                    'task_success', 'motion_quality_pass', 'all_obstacles_recovered', 'terminated'))
                or outcome.get('truncated') is not False):
            raise ValueError('Current physical recovery baseline is unqualified: '+family)
        baselines[(family, 0)] = dict(manifest_sha256=sha(root/'manifest.json'),
                                    result_sha256=manifest['result.json'])
    return QualifiedRecoveryBank(request.prepared_root, bank, bank_hash, pins_hash, baselines)


def training_identity(request, qualified):
    from . import recovery_runner as runner
    from .common_studio_v2_contract import profiles
    from .recovery_contract import CONTRACT_ID, RecoveryAdapter
    from .residual_workflow import runtime_versions
    config = qualified.bank['config']
    layout = qualified.layout(request.families[0], 0)
    controller, _, _, _ = runner.runtime_configuration(config, layout)
    profile = profiles()[request.profile]
    if profile['algorithm']['train_freq'] != 1 or profile['algorithm']['gradient_steps'] != 1:
        raise ValueError('Deferred recovery reset requires one-step TD3 rollouts')
    return dict(checkpoint_kind=CHECKPOINT_KIND, contract_id=CONTRACT_ID,
        bank_sha256=qualified.bank_sha256, source_pins_sha256=qualified.source_pins_sha256,
        source_pins=runner.sources(), families=list(request.families), seed=request.seed,
        budget=dict(transitions=request.transitions, maximum_launches=request.maximum_launches,
                    episode_transition_limit=request.episode_transition_limit),
        profile_id=request.profile, effective_profile=profile,
        runtime=runtime_versions(), controller_abi=RecoveryAdapter(controller).identity,
        recovery_configuration=config,
        baselines={f'{f}_s{s}': value for (f, s), value in qualified.baselines.items()},
        hardware_authorized=False, learned_benefit_verified=False)


def inspect_recovery_checkpoint(path, *, expected_identity=None, require_resumable=False):
    root = Path(path).expanduser().resolve()
    manifest = require_manifest(root, REQUIRED_FILES)
    if set(manifest) != REQUIRED_FILES:
        raise ValueError('Unsupported recovery checkpoint file set')
    identity, meta, state, qc, replay = (read_json(root/name) for name in
        ('identity.json', 'checkpoint.json', 'job_state.json', 'source_qc.json', 'replay_audit.json'))
    if (meta.get('kind') != CHECKPOINT_KIND or identity.get('checkpoint_kind') != CHECKPOINT_KIND
            or (expected_identity is not None and identity != expected_identity)):
        raise ValueError('Incompatible recovery checkpoint identity')
    transitions, launches = state.get('transitions'), state.get('launch_attempts')
    if (type(transitions) is not int or not 0 <= transitions <= 384
            or type(launches) is not int or not 0 <= launches <= 4
            or meta.get('global_steps') != transitions or meta.get('replay_size') != transitions
            or type(replay.get('rows_verified')) is not int
            or not 0 <= replay['rows_verified'] <= transitions
            or (replay.get('valid') is True and replay['rows_verified'] != transitions)):
        raise ValueError('Invalid recovery checkpoint counters/replay prefix')
    eligible = (meta.get('stored_episode_boundary') is True
                and meta.get('episode_qc_pass') is True and qc.get('valid') is True
                and replay.get('valid') is True and meta.get('qualified') is True)
    if meta.get('resumable') is not eligible:
        raise ValueError('Recovery checkpoint has contradictory resume qualification')
    if require_resumable and not eligible:
        raise ValueError('Diagnostic recovery bundle cannot resume')
    return dict(path=str(root), identity=identity, checkpoint=meta, state=state,
                source_qc=qc, replay_audit=replay, manifest_sha256=sha(root/'manifest.json'))
