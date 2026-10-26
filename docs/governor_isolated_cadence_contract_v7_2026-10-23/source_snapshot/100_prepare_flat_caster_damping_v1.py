#!/usr/bin/env python3
"""Prepare one isolated, untested caster axle damping candidate."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/nino_description/urdf/nino.urdf.xacro'
OUTPUT = ROOT / 'rl_runs/flat_caster_damping_candidate_v1'
AUDIT = ROOT / 'docs/flat_peak_contacts_2026-10-12/analysis.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    audit = json.loads(AUDIT.read_text())
    if audit['robot_model']['sha256'] != digest(SOURCE):
        raise ValueError('Audited geometry changed')
    code = SOURCE.read_text()
    begin = code.index('<xacro:macro name="caster"')
    end = code.index('</xacro:macro>', begin)
    block = code[begin:end]
    old = '<dynamics damping="0.01" friction="0.0"/>'
    if block.count(old) != 1:
        raise ValueError('Expected one caster axle damping declaration')
    corrected = code[:begin] + block.replace(old, '<dynamics damping="0.001" friction="0.0"/>') + code[end:]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / 'model.urdf.xacro'
    if target.exists() and target.read_text() != corrected:
        raise ValueError('Existing candidate differs')
    target.write_text(corrected)
    original_xml = subprocess.check_output(['xacro', str(SOURCE)])
    candidate_xml = subprocess.check_output(['xacro', str(target)])
    original, candidate = ET.fromstring(original_xml), ET.fromstring(candidate_xml)
    changes = []
    for side in ('left', 'right'):
        name = f'caster_{side}_wheel_joint'
        a = original.find(f"joint[@name='{name}']/dynamics")
        b = candidate.find(f"joint[@name='{name}']/dynamics")
        assert a.attrib['damping'] == '0.01' and b.attrib['damping'] == '0.001'
        changes.append(dict(joint=name, before=dict(a.attrib), after=dict(b.attrib)))
        b.attrib['damping'] = a.attrib['damping']
    assert ET.tostring(original) == ET.tostring(candidate), 'Unrelated expanded robot change'
    (OUTPUT / 'model.urdf').write_bytes(candidate_xml)
    plan = dict(revision='flat_caster_damping_candidate_v1', selected_correction=audit['selected_correction'],
        assets={str(p):digest(p) for p in (SOURCE,AUDIT,Path(__file__),target,OUTPUT/'model.urdf')},
        only_expanded_changes=changes, static_verification_passed=True, simulator_started=False,
        validated=False, optuna_held=True,
        unchanged=['geometry','mass/inertia','swivel damping','wheel friction','motor controller',
            'estimator','cable layout','1 ms physics','100 ms control','arrival/quality gates'],
        next_screen='Same seed 65004, full PI and original recovery-at-4.60-m schedule, two cold-start repetitions each',
        validation_targets=['caster rolling response on clear floor','impact/penetration repeatability',
            'physical arrival','physical tracking','completion time','whole-course and crossing-window vibration/slip'])
    (OUTPUT / 'candidate.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({k:plan[k] for k in ('only_expanded_changes','static_verification_passed','simulator_started','validated')},indent=2))


if __name__ == '__main__':
    main()
