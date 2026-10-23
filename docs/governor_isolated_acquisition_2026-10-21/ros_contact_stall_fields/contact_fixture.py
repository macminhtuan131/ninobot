import json,sys,time
from pathlib import Path
import nino_rl.governor_logger as logger
from ros_gz_interfaces.msg import Contacts
original=logger.message_to_ordereddict
fired=False
def convert(msg):
    global fired
    if isinstance(msg,Contacts) and msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9>=100.2 and not fired:
        fired=True
        begin=time.monotonic_ns()
        previous=sys.getswitchinterval()
        try:
            sys.setswitchinterval(.5)
            until=time.monotonic()+.25
            while time.monotonic()<until:pass
        finally:sys.setswitchinterval(previous)
        Path('/home/tuanmac/ninorobot/docs/governor_isolated_acquisition_2026-10-21/ros_contact_stall_fields/injected_stall.json').write_text(json.dumps(dict(kind="synthetic_contact_conversion_busy_stall",
            begin_monotonic_ns=begin,end_monotonic_ns=time.monotonic_ns())))
    return original(msg)
logger.message_to_ordereddict=convert
logger.main()
