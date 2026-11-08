"""Optional offline-cache CPU advisory. stdin/stdout JSON; never writes training artifacts."""
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
    try:
        monitor=Path(sys.argv[1]).resolve()
        spec=importlib.util.spec_from_file_location('nino_existing_laya_monitor',monitor)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        from laya import Router
        import torch
        torch.set_num_threads(1)
        router=Router(device='cpu',standalone_repos=True,max_loaded=1)
        for line in sys.stdin:
            payload=json.loads(line);summary=module.report(payload['rows'],20)
            advisory=module.classify(summary,router)
            print('@@NINO_LAYA@@'+json.dumps(dict(key=payload['key'],advisory=advisory,
                numeric_issue=summary['current']['most_common_failure_group'],
                monitor=str(monitor),source='Laya CPU; local cache only; uncalibrated for Nino')),flush=True)
    except Exception as exc:
        print('@@NINO_LAYA@@'+json.dumps(dict(error=type(exc).__name__+': '+str(exc))),flush=True)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
