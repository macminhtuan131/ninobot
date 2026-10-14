"""Optional governor must replace the reference smoother, not stack with it."""
import importlib.util
from pathlib import Path
from launch import LaunchContext

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location("nino_command_stack",ROOT/"src/nino_pi/launch/command_stack.launch.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def owner(enabled):
    context=LaunchContext()
    context.launch_configurations.update(control_params=str(ROOT/"src/nino_pi/config/control.yaml"),
        governor="true" if enabled else "false",
        governor_params=str(ROOT/"src/nino_control/config/speed_governor.yaml"))
    actions=module.command_owner(context)
    executables=[action.node_executable if isinstance(action.node_executable,str) else
                 "".join(s.perform(context) for s in action.node_executable) for action in actions]
    return executables


def test_default_smoother_owner_is_preserved():
    assert owner(False)==["velocity_smoother","lifecycle_manager"]


def test_governor_is_sole_reference_limiter_in_optional_pipeline():
    assert owner(True)==["speed_governor","lifecycle_manager"]
