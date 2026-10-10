"""Known-wall observability and failure handling, independent of ROS/Gazebo."""
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src/nino_rl'))
from nino_rl.core import load_config

spec = importlib.util.spec_from_file_location('rough_wall', ROOT/'src/nino_rl/scripts/rough_wall_odometry.py')
rough = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rough)
CFG = load_config(ROOT/'src/nino_rl/config/rough_turn_lidar_candidate.yaml')['odometry_assistance']


def synthetic_scan(x=0., y=0., yaw=0., roll=0., pitch=0.):
    a = np.linspace(-np.pi, np.pi, 360)
    cr,sr,cp,sp,cy,sy = np.cos(roll),np.sin(roll),np.cos(pitch),np.sin(pitch),np.cos(yaw),np.sin(yaw)
    rot = np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                    [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
    dirs = np.c_[np.cos(a),np.sin(a),np.zeros(360)] @ rot.T
    origin = np.array([x,y,0.]) + rot @ np.array([.2,0.,.2275])
    hits=[]
    with np.errstate(divide='ignore',invalid='ignore'):
        for bound,axis in [(-2,0),(12,0),(-7.2,1),(7.2,1),(0,2),(3,2)]:
            t=(bound-origin[axis])/dirs[:,axis]
            hits.append(np.where(t>0,t,np.inf))
    ranges=np.min(hits,axis=0)
    ranges[ranges>=12]=np.inf
    return ranges,-np.pi,2*np.pi/359,.08,12.


def test_tilted_scan_observes_xy_with_floor_and_ceiling_returns():
    pose=(2.65,-.71,-1.315,.004,-.297)
    fix=rough.wall_position(synthetic_scan(*pose[:3],roll=pose[4],pitch=pose[3]),pose,CFG['corridor_lidar'])
    assert fix is not None
    assert np.linalg.norm(fix[0]-pose[:2])<1e-6
    assert min(fix[1])>=8


def test_missing_axis_and_large_tilt_are_rejected():
    scan=list(synthetic_scan())
    scan[0]=np.full(360,.4)
    assert rough.wall_position(scan,(0,0,0,0,0),CFG['corridor_lidar']) is None
    assert rough.wall_position(synthetic_scan(),(0,0,0,0,.7),CFG['corridor_lidar']) is None


def test_near_goal_keeps_front_wall_when_rear_wall_is_out_of_range():
    pose=(10.03,-.047,.014,.0001,0.)
    fix=rough.wall_position(synthetic_scan(*pose[:3],pitch=pose[3]),pose,CFG['corridor_lidar'])
    assert fix is not None
    assert np.linalg.norm(fix[0]-pose[:2])<1e-6


def feed(estimator,t,left,right,scan=None):
    estimator.add_imu(t,0.,0.,0.)
    estimator.add_joint(t,left,right)
    if scan is not None:estimator.add_scan(t,*scan)


def test_spinning_wheels_do_not_create_stalled_translation():
    estimator=rough.CorridorOdometry(CFG)
    for i in range(101):
        feed(estimator,i*.02,i*.04,i*.04,synthetic_scan() if i%5==0 else None)
    assert estimator.stalled
    assert abs(estimator.x)<1e-6
    assert abs(estimator.y)<1e-6
    assert abs(estimator.pose()['linear_velocity'])<1e-6


def test_translation_resumes_when_scan_measures_motion_and_stale_fix_fails():
    estimator=rough.CorridorOdometry(CFG)
    for i in range(31):
        feed(estimator,i*.02,i*.04,i*.04,synthetic_scan() if i%5==0 else None)
    assert estimator.stalled
    for i in range(31,81):
        x=(i-30)*.002
        feed(estimator,i*.02,i*.04,i*.04,synthetic_scan(x=x) if i%5==0 else None)
    assert not estimator.stalled
    assert abs(estimator.x-.1)<1e-6
    for i in range(81,116):feed(estimator,i*.02,i*.04,i*.04)
    with pytest.raises(RuntimeError,match='scan input is stale'):
        estimator.pose()


def test_fresh_scans_without_a_wall_fix_mark_terminal_localization_loss():
    estimator=rough.CorridorOdometry(CFG)
    feed(estimator,0.,0.,0.,synthetic_scan())
    blocked=list(synthetic_scan())
    blocked[0]=np.full(360,.4)
    for i in range(1,51):
        feed(estimator,i*.02,0.,0.,blocked if i%5==0 else None)
    state=estimator.pose()
    assert state['localization_valid'] is False
    assert state['odom_stamp_s']==1.
    assert estimator.latest_scan==1.


def test_epoch_reset_rejects_old_scans_and_requires_a_new_fix():
    estimator=rough.CorridorOdometry(CFG)
    feed(estimator,1.,0.,0.,synthetic_scan())
    assert estimator.ready
    estimator.reset(2.)
    feed(estimator,1.9,0.,0.,synthetic_scan())
    assert not estimator.ready
    feed(estimator,2.1,0.,0.,synthetic_scan())
    assert estimator.ready


def test_encoder_gap_after_episode_reset_is_still_fatal():
    estimator=rough.CorridorOdometry(CFG)
    estimator.reset(2.)
    feed(estimator,2.1,0.,0.,synthetic_scan())
    estimator.add_imu(2.6,0.,0.,0.)
    with pytest.raises(RuntimeError,match='encoder gap exceeded'):
        estimator.add_joint(2.6,1.,1.)


def test_initial_discovery_gap_is_discarded_not_integrated():
    estimator=rough.CorridorOdometry(CFG)
    feed(estimator,1.,0.,0.,synthetic_scan())
    estimator.add_imu(1.6,0.,0.,0.)
    estimator.add_joint(1.6,10.,10.)
    assert not estimator.ready
    assert estimator.x==0.
    assert estimator.startup_gap_restarts==1


def test_startup_gap_released_by_imu_is_also_discarded():
    estimator=rough.CorridorOdometry(CFG)
    feed(estimator,1.,0.,0.,synthetic_scan())
    estimator.add_joint(1.6,10.,10.)  # queued until IMU arrives
    estimator.add_imu(1.6,0.,0.,0.)
    assert not estimator.ready
    assert estimator.startup_gap_restarts==1
    assert estimator.x==0.


def test_scored_gap_released_by_imu_is_fatal():
    estimator=rough.CorridorOdometry(CFG)
    estimator.reset(2.)
    feed(estimator,2.1,0.,0.,synthetic_scan())
    estimator.add_joint(2.6,10.,10.)
    with pytest.raises(RuntimeError,match='encoder gap exceeded'):
        estimator.add_imu(2.6,0.,0.,0.)


def test_queued_encoder_history_aligns_to_delayed_imu_at_action_boundary():
    estimator=rough.CorridorOdometry(CFG)
    feed(estimator,0.,0.,0.,synthetic_scan())
    for i in range(1,51):estimator.add_joint(i*.002,i*.002,i*.002)
    for i in range(1,6):estimator.add_imu(i*.02,0.,0.,0.)
    assert estimator.stamp==pytest.approx(.1)
    assert estimator.x==pytest.approx(.1*CFG.get('wheel_radius_m',.0625))


def synthetic_cloud(pose, sensor):
    x,y,yaw,pitch,roll=pose
    h=np.linspace(-np.pi,np.pi,sensor['horizontal_samples'])
    v=np.linspace(sensor['vertical_min_rad'],sensor['vertical_max_rad'],sensor['vertical_samples'])
    hv,vv=np.meshgrid(h,v)
    dirs=np.c_[ (np.cos(vv)*np.cos(hv)).ravel(),
                (np.cos(vv)*np.sin(hv)).ravel(),np.sin(vv).ravel()]
    cr,sr,cp,sp,cy,sy=np.cos(roll),np.sin(roll),np.cos(pitch),np.sin(pitch),np.cos(yaw),np.sin(yaw)
    rot=np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                  [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
    world=dirs@rot.T
    origin=np.array([x,y,0.])+rot@np.array([.2,0.,.2275])
    hits=[]
    with np.errstate(divide='ignore',invalid='ignore'):
        for bound,axis in [(-2,0),(12,0),(-7.2,1),(7.2,1),(0,2),(3,2)]:
            t=(bound-origin[axis])/world[:,axis]
            hits.append(np.where(t>0,t,np.inf))
    ranges=np.min(hits,axis=0)
    valid=ranges<sensor['range_max_m']
    return dirs[valid]*ranges[valid,None]


@pytest.mark.parametrize('pose',[
    (8.1,0.,0.,.26,.03), (8.1,0.,0.,.35,0.),
    (8.1,0.,0.,.026,0.), (8.1,0.,.2,.35,.25),
    (2.65,-.71,-1.315,.004,-.297), (10.1,0.,0.,0.,0.),
])
def test_vertical_channels_keep_xy_when_2d_plane_points_at_floor_or_ceiling(pose):
    config=load_config(ROOT/'src/nino_rl/config/rough_turn_cloud_candidate.yaml')
    cloud=synthetic_cloud(pose,config['rough_experiment_sensor'])
    fix=rough.cloud_position(cloud,pose,config['odometry_assistance']['corridor_lidar'])
    assert fix is not None
    assert np.linalg.norm(fix[0]-pose[:2])<1e-6
    assert min(fix[1])>=8


def test_cloud_wheel_spin_and_missing_cloud_preserve_stall_and_freshness_guards():
    config=load_config(ROOT/'src/nino_rl/config/rough_turn_cloud_candidate.yaml')
    estimator=rough.CorridorOdometry(config['odometry_assistance'])
    cloud=synthetic_cloud((0.,0.,0.,0.,0.),config['rough_experiment_sensor'])
    for i in range(51):
        feed(estimator,i*.02,i*.04,i*.04)
        if i%5==0:estimator.add_pointcloud(i*.02,cloud)
    assert estimator.stalled
    assert abs(estimator.pose()['linear_velocity'])<1e-6
    assert abs(estimator.x)<1e-6
    # The policy's original scan cannot refresh missing localization data.
    for i in range(51,91):feed(estimator,i*.02,i*.04,i*.04,synthetic_scan())
    with pytest.raises(RuntimeError,match='scan input is stale'):estimator.pose()


def test_ceiling_only_cloud_cannot_manufacture_xy():
    config=load_config(ROOT/'src/nino_rl/config/rough_turn_cloud_candidate.yaml')
    cloud=np.c_[np.linspace(-10,10,100),np.zeros(100),np.full(100,3.)]
    assert rough.cloud_position(cloud,(8.1,0.,0.,0.,0.),
        config['odometry_assistance']['corridor_lidar']) is None


def test_noisy_stationary_fixes_do_not_mask_wheel_spin():
    config=load_config(ROOT/'src/nino_rl/config/rough_turn_cloud_candidate.yaml')
    estimator=rough.CorridorOdometry(config['odometry_assistance'])
    base=synthetic_cloud((0.,0.,0.,0.,0.),config['rough_experiment_sensor'])
    for i in range(201):
        feed(estimator,i*.02,i*.04,i*.04)
        if i%5==0:
            # Deliberately correlated +/- 3 mm error produces 0.06 m/s
            # adjacent-fix motion but <=0.017 m/s over the longer window.
            noise=.003*(-1 if i//5%2 else 1)
            estimator.add_pointcloud(i*.02,base+np.array([noise,noise,0.]))
    assert estimator.stalled
    assert abs(estimator.pose()['linear_velocity'])<.025
    assert np.hypot(estimator.x,estimator.y)<.01
