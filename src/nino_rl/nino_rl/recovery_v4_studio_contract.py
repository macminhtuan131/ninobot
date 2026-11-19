"""Studio boundary for the simulator-only Recovery v4 campaign."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

ENGINE = "recovery107_v4"
CHECKPOINT_KIND = "nino_recovery_v4_checkpoint"
SMOKE_PROFILE = "recovery_v4_software_smoke"
RESEARCH_PROFILE = "recovery_v4_research"
OBSERVATION_DIM = 107
ACTION_DIM = 1
SMOKE_STEPS = 64
MAX_TIMESTEPS = 200000
SCENARIOS = {"clean": "Sàn sạch · v4", "short_obstacle": "Gờ cứng chưa biết · v4"}


def profiles():
    algorithm = dict(actor_lr=.0003, critic_lr=.0003, gamma=.99, tau=.005,
                     batch_size=256, buffer_size=200000, learning_starts=1000,
                     policy_delay=2, target_policy_noise=.2, target_noise_clip=.5,
                     exploration_noise=.1, train_freq=1, gradient_steps=1,
                     network_arch=[256, 256])
    return {name: dict(algorithm=deepcopy(algorithm), simulator_only=True,
                      observation_dim=OBSERVATION_DIM, action_dim=ACTION_DIM,
                      neutral_action=-1, profile_status="campaign_resolves_effective_algorithm")
            for name in (SMOKE_PROFILE, RESEARCH_PROFILE)}


def validate_request(raw):
    request = dict(raw)
    names = {"schema_version", "mode", "scenario", "profile", "timesteps", "seed",
             "checkpoint_every", "wall_minutes", "evaluate", "resume", "prepared_root"}
    if set(request) != names or type(request["schema_version"]) is not int or request["schema_version"] != 1:
        raise ValueError("A versioned Recovery v4 Studio request is required")
    if request["mode"] not in ("smoke", "qualify", "train"):
        raise ValueError("Choose software smoke, simulator qualification or training")
    if request["scenario"] not in SCENARIOS or request["profile"] not in profiles():
        raise ValueError("Recovery v4 requires its own family and profile")
    for key, low, high in (("timesteps", 1, MAX_TIMESTEPS), ("seed", 0, 2147483647),
                           ("checkpoint_every", 0, MAX_TIMESTEPS), ("wall_minutes", 1, 10080)):
        if type(request[key]) is not int or not low <= request[key] <= high:
            raise ValueError("Invalid Recovery v4 request field " + key)
    if type(request["evaluate"]) is not bool or request["resume"] is not None and not isinstance(request["resume"], str):
        raise ValueError("Explicit evaluation flag and optional checkpoint path required")
    if not isinstance(request["prepared_root"], str) or not request["prepared_root"].strip():
        raise ValueError("Select the prepared v4 root before running")
    if request["mode"] == "smoke" and (request["timesteps"] != SMOKE_STEPS or request["profile"] != SMOKE_PROFILE or request["resume"] is not None):
        raise ValueError("V4 software smoke uses 64 fresh transitions and its own profile")
    if request["mode"] == "train" and request["profile"] != RESEARCH_PROFILE:
        raise ValueError("Training requires the research profile")
    if request["mode"] == "train" and request["resume"] is None and request["timesteps"] <= profiles()[RESEARCH_PROFILE]["algorithm"]["learning_starts"]:
        raise ValueError("Fresh training must exceed the warmup budget")
    return request


def canonical_request(request):
    request = validate_request(request)
    return dict(prepared_root=str(Path(request["prepared_root"]).expanduser().resolve()),
                families=[request["scenario"]], transitions=request["timesteps"],
                seed=request["seed"], checkpoint_every=request["checkpoint_every"] or 25000,
                checkpoint_keep=10, wall_seconds=request["wall_minutes"] * 60,
                maximum_launches=2000, minimum_free_bytes=4294967296,
                raw_retention_bytes=536870912, successful_raw_keep=2,
                resume=request["resume"])


def budget(request):
    return dict(required_free_bytes=4294967296, reserve_bytes=4294967296,
                hardware_actions=0, simulator_only=True)


def require_disk(root, request):
    path = Path(root).expanduser().resolve()
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    result = budget(request)
    if free < result["required_free_bytes"]:
        raise ValueError("Recovery v4 requires at least 4 GiB free before launch")
    return dict(result, free_bytes=free)


def qualification_status(prepared_root):
    root = Path(prepared_root).expanduser()
    if not prepared_root or not root.is_dir():
        return "CHƯA CHUẨN BỊ · chọn prepared root v4"
    return "SIMULATOR · runner xác minh receipt và source hash trước train; thư mục tồn tại chưa phải release"


def inspect_checkpoint(path, verify_files=True, check_runtime=True):
    from .recovery_v4_campaign import inspect_checkpoint as inspect
    result = inspect(Path(path), verify_files=verify_files, check_runtime=check_runtime)
    identity = result.get("identity", {})
    family = result.get("family") or identity.get("family")
    families = identity.get("families", [])
    if family is None and len(families) == 1:
        family = families[0]
    return dict(result, engine=ENGINE, scenario=family, profile=RESEARCH_PROFILE,
                seed=identity["request"]["seed"],
                optimizer_updates=result.get("optimizer_updates", result.get("critic_updates", 0)),
                replay_size=result.get("replay_size", result.get("replay_rows_verified", 0)))
