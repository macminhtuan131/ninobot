from glob import glob
from setuptools import find_packages, setup

setup(
    name="nino_pi", version="0.1.0", packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/nino_pi"]),
        ("share/nino_pi", ["package.xml", "README.md", "REAL_DATA_COLLECTION.md", "REAL_DATA_STUDIO.md", "LAPTOP_CONTROL_AND_COLLECTION.md", "REAL_SESSION_FIELD_GUIDE.md", "STM32_USB_INTEGRATION.md", "WHEEL_RESPONSE_PROTOCOL.md", "CONTROL_MODES_GUI.md", "GUIDED_COLLECTION.md", "TD3_TRAINING_GUI.md"]),
        ("share/nino_pi/launch", glob("launch/*.launch.py")),
        ("share/nino_pi/config", glob("config/*.yaml")),
        ("share/nino_pi/config", glob("config/*.json")),
        ("share/nino_pi/scripts", glob("scripts/*.sh")),
    ],
    install_requires=["setuptools"], zip_safe=True,
    extras_require={"studio-export": ["pyarrow>=18,<27"]},
    package_data={"nino_pi": ["project_evidence.json", "research_plan.json", "collection_runtime.zip"]},
    maintainer="Nino Robot Maintainer", maintainer_email="maintainer@example.com",
    description="Navigation and teleoperation above an existing physical robot driver.",
    license="Apache-2.0",
    entry_points={"console_scripts": ["command_gate = nino_pi.command_gate:main",
                                      "keyboard_teleop = nino_pi.keyboard:main",
                                      "hardware_audit = nino_pi.hardware_audit:main",
                                      "state_monitor = nino_pi.state_monitor:main",
                                      "collect_real_data = nino_pi.collect_real_data:main",
                                      "laptop_control = nino_pi.laptop_control:main",
                                      "mode_gui = nino_pi.mode_gui:main",
                                      "td3_training_gui = nino_pi.td3_training_panel:main",
                                      "mode_bridge = nino_pi.mode_bridge:main"]},
)
