"""Conservative stationary XY readiness, not a replacement for collision monitor."""
from collections import deque
import math,time

def scene_problems(s):
    errors=[]
    if s.get('monitor_action')==1:errors.append('monitor STOP still active')
    if s.get('scan_count',0)<20 or s.get('span_s',0)<5:errors.append('need5s fresh clear scans')
    if s.get('age_s',999)>.5 or s.get('max_gap_s',999)>.5:errors.append('scan absent/stale/gap')
    if s.get('max_points',999)>=3:errors.append('points inside unchanged StopZone')
    if s.get('last_stop_age_s') is not None and s['last_stop_age_s']<5:errors.append('recent monitor STOP')
    return errors

class SceneTracker:
    def __init__(self,node):
        from sensor_msgs.msg import LaserScan
        from tf2_msgs.msg import TFMessage
        from nav2_msgs.msg import CollisionMonitorState
        from rclpy.qos import QoSProfile,DurabilityPolicy,ReliabilityPolicy,qos_profile_sensor_data
        self.rows=deque(maxlen=200);self.tf={};self.last_stop=None;self.monitor_action=None
        qos=QoSProfile(depth=100,durability=DurabilityPolicy.TRANSIENT_LOCAL,reliability=ReliabilityPolicy.RELIABLE)
        self.subs=[node.create_subscription(TFMessage,'/tf_static',self.transform,qos),node.create_subscription(LaserScan,'/scan_raw',self.scan,qos_profile_sensor_data),node.create_subscription(CollisionMonitorState,'/collision_monitor_state',self.monitor,10)]
    def transform(self,msg):
        for t in msg.transforms:self.tf[t.child_frame_id]=t
    def monitor(self,msg):
        self.monitor_action=int(msg.action_type)
        if msg.action_type==1:self.last_stop=time.monotonic()
    def scan(self,msg):
        t=self.tf.get(msg.header.frame_id)
        if t is None:return
        q=t.transform.rotation
        if t.header.frame_id!='base_link' or max(abs(q.x),abs(q.y),abs(q.z),abs(abs(q.w)-1))>1e-8:return
        count=0;finite=0
        for i,r in enumerate(msg.ranges):
            if math.isfinite(r) and msg.range_min<=r<=msg.range_max:
                finite+=1;a=msg.angle_min+i*msg.angle_increment
                x=t.transform.translation.x+r*math.cos(a);y=t.transform.translation.y+r*math.sin(a)
                count+=int(-.4<=x<=.46 and -.34<=y<=.34)
        if not finite:count=999
        self.rows.append((time.monotonic(),count))
    def snapshot(self):
        now=time.monotonic();r=[x for x in self.rows if now-x[0]<=5.3]
        return {'monitor_action':self.monitor_action,'scan_count':len(r),'span_s':r[-1][0]-r[0][0] if r else 0,'age_s':now-r[-1][0] if r else 999,'max_gap_s':max((b[0]-a[0] for a,b in zip(r,r[1:])),default=999),'max_points':max((p for t,p in r),default=999),'last_stop_age_s':now-self.last_stop if self.last_stop is not None else None}
