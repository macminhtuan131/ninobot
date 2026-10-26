"""Laptop SSH frontend for the existing Pi command stack; no ROS needed locally.

Does not install/start hardware drivers, enable on launch, or change PI settings.
Each invocation owns only its SSH session. Keyboard is executed in a Pi TTY.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess


ACTIONS = ("check", "teleop", "keyboard", "mapping", "navigation", "manual",
           "navigation-mode", "enable", "disable", "stop")


def load_config(path):
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    for key in ("host", "user"):
        if not isinstance(config.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", config[key]):
            raise ValueError(key + " must be a hostname/IP or username without shell syntax")
    if type(config.get("port")) is not int or not 1 <= config["port"] <= 65535:
        raise ValueError("port must be 1..65535")
    if type(config.get("ros_domain_id")) is not int or not 0 <= config["ros_domain_id"] <= 232:
        raise ValueError(
            f"config {path}: ros_domain_id must be an integer in 0..232; "
            "example null is not a value. Edit this config with the domain used by "
            "the REAL drivers. Check printenv ROS_DOMAIN_ID in the Pi terminal "
            "that starts the drivers, or their service configuration. "
            "An empty value in a new SSH terminal does not identify a running driver's domain."
        )
    for key in ("robot_setup", "control_params", "navigation_params"):
        remote_path(config.get(key))
    if config.get("driver_setup") is not None:
        remote_path(config["driver_setup"])
    return config


def remote_path(value):
    """Expand only remote ~/; keep all other characters literal via shell quoting."""
    if not isinstance(value, str) or not value or "\n" in value or "\x00" in value:
        raise ValueError("remote file paths must be nonempty strings without newline/NUL")
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    if value.startswith("/"):
        return shlex.quote(value)
    raise ValueError("remote file paths must start with / or ~/")


def remote_script(config, action, map_path=None):
    if action not in ACTIONS:
        raise ValueError("unknown action")
    lines = ["set -e", "source /opt/ros/jazzy/setup.bash"]
    if config.get("driver_setup"):
        lines.append("source " + remote_path(config["driver_setup"]))
    lines.extend(["source " + remote_path(config["robot_setup"]),
                  "export ROS_DOMAIN_ID=" + str(config["ros_domain_id"])])
    # All command publishers, gate and watchdogs remain on the Pi. Do not
    # change discovery settings of running drivers for SSH-only control.
    if action in ("teleop", "mapping", "navigation"):
        pattern = "*nino_command_gate*|*collision_monitor*|*velocity_smoother*"
        if action in ("mapping", "navigation"):
            pattern += "|*slam_toolbox*|*amcl*"
        lines.extend([
            'nino_existing_nodes="$(ros2 node list)"',
            'case "$nino_existing_nodes" in',
            pattern + ')',
            'echo "A command/localization stack is already visible. Stop its launch deliberately before starting another; nothing was killed." >&2; exit 2;;',
            'esac',
        ])
    control = 'control_params:=' + remote_path(config["control_params"])
    commands = {
        "check": "ros2 node list\nros2 topic list -t\nros2 topic info /cmd_vel --verbose",
        "teleop": "exec ros2 launch nino_pi teleop.launch.py " + control,
        "keyboard": "exec ros2 run nino_pi keyboard_teleop --ros-args -p use_sim_time:=false",
        "mapping": "exec ros2 launch nino_pi mapping.launch.py " + control,
        "manual": "exec ros2 service call /nino_command_gate/navigation_mode std_srvs/srv/SetBool '{data: false}'",
        "navigation-mode": "exec ros2 service call /nino_command_gate/navigation_mode std_srvs/srv/SetBool '{data: true}'",
        "enable": "exec ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'",
        "disable": "exec ros2 service call /nino_command_gate/enable std_srvs/srv/SetBool '{data: false}'",
        "stop": "exec ros2 topic pub --once /nino/emergency_stop std_msgs/msg/Bool '{data: true}'",
    }
    if action == "navigation":
        if map_path is None:
            raise ValueError("navigation requires --map pointing to the REAL occupancy map on the Pi")
        command = ("exec ros2 launch nino_pi navigation.launch.py " + control
                   + " params_file:=" + remote_path(config["navigation_params"])
                   + " map:=" + remote_path(map_path) + " rviz:=false")
    else:
        command = commands[action]
    return "\n".join([*lines, command])


def ssh_command(config, script):
    # ssh transmits its command through a remote shell; quote the entire bash
    # script, not just individual argv. Never interpolate unquoted file paths.
    return ["ssh", "-t", "-p", str(config["port"]), "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=2",
            "--", config["user"] + "@" + config["host"], "bash -lc " + shlex.quote(script)]


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print script only; do not connect or send commands")
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--map", help="remote absolute or ~/ occupancy-map YAML path; required for navigation")
    opt = parser.parse_args(args)
    try:
        config = load_config(opt.config)
        script = remote_script(config, opt.action, opt.map)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    if opt.dry_run:
        print(script)
        return 0
    try:
        return subprocess.call(ssh_command(config, script))
    except FileNotFoundError:
        parser.error("OpenSSH client not installed on the laptop")


if __name__ == "__main__":
    raise SystemExit(main())
