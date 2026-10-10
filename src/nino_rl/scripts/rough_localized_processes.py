"""Owned reliable IMU bridge for the isolated rough experiment only."""
from pathlib import Path
from train_rough_curriculum import Processes


class ReliableRoughProcesses(Processes):
    def launch(self, world, directory, gui):
        self.env['NINO_ROUGH_LOCALIZATION_LOG']=str(directory/'wall_observations.jsonl')
        self.env['NINO_ROUGH_RECOVERY_LOG']=str(directory/'recovery_events.jsonl')
        from run_rough_localized import EXPERIMENT, verify
        manifest = verify()
        if manifest['config']['rough_experiment'].get('localization_sensor') == 'vertical_cloud_v1':
            self.close()
            self.world = self.start(['ros2','launch',str(EXPERIMENT/'training_sim.launch.py'),
                f'world:={world}', 'world_name:=combined_rough_section',
                f'headless:={str(not gui).lower()}',
                f'pi_integrator_profile:={self.pi_integrator_profile}'], directory/'gazebo.log')
            self.run(['ros2','run','nino_rl','wait_for_sim'],directory/'readiness.log',timeout=90)
        else:
            super().launch(world,directory,gui)
        self.start(['ros2','run','ros_gz_bridge','parameter_bridge','--ros-args',
            '-r','__node:=rough_reliable_imu_bridge','-p',f'config_file:={EXPERIMENT / "imu_bridge.yaml"}'],
            directory/'imu_bridge.log')
        self.run(['ros2','topic','echo','/rough/imu/data','sensor_msgs/msg/Imu','--once','--qos-reliability','reliable',
                  '--field','header.stamp'],directory/'imu_readiness.log',timeout=30)
        if manifest['config']['rough_experiment'].get('localization_sensor') == 'vertical_cloud_v1':
            self.run(['ros2','topic','echo','/rough/localization/points','sensor_msgs/msg/PointCloud2',
                '--once','--qos-reliability','reliable','--field','header'],
                directory/'cloud_readiness.log',timeout=30)
