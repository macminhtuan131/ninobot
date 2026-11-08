from glob import glob
import os

from setuptools import find_packages, setup


package_name = "nino_rl"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        (
            "share/" + package_name,
            ["package.xml", "requirements.txt", "README.md", "README_VI.md", "ALGORITHM_V2.md",
             "REWARD_POLICY_UPDATE.md", "RL_IMPROVEMENTS.md"],
        ),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "config"), glob("config/*.json")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "scripts"), glob("scripts/residual_*.sh") + glob("scripts/common_training_studio.sh")),
        (os.path.join("share", package_name, "models", "completed_train"),
         glob("models/completed_train/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Nino Robot Maintainer",
    maintainer_email="maintainer@example.com",
    description="Nino historical RL experiments and offline bounded velocity residual research contract.",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "check_cuda = nino_rl.check_cuda:main",
            "evaluate = nino_rl.evaluate:main",
            "evaluate_baseline = nino_rl.evaluate_baseline:main",
            "governor_logger = nino_rl.governor_logger:main",
            "trajectory_metrics = nino_rl.trajectory_metrics:main",
            "compare_evaluations = nino_rl.evaluation:compare_main",
            "policy_node = nino_rl.policy_node:main",
            "preflight = nino_rl.preflight:main",
            "train = nino_rl.train:main",
            "prepare_residual = nino_rl.residual_experiment:prepare_main",
            "td3_parameters = nino_rl.td3_config:main",
            "residual_workflow = nino_rl.residual_workflow:main",
            "wait_for_sim = nino_rl.wait_for_sim:main",
            "sim_gain_effort_drive = nino_rl.gain_effort_drive:main",
            "sim_pi_screen_effort_drive = nino_rl.pi_screen_effort_drive:main",
        ],
    },
)
