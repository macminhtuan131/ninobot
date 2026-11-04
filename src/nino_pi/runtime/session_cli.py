"""New independent diagnostic runtime. CLI invocation is required; no auto retry."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent

def gui_metadata():
    value=os.environ.get('NINO_GUI_METADATA')
    return json.loads(value) if value else None


def save(path, value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temp.replace(path)


def verify_payload():
    hashes=json.loads((ROOT/'payload_hashes.json').read_text())
    for name, expected in hashes.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Prepared runtime file changed: '+name)


def identify_hardware(node, reference):
    """Keep exact previously evidenced GIDs; do not auto-pin arbitrary BARE_DDS nodes."""
    import endpoint_identity
    evidence={}
    for topic,pin in reference['endpoints'].items():
        get=node.get_publishers_info_by_topic if pin['direction']=='publishers' else node.get_subscriptions_info_by_topic
        found=get(topic)
        matches=[e for e in found if endpoint_identity.gid(e)==pin['gid'] and e.topic_type==pin['type']
                 and e.node_name in endpoint_identity.ALLOWED_HARDWARE_NAMES]
        evidence[topic]=[dict(node=e.node_name,gid=endpoint_identity.gid(e),type=e.topic_type) for e in found]
        if len(matches)!=1 or (pin['direction']=='publishers' and len(found)!=1):
            raise RuntimeError('Endpoint identity needs read-only review on '+topic+'; no automatic GID replacement: '+str(evidence[topic]))
    return evidence


def readiness():
    import time
    import rclpy
    import stack_readiness
    from rclpy.node import Node
    reference=json.loads((ROOT/'endpoint_reference.json').read_text())
    rclpy.init();node=Node('nino_diagnostic_prepare_readonly',enable_rosout=False,start_parameter_services=False)
    observer=stack_readiness.Observer(node)
    try:
        end=time.monotonic()+12
        last=None
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.02);observer.poll();snapshot=observer.snapshot()
            errors=stack_readiness.problems(snapshot)
            if not errors:
                identity=identify_hardware(node,reference)
                return dict(software_ready=True,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                            snapshot=snapshot,endpoint_identity=identity,commands_sent=0,
                            note='Read-only preallocation; not physical-motion or safety proof.')
            last=errors
        raise RuntimeError('Not ready; no slot consumed: '+str(last))
    finally:
        node.destroy_node();rclpy.try_shutdown()


def freeze_diagnostic(ready):
    import pilot_state
    current=ROOT/'pilot_contract.json'
    if current.exists():
        pilot_state.release(ROOT,require_ready=False)
        if (ROOT/'ledger.json').exists():
            ledger=json.loads((ROOT/'ledger.json').read_text())
            if ledger.get('attempts') or ledger.get('status')!='active':
                raise RuntimeError('This independent one-slot diagnostic is already used/closed. No retry or ledger reset.')
        save(ROOT/'readiness.json',ready)
        return
    profile=json.loads((ROOT/'motion_profile.template.json').read_text())
    profile['status']='user_authorized_single_verification'
    profile['operator_acceptance_evidence']='Operator explicitly invoked record-diagnostic with selected unchanged .05/.10/2s/60s plan. Physical conditions are recorded by collector prompts; no claim motion already happened.'
    save(ROOT/'motion_profile.accepted.json',profile)
    pins=json.loads((ROOT/'endpoint_reference.json').read_text());pins['boot_id']=ready['boot_id']
    pins['current_boot_readonly_evidence']=ready['endpoint_identity']
    save(ROOT/'endpoint_pins.json',pins)
    session=json.loads((ROOT/'session.template.json').read_text())
    session['test_stage']='wheel_body_diagnostic_one_slot_no_obstacle'
    session['research_plan_id']='nino_bounded_velocity_research_v1'
    session['operator_metadata']=gui_metadata()
    session['motion_contract']={'accepted_profile':profile,'independent_body_reference':None,
                                'claim_scope':'Requested/final ROS to reported wheel, compared with operator video. Not body GT, slip, stopping certification or repeated performance.'}
    save(ROOT/'session.base.json',session)
    contract=json.loads((ROOT/'contract.template.json').read_text())
    contract.update(status='user_authorized',motion_budget_released=True,maximum_attempts=1,
                    boot_id=ready['boot_id'],prepared_utc=datetime.now(timezone.utc).isoformat(),
                    user_authorization='Only operator invocation of this new CLI record-diagnostic. No historical ledger or slot is reopened.')
    frozen=list(json.loads((ROOT/'payload_hashes.json').read_text()))+['motion_profile.accepted.json','endpoint_pins.json','session.base.json','payload_hashes.json']
    contract['files_sha256']={name:pilot_state.digest(ROOT/name) for name in frozen}
    save(current,contract);save(ROOT/'readiness.json',ready)


def stationary():
    from nino_pi import collect_real_data
    ident='stationary_commands_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=Path.home()/'nino_real_data'/ident
    form=json.loads((ROOT/'session.template.json').read_text())
    form.update(session_id=ident,test_stage='stationary_recorder_only_no_command_publishers',date_utc=datetime.now(timezone.utc).isoformat())
    metadata=gui_metadata()
    form['operator_note']=metadata if metadata else input('Pose/caster/sàn/tải (unknown được phép): ').strip() or 'unknown'
    form['research_plan_id']='nino_bounded_velocity_research_v1'
    temporary=ROOT/(ident+'.session.json');save(temporary,form)
    started=time.monotonic_ns()
    save(ROOT/'last_session.json',dict(output=str(output),kind='stationary',closed=False,created_monotonic_ns=started))
    print('Recorder only: 60 s. Không enable/tiến. Chờ FINISHED; giữ nguồn Pi.',flush=True)
    rc=collect_real_data.main(['--config',str(ROOT/'stationary.json'),'--session',str(temporary),'--qos',str(ROOT/'qos.yaml'),'--output',str(output)])
    save(ROOT/'last_session.json',dict(output=str(output),kind='stationary',closed=True,collector_returncode=rc,created_monotonic_ns=started))
    print('FINISHED:',output,'collector exit:',rc,flush=True)
    return rc


def latest_closed():
    entry=json.loads((ROOT/'last_session.json').read_text())
    if not entry.get('closed'):raise RuntimeError('Recorder not closed; wait FINISHED')
    if not entry.get('output'):raise RuntimeError('No new session was allocated; retain the readiness error')
    return Path(entry['output'])


def review():
    from nino_pi.collect_real_data import inspect_bag
    from nino_pi.data_quality import assess_capture
    session=latest_closed()
    out=ROOT/'reviews'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,exist_ok=False)
    config=json.loads((session/'collection_config.json').read_text())
    manifest=json.loads((session/'manifest.json').read_text())
    hashes=json.loads((session/'sha256.json').read_text())
    bad=[];checked=0
    for name,digest in hashes.items():
        if name in ('collector_source','audit_source'):continue
        path=(session/name).resolve()
        if session.resolve() not in path.parents or not path.is_file():bad.append(name);continue
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
        checked+=1
        if h.hexdigest()!=digest:bad.append(name)
    bag=inspect_bag(session/'bag',config)
    audited={**manifest,'bag':bag}
    result=dict(status=manifest.get('status'),checked_hashes=checked,hash_mismatches=bad,
                collector_exit=0 if manifest.get('status')=='captured_not_calibrated' else None)
    grade=assess_capture(result,audited,config)
    save(out/'raw_quality.json',dict(session=str(session),bag=bag,quality_report=grade,
                                    body_motion_verified=False,window_review='pending',video_review='pending'))
    if (session/'trial_events.jsonl').exists():
        subprocess.run([sys.executable,str(ROOT/'analyze_commissioning.py'),str(session),'--output',str(out/'analysis.json')],check=True)
        analysis=json.loads((out/'analysis.json').read_text())
        if analysis.get('forward_event_present'):
            subprocess.run([sys.executable,str(ROOT/'export_trace.py'),str(session),'--output',str(out/'trace')],check=True)
    print('Review output:',out,'; grade:',grade['level'],'; body/video/window still need review. No next slot allocated.')
    entry=json.loads((ROOT/'last_session.json').read_text());entry['review_output']=str(out)
    save(ROOT/'last_session.json',entry)
    return 0


def plan(kind):
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest=ROOT/'plans'/(kind+'_'+stamp+'.json');dest.parent.mkdir(exist_ok=True)
    save(dest,dict(kind=kind,status='draft_not_released',motion_budget_released=False,
                   maximum_attempts=0,proposed_maximum_attempts=3 if kind=='repeatability' else None,
                   prerequisites=['Diagnostic reviewed with wheel/body video agreement','New explicit protocol/release; no old slots'],
                   profile=dict(v_m_s=.05,ramp_m_s2=.1,source_s=2,bag_s=60),accepted_thresholds=None,
                   independent_reference_calibration=None,claims_not_available=['body slip','physical stop latency','generalization']))
    print('Draft only:',dest,'; no robot action or slot allocation.')
    return 0

def observation():
    marker=json.loads((ROOT/'last_session.json').read_text())
    out=Path(marker['review_output'])
    metadata=gui_metadata() or {}
    if metadata.get('outcome') not in ('moved_stopped','no_motion','intervention','not_observed'):
        raise ValueError('Explicit physical outcome required')
    if not isinstance(metadata.get('text'),str) or not metadata['text'].strip():raise ValueError('Observation text required')
    dest=out/'operator_observation.json'
    if dest.exists():raise ValueError('Observation already saved; preserve it for review')
    save(dest,dict(operator_report=metadata,body_motion_measured=False,source='operator_gui',
                   timestamp_utc=datetime.now(timezone.utc).isoformat()))
    save(out/'operator_observation.sha256.json',{'operator_observation.json':hashlib.sha256(dest.read_bytes()).hexdigest()})
    print('Operator observation saved; not body ground truth or Q3 promotion.')
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['connect-sensors','inventory','stationary','start-stack','record-diagnostic','run-trial','review','status','observation','plan'])
    p.add_argument('kind',nargs='?',choices=['repeatability','body_reference','future'])
    a=p.parse_args(argv)
    verify_payload()
    if a.action=='plan':return plan(a.kind or 'repeatability')
    if a.action=='connect-sensors':os.execv(sys.executable,[sys.executable,str(ROOT/'connect_sensors.py')])
    if a.action=='inventory':
        dest=ROOT/'inventory'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        return subprocess.call([sys.executable,'-m','nino_pi.hardware_audit','--duration','10','--output',str(dest)])
    if a.action=='stationary':return stationary()
    if a.action=='start-stack':os.execv(sys.executable,[sys.executable,str(ROOT/'launch_checked_stack.py')])
    if a.action=='record-diagnostic':
        # This command remains read-only until the old collector prompts are confirmed.
        # Freezing a new one-slot contract does not publish any command.
        freeze_diagnostic(readiness())
        save(ROOT/'last_session.json',dict(kind='diagnostic',closed=False,output=None))
        rc=subprocess.call([sys.executable,str(ROOT/'collect_session.py')])
        if (ROOT/'ledger.json').exists():
            attempts=json.loads((ROOT/'ledger.json').read_text()).get('attempts',[])
            if attempts:
                attempt=attempts[-1]
                save(ROOT/'last_session.json',dict(kind='diagnostic',closed=attempt['status']!='recording',
                                                  output=attempt['output'],collector_returncode=rc))
            else:
                save(ROOT/'last_session.json',dict(kind='diagnostic',closed=True,output=None,status='not_allocated',collector_returncode=rc))
        else:
            save(ROOT/'last_session.json',dict(kind='diagnostic',closed=True,output=None,status='not_allocated',collector_returncode=rc))
        return rc
    if a.action=='run-trial':
        print('ONE NEW DIAGNOSTIC: enable, .05 m/s source 2 s, zero/disable. No retry.',flush=True)
        os.execv(sys.executable,[sys.executable,str(ROOT/'run_trial.py')])
    if a.action=='review':return review()
    if a.action=='observation':return observation()
    path=ROOT/'ledger.json'
    print(path.read_text() if path.exists() else 'New diagnostic: not started (no historical slots reopened).')
    return 0


if __name__=='__main__':raise SystemExit(main())
