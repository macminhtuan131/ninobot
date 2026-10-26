#!/usr/bin/env python3
"""Simulation-only first-contact intervention, using unchanged native scoring."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src/nino_rl"), str(ROOT / "src/nino_control")]

if __name__ == "__main__":
    from nino_rl.evaluation import run
    from nino_rl.research_contact_oracle import environment_factory
    run(baseline=True, env_factory=environment_factory, experiment_metadata=dict(
        kind="post_contact_oracle_h2", oracle_contact_input=True,
        sensor_trigger_suppressed=True, deployable=False,
        qualification="Simulation-only contact oracle; controlled cold starts, not identical snapshots or deployable governor"))
