"""The removed course cannot reopen ROS; factory generation is independent."""
import importlib.util
from pathlib import Path
import sys

import pytest
from nino_rl.ros_env import NinoGazeboEnv


@pytest.mark.parametrize('config', [
    {'world_name': 'combined_rough_section'},
    {'world_name': 'combined_hall'},
    {'task': 'rocky_tracking'},
    {'rough_curriculum': {'enabled': True}},
])
def test_retired_inputs_rejected_before_route_or_ros_setup(config):
    # Minimal inputs deliberately omit ROS/robot/topic fields: rejection must
    # happen before attempting to use any of them.
    with pytest.raises(ValueError, match='retired'):
        NinoGazeboEnv(config)


def test_factory_generator_imports_with_old_generators_unavailable(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    scripts = root / 'src/nino_description/scripts'
    monkeypatch.syspath_prepend(str(scripts))
    for name in ('generate_rough_section', 'generate_rocky_world', 'generate_combined_world'):
        monkeypatch.setitem(sys.modules, name, None)
    spec = importlib.util.spec_from_file_location('factory_without_retired_course', scripts/'generate_factory_floor_lab.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.make_world)
    assert (scripts.parent/'worlds/factory_floor_template.sdf').is_file()
