"""Studio-only startup transport repair. Frozen experiment backends unchanged.

One subscription re-registration during zero-command startup, never a physics
request retry or an in-task data repair. Failure retains all startup evidence.
"""
from copy import deepcopy
import time
from .drive_readiness_candidate import DriveReadinessBackend
from .residual_workflow import save

STATS='/world/factory_floor_lab/stats'
COMPONENTS=('left_wheel','right_wheel','caster_left_wheel','caster_right_wheel',
            'caster_bracket_left','caster_bracket_right','chassis')


class StudioStartupBackend(DriveReadinessBackend):
    def reset(self,seed=None):
        self._startup_active=True;self._startup_ros_since=None
        self._startup_rearmed=False;self._startup_rearmed_at=None
        self._startup_last_saved=0.;self._startup_events=[]
        try:
            return super().reset(seed=seed)
        except BaseException as exc:
            try:self._save_startup('failed',error=repr(exc))
            except Exception as logging_error:
                exc.add_note('Startup diagnostics could not be saved: '+repr(logging_error))
            raise
        finally:
            self._startup_active=False

    def _save_startup(self,phase,**extra):
        if not hasattr(self,'episode_dir'):return
        publisher=getattr(self,'publisher',None)
        subscribers=publisher.get_subscription_count() if publisher is not None else None
        with self.lock:
            data=dict(phase=phase,monotonic_s=time.monotonic(),clock_s=self.clock,
                      iterations=self.iterations,counts=deepcopy(self.counts),
                      required_ros_channels_present=all(k in self.messages for k in ('imu','wheel','truth','drive')),
                      command_subscribers=subscribers,
                      request=list(self.request),rearmed_once=self._startup_rearmed,
                      events=deepcopy(self._startup_events),**extra)
        save(self.episode_dir/'startup_diagnostics.json',data)

    def _rearm_startup_transport(self):
        from gz.msgs10.world_stats_pb2 import WorldStatistics
        from gz.msgs10.contacts_pb2 import Contacts
        node=self.gz_node
        topics=[STATS]+['/nino/contact_lab/'+c for c in COMPONENTS]
        for topic in topics:
            if not node.unsubscribe(topic):
                raise RuntimeError('Startup transport unsubscribe failed: '+topic)
        if node.subscribe(WorldStatistics,STATS,self._stats) is False:
            raise RuntimeError('Startup stats re-registration failed')
        for component in COMPONENTS:
            topic='/nino/contact_lab/'+component
            if node.subscribe(Contacts,topic,lambda m,k=component:self._contact(k,m)) is False:
                raise RuntimeError('Startup contact re-registration failed: '+component)

    def _check(self):
        super()._check()
        if not getattr(self,'_startup_active',False):return
        now=time.monotonic()
        with self.lock:
            ros_ready=all(k in self.messages for k in ('imu','wheel','truth','drive'))
            clock_ready=self.clock>0 and self.iterations>0
            zero=self.request==(0.,0.)
        if ros_ready and not clock_ready:
            if not zero:raise RuntimeError('Nonzero command during startup transport recovery')
            if self._startup_ros_since is None:self._startup_ros_since=now
            if not self._startup_rearmed and now-self._startup_ros_since>=8.:
                # Mark before the operation: an exception must not cause reattempt.
                self._startup_rearmed=True;self._startup_rearmed_at=now
                self._startup_events.append(dict(kind='one_startup_subscription_re_registration',
                    monotonic_s=now,physics_requests_retried=0,in_task=False))
                self._rearm_startup_transport()
            elif self._startup_rearmed and now-self._startup_rearmed_at>=15.:
                raise TimeoutError('Gazebo stats silent after one startup re-registration; inspect startup_diagnostics.json')
        if now-self._startup_last_saved>=1.:
            self._save_startup('clock_ready' if clock_ready else 'waiting')
            self._startup_last_saved=now

    def _stop_episode(self):
        # Explicitly release Python callbacks before discarding the transport
        # node. The base cleanup still owns zero/launch/executor/ROS shutdown.
        node=self.gz_node
        errors=[]
        try:
            if node is not None:
                for topic in [STATS]+['/nino/contact_lab/'+c for c in COMPONENTS]:
                    try:node.unsubscribe(topic)
                    except Exception as exc:errors.append(dict(topic=topic,error=repr(exc)))
        finally:
            super()._stop_episode()
        if errors:
            save(self.episode_dir/'transport_cleanup_errors.json',errors)
            raise RuntimeError('Gazebo subscription cleanup failed')
