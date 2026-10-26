#!/usr/bin/env python3
"""Read-only, wall-time controller discovery and profile check before a run."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/nino_rl'))
from nino_rl.core import load_config


def check_controller(config, timeout=30.):
    import rclpy
    from rcl_interfaces.srv import GetParameters
    from rclpy.parameter import parameter_value_to_python
    rclpy.init()
    node = rclpy.create_node('controller_startup_profile_check')
    try:
        client = node.create_client(GetParameters, '/effort_drive/get_parameters')
        if not client.wait_for_service(timeout_sec=timeout):
            raise TimeoutError('Controller parameter service unavailable; restart this course simulator')
        expected = config['drive_controller']['parameters']
        future = client.call_async(GetParameters.Request(names=list(expected)))
        rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
        if not future.done() or future.result() is None:
            raise TimeoutError('Controller service is advertised but not responding')
        values = future.result().values
        if len(values) != len(expected):
            raise ValueError('Incomplete controller profile response')
        for (name, wanted), value in zip(expected.items(), values):
            actual = parameter_value_to_python(value)
            matches = actual == wanted if isinstance(wanted, (str, bool)) else (
                isinstance(actual, (float, int)) and abs(actual - wanted) < 1e-9)
            if not matches:
                raise ValueError(f'Controller mismatch: {name}={actual!r}, required {wanted!r}')
        print('Controller service responded; all saved profile parameters match.', flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=30.)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    check_controller(load_config(args.config), args.timeout)
