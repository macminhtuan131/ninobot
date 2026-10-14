from glob import glob
from setuptools import find_packages, setup

setup(
    name="nino_pi", version="0.1.0", packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/nino_pi"]),
        ("share/nino_pi", ["package.xml", "README.md"]),
        ("share/nino_pi/launch", glob("launch/*.launch.py")),
        ("share/nino_pi/config", glob("config/*.yaml")),
        ("share/nino_pi/scripts", glob("scripts/*.sh")),
    ],
    install_requires=["setuptools"], zip_safe=True,
    maintainer="Nino Robot Maintainer", maintainer_email="maintainer@example.com",
    description="Navigation and teleoperation above an existing physical robot driver.",
    license="Apache-2.0",
    entry_points={"console_scripts": ["command_gate = nino_pi.command_gate:main",
                                      "keyboard_teleop = nino_pi.keyboard:main"]},
)
