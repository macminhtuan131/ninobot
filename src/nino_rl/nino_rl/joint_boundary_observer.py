"""Independent read-only JointState recorder and bounded snapshot IPC."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import time


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False, sort_keys=True) + '\n')
    temporary.replace(path)


def message_record(message, sequence, receipt_ns=None):
    from rclpy.serialization import serialize_message
    payload = bytes(serialize_message(message))
    # Re-serialized CDR padding need not be identical across processes. Compare
    # message fields, not a fresh serializer's padding bytes, for payload parity.
    finite = lambda values: [float(v) if math.isfinite(v) else dict(nonfinite=repr(v)) for v in values]
    semantic = dict(stamp_ns=message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
        frame_id=message.header.frame_id, name=list(message.name), position=finite(message.position),
        velocity=finite(message.velocity), effort=finite(message.effort))
    canonical = json.dumps(semantic, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    return dict(sequence=sequence, source_stamp_ns=message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
                receipt_monotonic_ns=time.monotonic_ns() if receipt_ns is None else receipt_ns,
                cdr_sha256=hashlib.sha256(payload).hexdigest(), cdr_bytes=len(payload),
                payload_sha256=hashlib.sha256(canonical).hexdigest(), payload_hash_schema='joint_fields_json_v1',
                frame_id=message.header.frame_id)


def endpoint_supported(record, target_ns, maximum_age_ns=40_000_000):
    return bool(record is not None and 0 <= target_ns - record['source_stamp_ns'] <= maximum_age_ns)


def snapshot(request, last, count, *, now_ns=None):
    """No interpolation, forward support, default zero or physics on timeout."""
    now_ns = time.monotonic_ns() if now_ns is None else now_ns
    supported = endpoint_supported(last, request['target_stamp_ns'], request['maximum_age_ns'])
    if not supported and now_ns < request['deadline_monotonic_ns']:
        return None
    return dict(request_id=request['request_id'], target_stamp_ns=request['target_stamp_ns'],
                request_monotonic_ns=request['request_monotonic_ns'], response_monotonic_ns=now_ns,
                supported=supported, timed_out=not supported, received_count=count, last=last,
                age_ns=None if last is None else request['target_stamp_ns'] - last['source_stamp_ns'])


def graph(node):
    result = []
    for endpoint in node.get_publishers_info_by_topic('/joint_states'):
        q = endpoint.qos_profile
        result.append(dict(node_name=endpoint.node_name, node_namespace=endpoint.node_namespace,
            topic_type=endpoint.topic_type, endpoint_gid=list(endpoint.endpoint_gid),
            qos=dict(reliability=int(q.reliability), history=int(q.history), depth=q.depth,
                     durability=int(q.durability))))
    return result


def run(directory, domain):
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
    node = Node('nino_joint_boundary_independent', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    stream = (directory / 'joint_records.jsonl').open('w', buffering=65536)
    state = dict(count=0, last=None, error=None)
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    def receive(message):
        try:
            state['count'] += 1
            record = message_record(message, state['count'])
            stream.write(json.dumps(record, allow_nan=False) + '\n')
            state['last'] = record
        except Exception as exc:
            state['error'] = repr(exc)
    qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(JointState, '/joint_states', receive, qos)
    atomic(directory / 'ready.json', dict(pid=os.getpid(), domain_id=domain, topic='/joint_states',
        node_name=node.get_name(), subscriber_qos=dict(depth=100, reliability=int(qos.reliability)),
        motor_command_publishers=0, ready_monotonic_ns=time.monotonic_ns()))
    handled, graph_at, last_graph = None, 0., None
    try:
        while not stopping:
            executor.spin_once(timeout_sec=.002)
            if state['error']:
                raise RuntimeError(state['error'])
            now = time.monotonic()
            if now >= graph_at:
                current = graph(node)
                if current != last_graph:
                    with (directory / 'graph.jsonl').open('a') as f:
                        f.write(json.dumps(dict(receipt_monotonic_ns=time.monotonic_ns(), publishers=current)) + '\n')
                    last_graph = current
                graph_at = now + .25
            path = directory / 'snapshot_request.json'
            if path.exists():
                request = read(path)
                if request['request_id'] != handled:
                    response = snapshot(request, state['last'], state['count'])
                    if response is not None:
                        stream.flush()
                        atomic(directory / 'snapshot_response.json', response)
                        handled = request['request_id']
        return 0
    finally:
        stream.flush()
        stream.close()
        atomic(directory / 'closed.json', dict(pid=os.getpid(), count=state['count'], last=state['last'],
            error=state['error'], closed_monotonic_ns=time.monotonic_ns(), motor_command_publishers=0))
        executor.shutdown(timeout_sec=2)
        node.destroy_node()
        if context.ok():context.shutdown()
        for s, handler in previous.items():signal.signal(s, handler)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--domain', default=129, type=int)
    a = p.parse_args(argv)
    return run(a.output, a.domain)


if __name__ == '__main__':
    raise SystemExit(main())
