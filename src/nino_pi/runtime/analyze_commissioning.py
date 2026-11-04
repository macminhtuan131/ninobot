"""Read-only original bag analysis; no motion/actuator control interfaces."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse,hashlib,json,math,sqlite3,statistics
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict
p=argparse.ArgumentParser();p.add_argument('session',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
r=args.session.expanduser().resolve();out=args.output.expanduser().resolve();assert out!=r and r not in out.parents
m=json.loads((r/'manifest.json').read_text());h=json.loads((r/'sha256.json').read_text());ev=[json.loads(s) for s in (r/'trial_events.jsonl').read_text().splitlines()] if (r/'trial_events.jsonl').exists() else []
hashes={k:(r/k).is_file() and hashlib.sha256((r/k).read_bytes()).hexdigest()==v for k,v in h.items() if k not in ('collector_source','audit_source')}
rows=defaultdict(list);integrity={}
wanted={'/cmd_vel_teleop','/cmd_vel_selected','/cmd_vel_smoothed','/cmd_vel','/motor_enable','/motor_status','/motor_fb','/imu/data','/collision_monitor_state'}
for f in (r/'bag').glob('*.db3'):
    with sqlite3.connect(f.as_uri()+'?mode=ro',uri=True) as db:
        integrity[f.name]=db.execute('PRAGMA integrity_check').fetchone()[0]
        types={i:(n,get_message(t)) for i,n,t in db.execute('SELECT id,name,type FROM topics') if n in wanted}
        for i,t,blob in db.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
            if i in types:
                name,typ=types[i];rows[name].append((t,deserialize_message(blob,typ)))
def event_time(kind):return next((e['wall_time_ns'] for e in ev if e['kind']==kind),None)
first=event_time('forward_publication');zero=event_time('zero_requested')
finalzero=event_time('final_zero_observed');end=event_time('trial_end')
def relative(stamp):return (stamp-first)/1e9 if first is not None else None
def stat(v):return {'count':len(v),'mean':statistics.mean(v) if v else None,'min':min(v) if v else None,'max':max(v) if v else None,'max_abs':max(map(abs,v)) if v else None}
command={};nonzero_trace={}
for t in ('/cmd_vel_teleop','/cmd_vel_selected','/cmd_vel_smoothed','/cmd_vel'):
    vals=rows[t];positive=[(stamp,x) for stamp,x in vals if x.linear.x>0]
    negative=[(stamp,x) for stamp,x in vals if x.linear.x<0]
    invalid=[stamp for stamp,x in vals if any(not math.isfinite(getattr(v,k)) for v in (x.linear,x.angular) for k in ('x','y','z'))]
    command[t]={'count':len(vals),'positive_count':len(positive),'negative_count':len(negative),'nonfinite_count':len(invalid),
        'max_linear_x_m_s':max((x.linear.x for stamp,x in vals),default=None),'max_abs_angular_z_rad_s':max((abs(x.angular.z) for stamp,x in vals),default=None),
        'first_positive_bag_s_from_source_event':(positive[0][0]-first)/1e9 if positive and first is not None else None,'last_positive_bag_s_from_source_event':(positive[-1][0]-first)/1e9 if positive and first is not None else None}
    nonzero_trace[t]=[{'t_from_source_s':relative(stamp),'bag_time_ns':stamp,'v_m_s':x.linear.x,'omega_rad_s':x.angular.z} for stamp,x in positive]
phases={}
phase_bounds={'baseline':(first-2*10**9,first),'source_forward':(first,zero),'ramp_down':(zero,finalzero),'post_final_zero':(finalzero,end)} if first is not None else {}
for label,(a,b) in phase_bounds.items():
    if a is None or b is None or b<=a:continue
    samples=[(t,x) for t,x in rows['/motor_fb'] if a<=t<b];v=defaultdict(list);pos=defaultdict(list);bad=0
    for t,x in samples:
        if len(x.name)!=len(x.velocity) or len(x.name)!=len(x.position):bad+=1
        for name,n in zip(x.name,x.velocity):v[name].append(n)
        for name,n in zip(x.name,x.position):pos[name].append(n)
    stamps=[x.header.stamp.sec*10**9+x.header.stamp.nanosec for t,x in samples]
    phases[label]={'duration_s':(b-a)/1e9,'wheel_velocity_rad_s':{j:stat(x) for j,x in v.items()},'wheel_position_rad':{j:{'first':x[0],'last':x[-1],'delta':x[-1]-x[0],'span':max(x)-min(x)} for j,x in pos.items() if x},
        'shape_errors':bad,'source_header_nonincreasing':sum(y<=x for x,y in zip(stamps,stamps[1:])),
        'max_source_gap_ms':max(((y-x)/1e6 for x,y in zip(stamps,stamps[1:])),default=None),
        'nonfinite_wheel_values':sum(not math.isfinite(n) for values in list(v.values())+list(pos.values()) for n in values),
        'status_histogram':dict(Counter(x.data for t,x in rows['/motor_status'] if a<=t<b))}
result={'forward_event_present':first is not None,'missing_trial_events':[k for k in ('forward_publication','zero_requested','final_zero_observed','trial_end') if event_time(k) is None],'no_forward_scope':'If no forward event, relative times are null and phases empty; primary is unknown. Do not export fixed-window primary without source anchor.','session':r.name,'hash_checks':hashes,'all_hashes_match':all(hashes.values()),'sqlite_integrity':integrity,'manifest_status':m['status'],'manifest_issues':m['issues'],
        'command_summary':command,'command_nonzero_trace':nonzero_trace,'phases':phases,
        'status_histogram':dict(Counter(x.data for t,x in rows['/motor_status'])),
        'enable_requests':[{'t_from_source_s':relative(t),'bag_time_ns':t,'value':x.data} for t,x in rows['/motor_enable']],
        'collision_state_events':[{'t_from_source_s':relative(t),'bag_time_ns':t,'message':message_to_ordereddict(x)} for t,x in rows['/collision_monitor_state']],
        'scope':'Original bag receipt time, no motor target/readback/body reference. Descriptive commissioning, no post hoc onset/settling gate.'}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('hash_checks','command_nonzero_trace')},indent=2))
