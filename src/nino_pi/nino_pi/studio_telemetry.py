"""Small live observer, separate from raw recording. Rates are receipt observations."""
from collections import deque
import time


class TelemetryObserver:
    def __init__(self, config):
        import os
        import rclpy
        self.rclpy=rclpy;self.config=config;self.samples={};self.subscriptions={};self.errors=[];self.graph={}
        rclpy.init();self.node=rclpy.create_node('nino_studio_observer_'+str(os.getpid()));self.next_scan=0.

    def receive(self,name,message):
        now=time.monotonic()
        row=self.samples.setdefault(name,dict(count=0,times=deque(maxlen=512)))
        row['count']+=1;row['times'].append(now)

    def poll(self):
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rosidl_runtime_py.utilities import get_message
        now=time.monotonic()
        if now>=self.next_scan:
            self.next_scan=now+1.;self.graph=dict(self.node.get_topic_names_and_types())
            for row in self.config['topics']:
                name=row['name']
                if name in self.subscriptions or name not in self.graph:continue
                try:
                    if len(self.graph[name])!=1:raise ValueError('Multiple types')
                    qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.BEST_EFFORT,
                        durability=DurabilityPolicy.TRANSIENT_LOCAL if name=='/tf_static' else DurabilityPolicy.VOLATILE)
                    self.subscriptions[name]=self.node.create_subscription(get_message(self.graph[name][0]),name,
                        lambda msg,n=name:self.receive(n,msg),qos)
                except Exception as exc:
                    text=name+':'+str(exc)
                    if text not in self.errors:self.errors.append(text)
        # Bound live observer work; receipt statistics are not the raw recorder's counts.
        end=time.monotonic()+.015
        while time.monotonic()<end:self.rclpy.spin_once(self.node,timeout_sec=.001)

    def snapshot(self):
        now=time.monotonic();rows=[]
        for topic in self.config['topics']:
            name=topic['name'];s=self.samples.get(name,{});times=list(s.get('times',[]))
            recent=[t for t in times if now-t<=5.]
            span=recent[-1]-recent[0] if len(recent)>1 else 0.
            pubs=self.node.get_publishers_info_by_topic(name) if name in self.graph else []
            rows.append(dict(name=name,types=self.graph.get(name,[]),publishers=len(pubs),
                required=topic['required'],count=s.get('count',0),observed_hz=(len(recent)-1)/span if span>0 else None,
                last_receipt_age_s=now-times[-1] if times else None,purpose=topic['purpose']))
        return rows

    def close(self):
        self.node.destroy_node();self.rclpy.shutdown()
