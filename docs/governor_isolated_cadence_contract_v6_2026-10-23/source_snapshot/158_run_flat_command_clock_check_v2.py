#!/usr/bin/env python3
"""Audit saved failure, then rerun only 1 ms/full PI/65004 with a command clock fix."""
import csv,json,os,shutil,sys,time,fcntl,re
from copy import deepcopy
from pathlib import Path
import numpy as np
import yaml
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(Path(__file__).parent),str(ROOT/'src/nino_rl')]
from prepare_rough_foundations import digest,immutable
from run_disturbance_reference_comparisons import read,verify,replace
from train_rough_curriculum import Processes,assert_isolated,complete_evaluation
from run_flat_bullet_contact_candidate_v3 import LIBRARY,RESET_LIBRARY
SOURCE=ROOT/'rl_runs/flat_bullet_contact_candidate_v3'
OUTPUT=ROOT/'rl_runs/flat_command_clock_check_v2'

def rows(p):
    with Path(p).open() as stream:return list(csv.DictReader(stream))

def audit():
    directory=SOURCE/'repeat_1/1ms/full/seed_65004'
    batch=complete_evaluation(directory,1)
    if batch is None or batch[0][0]['termination']!='navigation_invalid':raise ValueError('Unexpected source failure')
    episode=batch[0][0];run=next(p.parent for p in directory.glob('*/summary.json') if read(p)['complete'])
    control=rows(run/'episode-001/control_trace.csv');drive=rows(run/'episode-001/drive_trace.csv')
    start=float(control[-20]['sim_time_s']);end=float(control[-1]['sim_time_s'])
    ds=[r for r in drive if start<=float(r['sim_time_s'])<=end]
    slow=[r for r in control if float(r['elapsed_s'])>=6.4]
    contacts={}
    for r in rows(directory/'contacts.csv'):
        if not start<=float(r['sim_time_s'])<=end or int(r['points'])==0:continue
        key=r['collision'].split('::')[-2]+' / '+r['other'].split('::')[1]
        item=contacts.setdefault(key,dict(samples=0,max_depth_m=0.,maximum_force_n=0.))
        item['samples']+=1;item['max_depth_m']=max(item['max_depth_m'],float(r['max_depth_m']))
        if int(r['wrench_points']):item['maximum_force_n']=max(item['maximum_force_n'],float(np.linalg.norm([float(r[k]) for k in ('force_x_n','force_y_n','force_z_n')])))
    data=dict(source=str(directory),termination=episode['termination'],physical_arrival=False,
        elapsed_s=float(episode['time_seconds']),endpoint_error_m=float(episode['truth_endpoint_error_m']),
        last_two_seconds_drive_samples=len(ds),stale_drive_counts={k:sum(float(r[k])<.5 for r in ds) for k in ('cmd_fresh','policy_fresh','have_wheel_state')},
        late_physical_x_range_m=[min(float(r['physical_x_m']) for r in slow),max(float(r['physical_x_m']) for r in slow)],
        late_mean_executed_speed_m_s=float(np.mean([float(r['executed_linear_m_s']) for r in ds])),
        late_wheel_tracking_rmse_rad_s=float(np.sqrt(np.mean([(float(r[s+'_actual_rad_s'])-float(r[s+'_target_rad_s']))**2 for r in ds for s in ('left','right')]))),
        contacts=contacts,imu_minimum_interval_coverage_fraction=min(float(r['step_imu_coverage_s'])/float(r['step_dt_s']) for r in slow),
        maximum_motion_stamp_lag_s=max(float(r['sim_time_s'])-float(r['raw_wheel_stamp_s']) for r in slow),
        supported_correction='Own straight-command age measured in simulation time in lockstep; sensor wall-age and motion/IMU timing checks unchanged',
        causal_limit='Old traces did not record which reference stream was stale. Fresh motor commands plus wall-time command aging support a diagnostic hypothesis, not proof of contact repair.',
        preserved_data={str(p):digest(p) for p in (run/'episodes.csv',run/'episode-001/control_trace.csv',run/'episode-001/drive_trace.csv')})
    immutable(OUTPUT/'saved_failure_audit.json',json.dumps(data,indent=2)+'\n');return data

