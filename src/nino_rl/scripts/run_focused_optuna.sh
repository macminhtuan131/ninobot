#!/usr/bin/env bash
# Separate studies. Usage: bash ... flat sim|prepare|tune|recover-eval [args]
set -e
course="${1:-}"
operation="${2:-}"
if [[ "$course" != flat ]] ||
   [[ "$operation" != sim && "$operation" != prepare && "$operation" != tune && "$operation" != recover-eval && "$operation" != check && "$operation" != continue ]]; then
  echo "Usage: bash $0 flat sim|prepare|tune|recover-eval|check|continue [extra arguments]" >&2
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
