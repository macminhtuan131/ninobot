#!/usr/bin/env python3
"""Verify raw immutability, historical helper equivalence and native replay."""
import ast
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'src/nino_rl/scripts'),str(ROOT/'src/nino_rl'),str(ROOT/'src/nino_control')]
from prepare_isolated_cadence_contract import validate


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


provenance=json.loads((HERE/'results/provenance.json').read_text())
changed=[p for p,h in provenance['inputs_sha256'].items() if sha(p)!=h]
historical=json.loads((ROOT/'docs/governor_survey_phase_audit_2026-10-20/provenance.json').read_text())['inputs_sha256']
historical_drift=[p for p,h in historical.items() if sha(p)!=h]
equivalence=[]
snapshot=ROOT/'docs/governor_descriptive_survey_2026-10-18/source_snapshot'
for relative,name,functions in [
    ('src/nino_control/nino_control/governor_core.py','06_governor_core.py',['quaternion_rpy','vertical_acceleration']),
    ('src/nino_rl/scripts/prepare_governor_contact_sequence.py','17_prepare_governor_contact_sequence.py',['signal_stats'])]:
    now,old=ROOT/relative,snapshot/name
    def nodes(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
    a,b=nodes(now),nodes(old)
    equivalence.append(dict(current=relative,historical_source_sha256=sha(old),
        snapshot_matches_historical_audit=sha(old)==historical[str(now)],
        used_functions_unchanged={n:a[n]==b[n] for n in functions}))
expected={str(ROOT/e['current']) for e in equivalence}
assert set(historical_drift)==expected
assert all(e['snapshot_matches_historical_audit'] and all(e['used_functions_unchanged'].values()) for e in equivalence)
assert not changed
report=json.loads((HERE/'results/report.json').read_text())
native_checks=[]
for batch,folder in [('survey','governor_descriptive_survey_2026-10-18'),('cadence','governor_cadence_experiment_2026-10-20')]:
    slots=json.loads((ROOT/'rl_runs'/folder/'ledger.json').read_text())['slots']
    for e in [e for e in report['episodes'] if e['batch']==batch]:
        s=next(s for s in slots if s['attempt']==int(e['id'].split('_')[-1]))
        with (Path(s['result']['evaluation'])/'episodes.csv').open() as stream:
            original=next(csv.DictReader(stream))
        same=math.isclose(e['native']['rms'],float(original['rms_wheel_slip']),rel_tol=1e-10,abs_tol=1e-12)
        assert same
        native_checks.append(dict(id=e['id'],native_rms_matches=same))
v2=validate(ROOT/'docs/governor_isolated_cadence_contract_v2_2026-10-22')
result=dict(current_input_files=len(provenance['inputs_sha256']),current_inputs_unchanged=True,
    historical_input_files=len(historical),historical_matching_files=len(historical)-len(historical_drift),
    historical_source_drift=historical_drift,used_function_equivalence=equivalence,
    qualification='Two source files changed before this audit; exact used helper ASTs match hash-verified historical snapshots. Raw historical artifacts match.',
    native_replay=native_checks,contract=v2)
(HERE/'results/verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(native_replays=len(native_checks),raw_and_current_provenance=True,v2=v2),indent=2))
