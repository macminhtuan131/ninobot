"""Exercise the actual EffortDrive with local synthetic source clocks, without physics."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def probe(output, wall_period):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64MultiArray
    from rclpy.qos import QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, ROS_DOMAIN_ID='130', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    command = [sys.executable, '-c', 'from nino_control.effort_drive import main; main()',
               '--ros-args', '-p', 'use_sim_time:=true', '-p', 'accept_torque:=false',
               '-p', 'pi_integrator_profile:=conditional_v1']
    log = (output/'drive.log').open('w')
    child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    ctx = Context()
    rclpy.init(context=ctx, domain_id=130)
    node = Node('drive_clock_fixture', context=ctx)
    clock = node.create_publisher(Clock, '/clock',
        QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT))
    joint = node.create_publisher(JointState, '/joint_states', qos_profile_sensor_data)
    rows = []
    lock = threading.Lock()
    def receive(message):
        fields = message.layout.dim[0].label.split(',')
        with lock:
            rows.append(dict(zip(fields, message.data)))
    node.create_subscription(Float64MultiArray, '/nino_drive/diagnostics', receive, 1000)
    executor = SingleThreadedExecutor(context=ctx)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic()+10
        while clock.get_subscription_count() < 1 or joint.get_subscription_count() < 1:
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Fixture discovery failed')
            time.sleep(.02)
        time.sleep(1.)
        began = time.monotonic()
        for tick in range(1, 501):
            ns = tick*2_000_000
            state = JointState()
            state.header.stamp.sec, state.header.stamp.nanosec = divmod(ns, 1_000_000_000)
            state.name = ['left_wheel_joint', 'right_wheel_joint']
            state.velocity = [0., 0.]
            joint.publish(state)
            message = Clock()
            message.clock = state.header.stamp
            clock.publish(message)
            if wall_period:
                time.sleep(wall_period)
        time.sleep(.5)
        wall = time.monotonic()-began
        with lock:
            retained = list(rows)
        middle = [r for r in retained if .04 <= r['sim_time_s'] <= .98]
        result = dict(synthetic_clock_only=True, physics_tested=False, source_step_s=.002,
            wall_period_s=wall_period, ticks=500, wall_s=wall,
            diagnostics=len(retained), inspected_windows=len(middle),
            control_updates=sum(r['control_updates'] for r in middle),
            maximum_control_dt_s=max((r['control_raw_dt_max_s'] for r in middle), default=None),
            long_intervals=sum(r['control_dt_over_4ms'] for r in middle),
            invalid=sum(r['control_dt_invalid'] for r in middle),
            fallbacks=sum(r['control_dt_fallbacks'] for r in middle))
        result['timing_pass'] = bool(middle and result['maximum_control_dt_s'] <= .004000001
            and not any(result[k] for k in ('long_intervals', 'invalid', 'fallbacks')))
        (output/'diagnostics.json').write_text(json.dumps(retained, indent=2)+'\n')
        (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        return result
    finally:
        os.killpg(child.pid, signal.SIGINT)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        executor.shutdown(timeout_sec=3)
        thread.join(timeout=3)
        node.destroy_node()
        ctx.shutdown()
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {name: probe(args.output/name, period)
               for name, period in [('burst', 0.), ('paced', .01)]}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
