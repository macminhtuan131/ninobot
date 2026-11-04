"""Read-only live stack readiness. No publishers or lifecycle transitions."""
import math,time
from scene_guard import SceneTracker, scene_problems
TOPICS=('/cmd_vel_selected','/cmd_vel_smoothed','/cmd_vel')
EXPECTED={'/cmd_vel_selected':['nino_command_gate'],'/cmd_vel_smoothed':['velocity_smoother'],'/cmd_vel':['collision_monitor']}

def problems(s):
    errors=[]
    for node in ('velocity_smoother','collision_monitor'):
        if s['states'].get(node)!=3:errors.append(node+' not active')
    for topic in TOPICS:
        if s['counts'].get(topic,0)<10 or s['ages'].get(topic,999)>.2:errors.append(topic+' absent/stale')
        if s['owners'].get(topic)!=EXPECTED[topic]:errors.append(topic+' owner mismatch')
    if any(s.get('competing_source_owners',{}).values()):errors.append('competing source/enable owner')
    if s.get('nonzero_or_nonfinite',0):errors.append('nonzero/nonfinite before trial')
    if s.get('status_age_s',999)>.6:errors.append('motor status stale')
    st=s.get('status',0)
    if st&3!=3 or st&76:errors.append('wheel freshness/fault/mode')
    errors.extend(scene_problems(s.get("clear_zone",{})))
    return errors

class Observer:
    def __init__(self,node):
        from geometry_msgs.msg import Twist
        from std_msgs.msg import UInt8
        from lifecycle_msgs.srv import GetState
        self.scene=SceneTracker(node)
        self.node=node;self.counts={};self.times={};self.nonzero=0;self.states={};self.pending={};self.last_query=0;self.status=None;self.status_time=0
        def command(topic,m):
            self.counts[topic]=self.counts.get(topic,0)+1;self.times[topic]=time.monotonic()
            if any(not math.isfinite(getattr(v,k)) or getattr(v,k)!=0 for v in (m.linear,m.angular) for k in ('x','y','z')):self.nonzero+=1
        self.subs=[node.create_subscription(Twist,t,lambda m,t=t:command(t,m),10) for t in TOPICS]
        self.subs.append(node.create_subscription(UInt8,'/motor_status',self.receive_status,100))
        self.clients={name:node.create_client(GetState,'/'+name+'/get_state') for name in ('velocity_smoother','collision_monitor')};self.request=GetState.Request
    def receive_status(self,m):self.status=m.data;self.status_time=time.monotonic()
    def poll(self):
        now=time.monotonic()
        for name,(f,at) in list(self.pending.items()):
            if f.done():
                try:self.states[name]=(f.result().current_state.id,now)
                except Exception:self.states[name]=(None,now)
                del self.pending[name]
            elif now-at>1.:
                self.clients[name].remove_pending_request(f);self.states[name]=(None,now);del self.pending[name]
        if now-self.last_query>.3:
            self.last_query=now
            for name,c in self.clients.items():
                if name not in self.pending and c.service_is_ready():self.pending[name]=(c.call_async(self.request()),now)
    def snapshot(self):
        now=time.monotonic()
        return {'clear_zone':self.scene.snapshot(),'states':{n:s for n,(s,t) in self.states.items() if now-t<2},'counts':dict(self.counts),'ages':{t:now-at for t,at in self.times.items()},'owners':{t:sorted(e.node_name for e in self.node.get_publishers_info_by_topic(t)) for t in TOPICS},'competing_source_owners':{t:[e.node_name for e in self.node.get_publishers_info_by_topic(t)] for t in ('/cmd_vel_teleop','/cmd_vel_nav','/cmd_mit','/cmd_torque','/motor_enable')},'nonzero_or_nonfinite':self.nonzero,'status':self.status or 0,'status_age_s':now-self.status_time}
