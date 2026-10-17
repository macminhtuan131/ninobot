# Simulation and hardware reference

Use [the root README](../README.md) for installation and RL training.

## Verify ros2_control

With the simulation running:

```bash
ros2 control list_controllers
ros2 control list_hardware_interfaces
ros2 topic hz /joint_states
```

The expected active controllers are `joint_state_broadcaster` and
`wheel_effort_controller`. The claimed command interfaces are:

```text
left_wheel_joint/effort
right_wheel_joint/effort
```

The controller's input is a `std_msgs/msg/Float64MultiArray` ordered as
`[left_wheel_joint, right_wheel_joint]`.

## View IMU, encoder, and lidar data

The simulated sensors use standard ROS 2 messages and Linorobot2 topic names:

| Sensor | Topic | Type | Frame/rate |
|---|---|---|---|
| IMU | `/imu/data` | `sensor_msgs/msg/Imu` | `imu_link`, 50 Hz |
| Wheel encoders | `/joint_states` | `sensor_msgs/msg/JointState` | left/right joints, 500 Hz |
| 2D lidar | `/scan` | `sensor_msgs/msg/LaserScan` | `laser`, 10 Hz |

View each complete message:

```bash
ros2 topic echo /imu/data
ros2 topic echo /joint_states
ros2 topic echo /scan
```

Or view all three as a compact live summary:

```bash
ros2 run nino_control sensor_monitor --ros-args -p use_sim_time:=true
```

Check that data is flowing at the expected rates:

```bash
ros2 topic hz /imu/data
ros2 topic hz /joint_states
ros2 topic hz /scan
```

Plot the IMU angular velocity in real time:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run rqt_plot rqt_plot -e \
  /imu/data/angular_velocity/x:y:z
```

`QLayout::removeWidget: Cannot remove a null widget` is a harmless startup
warning from `rqt_plot` 1.4.5 on Jazzy. If the plot window opens, it can be
ignored. If no curves appear, first verify the sensor with
`ros2 topic echo /imu/data --once` and `ros2 topic hz /imu/data`.

To capture an exact 30-second interval, run:

```bash
timeout --signal=INT 30s ros2 bag record -o imu_30s /imu/data
```

In `/joint_states`, `position` is the encoder angle in radians and `velocity`
is radians per second. Match values to `left_wheel_joint` and
`right_wheel_joint` using the same array index in `name`, `position`, and
`velocity`.

## Drive with `/cmd_vel`

The default `effort_drive` node converts desired base velocity into wheel-speed
targets, closes a PI loop using measured `/joint_states`, and sends bounded
torque to `JointGroupEffortController`.

Keyboard control:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/cmd_vel
```

Constant forward command:

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.3}, angular: {z: 0.0}}"
```

The `/cmd_vel` watchdog applies zero target velocity after 0.5 seconds without
a new command.

## Control wheel torque directly

The safe direct-torque input is `/wheel_torque_commands`. Values are N·m in
left/right order, are clamped to the configured limit, and expire after 0.25 s.

Apply `0.8 N·m` to both wheels:

```bash
ros2 topic pub --rate 20 /wheel_torque_commands \
  std_msgs/msg/Float64MultiArray "{data: [0.8, 0.8]}"
```

The two entries are independent. For example, apply `0.8 N·m` to the left
wheel and `0.4 N·m` to the right wheel:

```bash
ros2 topic pub --rate 20 /wheel_torque_commands \
  std_msgs/msg/Float64MultiArray "{data: [0.8, 0.4]}"
```

Use a negative value to reverse a wheel. The order is always
`[left_wheel_joint, right_wheel_joint]`.

Stop the publisher with `Ctrl-C`. The timeout returns both commands to zero.
Monitor the torque actually sent by the adapter:

```bash
ros2 topic echo /wheel_torque_applied
```

This topic reports the safe applied command, which can be lower than the
requested torque while the torque ramp or wheel-speed guard is active.

To inspect `JointGroupEffortController` without the safety adapter, launch with:

```bash
ros2 launch nino_description sim.launch.py start_effort_drive:=false
```

Then publish to the controller directly:

```bash
ros2 topic pub --rate 20 /wheel_effort_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.8, 0.8]}"
```

The raw interface bypasses the watchdog, torque ramp, and software speed guard;
use it only with the robot restrained or for a short controller check. It holds
its last received effort. Always send zero before stopping the raw publisher:

```bash
ros2 topic pub --once /wheel_effort_controller/commands \
  std_msgs/msg/Float64MultiArray "{data: [0.0, 0.0]}"
