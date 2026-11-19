from copy import deepcopy
import math
import time

from .coverage_reset_readiness import assess_zero_reset
from .residual_workflow import save


def verify_reset_state(messages, *, now_s, declared_pose=None, after_s=None):
    return _verify_reset_observation(messages, now_s=now_s, declared_pose=declared_pose,
                                     after_s=after_s, twist_interval_continuous=True)


def _verify_reset_observation(messages, *, now_s, declared_pose=None, after_s=None,
                              twist_interval_continuous):
    def finite(value):
        return type(value) in (float, int) and math.isfinite(value)

    if not finite(now_s):
        raise ValueError('Invalid reset observation clock')
    for channel in ('truth', 'wheel', 'drive'):
        row = messages.get(channel, {})
        source = row.get('stamp_s')
        if not finite(source) or not -1e-8 <= now_s-source <= .04+1e-9:
            raise ValueError('Reset observation stale, future or missing: '+channel)
    truth = messages['truth']['values']
    wheel = messages['wheel']['values']
    pose = truth['pose']
    values = [*pose, *wheel, *(truth[k] for k in ('speed_norm', 'yaw_rate', 'roll', 'pitch'))]
    if (len(pose) != 4 or len(wheel) != 2 or not all(map(finite, values))
            or truth['speed_norm'] < 0):
        raise ValueError('Invalid reset physical observation')
    quiet = ((not twist_interval_continuous or
              (0 <= truth['speed_norm'] < .01 and abs(truth['yaw_rate']) < .05))
             and max(map(abs, wheel)) < .15
             and max(abs(truth['roll']), abs(truth['pitch'])) < .2)
    drive = messages['drive']
    check = assess_zero_reset(drive['values'], source_age_s=now_s-drive['stamp_s'],
                              physically_quiet=quiet)
    for key in ('requested_linear_m_s', 'requested_yaw_rad_s'):
        if not finite(drive['values'].get(key)) or drive['values'][key] != 0.:
            check['ready'] = False
            check['reasons'].append('zero_request_not_acknowledged:'+key)
    if not check['ready']:
        raise ValueError('Reset requires physical quiet and zero drive ACK: '+str(check['reasons']))
    result = dict(ready=True, truth_stamp_s=messages['truth']['stamp_s'],
                  observed_pose_m_rad=list(pose), settled_z_m=pose[2], readiness=check,
                  twist_quiet_verified=twist_interval_continuous,
                  observed_speed_norm_m_s=truth['speed_norm'],
                  observed_yaw_rate_rad_s=truth['yaw_rate'])
    if after_s is not None:
        if not finite(after_s):
            raise ValueError('Invalid reset phase boundary')
        for channel in ('truth', 'wheel', 'drive'):
            if not 0 < messages[channel]['stamp_s']-after_s <= .04+1e-9:
                raise ValueError('Reset application lacks fresh bounded truth/wheel/drive evidence: '+channel)
    if declared_pose is not None:
        if len(declared_pose) != 3 or not all(map(finite, declared_pose)):
            raise ValueError('Finite declared reset XY/yaw required')
        position_error = math.hypot(pose[0]-declared_pose[0], pose[1]-declared_pose[1])
        heading_error = abs(math.atan2(math.sin(pose[3]-declared_pose[2]),
                                      math.cos(pose[3]-declared_pose[2])))
        if position_error > .001 or heading_error > .001:
            raise ValueError('Observed reset pose differs from declared target')
        result.update(position_error_m=position_error, heading_error_rad=heading_error)
    return result


def _set_pose_once(backend, declared_pose, z_m):
    from ros_gz_interfaces.msg import Entity
    from ros_gz_interfaces.srv import SetEntityPose

    client = backend.node.create_client(SetEntityPose, '/world/factory_floor_lab/set_pose')
    try:
        if not client.wait_for_service(timeout_sec=5.):
            raise TimeoutError('Missing recovery physical reset service')
        request = SetEntityPose.Request()
        request.entity.name = 'nino'
        request.entity.type = Entity.MODEL
        request.pose.position.x, request.pose.position.y = map(float, declared_pose[:2])
        request.pose.position.z = float(z_m)
        request.pose.orientation.z = math.sin(declared_pose[2]/2)
        request.pose.orientation.w = math.cos(declared_pose[2]/2)
        future = client.call_async(request)
        deadline = time.monotonic()+5.
        while not future.done() and time.monotonic() < deadline:
            backend._check()
            time.sleep(.002)
        if not future.done():
            client.remove_pending_request(future)
            raise TimeoutError('Recovery physical reset ACK missing; no request retried')
        reply = future.result()
        if reply is None or reply.success is not True:
            raise RuntimeError('Recovery physical reset explicitly rejected')
    finally:
        backend.node.destroy_client(client)


