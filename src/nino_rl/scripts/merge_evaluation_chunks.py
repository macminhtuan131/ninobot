#!/usr/bin/env python3
"""Combine completed evaluation episodes after a transport interruption.

Never copy an unfinished episode or change original results. Every expected
scenario must occur exactly once under identical configuration/provenance.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nino_rl.evaluation import benchmark_id, summarize
from nino_rl.trajectory_metrics import write_csv
from laya_training_monitor import read_episodes


def merge(runs, seeds, output):
    if len(set(seeds)) != len(seeds):
        raise ValueError('Expected seeds must be distinct')
    rows, sources, common, config = [], [], None, None
    ignored = {'seed', 'evaluation_seeds'}
    for directory in runs:
        directory = directory.resolve()
        metadata = json.loads((directory / 'metadata.json').read_text())
        identity = {k: v for k, v in metadata.items() if k not in ignored}
        settings = yaml.safe_load((directory / 'config.yaml').read_text())
        if benchmark_id(settings) != metadata['benchmark_id']:
            raise ValueError(f'Configuration does not match saved benchmark: {directory}')
        if common is None:
            common, config = identity, settings
        if identity != common or settings != config:
            raise ValueError(f'Incompatible evaluation configuration/provenance: {directory}')
        completed = read_episodes(directory / 'episodes.csv')
        declared = metadata['evaluation_seeds']
        for row in completed:
            if row['seed'] not in declared:
                raise ValueError('Completed seed is absent from source provenance')
            episode = directory / f"episode-{row['episode']:03d}"
            for artifact in ('trajectory.csv', 'ground_truth/trajectory.csv'):
                if not (episode / artifact).is_file():
                    raise ValueError(f'Missing completed physical/estimated trajectory: {episode}')
            rows.append({**row, 'source_run': str(directory), 'source_episode': row['episode']})
        sources.append({'run': str(directory), 'completed_episodes': len(completed),
                        'requested_seeds': declared})
    observed = [row['seed'] for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != set(seeds):
        raise ValueError(f'Scenario coverage is incomplete or duplicated: expected {seeds}; got {observed}')
    by_seed = {row['seed']: row for row in rows}
    rows = [deepcopy(by_seed[seed]) for seed in seeds]
    for index, row in enumerate(rows, 1):
        row['episode'] = index
    metadata = {**common, 'seed': seeds[0], 'evaluation_seeds': seeds,
                'requested_episodes': len(seeds), 'complete': True,
                'source_chunks': sources,
                'aggregation': 'completed episodes only; original traces retained in source_run/source_episode'}
    result = summarize(rows, metadata)
    encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / 'episodes.csv', rows)
    (output / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'summary.json').write_text(encoded)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--seeds', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = merge(args.runs, args.seeds, args.output)
    print(f"Saved {result['episodes']} complete scenarios to {args.output}")


if __name__ == '__main__':
    main()
