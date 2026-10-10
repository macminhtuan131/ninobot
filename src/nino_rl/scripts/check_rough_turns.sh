#!/usr/bin/env bash
# Diagnostic PI runs only; no Optuna/PPO training or old-study mutation.
set -e
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$project_dir"
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78 GZ_PARTITION=nino_rough_78
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
profile=src/nino_rl/config/rough_turn_pi_candidate.yaml
if [[ "${1:-check}" == sim ]]; then
  exec ros2 launch nino_rl training_sim.launch.py \
    world:="$project_dir/rl_runs/rough_terrain_bank_v1/worlds/original.sdf" \
    world_name:=combined_rough_section headless:=true pi_integrator_profile:=conditional_v1
elif [[ "${1:-check}" != check ]]; then
  echo "Usage: bash $0 [sim|check]" >&2
  exit 2
fi
python src/nino_rl/scripts/wait_for_drive_profile.py --config "$profile"
for route in E1 N1 S1; do
  case "$route" in
    E1) seeds=(10000 10003 10006);;
    N1) seeds=(10001 10004 10007);;
    S1) seeds=(10002 10005 10008);;
  esac
  ros2 run nino_rl evaluate_baseline --config "$profile" --route "$route" \
    --baseline-speed-scale 1.0 --seeds "${seeds[@]}" --control-trace \
    --output "rl_runs/rough_turn_pi_candidate_20261009/$route"
done
echo "PI traces saved. Rough tuning/training remains held pending physical-arrival and odometry review."
