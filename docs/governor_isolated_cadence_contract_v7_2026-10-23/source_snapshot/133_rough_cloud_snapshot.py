"""Build an isolated sensor/launch profile without touching the flat robot."""
from pathlib import Path


def generate_sensor_files(root, experiment, config):
    sensor = config['rough_experiment_sensor']
    urdf = (root/'src/nino_description/urdf/nino.urdf.xacro').read_text()
    added = f'''
  <!-- Localization-only vertical channels; physical links/inertias unchanged. -->
  <gazebo reference="laser">
    <sensor name="rough_localization_lidar" type="gpu_lidar">
      <topic>rough_localization_scan</topic>
      <update_rate>{sensor['rate_hz']}</update_rate>
      <always_on>true</always_on><visualize>false</visualize>
      <lidar>
        <visibility_mask>4294967291</visibility_mask>
        <scan>
          <horizontal><samples>{sensor['horizontal_samples']}</samples><resolution>1</resolution>
            <min_angle>-${{pi}}</min_angle><max_angle>${{pi}}</max_angle></horizontal>
          <vertical><samples>{sensor['vertical_samples']}</samples><resolution>1</resolution>
            <min_angle>{sensor['vertical_min_rad']}</min_angle>
            <max_angle>{sensor['vertical_max_rad']}</max_angle></vertical>
        </scan>
        <range><min>0.08</min><max>{sensor['range_max_m']}</max><resolution>0.01</resolution></range>
        <noise><type>gaussian</type><mean>0</mean><stddev>{sensor['range_noise_stddev_m']}</stddev></noise>
      </lidar>
    </sensor>
  </gazebo>
'''
    if urdf.count('</robot>') != 1:
        raise RuntimeError('Robot XML end marker changed')
    result = {'rough_robot.urdf.xacro':urdf.replace('</robot>',added+'</robot>')}
    sim = (root/'src/nino_description/launch/sim.launch.py').read_text()
    original = 'xacro_file = PathJoinSubstitution([package_share, "urdf", "nino.urdf.xacro"])'
    if sim.count(original) != 1:
        raise RuntimeError('Robot launch template changed')
    result['sim.launch.py'] = sim.replace(original, f'xacro_file = {str(experiment/"rough_robot.urdf.xacro")!r}')
    training = (root/'src/nino_rl/launch/training_sim.launch.py').read_text()
    original = '''PathJoinSubstitution(
                [FindPackageShare("nino_description"), "launch", "sim.launch.py"]
            )'''
    if training.count(original) != 1:
        raise RuntimeError('Training launch template changed')
    result['training_sim.launch.py'] = training.replace(original, repr(str(experiment/'sim.launch.py')))
    return result


def install_cloud_subscription(interface):
    """Patch the isolated copied interface, never live package source."""
    text = interface.read_text()
    original = 'from sensor_msgs.msg import Imu, JointState, LaserScan'
    if text.count(original) != 1:
        raise RuntimeError('Sensor imports changed')
    text = text.replace(original, original+', PointCloud2\nfrom sensor_msgs_py.point_cloud2 import read_points_numpy')
    original = 'self.create_subscription(JointState, "/joint_states", self._joint_callback, SENSOR_QOS)'
    replacement = '''self.create_subscription(JointState, "/joint_states", self._joint_callback,
            QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100,
                       reliability=ReliabilityPolicy.BEST_EFFORT))'''
    if text.count(original) != 1:
        raise RuntimeError('Encoder subscription changed')
    text = text.replace(original,replacement)
    anchor = '        self._assisted_error = None'
    added = '''        if self._assisted_odometry and getattr(self._assisted_odometry, 'use_pointcloud', False):
            self.create_subscription(PointCloud2,
                odometry_assistance['corridor_lidar']['pointcloud_topic'],
                self._rough_cloud_callback, IMU_QOS)
'''
    text = text.replace(anchor, added+anchor, 1)
    anchor = '    def _scan_callback(self, message: LaserScan) -> None:'
    added = '''    def _rough_cloud_callback(self, message: PointCloud2) -> None:
        # Gazebo's GPU lidar packed XYZ is in the laser frame. IMU rotation
        # and calibrated sensor offset are applied in the estimator.
        points = read_points_numpy(message, field_names=('x', 'y', 'z'), skip_nans=True)
        with self._lock:
            self._update_assisted('pointcloud',
                message.header.stamp.sec + message.header.stamp.nanosec*1e-9,
                points.reshape(-1, 3))
            self._mark_received('rough_cloud')

'''
    if text.count(anchor) != 1:
        raise RuntimeError('Laser callback declaration changed')
    interface.write_text(text.replace(anchor,added+anchor))
