"""Offline candidate: immutable marker receipt plus a fresh live heartbeat.

Not imported by any executor/logger. No ROS, simulation or file mutation.
The frozen v3 validator remains unchanged and continues to reject this run.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/nino_rl'))
from nino_rl.acquisition_contract import check_status,SENSOR_TOPICS


def check_delivery(session,live,receipt,role,marker,now_mono_ns):
    # An immutable ACK proves exact delivery at its own recorded instant.
    # It cannot stand in for the process's current heartbeat.
    check_status(session,receipt,role,marker=marker,
                 now_mono_ns=receipt['monotonic_ns'])
    for key in ('schema','session_id','protocol_sha256','role','source_sha256','pid','output'):
        if live.get(key)!=receipt.get(key):
            raise ValueError('Live/receipt identity mismatch: '+key)
    if live.get('error') or live.get('ready') is not True or live.get('closed') is not False:
        raise ValueError('Live process is not ready/open/error-free')
    age=(now_mono_ns-live['monotonic_ns'])*1e-9
    if not 0<=age<=session['max_status_age_s']:
        raise ValueError('Stale/future live heartbeat')
    if receipt['monotonic_ns']>live['monotonic_ns']:
        raise ValueError('Receipt newer than live evidence')
    if marker not in live.get('lifecycle',[]):
        raise ValueError('Live process does not acknowledge expected marker')
    for topic in SENSOR_TOPICS:
        if (not live['counts'].get(topic)
                or live['counts'][topic]<receipt['counts'][topic]
                or live['latest_source_ns'].get(topic) is None
                or live['latest_source_ns'][topic]<receipt['latest_source_ns'][topic]):
            raise ValueError('Live stream missing/regressed: '+topic)
    return True
