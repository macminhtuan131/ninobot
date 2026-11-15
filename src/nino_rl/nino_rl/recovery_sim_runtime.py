import hashlib
import json
import os
from pathlib import Path

from .residual_factory_workflow import repo

CLOCK_CONTRACT = 'controller_manager_4_48_0_passed_ros_time_v1'
OVERLAY = repo()/'.sim_dependencies/recovery_clock'


def dependency_identity(root=OVERLAY):
    root = Path(root).resolve()
    manifest = root/'manifest.json'
    if not manifest.is_file():
        return dict(contract_id=CLOCK_CONTRACT, available=False)
    value = json.loads(manifest.read_text())
    if (set(value) != {'contract_id', 'library', 'sha256', 'source_commit', 'patch_sha256',
                       'package_version'} or value['contract_id'] != CLOCK_CONTRACT
            or value['package_version'] != '4.48.0'):
        raise ValueError('Unsupported recovery simulation dependency manifest')
    for name, length in (('sha256',64), ('patch_sha256',64), ('source_commit',40)):
        if (type(value[name]) is not str or len(value[name]) != length
                or any(c not in '0123456789abcdef' for c in value[name])):
            raise ValueError('Invalid pinned simulation dependency digest')
    library = (root/value['library']).resolve()
    if (not library.is_relative_to(root) or library.name != 'libcontroller_manager.so'
            or hashlib.sha256(library.read_bytes()).hexdigest() != value['sha256']):
        raise ValueError('Recovery controller-manager library missing or changed')
    return dict(value, available=True, resolved_library=str(library),
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())


def configure_dependency(environment, expected):
    current = dependency_identity()
    if current.get('available') is not True or current != expected:
        raise ValueError('Build and pin recovery simulation clock dependency before live Gazebo')
    result = dict(environment)
    directory = str(Path(current['resolved_library']).parent)
    result['LD_LIBRARY_PATH'] = directory+os.pathsep+result.get('LD_LIBRARY_PATH','')
    return result


def verify_loaded_dependency(launch, expected, *, proc_root=Path('/proc')):
    if expected != dependency_identity():
        raise ValueError('Recovery simulation dependency changed during launch')
    expected_path = Path(expected['resolved_library'])
    loaded = []
    group = os.getpgid(launch.pid)
    for process in proc_root.glob('[0-9]*'):
        try:
            if os.getpgid(int(process.name)) != group:
                continue
            for line in (process/'maps').read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) == 6 and 'libcontroller_manager.so' in fields[5]:
                    actual = Path(fields[5]).resolve()
                    if actual != expected_path:
                        raise ValueError('Owned simulator loaded an unpinned controller-manager library')
                    loaded.append(int(process.name))
        except (ProcessLookupError, FileNotFoundError):
            continue
    if not loaded:
        raise ValueError('Pinned controller-manager library not found in owned simulator')
    return dict(contract_id=CLOCK_CONTRACT, library=str(expected_path),
                sha256=expected['sha256'], owned_processes=sorted(set(loaded)),
                actual_loaded_mapping_verified=True)
