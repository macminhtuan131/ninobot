"""Inspectable GUI training requests and checkpoint provenance, without Torch/ROS."""
import hashlib
import json
from pathlib import Path
from . import residual_guided_td3 as guided
from .residual_workflow import runtime_versions
from .td3_config import apply_profile, load_profiles

SCENARIOS={'clear_box':'Sàn sạch · controlled factory fixture','box_c1_6mm':'Gờ 6 mm · controlled factory fixture'}
SMOKE_PROFILE='nino_td3_smoke_h5_v1'
CHECKPOINT_KIND='nino_td3_studio_checkpoint_v1'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def profiles():return {k:v for k,v in load_profiles().items() if v['observation']['history_len']==5 and v['observation']['policy_rate_hz']==10}

def validate_request(value):
    fields={'schema_version','mode','scenario','profile','timesteps','seed','checkpoint_every','wall_minutes','evaluate','resume'}
    if not isinstance(value,dict) or set(value)!=fields:raise ValueError('Invalid TD3 Studio request fields')
    if value['schema_version']!=1 or value['mode'] not in ('smoke','train'):raise ValueError('Request version/mode invalid')
    if value['scenario'] not in SCENARIOS or value['profile'] not in profiles():raise ValueError('Choose supported guided h5 scenario/profile')
    for key,low,high in [('timesteps',1,1_000_000_000),('seed',0,2_147_483_647),('checkpoint_every',0,1_000_000_000),('wall_minutes',1,10080)]:
        if type(value[key]) is not int or not low<=value[key]<=high:raise ValueError(f'{key} must be integer in [{low}, {high}]')
    if type(value['evaluate']) is not bool or value['resume'] is not None and not isinstance(value['resume'],str):raise ValueError('Invalid evaluate/resume')
    if value['mode']=='smoke' and (value['timesteps']!=64 or value['profile']!=SMOKE_PROFILE or value['resume'] is not None):
        raise ValueError('Smoke uses a fresh model, smoke h5 profile and exactly 64 steps')
    return dict(value)

def configuration(request):
    c,g,parent,condition=guided.configuration(request['scenario'],training=True)
    c=apply_profile(c,request['profile'])
    c['backend']['max_episodes']=(request['timesteps']+139)//140+2
    return c,g,parent,condition

def identity(request):
    c,_,_,_=configuration(request)
    return dict(kind='nino_td3_studio_identity_v1',guided_task=guided.identity(),scenario=request['scenario'],
        parameter_profile=c['parameter_profile'],algorithm_parameters=c['algorithm_parameters']['TD3'],
        exploration_sigma=c['exploration_sigma'],seed=request['seed'],hardware_authorized=False)

def inspect_checkpoint(path,check_runtime=False,verify_files=True):
    """Only complete known checkpoint bundles are resumable, not bare actor ZIPs."""
    p=Path(path).expanduser().resolve()
    if p.is_file():
        if p.name!='model.zip':raise ValueError('Select model.zip or its checkpoint directory')
        p=p.parent
    manifest=json.loads((p/'manifest.json').read_text())
    if manifest.get('kind')==CHECKPOINT_KIND:
        if manifest.get('status')!='resumable':raise ValueError('Checkpoint is not marked resumable')
        meta=json.loads((p/'checkpoint.json').read_text());ident=json.loads((p/'resume_identity.json').read_text())
        if meta['identity']!=ident:raise ValueError('Checkpoint identity mismatch')
        result=dict(path=str(p),kind='studio',scenario=ident['scenario'],profile=ident['parameter_profile']['profile_id'],seed=ident['seed'],
            global_steps=meta['global_steps'],optimizer_updates=meta['optimizer_updates'],replay_size=meta['replay_size'],identity=ident)
    elif manifest.get('guided_td3_fingerprint')==guided.fingerprint() and manifest.get('action')=='sim-v3-train' and manifest.get('status')=='completed':
        saved=json.loads((p/'task_checkpoint.json').read_text())
        if saved!=guided.identity():raise ValueError('Legacy guided task mismatch')
        config=json.loads((p/'training_config.json').read_text());summary=json.loads((p/'training_result.json').read_text())
        result=dict(path=str(p),kind='guided_v3',scenario=summary['scenario'],profile=config['parameter_profile']['profile_id'],seed=summary['learner_seeds'][0],
            global_steps=summary['transitions'],optimizer_updates=summary['optimizer_updates'],replay_size=summary['transitions'])
        spec=dict(schema_version=1,mode='train',scenario=result['scenario'],profile=result['profile'],seed=result['seed'],
            timesteps=1,checkpoint_every=0,wall_minutes=1,evaluate=False,resume=None)
        result['identity']=identity(spec)
    else:raise ValueError('Unsupported/stale checkpoint: need Studio bundle or unchanged guided TD3 V3 training bundle')
    required={'model.zip','replay_buffer.pkl'}
    if result['kind']=='studio':required.update({'checkpoint.json','resume_identity.json','task_checkpoint.json'})
    if not required.issubset(manifest.get('files',{})):raise ValueError('Checkpoint needs model.zip AND replay_buffer.pkl')
    for name,sha in manifest['files'].items():
        file=(p/name).resolve()
        if not file.is_relative_to(p) or not file.is_file() or verify_files and digest(file)!=sha:raise ValueError('Checkpoint hash mismatch: '+name)
    if check_runtime and manifest.get('runtime')!=runtime_versions():raise ValueError('Checkpoint/runtime versions differ')
    result['manifest_sha256']=digest(p/'manifest.json')
    result['files_verified']=verify_files
    return result

def require_resume(request,check_runtime=True):
    if not request['resume']:return None
    info=inspect_checkpoint(request['resume'],check_runtime)
    if info['identity']!=identity(request):raise ValueError('Resume requires the same task, scenario, profile, seed, reward, ABI and baseline')
    return info
