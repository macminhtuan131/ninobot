# Raspberry Pi 5 navigation and teleop bundle

Download `nino_pi5_navigation_teleop_2026-10-14.zip` and extract its `nino_pi/`
directory under `~/nino_pi_ws/src/` on the Pi. Follow `nino_pi/README.md`.

Target: 64-bit Ubuntu 24.04 with ROS 2 Jazzy. Includes Nav2 navigation,
SLAM mapping, keyboard and joystick teleop, command selection and a read-only
driver check. No Gazebo, CUDA, RL checkpoint or hardware CAN/sensor driver.

Validated on the development laptop: 10 unit tests; build and launch arguments;
isolated synthetic velocity pipeline; ten navigation lifecycle nodes active;
interactive terminal command expiry. No Pi or physical robot validation yet.
