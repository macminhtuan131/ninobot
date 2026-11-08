"""Read-only fixture reader with one scheduled executor pause; no motor output."""
import argparse
import json
import os
from pathlib import Path
import signal
import time
from . import joint_boundary_observer as shared
from .joint_reliability_candidate import replace_joint_subscription, qos_record


def run(directory, domain, role):
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import JointState
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    context = Context()
    rclpy.init(context=context, domain_id=domain, signal_handler_options=rclpy.signals.SignalHandlerOptions.NO)
    node = Node('nino_joint_fixture_' + role, context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    stopping, count, last, error = False, 0, None, None
    stream = (directory / 'joint_records.jsonl').open('w', buffering=65536)
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    def receive(message):
        nonlocal count, last, error
        try:
            count += 1
            last = shared.message_record(message, count)
            stream.write(json.dumps(last, allow_nan=False) + '\n')
        except Exception as exc:error = repr(exc)
    q = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
    subscription = node.create_subscription(JointState, '/joint_states', receive, q)
    change = None
    if role == 'reliable':
        change = replace_joint_subscription(node, receive)
        subscription = next(s for s in node.subscriptions if s.topic_name == '/joint_states')
    shared.atomic(directory / 'ready.json', dict(pid=os.getpid(), domain_id=domain, role=role, motor_command_publishers=0,
        subscriber_qos=qos_record(subscription.qos_profile), candidate_change=change))
    handled, graph_at, last_graph, paused = None, 0., None, False
    try:
        while not stopping:
            plan_path = directory / 'pause_plan.json'
            if plan_path.exists() and not paused:
                plan = shared.read(plan_path)
                if time.monotonic_ns() >= plan['start_monotonic_ns']:
                    started = time.monotonic_ns()
                    shared.atomic(directory / 'pause_started.json', dict(request_id=plan['request_id'], actual_start_ns=started,
                        planned_start_ns=plan['start_monotonic_ns'], received_count=count, last=last))
                    # Intentional blocking of this reader only. Source is a separate process.
                    time.sleep(plan['duration_ns'] / 10**9)
                    shared.atomic(directory / 'pause_ended.json', dict(request_id=plan['request_id'], actual_start_ns=started,
                        actual_end_ns=time.monotonic_ns(), received_count=count, last=last))
                    paused = True
            executor.spin_once(timeout_sec=.001)
            if error:raise RuntimeError(error)
            if time.monotonic() >= graph_at:
                current = shared.graph(node)
                if current != last_graph:
                    with (directory / 'graph.jsonl').open('a') as f:f.write(json.dumps(dict(receipt_monotonic_ns=time.monotonic_ns(), publishers=current)) + '\n')
                    last_graph = current
                graph_at = time.monotonic() + .1
            path = directory / 'snapshot_request.json'
            if path.exists():
                request = shared.read(path)
                if request['request_id'] != handled:
                    reply = shared.snapshot(request, last, count)
                    if reply is not None:
                        stream.flush()
                        shared.atomic(directory / 'snapshot_response.json', reply)
                        handled = request['request_id']
        return 0
    finally:
        stream.flush();stream.close()
        shared.atomic(directory / 'closed.json', dict(pid=os.getpid(), role=role, count=count, last=last, error=error,
            pause_performed=paused, motor_command_publishers=0, closed_monotonic_ns=time.monotonic_ns()))
        executor.shutdown(timeout_sec=2)
        node.destroy_node()
        if context.ok():context.shutdown()
        for s, handler in previous.items():signal.signal(s, handler)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--domain', type=int, default=139)
    p.add_argument('--role', choices=['best_effort', 'reliable'], required=True)
    a = p.parse_args(argv)
    return run(a.output, a.domain, a.role)


if __name__ == '__main__':raise SystemExit(main())
