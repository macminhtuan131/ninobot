"""Retain encoder samples needed by IMU interpolation in paused lockstep.

This changes transport history only. Fusion, action duration and freshness
limits are untouched; no prediction or extra physics step fills a missing pose.
"""


def patch_interface(code):
    anchor = "AMCL_POSE_QOS = QoSProfile("
    subscription = 'self.create_subscription(JointState, "/joint_states", self._joint_callback, SENSOR_QOS)'
    if code.count(anchor) != 1 or code.count(subscription) != 1:
        raise ValueError("Unexpected frozen encoder subscription")
    code = code.replace(anchor,
        "# Encoder history must survive IMU/encoder delivery reordering.\n"
        "JOINT_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100,\n"
        "                       reliability=ReliabilityPolicy.BEST_EFFORT)\n\n" + anchor)
    return code.replace(subscription, subscription.replace("SENSOR_QOS", "JOINT_QOS"))
