"""Robot and controller failures must not proceed to motor actuation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from launch.actions import LogInfo, Shutdown

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("nino_sim_launch",ROOT / "src/nino_description/launch/sim.launch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("label",["Robot spawn","Controller activation"])
def test_failed_startup_stops_instead_of_running_next_stage(label):
    motor_start = object()
    actions = module.after_required_process(SimpleNamespace(returncode=1),None,
                                           label=label,success_actions=[motor_start])
    assert motor_start not in actions
    assert any(isinstance(action,Shutdown) for action in actions)
    assert any(isinstance(action,LogInfo) for action in actions)


def test_successful_startup_proceeds():
    motor_start = object()
    assert module.after_required_process(SimpleNamespace(returncode=0),None,
                                        label="Controller activation",success_actions=[motor_start]) == [motor_start]
