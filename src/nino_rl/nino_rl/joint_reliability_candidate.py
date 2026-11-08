"""One isolated observer change: JointState reliability; frozen parent untouched."""
from . import residual_joint_boundary as diagnostic
from .residual_workflow import save


def qos_record(q):
    return dict(reliability=int(q.reliability), depth=q.depth, history=int(q.history), durability=int(q.durability),
                lifespan_ns=q.lifespan.nanoseconds, deadline_ns=q.deadline.nanoseconds, liveliness=int(q.liveliness),
                liveliness_lease_ns=q.liveliness_lease_duration.nanoseconds, avoid_ros_namespace_conventions=q.avoid_ros_namespace_conventions)


def replace_joint_subscription(node, receive):
    """Replace the sole joint subscription before messages/owned Gazebo launch."""
    from rclpy.qos import ReliabilityPolicy, QoSProfile
    subscriptions = list(node.subscriptions)
    joint = [s for s in subscriptions if s.topic_name == '/joint_states']
    if len(joint) != 1:
        raise ValueError('Expected one joint subscription before candidate replacement')
    old = joint[0]
    before = qos_record(old.qos_profile)
    if before['reliability'] != int(ReliabilityPolicy.BEST_EFFORT) or before['depth'] != 100:
        raise ValueError('Unexpected frozen joint observer QoS')
    others = {s.topic_name: (id(s), qos_record(s.qos_profile)) for s in subscriptions if s is not old}
    previous = old.qos_profile
    q = QoSProfile(history=previous.history, depth=previous.depth, reliability=ReliabilityPolicy.RELIABLE,
        durability=previous.durability, lifespan=previous.lifespan, deadline=previous.deadline,
        liveliness=previous.liveliness, liveliness_lease_duration=previous.liveliness_lease_duration,
        avoid_ros_namespace_conventions=previous.avoid_ros_namespace_conventions)
    if not node.destroy_subscription(old):
        raise RuntimeError('Could not destroy initial joint subscription')
    sub = node.create_subscription(old.msg_type, '/joint_states', receive, q)
    after = qos_record(sub.qos_profile)
    expected = dict(before, reliability=int(ReliabilityPolicy.RELIABLE))
    if after != expected:
        raise ValueError('Candidate changed more than joint reliability')
    actual = {s.topic_name: (id(s), qos_record(s.qos_profile)) for s in node.subscriptions if s is not sub}
    if actual != others:
        raise ValueError('Nonjoint subscriptions changed')
    return dict(before=before, after=after, nonjoint_subscriptions_unchanged=True, replaced_before_owned_launch=True)


class ReliableBoundaryBackend(diagnostic.BoundaryBackend):
    """Same diagnostics/physics/guidance; only primary joint reader is RELIABLE."""
    def _start_io(self):
        super()._start_io()
        if self.counts.get('wheel', 0):
            raise ValueError('Candidate must replace QoS before any joint sample')
        self.candidate_subscription = replace_joint_subscription(self.node, lambda message: self._receive('wheel', message))
        save(self.audit_dir / 'candidate_subscription.json', self.candidate_subscription)