```

Limit the simulated wheel torque below the URDF maximum when launching:

```bash
ros2 launch nino_description sim.launch.py max_wheel_torque:=3.0
```

The hard URDF and ros2_control interface limit is `±12 N·m`. The default
`/cmd_vel` speed loop is separately limited to `±2 N·m`; direct torque mode can
use the full configured hardware limit. PI gains, acceleration limits, watchdog
times, and odometry settings are kept in
`src/nino_control/config/effort_drive.yaml`.

Direct effort is slew-limited to `10 N·m/s`. A `12 rad/s` software wheel-speed
guard removes torque that would accelerate an overspeed wheel, while allowing
opposite braking torque. The URDF's `24 rad/s` emergency limit remains enabled
as a final independent backstop.

## Nav2 and Linorobot2 compatibility

The training launch includes Nav2. The standalone description launch provides
the mobile-base interfaces below without launching Nav2:

- `/cmd_vel` — `geometry_msgs/msg/Twist`
- `/odom` — `nav_msgs/msg/Odometry`
- `odom -> base_footprint` TF
- `base_footprint -> base_link` and wheel TF from `robot_state_publisher`

Linorobot2's Jazzy EKF expects raw wheel odometry on `/odom/unfiltered` and
publishes filtered `/odom` plus the odometry TF. Use:

```bash
ros2 launch nino_description sim.launch.py linorobot2_mode:=true
```

In this mode Nino publishes `/odom/unfiltered` and does not publish
`odom -> base_footprint`, avoiding duplicate `/odom` publishers or TF sources
when Linorobot2's `ekf_filter_node` runs. The IMU and lidar remain available on
`/imu/data` and `/scan`. Use the `jazzy` branch of
[Linorobot2](https://github.com/linorobot/linorobot2/tree/jazzy), select its 2WD
base configuration, and keep its standard `cmd_vel`, `odom`,
`base_footprint`, `base_link`, `imu_link`, and `laser` names.

Start Nino in the Linorobot2-compatible mode:

```bash
ros2 launch nino_description sim.launch.py linorobot2_mode:=true rviz:=true sensor_monitor:=true
```

Then run Linorobot2's Jazzy EKF (from a terminal where Linorobot2 is built and
sourced):

```bash
ros2 run robot_localization ekf_node --ros-args \
  --params-file "$(ros2 pkg prefix --share linorobot2_base)/config/ekf.yaml" \
  -p use_sim_time:=true -r odometry/filtered:=/odom
```

Do not run Linorobot2's full Gazebo launch at the same time as Nino's simulation;
that launch creates another robot and another Gazebo instance. Run its EKF and
navigation/SLAM nodes against Nino's standard topics instead.

## Moving from Gazebo to Xiaomi CyberGear hardware

`gz_ros2_control/GazeboSimSystem` is simulation-only. On the physical robot,
replace that hardware plugin with a ros2_control `SystemInterface` that:

1. Converts `left_wheel_joint/effort` and `right_wheel_joint/effort` from N·m
   into CyberGear CAN torque commands.
2. Reports measured joint position, velocity, and effort in SI units.
3. Enforces the motor, gearbox, electrical, thermal, and emergency-stop limits
   for the actual installation.

The controller and high-level topic contract can remain unchanged, so
`/cmd_vel`, direct torque commands, odometry, Linorobot2, and later Nav2 do not
need to know whether the joint backend is Gazebo or CyberGear CAN hardware.

## Physics and collision model

These are **simulation parameters derived from CAD and configuration**, not
confirmed physical measurements. In particular, the chassis mass is configured
as `2.5 kg`, with scaled CAD moments and symmetric lateral properties; the
model does not retain every original CAD mass/inertia unchanged. Wheel
dimensions and effective separation are derived from the supplied exports.
The chassis and caster bracket use matching visual/collision mesh files and
frames. That alignment does not establish how the physics engine resolves
the open fork or whether contact agrees with the physical robot. Rolling
collisions use cylinders; their dimensions and contact behavior still need
hardware validation.

For the expanded robot used in the 16 October frozen governor screen, the
modeled mass is **`5.5905812626 kg`** and aggregate COM at zero joint angles in
`base_footprint` is approximately **`[0.081196, 0.0, 0.137831] m`**. The former
`4.6888672492 kg` entry was stale. This is a documentation correction, not a
mass or dynamics change. The configured LiDAR link alone contributes `1.3 kg`;
its physical mass has not been confirmed here.

The same nominal model has **9.03 mm minimum bracket-to-floor clearance** and
**32 mm caster diameter**. The recent single-obstacle screen uses a **22 mm
high rigid capsule ridge**. These values identify geometry to compare with
hardware; clearance alone is not the maximum traversable obstacle height.
See the [mechanical reference and measurement procedure](CASTER_MECHANICAL_REFERENCE_2026-10-16.md)
for provenance, limits and the two measurements still needed.

The older closed-hall world is 34 m long and 4 m wide. Its 29 cable bumps
vary from 16–44 mm diameter and −22° to +24°. Every angled cable length is
`4.0 / cos(angle)`, so it reaches both inner wall faces. A marked
`1.30 x 1.00 m` area centered on `(0,0,0)` remains cable-free for deterministic
spawning and resets; the nearest cable centers are at `x=-1.10 m` and
`x=0.90 m`.
This describes that world, not the factory-floor contact lab or the recent
single-obstacle frozen screen. Use the selected launch/config and captured
world when interpreting an experiment.
