"""Explicit engine dispatch for one Studio UI; legacy requests remain version 1."""
from . import td3_studio_contract as legacy
from . import common_studio_contract as common

ENGINES = {'common103_v1': 'Common103D/1D · Ki0.10 · nhánh hiện tại',
           'legacy100_v1': 'Legacy100D/2D · fixture lịch sử'}


def module(engine):
    if engine not in ENGINES:
        raise ValueError('Unknown training engine')
    return common if engine == common.ENGINE else legacy


def split(request):
    value = dict(request)
    if value.get('schema_version') == 1:
        return 'legacy100_v1', legacy.validate_request(value)
    if value.get('schema_version') != 2 or 'engine' not in value:
        raise ValueError('Invalid Studio engine request')
    engine = value.pop('engine')
    value['schema_version'] = 1
    return engine, module(engine).validate_request(value)


def validate_request(request):
    engine, value = split(request)
    if request['schema_version'] == 1:
        return value
    return dict(value, schema_version=2, engine=engine)


def inspect_checkpoint(path, **kwargs):
    import json
    from pathlib import Path
    p = Path(path).expanduser().resolve()
    if p.is_file():
        p = p.parent
    kind = json.loads((p/'manifest.json').read_text()).get('kind')
    engine = common.ENGINE if kind == common.CHECKPOINT_KIND else 'legacy100_v1'
    return dict(module(engine).inspect_checkpoint(path, **kwargs), engine=engine)


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description='One Studio training dispatcher; explicit ABI')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    engine, request = split(json.loads(args.request.read_text()))
    if engine == common.ENGINE:
        from .common_training_studio import run
    else:
        from .td3_training_studio import run
    _, status = run(args.output, request)
    return 0 if status == 'completed' else 2 if status == 'cancelled' else 1


if __name__ == '__main__':
    raise SystemExit(main())
