"""Explicit button starts reviewed sensor-only wrappers; never command owners.

Already occupied serial ports are reused and audited separately, never killed.
Only children started by this invocation are stopped on GUI cancellation.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

WRAPPERS = {
    'agent': ('nino_runtime/mounting_xyz_20261027_v1/run_agent.sh',
              '7d3812831d4eb5352459b6e1fb14d41d241c86592664b58c9f65e32bb810fe93'),
    'sensors': ('nino_runtime/sensor_observation_20261027_v1/run_observe_sensors.sh',
                '40859dc956d0030e0bf237f1649c29846f29289f11bf70df99c2522bd49fe529'),
    'lidar': ('nino_runtime/sensor_observation_20261027_v1/run_lidar_a1.sh',
              '1497e0224ac628e0243348aaa35709e821fc80ca307b5ce65df99fcf5edd4e30'),
}


def main():
    paths = [Path('/dev/ttyACM0'), Path('/dev/ttyUSB0')]
    if not all(p.exists() for p in paths):
        raise RuntimeError('Expected USB ports absent; inspect inventory, do not guess device mapping')
    used = []
    for path in paths:
        probe = subprocess.run(['fuser', str(path)], capture_output=True, text=True)
        if probe.returncode not in (0,1):raise RuntimeError('Cannot establish serial ownership: '+probe.stderr)
        used.append(probe.returncode == 0)
    if any(used):
        print('SENSORS: existing serial users retained; no duplicate agent or driver started. Run inventory.', flush=True)
        return 0
    wrappers={name:Path.home()/rel for name,(rel,_) in WRAPPERS.items()}
    for name,path in wrappers.items():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=WRAPPERS[name][1]:
            raise RuntimeError('Reviewed sensor wrapper absent/changed: '+str(path)+'; inspect read-only before starting')
    root=Path(__file__).resolve().parent/'sensor_jobs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True,exist_ok=False)
    children=[];interrupted=False
    def stop(signum,frame):raise KeyboardInterrupt
    old={sig:signal.signal(sig,stop) for sig in (signal.SIGINT,signal.SIGTERM)}
    try:
        for name,path in wrappers.items():
            with (root/(name+'.log')).open('x') as log:
                child=subprocess.Popen(['bash',str(path)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            children.append(child)
        time.sleep(1.)
        if any(c.poll() is not None for c in children):raise RuntimeError('Sensor wrapper exited; inspect '+str(root))
        print('SENSORS: reviewed sensor-only wrappers launched. No enable/velocity sent. Run inventory for actual data.',flush=True)
        while all(c.poll() is None for c in children):time.sleep(.2)
        raise RuntimeError('A sensor process exited; retain logs, no auto restart')
    except KeyboardInterrupt:
        interrupted=True
    finally:
        for c in children:
            if c.poll() is None:os.killpg(c.pid,signal.SIGINT)
        for c in children:
            try:c.wait(timeout=8)
            except subprocess.TimeoutExpired:os.killpg(c.pid,signal.SIGKILL);c.wait()
        for sig,handler in old.items():signal.signal(sig,handler)
        (root/'closure.json').write_text(json.dumps(dict(operator_cancel=interrupted,returncodes=[c.returncode for c in children]))+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
