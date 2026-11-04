from concurrent.futures import Future
from pathlib import Path
import pytest
from nino_rl.factory_velocity_backend import FactoryVelocityBackend
from nino_rl.factory_velocity_backend import simulation_seconds
from nino_rl.residual_sim_pilot import config,repo


def test_read_only_retry_is_bounded_and_does_not_step_physics(tmp_path,monkeypatch):
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf');b.episode_dir=tmp_path
    b.step_world=lambda _:pytest.fail('Parameter readback must not step physics')
    monkeypatch.setattr('nino_rl.factory_velocity_backend.time.sleep',lambda _:None)
    clock=[0.]
    def now():clock[0]+=1.;return clock[0]
    monkeypatch.setattr('nino_rl.factory_velocity_backend.time.monotonic',now)
    class Response:values=[1]
    class Client:
        calls=0;removed=0
        def wait_for_service(self,timeout_sec):return True
        def call_async(self,request):
            self.calls+=1;f=Future()
            if self.calls==2:f.set_result(Response())
            return f
        def remove_pending_request(self,future):self.removed+=1
    client=Client();assert b._parameter_readback(client,['example'])==[1]
    assert client.calls==2 and client.removed==1
    assert len((tmp_path/'parameter_readback.jsonl').read_text().splitlines())==2


def test_nanosecond_canonicalization_does_not_relax_future_clock_gate(tmp_path):
    assert simulation_seconds(5.6)==simulation_seconds(5.6000000000000005)
    assert simulation_seconds(5.600000001)>simulation_seconds(5.6)
    b=FactoryVelocityBackend(config(),tmp_path,repo(),tmp_path/'world.sdf')
    now=5.6;b.time=now;b.start_time=0.
    b._store('imu',now,[0.,0.,0.,0.,0.,9.80665]);b._store('wheel',now,[0.,0.])
    fields=dict(executed_linear_m_s=0.,executed_yaw_rad_s=0.,have_wheel_state=1.,left_target_rad_s=0.,right_target_rad_s=0.)
    b._store('drive',5.6000000000000005,fields)
    assert b.view()['input_ages_s']['final']==0.
    b.assembler.reset();b._store('drive',5.600000001,fields)
    with pytest.raises(ValueError,match='future'):b.view()