def prepare():
    if (OUTPUT/'contract.json').exists():p=read(OUTPUT/'contract.json');verify(p);return p
    OUTPUT.mkdir(parents=True,exist_ok=True);source=read(SOURCE/'contract.json');verify(source);audit()
    package=OUTPUT/'python/nino_rl';shutil.copytree(SOURCE/'python/nino_rl',package,ignore=shutil.ignore_patterns('__pycache__'))
    config=yaml.safe_load((SOURCE/'config_1ms.yaml').read_text());old=deepcopy(config)
    config['navigation']['command_freshness_clock']='simulation'
    restored=deepcopy(config);restored['navigation'].pop('command_freshness_clock');assert restored==old
    path=package/'ros_interface.py';code=path.read_text()
    code=replace(code,'        odometry_assistance: dict | None = None,',
        '        odometry_assistance: dict | None = None,\n        command_freshness_clock: str = "wall",')
    code=replace(code,'        self._sim_clock_stamp = None',
        '''        self._sim_clock_stamp = None
        if command_freshness_clock not in ('wall', 'simulation') or (command_freshness_clock == 'simulation' and not use_sim_time):
            raise ValueError('Simulation command clock requires use_sim_time')
        self.command_freshness_clock = command_freshness_clock
        self._straight_cmd_sim_stamp = None''')
    code=replace(code,'            self._mark_received("straight_cmd")',
        '            self._mark_received("straight_cmd")\n            self._straight_cmd_sim_stamp = self._sim_clock_stamp')
    code=replace(code,'''            return [
                name
                for name in ("odom", "imu", "joint", "straight_cmd")
                if name not in self._received_at
                or now - self._received_at[name] > stale_after
            ]''',
        '''            missing = [name for name in ('odom','imu','joint')
                if name not in self._received_at or now-self._received_at[name] > stale_after]
            if self.command_freshness_clock == 'simulation':
                clock,stamp=self._sim_clock_stamp,self._straight_cmd_sim_stamp
                invalid = clock is None or stamp is None or stamp > clock+1e-8 or clock-stamp > stale_after
            else:
                invalid = now-self._received_at.get('straight_cmd',-float('inf')) > stale_after
            if invalid:missing.append('straight_cmd')
            return missing''')
    code+='''
    def command_clock_diagnostics(self, stale_after):
        now=monotonic()
        with self._lock:
            clock,stamp=self._sim_clock_stamp,self._straight_cmd_sim_stamp
            return dict(command_wall_age_s=now-self._received_at.get('straight_cmd',now),
                command_sim_age_s=clock-stamp if clock is not None and stamp is not None else -1.,
                command_wall_would_expire=int(now-self._received_at.get('straight_cmd',-float('inf'))>stale_after),
                **{name+'_wall_age_s':now-self._received_at.get(name,now) for name in ('odom','imu','joint')})
'''
    path.write_text(code)
    path=package/'ros_env.py';code=replace(path.read_text(),'            subscribe_plan=False,',
        '            subscribe_plan=False,\n            command_freshness_clock=navigation.get("command_freshness_clock","wall"),')
    code=replace(code,'                "step_dt_s": step_dt, "step_imu_energy": imu["square_integral"],',
        '                **self.ros.command_clock_diagnostics(self.nav_stale_seconds),\n                "reference_valid": int(reference.valid),\n                "step_dt_s": step_dt, "step_imu_energy": imu["square_integral"],')
    path.write_text(code)
    path=package/'evaluation.py'
    code=replace(path.read_text(),
        '                        samples = env.ros.drive_diagnostics(start_sim, env.lockstep_sim_time)',
        '''                        import time
                        delivery_started = time.monotonic()
                        samples = env.ros.drive_diagnostics(start_sim, env.lockstep_sim_time)
                        while not samples and time.monotonic()-delivery_started < config['policy_v2']['sensor_wait_timeout_seconds']:
                            time.sleep(.005)
                            samples = env.ros.drive_diagnostics(start_sim, env.lockstep_sim_time)
                        info['control_trace']['diagnostic_delivery_wait_wall_s'] = time.monotonic()-delivery_started''')
    path.write_text(code)
    for p in package.glob('*.py'):
        compile(p.read_text(),str(p),'exec')
        if p.name not in ('ros_interface.py','ros_env.py','evaluation.py'):assert p.read_bytes()==(SOURCE/'python/nino_rl'/p.name).read_bytes()
    immutable(OUTPUT/'config.yaml',yaml.safe_dump(config,sort_keys=False))
    assets=dict(source['assets']);assets.update({str(p):digest(p) for p in package.glob('*.py')})
    for p in (Path(__file__),OUTPUT/'config.yaml',OUTPUT/'saved_failure_audit.json'):assets[str(p)]=digest(p)
    plan=dict(revision='flat_command_clock_check_v2',assets=assets,world=source['profiles']['1ms']['world'],seed=65004,
        selected_change='Own-command freshness clock; bounded existing DDS delivery timeout for genuine in-interval diagnostic samples; no physics advance or stale-sample fallback',
        unchanged=['1 ms physics','0.1 s action interval','controller','all sensor age/coverage/barrier checks','terrain/geometry','scoring','full PI'],
        source_failure='repeat_1/1ms/full/65004',qualification='One cold rerun; no contact convergence, no PPO/Optuna qualification',optuna_held=True)
    immutable(OUTPUT/'contract.json',json.dumps(plan,indent=2)+'\n');return plan

