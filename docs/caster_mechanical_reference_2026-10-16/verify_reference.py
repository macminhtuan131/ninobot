"""Reproduce offline checks without ROS, modifying only verification.json."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
script = ROOT / "src/nino_rl/scripts/audit_caster_mechanical_reference.py"
spec = importlib.util.spec_from_file_location("mechanical_reference", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

baseline = json.loads((OUT / "nominal_reference.json").read_text())
urdfs = sorted((ROOT / "rl_runs/governor_frozen_repeats_2026-10-16").glob(
    "attempt_*/confirmation/repeat/screen/*/contact/*/robot_description.urdf"))
results = [module.audit(path, ROOT / "src/nino_description") for path in urdfs]
prior = json.loads((ROOT / "docs/governor_frozen_repeats_2026-10-16/bracket_first_contact_geometry.json").read_text())
protocol = json.loads((ROOT / "docs/governor_frozen_repeats_2026-10-16/protocol_before_results.json").read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def changed(manifest):
    return [name for name, digest in manifest.items()
            if not Path(name).is_file() or sha(name) != digest]

# Independent scalar mass/COM calculation from the named link specifications.
mass = 2.5 + 1.3 + 2 * .8 + 2 * (.0821604275 + .0131302038)
x_moment = 2.5 * .0592774512 + 1.3 * .20 + 2 * (
    .0821604275 * (.24362 - .0016273079) + .0131302038 * (.24362 - .016))
z_moment = 2.5 * (.0625 + .0848297985) + 1.3 * (.0625 + .165) + 1.6 * .0625 + 2 * (
    .0821604275 * (.0625 - .0215 - .0041294433) + .0131302038 * .016)
rotated = module.matvec(module.origin(module.ET.fromstring(
    '<origin xyz="0 0 0" rpy="0 0 1.5707963267948966"/>'))[0], (1., 0., 0.))
checks = {
    "four_captured_urdfs": len(urdfs) == 4,
    "captured_urdfs_identical": len({sha(path) for path in urdfs}) == 1,
    "repeat_extraction_identical": json.loads(json.dumps(results[0])) == baseline,
    "bracket_clearance_matches_independent_prior_vertex_audit": all(
        math.isclose(side["bracket_lowest_nominal_mm"] / 1000,
                     prior["nominal_bracket_lowest_z_m"], abs_tol=1e-12)
        for result in results for side in result["casters"].values()),
    "both_wheels_on_nominal_floor": all(
        abs(side["wheel_lowest_nominal_mm"]) < 1e-9
        for result in results for side in result["casters"].values()),
    "nominal_mass_independent_sum": math.isclose(baseline["modeled_mass_kg"], mass, abs_tol=1e-12),
    "nominal_com_independent_scalar_moments": all(math.isclose(a, b, abs_tol=1e-12)
        for a, b in zip(baseline["nominal_aggregate_com_m"], [x_moment / mass, 0., z_moment / mass])),
    "rotation_convention_quarter_turn": all(math.isclose(a, b, abs_tol=1e-12)
        for a, b in zip(rotated, (0., 1., 0.))),
    "runtime_hashes_unchanged": not changed(protocol["source_sha256"]),
    "config_hash_unchanged": sha(ROOT / "rl_runs/governor_frozen_repeats_2026-10-16/config.yaml") ==
        protocol["prepared_protocol"]["fixed_config_sha256"],
    "real_measurements_still_unknown": json.loads((OUT / "hardware_measurements.json").read_text())["status"] ==
        "awaiting_real_measurements",
}
manifests = {}
for name in ("preservation_before.json", "source_manifest_sha256.json"):
    data = json.loads((ROOT / "docs/governor_frozen_repeats_2026-10-16" / name).read_text())
    delta = changed(data)
    manifests[name] = dict(files=len(data), changed=delta)
    checks[name + "_unchanged"] = not delta
report = dict(checks=checks, all_pass=all(checks.values()), manifests=manifests,
              extractor_sha256=sha(script), new_simulation_episodes=0,
              physics_controller_or_metric_changes=False,
              qualification="Offline arithmetic/provenance checks, not hardware/contact fidelity tests.")
with (OUT / "verification.json").open("x") as stream:
    json.dump(report, stream, indent=2)
    stream.write("\n")
print(json.dumps(report, indent=2))
if not report["all_pass"]:
    raise SystemExit(1)
