"""SSH construction only; never connect to a Pi or send robot commands."""
import json
from pathlib import Path
import shlex
import subprocess

import pytest

from nino_pi import laptop_control as control


CONFIG = Path(__file__).resolve().parents[1] / "config"


def config():
    value = json.loads((CONFIG / "laptop_control.example.json").read_text())
    value["ros_domain_id"] = 228
    return value


@pytest.mark.parametrize("action", control.ACTIONS)
def test_every_script_valid_bash_and_domain_explicit(action):
    script = control.remote_script(config(), action, "~/maps/factory.yaml" if action == "navigation" else None)
    result = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "export ROS_DOMAIN_ID=228" in script
    assert "use_sim_time:=true" not in script
    if action != "enable":
        assert "/nino_command_gate/enable std_srvs/srv/SetBool '{data: true}'" not in script


@pytest.mark.parametrize("action", ["teleop", "mapping", "navigation"])
def test_launch_refuses_existing_stack_and_never_kills_it(action):
    script = control.remote_script(config(), action, "~/maps/factory.yaml" if action == "navigation" else None)
    assert "nino_existing_nodes" in script and "exit 2" in script
    assert "kill " not in script and "pkill" not in script
    assert "control_params:=" in script
    assert "governor:=true" not in script


def test_keyboard_uses_existing_teleop_node_no_direct_cmd_vel():
    script = control.remote_script(config(), "keyboard")
    assert "keyboard_teleop" in script
    assert "/cmd_vel" not in script
    assert "create_publisher" not in script


def test_teleop_can_use_existing_localization_but_navigation_cannot_duplicate_it():
    teleop = control.remote_script(config(), "teleop")
    navigation = control.remote_script(config(), "navigation", "~/maps/factory.yaml")
    assert "|*amcl*" not in teleop and "|*slam_toolbox*" not in teleop
    assert "|*amcl*" in navigation and "|*slam_toolbox*" in navigation


def test_navigation_needs_real_remote_map():
    with pytest.raises(ValueError):
        control.remote_script(config(), "navigation")
    script = control.remote_script(config(), "navigation", "~/maps/our factory.yaml")
    assert 'map:="$HOME"/\'maps/our factory.yaml\'' in script
    assert "rviz:=false" in script


def test_nested_shell_quoting_keeps_user_paths_literal():
    value = config()
    value["driver_setup"] = "~/driver ws/install/setup.bash"
    value["robot_setup"] = "~/robot $(touch SHOULD_NOT_EXIST)/setup.bash"
    script = control.remote_script(value, "check")
    assert '"$HOME"/\'robot $(touch SHOULD_NOT_EXIST)/setup.bash\'' in script
    argv = control.ssh_command(value, script)
    assert argv[0] == "ssh" and "-t" in argv
    assert argv[argv.index("--") + 1] == "d@192.168.0.107"
    assert shlex.split(argv[-1]) == ["bash", "-lc", script]


@pytest.mark.parametrize("key,value", [("host", "-oProxyCommand=evil"), ("host", "host;whoami"),
    ("user", "d@elsewhere"), ("ros_domain_id", None), ("ros_domain_id", True),
    ("ros_domain_id", 233), ("port", 0), ("robot_setup", "relative/path")])
def test_invalid_or_unconfigured_host_domain_paths_are_rejected(tmp_path, key, value):
    data = config()
    data[key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        control.load_config(path)


def test_dry_run_does_not_connect_or_enable(tmp_path, monkeypatch, capsys):
    path = tmp_path / "laptop.json"
    path.write_text(json.dumps(config()))
    monkeypatch.setattr(control.subprocess, "call", lambda *a, **k: pytest.fail("SSH must not run"))
    assert control.main(["--config", str(path), "--dry-run", "teleop"]) == 0
    assert "teleop.launch.py" in capsys.readouterr().out


def test_null_domain_error_identifies_config_and_never_connects(tmp_path, monkeypatch, capsys):
    path = tmp_path / "my_laptop.json"
    data = config()
    data["ros_domain_id"] = None
    original = json.dumps(data)
    path.write_text(original)
    monkeypatch.setattr(control.subprocess, "call", lambda *a, **k: pytest.fail("SSH must not run"))
    with pytest.raises(SystemExit) as exc:
        control.main(["--config", str(path), "--dry-run", "teleop"])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert str(path) in error
    assert "printenv ROS_DOMAIN_ID" in error
    assert path.read_text() == original


def test_ssh_connection_failure_is_not_hidden(tmp_path, monkeypatch):
    path = tmp_path / "laptop.json"
    path.write_text(json.dumps(config()))
    monkeypatch.setattr(control.subprocess, "call", lambda *a, **k: 255)
    assert control.main(["--config", str(path), "check"]) == 255


def test_mapping_forwards_control_profile():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nino_mapping", CONFIG.parent / "launch" / "mapping.launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from launch.actions import IncludeLaunchDescription
    actions = module.generate_launch_description().entities
    teleop = [a for a in actions if isinstance(a, IncludeLaunchDescription)][0]
    assert "control_params" in dict(teleop.launch_arguments)
