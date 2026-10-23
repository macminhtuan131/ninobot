import time,sys
from pathlib import Path
import nino_rl.governor_logger as logger
from ros_gz_interfaces.msg import Contacts
old=logger.message_to_ordereddict
fired=False
def convert(message):
    global fired
    if isinstance(message,Contacts) and not fired:
        fired=True
        begin=time.monotonic_ns()
        old_interval=sys.getswitchinterval()
        try:
            sys.setswitchinterval(.5)
            until=time.monotonic()+.2
            while time.monotonic()<until:pass
        finally:sys.setswitchinterval(old_interval)
        Path('/home/tuanmac/ninorobot/docs/governor_acquisition_integration_2026-10-22/ros_fixture/injected_stall_ns.txt').write_text(str(time.monotonic_ns()-begin))
    return old(message)
logger.message_to_ordereddict=convert
logger.main()