def reanchor(backend, declared_pose):
    report = dict(contract_id='declared_physical_reset_challenge_plus_wheel_gyro_v2', valid=False,
                  declared_pose_m_rad=repr(declared_pose), command_requests=0,
                  command_accepted=False, physics_requests_retried=0, legs=[],
                  truth_role='physical_reset_and_quiet_verification_only',
                  truth_input_to_actor=False, initial_pose_source='declared_reset_command',
                  maximum_prefix_s=.04, application_steps_per_leg=20,
                  quiet_verification_steps_per_leg=20,
                  prefix_collection_steps=[20, 20], application_time_exact=False)
    try:
        if len(declared_pose) != 3 or not all(type(v) in (float, int) and math.isfinite(v)
                                              for v in declared_pose):
            raise ValueError('Finite declared reset XY/yaw required')
        report['declared_pose_m_rad'] = list(declared_pose)
        with backend.lock:
            if backend.request != (0., 0.):
                raise ValueError('Physical reset requires a zero requested reference')
            now = backend.time
            before = deepcopy(backend.messages)
        report['pre_reset'] = verify_reset_state(before, now_s=now)
        report['command_z_m'] = report['pre_reset']['settled_z_m']
        challenge = [declared_pose[0]+.020, declared_pose[1], declared_pose[2]]
        pre_pose = before['truth']['values']['pose']
        separation = math.hypot(pre_pose[0]-challenge[0], pre_pose[1]-challenge[1])
        if separation <= .010:
            raise ValueError('Reset challenge is not separated from the observed pre-reset pose')
        report['challenge_pre_pose_separation_m'] = separation
        for name, target in [('challenge', challenge), ('declared_return', list(declared_pose))]:
            with backend.lock:
                start = backend.time
                if backend.request != (0., 0.):
                    raise ValueError('Nonzero reference before physical reset leg')
            leg = dict(name=name, target_pose_m_rad=target, pre_command_time_s=start,
                       command_accepted=False)
            report['legs'].append(leg)
            report['command_requests'] += 1
            _set_pose_once(backend, target, report['command_z_m'])
            leg['command_accepted'] = True
            with backend.lock:
                if backend.request != (0., 0.) or abs(backend.clock-start) > 1e-8:
                    raise ValueError('Reset command window was not paused and zero')
            backend.step_world(20)
            backend._wait_feedback(backend.time)
            with backend.lock:
                if backend.request != (0., 0.):
                    raise ValueError('Nonzero reference during physical reset verification')
                now = backend.time
                after = deepcopy(backend.messages)
            if not math.isclose(now-start, .02, abs_tol=1e-8):
                raise ValueError('Reset application physics budget changed')
            application = _verify_reset_observation(after, now_s=now, declared_pose=target,
                after_s=start, twist_interval_continuous=False)
            leg.update(verification=application,
                       twist_interval_role='pose_change_interval_not_a_physical_quiet_measurement',
                       observed_application_interval_s=[start, application['truth_stamp_s']],
                       post_application_time_s=now)
            backend.step_world(20)
            backend._wait_feedback(backend.time)
            with backend.lock:
                if backend.request != (0., 0.):
                    raise ValueError('Nonzero reference during post-application quiet verification')
                now = backend.time
                continuous = deepcopy(backend.messages)
            if not math.isclose(now-leg['post_application_time_s'], .02, abs_tol=1e-8):
                raise ValueError('Reset quiet verification physics budget changed')
            quiet = verify_reset_state(continuous, now_s=now, declared_pose=target,
                                       after_s=leg['post_application_time_s'])
            leg.update(quiet_verification=quiet, quiet_verification_time_s=now)
        report['command_accepted'] = True
        report['post_reset'] = application
        report['post_reset_quiet'] = quiet
        epoch = application['truth_stamp_s']
        report.update(source_epoch_s=epoch,
                      post_application_time_s=report['legs'][-1]['post_application_time_s'],
                      prefix_collection_start_time_s=now,
                      observed_application_interval_s=report['legs'][-1]['observed_application_interval_s'],
                      timing_uncertainty='application interval retained; epoch is the verified final truth stamp')
        for _ in range(2):
            backend.step_world(20)
            backend._wait_feedback(backend.time)
            with backend.lock:
                if backend.request != (0., 0.):
                    raise ValueError('Nonzero reference during reset prefix collection')
                now = backend.time
                current = deepcopy(backend.messages)
            verify_reset_state(current, now_s=now)
        if not math.isclose(now-report['prefix_collection_start_time_s'], .04, abs_tol=1e-8):
            raise ValueError('Reset prefix collection physics budget changed')
        with backend.lock:
            rows = deepcopy(backend.raw)
        counts = {}
        for channel in ('wheel', 'imu'):
            stamps = [r['stamp_s'] for r in rows if r['channel'] == channel and epoch < r['stamp_s'] <= now]
            if (len(stamps) < 2 or stamps[0]-epoch > .04+1e-9 or now-stamps[-1] > .04+1e-9
                    or any(not 0 < b-a <= .04+1e-9 for a, b in zip(stamps, stamps[1:]))):
                raise ValueError('Reset prefix lacks continuous post-epoch support: '+channel)
            counts[channel] = len(stamps)
        report.update(valid=True, prefix_end_time_s=now, prefix_counts=counts,
                      post_collection=verify_reset_state(current, now_s=now))
        return report
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        save(backend.episode_dir/'reanchor.json', report)
