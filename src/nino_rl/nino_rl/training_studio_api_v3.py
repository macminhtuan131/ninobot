"""Goal100 Studio dispatcher; old v1/v2 dispatchers and training sources unchanged."""
import argparse
import json
from pathlib import Path

from . import training_studio_api_v2 as prior
from . import goal_studio_contract as goal

ENGINES = dict(prior.ENGINES, **{goal.ENGINE:'Gờ không biết · Goal100D/1D · tới goal, không lịch stop'})


def module(engine):
    return goal if engine==goal.ENGINE else prior.module(engine)


def split(request):
    if request.get('schema_version')==2 and request.get('engine')==goal.ENGINE:
        raw=dict(request);raw.pop('engine');raw['schema_version']=1
        return goal.ENGINE,goal.validate_request(raw)
    return prior.split(request)


def validate_request(request):
    engine,value=split(request)
    return dict(value,schema_version=2,engine=engine) if request.get('schema_version')==2 else value


def inspect_checkpoint(path,**kwargs):
    p=Path(path).expanduser().resolve();p=p.parent if p.is_file() else p
    m=json.loads((p/'manifest.json').read_text())
    if m.get('kind')==goal.CHECKPOINT_KIND:
        return goal.inspect_checkpoint(path,**kwargs)
    return prior.inspect_checkpoint(path,**kwargs)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv);raw=json.loads(args.request.read_text())
    engine,request=split(raw)
    if engine!=goal.ENGINE:
        return prior.main(argv)
    from .goal_training_studio import run
    _,status=run(args.output,request)
    return 0 if status=='completed' else 2 if status=='cancelled' else 1


if __name__=='__main__':
    raise SystemExit(main())
