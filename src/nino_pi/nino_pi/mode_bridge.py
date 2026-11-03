"""GUI bridge on Pi: authority plus opt-in capture/teleop through the command stack."""
import argparse
import json
import os
import secrets
import select
import sys
import time
from .mode_protocol import Session, STATE_TOPIC, REQUEST_TOPIC, VERSION, MAGIC
from .data_bridge import DataBridge, DemoIO

output_closed = False


def emit(value):
    global output_closed
    if not output_closed:
        try:
            print(json.dumps(value, ensure_ascii=False), flush=True)
        except BrokenPipeError:
            output_closed = True


class Demo:
    """UI demonstrator only, not a substitute for the production C policy tests."""
    def __init__(self):
        self.start = time.monotonic()
        self.values = [VERSION, MAGIC, 0, 0, 0, 0, 0, 1, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0]
        self.lease = time.monotonic()

    def send(self, q):
        _, client, seq, op, arg = q
        s = self.values
        result = 0
        if op == 1:
            if s[2] and s[2] != client:
                result = 2
            else:
                s[2:6] = [client, seq, 0, 0]
                self.lease = time.monotonic()
        elif op in (5, 6):
            s[5] = 0
            if op == 6:
                s[6], s[7] = 1, 4
        elif client != s[2]:
            result = 3
        elif op == 2:
            self.lease = time.monotonic()
        elif op == 3:
            s[4:6], s[7] = [arg, 0], 3
        elif op == 4:
            if s[6]:
                result = 8
            elif not s[4]:
                result = 9
            elif s[4] == 1:
                result = 6  # demo has no RC receiver
            else:
                s[5], s[7] = 1, 0
        elif op == 7:
            s[6], s[7] = 0, 2
        elif op == 8:
            s[2:6], s[7] = [0, 0, 0, 0], 10
        if s[2] == client:
            s[3] = seq
        if op != 2:
            s[14:17] = [client, seq, result]

    def spin(self):
        s = self.values
        s[19] = int((time.monotonic() - self.start) * 1000)
        s[13] = int((time.monotonic() - self.lease) * 1000) if s[2] else 0xFFFFFFFF
        if s[2] and s[13] > 500:
            s[2:8] = [0, 0, 0, 0, 1, 5]
        s[17] = s[5]
        return s[:]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demo", action="store_true")
    args = p.parse_args(argv)
    node = None
    if args.demo:
        backend = Demo()
        send = backend.send
    else:
        import rclpy
        from rclpy.node import Node
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from std_msgs.msg import UInt32MultiArray
        rclpy.init(args=[])
        node = Node("nino_mode_bridge_" + secrets.token_hex(3))
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        pub = node.create_publisher(UInt32MultiArray, REQUEST_TOPIC, qos)

        def send(q):
            pub.publish(UInt32MultiArray(data=q))

    session = Session(secrets.randbelow(0xFFFFFFFF) + 1, send, emit, time.monotonic)
    data = None
    try:
        if args.demo:
            io = DemoIO()
        else:
            from .mode_data_io import DataIO
            io = DataIO(node, emit)
        data = DataBridge(session, emit, io, demo=args.demo)
    except ImportError as e:
        emit({"type": "error", "message": "Thiếu dependency cho phần data: " + str(e)})
    if node:
        def receive(msg):
            try:
                session.receive(list(msg.data))
            except ValueError as e:
                session.fail(str(e))
        node.create_subscription(UInt32MultiArray, STATE_TOPIC, receive, qos)
    emit({"type": "connected", "demo": args.demo, "client": session.client,
          "data_supported": data is not None,
          "message": "DEMO — không kết nối robot" if args.demo else "Đã nối bridge; đang chờ firmware authority v1"})
    buf = b""
    last_demo = 0.0
    running = True
    try:
        while running:
            if select.select([sys.stdin], [], [], 0)[0]:
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 16384:
                    raise ValueError("GUI input quá dài")
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    try:
                        message = json.loads(raw)
                        if message.get("action") == "pulse":
                            session.pulse_at = time.monotonic()
                        elif message.get("action") == "close":
                            running = False
                            break
                        elif message.get("action") in DataBridge.ACTIONS:
                            if data is None:
                                raise ValueError("Bridge thiếu dependency phần thu data")
                            data.handle(message)
                        elif data is not None:
                            data.operator_action(message.get("action"))
                        else:
                            session.request(message.get("action"))
                    except (ValueError, TypeError, AttributeError) as e:
                        emit({"type": "error", "message": str(e)})
            if args.demo:
                if time.monotonic() - last_demo > 0.2:
                    session.receive(backend.spin())
                    last_demo = time.monotonic()
                time.sleep(0.01)
            else:
                rclpy.spin_once(node, timeout_sec=0.01)
            session.tick()
            if data is not None:
                data.tick()
    finally:
        if data is not None:
            data.close()
        session.close()
        if node:
            # Best effort delivery only. STM32 lease remains the independent backstop.
            for _ in range(5):
                rclpy.spin_once(node, timeout_sec=0.02)
            node.destroy_node()
            rclpy.shutdown()
        if data is not None and data.capture.active():
            # Recorder cleanup continues after control ownership is released.
            # A timeout remains incomplete; never pretend a bag closed successfully.
            deadline = time.monotonic() + 50
            while data.capture.active() and time.monotonic() < deadline:
                data.capture.poll()
                time.sleep(.1)


if __name__ == "__main__":
    main()
