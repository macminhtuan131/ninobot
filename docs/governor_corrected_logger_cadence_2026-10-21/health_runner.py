"""One separately released follow-up; original failed batch is never resumed."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/"src/nino_rl/scripts"), str(ROOT/"src/nino_rl")]
import run_governor_cadence_experiment as runner
from nino_rl.observer_health import check_sidecar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("bundle", "output", "release"):
        parser.add_argument("--"+field, type=Path, required=True)
    parser.add_argument("--domain", type=int, default=131)
    args = parser.parse_args()
    protocol = json.loads((args.bundle/"protocol.json").read_text())
    assert protocol["observer_health"]["required"] is True
    original = runner.collect_attempt
    expected = hashlib.sha256((ROOT/"src/nino_rl/nino_rl/observer_health.py").read_bytes()).hexdigest()
    def collect(bundle, job, attempt):
        result = original(bundle, job, attempt)
        path = result.get("logger")
        check = check_sidecar(Path(path), expected) if path else dict(valid=False, error="logger_unavailable")
        result["observer_health_integrity"] = check
        result["measurement_integrity_pass"] &= check["valid"]
        return result
    runner.collect_attempt = collect
    print(json.dumps(runner.execute(args.bundle.resolve(), args.output.resolve(),
                                    args.release.resolve(), args.domain), indent=2))


if __name__ == "__main__":
    main()
