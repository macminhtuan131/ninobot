#!/usr/bin/env python3
"""Capture the rejected N1 maneuver with physical contacts; no learning updates."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'rl_runs/foundations_20261011/rough_contact')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT / 'src/nino_rl'), str(Path(__file__).parent)]
    from tune_rough_e1_v16 import bootstrap
    bootstrap()
    import yaml
    from run_rough_trial8_validation import Validation, write
    from train_rough_curriculum import complete_evaluation
    from nino_rl.tuning_trials import digest
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    original = ROOT / 'rl_runs/rough_n1_heading_braking_v20'
    validator = Validation(output)
    config = yaml.safe_load((original / 'config.yaml').read_text())
    config['rough_runtime']['stage_index'] = 1
    validator.config = config
    assets = json.loads((original / 'correction_contract.json').read_text())
    write(output / 'correction_contract.json', assets)
    library = ROOT / 'build/rough_contact_probe/libnino_rough_contact_probe.so'
    contract = dict(revision='n1_v20_contact_capture_v1', config_sha256=digest(original / 'config.yaml'),
        probe_sha256=digest(library), source_contract_sha256=digest(original / 'continuous_contract.json'),
        seed=13000, updates=0, physical_geometry='unchanged', contact_capture='50 Hz, diagnostic only')
    contract_path = output / 'contact_contract.json'
    if contract_path.exists() and json.loads(contract_path.read_text()) != contract:
        raise ValueError('Contact contract changed; use a new output')
    write(contract_path, contract)
    config_path = output / 'config.yaml'
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    directory = output / 'evaluation'
    directory.mkdir(exist_ok=True)
    status = output / 'status.json'
    try:
        if complete_evaluation(directory, 1) is None:
            write(status, dict(stage='starting_simulator', pid=os.getpid()))
            validator.launch(directory, config_path, original / 'python')
            payload = ('entity {name: "combined_rough_section" type: WORLD} plugins {'
                       'name: "NinoContactProbe" filename: ' + json.dumps(str(library)) +
                       ' innerxml: ' + json.dumps(f'<output>{output / "contacts.csv"}</output>') + '}')
            validator.processes.run(['gz', 'service', '-s', '/world/combined_rough_section/entity/system/add',
                '--reqtype', 'gz.msgs.EntityPlugin_V', '--reptype', 'gz.msgs.Boolean',
                '--timeout', '5000', '--req', payload], output / 'probe.log', timeout=10)
            if 'data: true' not in (output / 'probe.log').read_text():
                raise RuntimeError('Contact probe was not acknowledged')
            write(status, dict(stage='capturing_n1', pid=os.getpid()))
            validator.processes.run(['ros2', 'run', 'nino_rl', 'evaluate_baseline', '--config', config_path,
                '--route', 'N1', '--seeds', '13000', '--control-trace', '--output', directory],
                output / 'evaluate.log', timeout=300)
        result = complete_evaluation(directory, 1)
        if result is None or not (output / 'contacts.csv').exists():
            raise RuntimeError('Incomplete contact/physical episode evidence')
        with (output / 'contacts.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        contacts = [r for r in rows if int(r['points']) > 0]
        by_collision = {}
        for row in contacts:
            key = row['collision']
            item = by_collision.setdefault(key, dict(samples=0, max_depth_m=0., others=[]))
            item['samples'] += 1
            item['max_depth_m'] = max(item['max_depth_m'], float(row['max_depth_m']))
            if row['other'] not in item['others']:
                item['others'].append(row['other'])
        write(output / 'contact_summary.json', dict(episode=result[1], collisions=by_collision,
            contact_samples=len(contacts), captured_rows=len(rows),
            limitation='Contact presence is not itself causal proof; correlate with the stalled physical pose.'))
        write(status, dict(stage='complete', pid=os.getpid(), contact_samples=len(contacts)))
        print(json.dumps(dict(stage='complete', contacts=by_collision), indent=2), flush=True)
    except BaseException as error:
        write(status, dict(stage='failed', error=str(error), pid=os.getpid()))
        raise
    finally:
        validator.processes.close()


if __name__ == '__main__':
    main()
