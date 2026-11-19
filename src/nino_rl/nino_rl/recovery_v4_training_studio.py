"""Translate Studio jobs to the canonical v4 campaign without motor access."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import traceback

from .recovery_v4_studio_contract import ENGINE, canonical_request, validate_request

PREFIX = "@@NINO_RESEARCH@@"


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def emit(directory, **fields):
    print(PREFIX + json.dumps(dict(action="td3-recovery-v4", directory=str(directory), **fields)), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    raw = json.loads(args.request.read_text())
    from .training_studio_api_v3 import split
    engine, request = split(raw)
    if engine != ENGINE:
        raise ValueError("Recovery v4 adapter rejects other engines")
    request = validate_request(request)
    directory = args.output.expanduser().resolve() / ("recovery_v4_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True)
    write(directory / "job.json", dict(status="running", request=request, engine=ENGINE,
                                      simulator_only=True, mode=request["mode"]))
    canonical = canonical_request(request)
    request_path = directory / "campaign_request.json"
    write(request_path, canonical)
    emit(directory, phase="prepare", message="SIMULATOR v4. Neutral action -1. Canonical runner validates release.")
    action = {"smoke": "software-smoke", "qualify": "qualify", "train": "train"}[request["mode"]]
    try:
        from .recovery_v4_campaign import main as campaign
        code = campaign([action, "--request", str(request_path), "--output", str(directory / "campaign")])
        source = directory / "campaign" / "result.json"
        native = json.loads(source.read_text()) if source.is_file() else {}
        progress = directory / "campaign" / "progress.json"
        live = json.loads(progress.read_text()) if progress.is_file() else {}
        steps = native.get("global_steps", live.get("global_steps", 0))
        start = native.get("starting_global_steps", live.get("starting_global_steps", 0))
        critic = native.get("critic_updates", live.get("critic_updates", 0))
        actor = native.get("actor_updates", live.get("actor_updates", 0))
        result = dict(native, engine=ENGINE, simulator_only=request["mode"] != "smoke",
                      software_fixture=request["mode"] == "smoke",
                      transitions=max(0, steps-start), starting_global_steps=start,
                      global_steps=steps, optimizer_updates_this_job=native.get("optimizer_updates_this_job", critic),
                      optimizer_updates_total=critic, actor_updates_total=actor,
                      checkpoint=native.get("checkpoint") or "", final_segment_right_censored=native.get("final_segment_right_censored", False))
        write(directory / "result.json", result)
        status = "completed" if not code else "failed"
        write(directory / "job.json", dict(status=status, request=request, engine=ENGINE, error=native.get("error")))
        emit(directory, phase=status, result=result, error=native.get("error"))
        return code or 0
    except BaseException as error:
        (directory / "error.txt").write_text(traceback.format_exc())
        write(directory / "job.json", dict(status="failed", request=request, engine=ENGINE, error=str(error)))
        emit(directory, phase="failed", error=str(error), message=str(error))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
