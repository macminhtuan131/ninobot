# Nino live state monitor on Pi 5 — 17/10/2026

Read-only terminal monitor for Ubuntu Server / ROS 2 Jazzy. Runs alongside
existing hardware drivers and your normal robot control session. It does not
start drivers, enable motors, publish commands, change parameters or call
robot services. No Gazebo, PyTorch or desktop required.

## 1. Copy and run

On the laptop (replace the Pi IP if it changed):

```bash
scp /home/tuanmac/ninorobot/src/nino_pi/nino_pi/state_monitor.py \
  d@192.168.0.127:~/state_monitor.py
ssh d@192.168.0.127
```

On Pi, in a separate terminal from the controller:

```bash
source /opt/ros/jazzy/setup.bash
if [ -f "$HOME/nino_pi_ws/install/setup.bash" ]; then
  source "$HOME/nino_pi_ws/install/setup.bash"
fi
# Also source your actual motor/sensor workspace if it is separate.
# Keep the same ROS_DOMAIN_ID / discovery configuration as those drivers.

/usr/bin/python3 "$HOME/state_monitor.py"
```

Stop with Ctrl+C. This stops the monitor, **not the robot controller**.
It is a passive observer of any motion already commanded by other nodes.
Without hardware/driver data, entries remain WAITING; this is not an
automatic diagnosis that drivers are not installed.

For a fixed 60-second session with recording:

```bash
/usr/bin/python3 "$HOME/state_monitor.py" \
  --duration 60 --display-hz 2 \
  --record "$HOME/nino_states/$(date +%Y%m%d_%H%M%S)"
```

Standalone script needs no colcon build. After building an updated `nino_pi`
package, the equivalent executable is `ros2 run nino_pi state_monitor`.

## 2. Default data shown

| Topic | Display |
|---|---|
| `/imu/data` | Acceleration XYZ m/s², gyro XYZ rad/s, RPY degrees if orientation is valid/available |
| `/joint_states` | Per-joint position rad, velocity rad/s, reported effort N·m for revolute joints; joint names retained |
| `/odom` | Estimated XYZ position and linear/angular velocity; not independent ground truth |
| `/cmd_vel` | Commanded linear/angular velocity, Twist or TwistStamped discovered from graph |
| `/nino_drive/diagnostics` | Nino named wheel target/actual velocities and PI/applied torque commands |
| `/wheel_torque_applied` | Actuator torque command array, producer-defined ordering |
| `/scan` | Finite returns and nearest valid range |
| `/battery_state` | Reported battery voltage, current, temperature, percentage fraction if available |

Every received source displays receive rate, last-receipt age, source-header
age if present, and warnings. WAITING means no sample observed; STALE means
the last value is retained and old, **not zero**. Default diagnostic stale
threshold is 0.5 s and can be changed with `--stale-seconds`.

Source-header age uses collector ROS clock; unsynchronized device clocks or
simulated timestamps can produce clock warnings. Unstamped messages only
have receipt age, not measurement age at the device. Receive rate uses a
bounded recent history (4096 receipts/source), not the display frequency.
Sources are asynchronous; this is not a synchronized robot state estimate.
Sensor acceleration is displayed as reported, possibly including gravity;
RPY is in the reported IMU orientation convention, not automatically base
axes, a verified world heading or calibrated mounting.

Changing topic names:

```bash
/usr/bin/python3 "$HOME/state_monitor.py" \
  --imu-topic /robot/imu/data \
  --joints-topic /robot/joint_states \
  --odom-topic /robot/odom \
  --drive-topic /robot/drive/diagnostics
```

Use `--help` for scan, command, torque-command and battery topic overrides.
Default roles require distinct topic names. Remapped custom message types
need the mapping described below rather than being silently decoded as a
standard message.

## 3. Torque, current and temperature: what is actually available?

**The monitor cannot manufacture motor feedback the driver does not publish.**

- `JointState.effort` is optional. Empty effort arrays show N/A. Default
  classification is `reported_unverified`; the driver may report a measured
  torque, an estimate or a command echo. Check firmware/unit/gear conversion.
- Nino's `left_pi_nm`, `right_pi_nm`, `left_applied_nm`, `right_applied_nm`
  are **controller commands**, not measured shaft torque. The historical
  name `/wheel_torque_applied` does not prove a sensor measured it.
