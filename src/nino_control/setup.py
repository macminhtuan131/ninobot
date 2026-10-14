from glob import glob
import os

from setuptools import find_packages, setup


package_name = "nino_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Nino Robot Maintainer",
    maintainer_email="maintainer@example.com",
    description="Torque-controlled differential-drive adapter for Nino.",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "effort_drive = nino_control.effort_drive:main",
            "sensor_monitor = nino_control.sensor_monitor:main",
            "speed_governor = nino_control.speed_governor:main",
        ],
    },
)
