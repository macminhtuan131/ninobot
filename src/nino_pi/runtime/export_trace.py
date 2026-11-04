"""Read-only trace export. Creates derived CSV outside the original session."""
import csv,json,sqlite3,argparse
from pathlib import Path
from collections import Counter
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
p=argparse.ArgumentParser();p.add_argument('session',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
r=a.session.expanduser().resolve();out=a.output.expanduser().resolve();assert r not in out.parents
es=[json.loads(s) for s in (r/'trial_events.jsonl').read_text().splitlines()]
start=next(e['wall_time_ns'] for e in es if e['kind']=='forward_publication')
out.mkdir(parents=True,exist_ok=True)
with (out/'trace.csv').open('w') as f:
    w=csv.writer(f);w.writerow(['bag_time_relative_source_s','topic','joint','velocity_value','position_rad','source_header_ns'])
    for path in (r/'bag').glob('*.db3'):
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            types={i:(n,get_message(t)) for i,n,t in db.execute('SELECT id,name,type FROM topics') if n in ('/motor_fb','/cmd_vel','/cmd_vel_teleop')}
            for i,t,blob in db.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp,id'):
                if i not in types or not -2<=(t-start)/1e9<=6:continue
                n,typ=types[i];msg=deserialize_message(blob,typ)
                if n=='/motor_fb':
                    hdr=msg.header.stamp.sec*10**9+msg.header.stamp.nanosec
                    for j,v,x in zip(msg.name,msg.velocity,msg.position):w.writerow([(t-start)/1e9,n,j,v,x,hdr])
                else:w.writerow([(t-start)/1e9,n,'linear_x',msg.linear.x,'',''])
anchors={e['kind']:(e['wall_time_ns']-start)/1e9 for e in es if e['kind'] in ('zero_requested','final_zero_observed','firmware_disable_ack')}
(out/'anchors.json').write_text(json.dumps(anchors,indent=2)+'\n')
print(str(out/'trace.csv'))