- `executed_linear_m_s` in Nino drive diagnostics is a limited reference,
  not measured robot body velocity. Target/actual wheel values are separate.
- This monitor does not compute torque from current without a validated
  torque constant, gearing and driver convention; it does not compute
  absolute slip from IMU/encoder alone.
- BatteryState voltage does not measure the Pi's 5 V rail or prove that
  undervoltage was resolved. Use the separate hardware audit for hwmon/logs.

If the producer's semantics have been checked, `--effort-kind estimate`,
`--effort-kind measured` or `--effort-kind command` can label JointState
effort. This classification is supplied by you, not verified by the monitor.

### Connect driver-specific telemetry

Inspect the real interface first (read-only commands):

```bash
ros2 topic list -t
ros2 topic info /YOUR_MOTOR_FEEDBACK_TOPIC -v
ros2 interface show your_driver_msgs/msg/MotorState
```

Create JSON mappings for actual numeric fields. Example for a hypothetical
driver; these names are **not a claim about the installed Nino driver**:

```json
{
  "signals": [
    {"name": "left_current", "topic": "/motor/left/state", "type": "your_driver_msgs/msg/MotorState", "field": "current", "unit": "A", "kind": "reported_unverified"},
    {"name": "left_torque", "topic": "/motor/left/state", "type": "your_driver_msgs/msg/MotorState", "field": "torque", "unit": "Nm", "kind": "reported_unverified"},
    {"name": "left_temperature", "topic": "/motor/left/state", "type": "your_driver_msgs/msg/MotorState", "field": "temperature", "unit": "degC", "kind": "reported_unverified"}
  ]
}
```

Field paths support `motor.current` or `data[0]`; no Python expressions or
`eval`. Units are labels, not conversion factors. Missing/non-numeric values
remain N/A with a field error. Supported classifications: `reported_unverified`,
`measured`, `estimate`, `command`; classification always comes from config.
The message package must exist in the sourced driver workspace on Pi.

```bash
/usr/bin/python3 "$HOME/state_monitor.py" \
  --signals "$HOME/motor_telemetry.json" \
  --record "$HOME/nino_states/$(date +%Y%m%d_%H%M%S)"
```

`src/nino_pi/config/motor_telemetry.example.json` is another optional template
for separate scalar Float32 topics. Edit it to match real topics/types first.
It is not loaded by default.

## 4. Saved data

- `messages.jsonl`: full decoded subscribed ROS messages, message type,
  header timestamp if present, receipt ROS and monotonic timestamps. Keeps
  drive layout labels and full laser scan arrays. Logging is per callback,
  independent of display rate; no claim that every DDS sample was delivered.
- `config.json`: source hash, selected topics/mappings and options.
- `final_state.json`: latest values, source counts, timestamp diagnostics,
  errors and interruption status.
- `recording_status.json`: raw byte count, omitted-message count and limit
  status. Default raw limit 256 MiB (`--max-log-mb`); live display continues
  after the limit and prints a warning. No output folder is overwritten.

Raw NaN/inf values are explicit JSON markers, not zero or invalid JSON
numbers. Live summaries use N/A. These JSON logs are not rosbag, and missing
samples/recording limits must be considered before using them for evaluation.
For long/high-rate acquisition, use rosbag alongside the monitor and measure
load/dropouts on the Pi; this laptop test does not establish Pi throughput.

Machine-readable display snapshots:

```bash
/usr/bin/python3 "$HOME/state_monitor.py" --json --duration 60
```

Redirecting stdout alone records display snapshots only; use `--record` or
rosbag to retain native callback data. No motor topics or hardware safety
settings are changed. An observer process can still consume CPU/network/disk;
check actual sensor rates during a real session.

## 5. Verification scope

Tests cover missing effort, torque command classification, named diagnostic
schemas, stale data, clock issues, invalid values, numeric field mappings,
bounded logging and the absence of publisher/service calls. ROS integration
uses synthetic IMU/joint/drive/current telemetry in an isolated localhost
domain; no real motor commands or Gazebo. Pi ARM64/hardware and your real
driver's torque semantics still require verification.

The governor, PI, H2 protocol/scoring and unapproved simulation budget are
unchanged by this monitor.
