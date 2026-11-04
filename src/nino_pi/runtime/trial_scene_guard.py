"""Trial supervision only; no publishers, actuator or lifecycle interfaces."""
from scene_guard import SceneTracker,scene_problems

class TrialSceneGuard(SceneTracker):
    def __init__(self,node):
        self.stop_latched=False
        super().__init__(node)

    def monitor(self,msg):
        super().monitor(msg)
        if msg.action_type==1:self.stop_latched=True

    def snapshot(self):
        return {**super().snapshot(),'trial_stop_latched':self.stop_latched}

    def require_clear(self):
        s=self.snapshot()
        if self.stop_latched:raise RuntimeError('Trial aborted: monitor STOP observed; no automatic resume')
        errors=scene_problems(s)
        if errors:raise RuntimeError('Trial scene not ready: '+str(errors))
        return s