def verify_clock_logic():
    import ast,threading
    code=(OUTPUT/'python/nino_rl/ros_interface.py').read_text();tree=ast.parse(code)
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='RosRobotInterface')
    method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='stale_straight_reference_streams')
    module=ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[]));scope={'monotonic':lambda:100.}
    exec(compile(module,'clock-test','exec'),scope);fn=scope[method.name]
    from types import SimpleNamespace
    fake=SimpleNamespace(_lock=threading.Lock(),_received_at={k:99.99 for k in ('odom','imu','joint')},
        _sim_clock_stamp=10.1,_straight_cmd_sim_stamp=10.,command_freshness_clock='simulation')
    fake._received_at['straight_cmd']=97.;assert fn(fake,2.)==[]
    fake.command_freshness_clock='wall';assert fn(fake,2.)==['straight_cmd']
    fake.command_freshness_clock='simulation';fake._received_at['odom']=97.;assert fn(fake,2.)==['odom']
    fake._received_at['odom']=99.99;fake._sim_clock_stamp=13.;assert fn(fake,2.)==['straight_cmd']
    fake._straight_cmd_sim_stamp=14.;assert fn(fake,2.)==['straight_cmd']
    fake._straight_cmd_sim_stamp=None;assert fn(fake,2.)==['straight_cmd']
    immutable(OUTPUT/'clock_verification.json',json.dumps(dict(passed=True,wall_default_preserved=True,
        missing_stale_future_command_rejected=True,sensor_wall_staleness_preserved=True),indent=2)+'\n')

def main():
    os.chdir(ROOT);plan=prepare();verify_clock_logic();lock=(OUTPUT/'runner.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def status(stage,**extra):
        data=dict(stage=stage,pid=os.getpid(),optuna_held=True,training_started=False,**extra)
        (OUTPUT/'status.json').write_text(json.dumps(data,indent=2)+'\n');print(stage,flush=True)
    os.environ.update(ROS_DOMAIN_ID='79',NINO_ROS_DOMAIN_ID='79',GZ_PARTITION='nino_flat_79',ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    env=os.environ.copy();env['PYTHONPATH']=str(OUTPUT/'python')+os.pathsep+str(ROOT/'src/nino_rl')+os.pathsep+env.get('PYTHONPATH','');env['PYTHONUNBUFFERED']='1'
    env.update(NINO_AUTHORITY_PROFILE='full',NINO_MATCH_SCALE='1')
    processes=Processes(env,pi_integrator_profile='conditional_v1');directory=OUTPUT/'rerun'
    try:
        if complete_evaluation(directory,1) is None:
            status('rerunning only failed seed 65004: 1 ms/full PI');verify(plan);assert_isolated(79,'nino_flat_79')
            processes.world=processes.start(['ros2','launch','nino_rl','training_sim.launch.py','world:='+plan['world'],
                'world_name:=combined_flat_section','headless:=true','pi_integrator_profile:=conditional_v1','verbosity:=3'],directory/'gazebo.log')
            processes.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
            processes.run([sys.executable,'src/nino_rl/scripts/wait_for_drive_profile.py','--config',OUTPUT/'config.yaml','--timeout','60'],directory/'profile.log',timeout=65)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if 'Using [bullet] collision detector' in re.sub(r'\x1b\[[0-9;]*m','',(directory/'gazebo.log').read_text()):break
                time.sleep(.25)
            else:raise ValueError('No detector acknowledgement')
            for name,library,file in [('NinoFlatContactProbe',LIBRARY,'contacts.csv'),('NinoFlatResetProbe',RESET_LIBRARY,'joints.csv')]:
                payload='entity {name: "combined_flat_section" type: WORLD} plugins {name: '+json.dumps(name)+' filename: '+json.dumps(str(library))+' innerxml: '+json.dumps(f'<output>{directory/file}</output>')+'}'
                log=directory/(name+'.log');processes.run(['gz','service','-s','/world/combined_flat_section/entity/system/add','--reqtype','gz.msgs.EntityPlugin_V','--reptype','gz.msgs.Boolean','--timeout','5000','--req',payload],log,timeout=10)
                if 'data: true' not in log.read_text():raise ValueError('Probe not acknowledged')
            processes.run(['ros2','run','nino_rl','evaluate_baseline','--config',OUTPUT/'config.yaml','--seeds',65004,
                '--baseline-speed-scale','1','--control-trace','--output',directory],directory/'evaluate.log',timeout=900);processes.close()
        batch=complete_evaluation(directory,1)
        if batch is None:raise ValueError('Missing rerun result')
        run=next(p.parent for p in directory.glob('*/summary.json') if read(p)['complete']);trace=rows(run/'episode-001/control_trace.csv');episode=batch[0][0]
        wall_stale=[r for r in trace if int(r['command_wall_would_expire'])]
        result=dict(complete=True,episode=episode,source_failed_arrival_preserved=True,
            self_command_wall_expiry_frames=len(wall_stale),all_reference_valid=all(int(r['reference_valid']) for r in trace),
            maximum_command_sim_age_s=max(float(r['command_sim_age_s']) for r in trace),
            max_clock_error_seconds=float(episode['max_clock_error_seconds']),
            physical_arrival=episode['success']=='True' and float(episode['truth_endpoint_error_m'])<=.2+1e-6,
            qualification=plan['qualification'],optuna_held=True,flat_ppo_started=False)
        (OUTPUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');status('complete: one diagnostic rerun; broader testing held',physical_arrival=result['physical_arrival'])
    except BaseException as exc:status('interrupted; evidence preserved',error=str(exc));raise
    finally:processes.close();lock.close()

if __name__=='__main__':main()
