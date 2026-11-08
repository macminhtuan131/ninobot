"""Incremental, read-only summaries of Studio artifacts; no RL imports."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from .training_live import read_json


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def pose(value):
    return list(value[:3]) if isinstance(value,(list,tuple)) and len(value)>=3 and all(finite(v) for v in value[:3]) else None


def transform(values):
    x,y,z,r,p,w=(list(values)+[0.]*6)[:6]
    cr,sr,cp,sp,cw,sw=math.cos(r),math.sin(r),math.cos(p),math.sin(p),math.cos(w),math.sin(w)
    return [[cw*cp,cw*sp*sr-sw*cr,cw*sp*cr+sw*sr,x],
            [sw*cp,sw*sp*sr+cw*cr,sw*sp*cr-cw*sr,y],[-sp,cp*sr,cp*cr,z],[0,0,0,1]]


def multiply(a,b):return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def xyz(matrix,point):return [sum(matrix[i][j]*([*point,1][j]) for j in range(4)) for i in range(3)]
def numbers(node,tag,default):
    text=node.findtext(tag)
    return [float(v) for v in text.split()] if text else default


def hull(points):
    points=sorted(set((round(p[0],9),round(p[1],9)) for p in points))
    if len(points)<=2:return points
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def half(seq):
        out=[]
        for p in seq:
            while len(out)>=2 and cross(out[-2],out[-1],p)<=0:out.pop()
            out.append(p)
        return out
    return half(points)[:-1]+half(reversed(points))[:-1]


def world_geometry(directory,scenario):
    """Top-down collision footprints with composed model/link/shape SDF poses.

    Unsupported includes/meshes/relative frames are reported, never invented.
    """
    directory=Path(directory);catalog=read_json(directory/'worlds.json',{})
    entry=catalog.get(scenario,{})
    path=Path(entry.get('path',directory/(str(scenario)+'.sdf')))
    if not path.is_file():return dict(shapes=[],warnings=['Chưa có world SDF cho scenario này'],path=str(path))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if entry.get('sha256') and entry['sha256']!=digest:
        return dict(shapes=[],warnings=['World hash không khớp worlds.json; không vẽ geometry'],path=str(path))
    shapes=[];warnings=[];root=ET.parse(path).getroot();world=root.find('world')
    if world is None:world=root
    def visit(node,parent,name=''):
        local=node.find('pose')
        if local is not None and local.get('relative_to'):
            warnings.append(name+': chưa hỗ trợ relative_to');return
        matrix=multiply(parent,transform(numbers(node,'pose',[0]*6)))
        for inc in node.findall('include'):warnings.append('Include chưa giải: '+str(inc.findtext('uri')))
        for model in node.findall('model'):visit(model,matrix,name+'/'+model.get('name','model'))
        for link in node.findall('link'):
            lm=multiply(matrix,transform(numbers(link,'pose',[0]*6)))
            if link.find('pose') is not None and link.find('pose').get('relative_to'):
                warnings.append(name+'/'+link.get('name','')+': relative_to');continue
            nodes=link.findall('collision') or link.findall('visual')
            for shape in nodes:
                label=name.strip('/')+'/'+shape.get('name','shape')
                if shape.find('pose') is not None and shape.find('pose').get('relative_to'):
                    warnings.append(label+': relative_to');continue
                sm=multiply(lm,transform(numbers(shape,'pose',[0]*6)))
                g=shape.find('geometry');points=[]
                if g is None:continue
                box=g.find('box');cylinder=g.find('cylinder');sphere=g.find('sphere')
                if box is not None:
                    sx,sy,sz=numbers(box,'size',[0,0,0])
                    points=[xyz(sm,[x*sx/2,y*sy/2,z*sz/2]) for x in (-1,1) for y in (-1,1) for z in (-1,1)]
                elif cylinder is not None:
                    radius=float(cylinder.findtext('radius','0'));length=float(cylinder.findtext('length','0'))
                    points=[xyz(sm,[radius*math.cos(a*math.pi/24),radius*math.sin(a*math.pi/24),z*length/2]) for a in range(48) for z in (-1,1)]
                elif sphere is not None:
                    radius=float(sphere.findtext('radius','0'));center=xyz(sm,[0,0,0])
                    points=[[center[0]+radius*math.cos(a*math.pi/24),center[1]+radius*math.sin(a*math.pi/24)] for a in range(48)]
                else:warnings.append(label+': geometry chưa hỗ trợ ('+','.join(c.tag for c in g)+')');continue
                polygon=hull(points)
                if polygon:shapes.append(dict(name=label,polygon=polygon,kind='floor' if 'floor' in label.lower() else 'wall' if 'wall' in label.lower() else 'object'))
    visit(world,transform([0]*6))
    return dict(shapes=shapes,warnings=warnings,path=str(path),sha256=digest,scenario=scenario)


class Episode:
    def __init__(self,index,start):
        self.index=index;self.start=start;self.rows=0;self.reward=0.;self.reward_count=0;self.sums={};self.counts={};self.last={}
        self.truth=[];self.estimate=[];self.end=start;self.step_end=None
    def add(self,row,step):
        self.rows+=1;self.last=row;self.end=step
        if finite(row.get('reward')):self.reward+=row['reward'];self.reward_count+=1
        task=row.get('task',{})
        for key in ('velocity_error_m_s','cross_track_m','yaw_rate_error_rad_s'):
            value=task.get(key)
            if finite(value):self.sums[key]=self.sums.get(key,0)+value*value;self.counts[key]=self.counts.get(key,0)+1
        for key,target in (('truth_pose_m_rad',self.truth),):
            p=pose(row.get(key))
            if p:target.append(p)
        p=pose(row.get('estimator_audit',{}).get('pose'))
        if p:self.estimate.append(p)
    def summary(self,status='running'):
        task=self.last.get('task',{});done=bool(self.last.get('done'))
        condition=self.last.get('qualification_condition',self.last.get('condition',{}))
        metrics={k:math.sqrt(v/self.counts[k]) for k,v in self.sums.items()}
        return dict(episode=self.index+1,rows=self.rows,start_step=self.start,end_step=self.end,
            status='completed' if done else 'right_censored' if status!='running' else 'running',
            reward=self.reward if self.reward_count else None,elapsed_s=task.get('elapsed_s'),source_stop_s=condition.get('source_stop_s'),
            task_success=task.get('task_success') if done else None,stop_completed=task.get('stop_completed') if done else None,
            termination=self.last.get('termination_reason') if done else None,metrics=metrics,
            metric_samples=dict(self.counts),truth_pose=pose(self.last.get('truth_pose_m_rad')),
            estimate_pose=pose(self.last.get('estimator_audit',{}).get('pose')))


def window_statistics(episodes):
    rows=[e for e in episodes if e['status']=='completed'][-20:]
    def mean(key):
        vals=[e['metrics'][key] for e in rows if finite(e['metrics'].get(key))]
        return sum(vals)/len(vals) if vals else None
    return dict(episodes=len(rows),successes=sum(e['task_success'] is True for e in rows),
        velocity_rmse_m_s=mean('velocity_error_m_s'),path_rmse_m=mean('cross_track_m'),
        scope='Mean per-episode RMS, latest up to 20 completed episodes in this job; native trace, not final QC')


class DashboardReader:
    """Bounded incremental scan. Keeps scalar aggregates and one episode path."""
    def __init__(self,directory):
        self.directory=Path(directory);self.offset=0;self.buffer=b'';self.inode=None
        self.current=None;self.episodes=[];self.total=0;self.errors=[];self.geometry=None;self.config={}
        self.checkpoint_cache={};self.start=0;self.start_known=True
        self.evaluation_reader=None
        request=read_json(self.directory/'request.json') or read_json(self.directory/'job.json',{}).get('request',{})
        self.request=request
        if request.get('resume'):
            p=Path(request['resume']).expanduser();p=p.parent if p.is_file() else p
            meta=read_json(p/'checkpoint.json',{})
            self.start_known=type(meta.get('global_steps')) is int;self.start=meta.get('global_steps',0)
        self.trace=self.directory/'environment_trace.jsonl'
        if not self.trace.is_file():self.trace=self.directory/'training_trace.jsonl'
    def poll(self,interrupted=lambda:False):
        if self.offset==0 and (self.directory/'environment_trace.jsonl').is_file():self.trace=self.directory/'environment_trace.jsonl'
        try:
            stat=self.trace.stat();identity=(stat.st_dev,stat.st_ino)
            if self.inode is not None and (self.inode!=identity or stat.st_size<self.offset):
                raise ValueError('Trace bị thay/thu nhỏ; cần mở lại phiên để đọc từ đầu')
            self.inode=identity
            with self.trace.open('rb') as stream:
                stream.seek(self.offset);chunk=stream.read(16*1024*1024);self.offset=stream.tell()
            self.buffer+=chunk;lines=self.buffer.split(b'\n');self.buffer=lines.pop()
            for line in lines:
                if interrupted():return None
                if not line.strip():continue
                try:row=json.loads(line)
                except ValueError:
                    self.errors.append('JSONL lỗi trước EOF; global offset từ đó chưa xác định, không suy diễn episode')
                    self.start_known=False;continue
                self.total+=1
                index=row.get('episode')
                if index is None:
                    index=0 if self.current is None else self.current.index+int(bool(self.current.last.get('done')))
                step=row.get('timestep',self.start+self.total if self.start_known else None)
                if self.current is None or index!=self.current.index:
                    if self.current:self.episodes.append(self.current.summary('closed' if not self.current.last.get('done') else 'running'))
                    self.current=Episode(index,step)
                self.current.add(row,step)
            backlog=max(0,stat.st_size-self.offset)
        except FileNotFoundError:backlog=0
        except (OSError,ValueError,TypeError) as exc:self.errors.append(str(exc));backlog=0
        job=read_json(self.directory/'job.json',{});status=job.get('status','unknown')
        episodes=list(self.episodes)
        if self.current:episodes.append(self.current.summary(status if not backlog else 'running'))
        if self.geometry is None or (not self.geometry.get('sha256') and (self.directory/(str(self.request.get('scenario','clear_box'))+'.sdf')).is_file()):
            try:self.geometry=world_geometry(self.directory,self.request.get('scenario','clear_box'))
            except (OSError,ValueError,ET.ParseError) as exc:self.geometry=dict(shapes=[],warnings=[str(exc)])
        if not self.config:
            p=self.directory/'episode_0_reset.json';self.config=read_json(p,{})
            if not self.config:self.config=read_json(self.directory/'training_config.json',{})
        reset=self.config.get('reset',{})
        path=reset.get('guidance_contract',{}).get('configuration',{}).get('path_points_m',[])
        checkpoints=[]
        for p in sorted((self.directory/'checkpoints').glob('*/checkpoint.json')):
            if p.parent.name.startswith('.') or not (p.parent/'manifest.json').is_file():continue
            if str(p) not in self.checkpoint_cache:
                meta=read_json(p)
                if meta:self.checkpoint_cache[str(p)]=meta
            meta=self.checkpoint_cache.get(str(p),{});global_step=meta.get('global_steps')
            included=[e for e in episodes if e['end_step'] is not None and global_step is not None and e['end_step']<=global_step]
            checkpoints.append(dict(path=str(p.parent),global_steps=global_step,critic_updates=meta.get('optimizer_updates'),
                replay_size=meta.get('replay_size'),reason=meta.get('reason'),window=window_statistics(included),
                trace_caught_up=self.start_known and global_step is not None and self.start+self.total>=global_step))
        current=self.current.summary(status) if self.current else {}
        evaluation=read_json(self.directory/'evaluation_progress.json',[])
        snapshot=dict(directory=str(self.directory),status=status,episodes=episodes,checkpoints=checkpoints,
            world=self.geometry,path=path,truth_path=list(self.current.truth) if self.current else [],
            estimate_path=list(self.current.estimate) if self.current else [],current=current,
            window=window_statistics(episodes),backlog_bytes=backlog,trace_rows=self.total,
            trace_path=str(self.trace),trace_age_s=max(0,time.time()-self.trace.stat().st_mtime) if self.trace.is_file() else None,
            warnings=list(dict.fromkeys(self.errors))[-10:],evaluation=evaluation,map_scope='TRAIN · native trace')
        retention=read_json(self.directory/'storage_retention.json',{})
        if retention:
            snapshot['warnings'].append('Raw episode train đã dọn có chủ đích; thống kê từ trace giữ lại. '
                'Không còn đủ raw để kiểm lại toàn bộ manifest gốc. Retention: '+str(retention.get('status','unknown')))
        # Training is followed by fresh frozen-policy evaluation launches. Keep
        # training tables, but move the map to the robot in the active eval arm.
        if (self.directory/'training_result.json').is_file():
            paths=list((self.directory/'evaluation').glob('*/environment_trace.jsonl'))
            if not paths:paths=list((self.directory/'evaluation').glob('*/training_trace.jsonl'))
            if paths:
                latest=max(paths,key=lambda p:p.stat().st_mtime)
                if self.evaluation_reader is None or self.evaluation_reader.directory!=latest.parent:
                    self.evaluation_reader=DashboardReader(latest.parent)
                active=self.evaluation_reader.poll(interrupted)
                if active:
                    for key in ('current','truth_path','estimate_path','trace_age_s'):
                        snapshot[key]=active[key]
                    if active['path']:snapshot['path']=active['path']
                    snapshot['map_scope']='EVAL '+latest.parent.name+' · frozen policy, không update'
        return snapshot


def laya_summary(snapshot):
    """Explicit adapter for the existing Laya monitor; no invented goal errors."""
    rows=[]
    for e in snapshot['episodes']:
        if e['status']!='completed':continue
        rows.append(dict(success=e['task_success'],termination=e['termination'] or 'unknown',
            truth_path_rmse_m=e['metrics'].get('cross_track_m'),path_rmse_m=None,
            final_progress_fraction=None,truth_endpoint_error_m=None,endpoint_error_m=None,
            odom_truth_position_error_m=None,rms_wheel_slip=None,rms_vertical_acceleration_m_s2=None))
    return rows
