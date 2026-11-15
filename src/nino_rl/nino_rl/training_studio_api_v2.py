"""Extended Studio dispatcher supporting common103_v2 + multi-seed [11, 22, 33].

Leaves frozen training_studio_api.py untouched while providing full backward
compatibility for common103_v1 and legacy100_v1 plus common103_v2 single-seed
and multi-seed campaign execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import common_studio_contract as common_v1
from . import common_studio_v2_contract as common_v2
from . import td3_studio_contract as legacy
from . import training_studio_api as v1_api

ENGINES = {
    'common103_v1': v1_api.ENGINES['common103_v1'],
    'common103_v2': 'Common103D/1D v2 · Replay 100k · Gờ 6mm/DR · Sạch phạt đóng cổng',
    'legacy100_v1': v1_api.ENGINES['legacy100_v1'],
}


def module(engine: str):
    if engine == common_v2.ENGINE:
        return common_v2
    return v1_api.module(engine)


def split(request: dict):
    value = dict(request)
    multi_seeds = value.pop('multi_seeds', None)
    auto_prune_raw = value.pop('auto_prune_raw', False)
    if type(auto_prune_raw) is not bool:
        raise ValueError('auto_prune_raw must be boolean')
    if value.get('schema_version') == 1:
        return 'legacy100_v1', legacy.validate_request(value)
    if value.get('schema_version') != 2 or 'engine' not in value:
        raise ValueError('Invalid Studio engine request')
    engine = value.pop('engine')
    if engine == common_v2.ENGINE:
        value['schema_version'] = 1
        checked = common_v2.validate_request(value)
        if multi_seeds is not None:
            if (
                not isinstance(multi_seeds, list)
                or len(multi_seeds) < 3
                or any(type(s) is not int or s < 0 for s in multi_seeds)
                or len(set(multi_seeds)) != len(multi_seeds)
            ):
                raise ValueError('multi_seeds requires >= 3 distinct non-negative integer seeds')
            if checked.get('resume') is not None:
                raise ValueError('Multi-seed campaign starts fresh independent seeds; resume must be None')
            if checked['mode'] != 'train' or checked['evaluate'] is not True:
                raise ValueError('Multi-seed campaign requires train mode and evaluation=True')
            checked['multi_seeds'] = list(multi_seeds)
            checked['auto_prune_raw'] = auto_prune_raw
        elif auto_prune_raw:
            raise ValueError('CLI auto_prune_raw is supported only for a multi-seed campaign; Studio handles single-job retention')
        return engine, checked
    return v1_api.split(request)


def validate_request(request: dict) -> dict:
    engine, value = split(request)
    if request.get('schema_version') == 1:
        return value
    out = dict(value, schema_version=2, engine=engine)
    return out


def inspect_checkpoint(path, **kwargs) -> dict:
    p = Path(path).expanduser().resolve()
    if p.is_file():
        p = p.parent
    kind = json.loads((p / 'manifest.json').read_text()).get('kind')
    if kind == common_v2.CHECKPOINT_KIND:
        return dict(common_v2.inspect_checkpoint(path, **kwargs), engine=common_v2.ENGINE)
    return v1_api.inspect_checkpoint(path, **kwargs)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Studio v2 dispatcher with multi-seed support')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument(
        '--seeds',
        type=str,
        default=None,
        help='Optional comma-separated independent seeds (e.g. 11,22,33) for common103_v2 campaign',
    )
    parser.add_argument(
        '--auto-prune-raw',
        action='store_true',
        help='Prune raw training episodes after each completed seed job while keeping checkpoints/eval/traces',
    )
    args = parser.parse_args(argv)
    raw = json.loads(args.request.read_text())
    if args.seeds:
        raw['multi_seeds'] = [int(x.strip()) for x in args.seeds.split(',') if x.strip()]
    if args.auto_prune_raw:
        raw['auto_prune_raw'] = True
    engine, request = split(raw)
    if engine == common_v2.ENGINE:
        multi_seeds = request.pop('multi_seeds', None)
        auto_prune = bool(request.pop('auto_prune_raw', False))
        if multi_seeds:
            from .common_training_studio_v2 import run_multi_seed_campaign

            _, status = run_multi_seed_campaign(
                args.output,
                request,
                seeds=multi_seeds,
                auto_prune_raw=auto_prune,
            )
        else:
            from .common_training_studio_v2 import run

            _, status = run(args.output, request)
    elif engine == common_v1.ENGINE:
        from .common_training_studio import run

        _, status = run(args.output, request)
    else:
        from .td3_training_studio import run

        _, status = run(args.output, request)
    return 0 if status == 'completed' else 2 if status == 'cancelled' else 1


if __name__ == '__main__':
    raise SystemExit(main())

