"""Live readiness before allocating a pilot slot. No motion publishers."""
import time
import stack_readiness
import pilot_state

def observe_active_zero():
    import rclpy
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(args=[],signal_handler_options=SignalHandlerOptions.NO)
    n=Node('nino_before_recording_readonly',enable_rosout=False,start_parameter_services=False)
    obs=stack_readiness.Observer(n)
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            rclpy.spin_once(n,timeout_sec=.02);obs.poll();s=obs.snapshot()
            if not stack_readiness.problems(s):return s
        return obs.snapshot()
    finally:n.destroy_node();rclpy.try_shutdown()

def begin_after_ready(root,session_id,output,conditions,reader=None):
    s=(reader or observe_active_zero)()
    errors=stack_readiness.problems(s)
    if errors:raise RuntimeError('No pilot slot consumed; stack not ready: '+str(errors))
    return pilot_state.begin(root,session_id,output,{**conditions,'preallocation_ready_snapshot':s})
