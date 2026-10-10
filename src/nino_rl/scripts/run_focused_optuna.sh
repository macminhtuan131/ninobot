#!/usr/bin/env bash
# Separate studies. Usage: bash ... flat|rough sim|prepare|tune|recover-eval [args]
set -e
course="${1:-}"
operation="${2:-}"
if [[ "$course" != flat && "$course" != rough ]] ||
   [[ "$operation" != sim && "$operation" != prepare && "$operation" != tune && "$operation" != recover-eval && "$operation" != check && "$operation" != continue ]]; then
  echo "Usage: bash $0 flat|rough sim|prepare|tune|recover-eval|check|continue [extra arguments]" >&2
  exit 2
fi
shift 2
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$project_dir"
source /opt/ros/jazzy/setup.bash
source .venv/bin/activate
source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
if [[ "$course" == flat ]]; then
  export ROS_DOMAIN_ID=79 NINO_ROS_DOMAIN_ID=79 GZ_PARTITION=nino_flat_79
  profile=src/nino_rl/config/combined_flat_pi_tracking.yaml
  world=src/nino_description/worlds/combined_flat_section.sdf
  model=rl_runs/flat_feedback_pilot/20261008-035120-161159/nino_ppo_final.zip
  evaluation=(--eval-episodes 24 --eval-seed 61000
    --pi-reference rl_runs/flat_pi_tracking_slow_complete/20261008-validation/summary.json
    --pi-reference rl_runs/flat_pi_tracking_normal_targeted/20261008-110002-871004/summary.json)
  if [[ "$operation" == sim ]]; then
    exec ros2 launch nino_rl combined_flat_section_training.launch.py \
      headless:=true pi_integrator_profile:=conditional_v1 "$@"
  fi
else
  export ROS_DOMAIN_ID=78 NINO_ROS_DOMAIN_ID=78 GZ_PARTITION=nino_rough_78
  profile=src/nino_rl/config/rough_e1_n1_s1_fixed.yaml
  world=rl_runs/rough_terrain_bank_v1/worlds/original.sdf
  model=rl_runs/rough_e1_imu_assisted_pilot/20261008-013943-771247/nino_ppo_final.zip
  evaluation=(--eval-episodes 12 --eval-seed 10000
    --pi-reference rl_runs/rough_e1_n1_s1_route_pi/20261008-104043-455255/summary.json)
  if [[ "$operation" == sim ]]; then
    exec ros2 launch nino_rl training_sim.launch.py \
      world:="$project_dir/$world" world_name:=combined_rough_section \
      headless:=true pi_integrator_profile:=legacy "$@"
  fi
fi
if [[ "$operation" == check ]]; then
  exec python src/nino_rl/scripts/wait_for_drive_profile.py --config "$profile" "$@"
fi
if [[ "$operation" == continue ]]; then
  if [[ "$course" != flat ]]; then
    echo "Rough tuning is held; validate the turning PI/odometry candidate first." >&2
    exit 2
  fi
  exec python src/nino_rl/scripts/continue_flat_optuna.py "$@"
fi
if [[ "$operation" == recover-eval ]]; then
  exec python src/nino_rl/scripts/recover_optuna_evaluation.py --section "$course" "$@"
fi
preparation=()
if [[ "$operation" == prepare ]]; then
  preparation=(--prepare-study)
fi
exec python src/nino_rl/scripts/tune_split_optuna.py \
  --section "$course" --search-space focused --config "$profile" --world "$world" \
  --init-model "$model" --device cuda --trials 12 --timesteps 20000 \
  "${evaluation[@]}" --output "rl_runs/${course}_focused_optuna_v1" \
  "${preparation[@]}" "$@"
