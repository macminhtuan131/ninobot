import hashlib
import json
import os
from pathlib import Path

from .residual_factory_workflow import repo

CLOCK_CONTRACT = 'controller_manager_4_48_0_passed_ros_time_v1'
SOURCE_COMMIT = 'cdbc1127521074c2c5d19b4af2b73591e69d762b'
OVERLAY = repo()/'.sim_dependencies/recovery_clock'
PATCH = repo()/'src/nino_rl/runtime/controller_manager_4.48.0_sim_time.patch'
BUILDER = repo()/'src/nino_rl/scripts/build_recovery_clock_overlay.py'


def dependency_identity(root=OVERLAY):
    root = Path(root).resolve()
    manifest = root/'manifest.json'
    if not manifest.is_file():
        return dict(contract_id=CLOCK_CONTRACT, available=False)
    value = json.loads(manifest.read_text())
    if (set(value) != {'contract_id', 'library', 'sha256', 'source_commit', 'patch_sha256',
                       'package_version'} or value['contract_id'] != CLOCK_CONTRACT
            or value['source_commit'] != SOURCE_COMMIT
            or value['package_version'] != '4.48.0'):
        raise ValueError('Unsupported recovery simulation dependency manifest')
    for name, length in (('sha256',64), ('patch_sha256',64), ('source_commit',40)):
        if (type(value[name]) is not str or len(value[name]) != length
                or any(c not in '0123456789abcdef' for c in value[name])):
            raise ValueError('Invalid pinned simulation dependency digest')
    if value['patch_sha256'] != hashlib.sha256(PATCH.read_bytes()).hexdigest():
        raise ValueError('Recovery simulation patch recipe changed')
    library = (root/value['library']).resolve()
    if (not library.is_relative_to(root) or library.name != 'libcontroller_manager.so'
            or hashlib.sha256(library.read_bytes()).hexdigest() != value['sha256']):
        raise ValueError('Recovery controller-manager library missing or changed')
    return dict(value, available=True, resolved_library=str(library),
                build_recipe_sha256=hashlib.sha256(BUILDER.read_bytes()).hexdigest(),
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())


def configure_dependency(environment, expected):
    current = dependency_identity()
    if current.get('available') is not True or current != expected:
        raise ValueError('Build and pin recovery simulation clock dependency before live Gazebo')
    result = dict(environment)
    directory = str(Path(current['resolved_library']).parent)
    result['LD_LIBRARY_PATH'] = directory+os.pathsep+result.get('LD_LIBRARY_PATH','')
    return result


def verify_loaded_dependency(launch, expected, *, partition, proc_root=Path('/proc')):
    if expected != dependency_identity():
        raise ValueError('Recovery simulation dependency changed during launch')
    expected_path = Path(expected['resolved_library'])
    if type(partition) is not str or not partition:
        raise ValueError('Explicit owned Gazebo partition required')
    loaded = []
    parents = {}
    for process in proc_root.glob('[0-9]*'):
        try:
            fields = dict(line.split(':',1) for line in (process/'status').read_text().splitlines()
                          if ':' in line)
            parents[int(process.name)] = int(fields['PPid'])
        except (ProcessLookupError, FileNotFoundError):
            continue
    owned = {launch.pid}
    while True:
        children = {pid for pid,parent in parents.items() if parent in owned}
        expanded = owned | children
        if expanded == owned:
            break
        owned = expanded
    for pid in owned:
        process = proc_root/str(pid)
        try:
            for line in (process/'maps').read_text().splitlines():
                fields = line.split(maxsplit=5)
                if len(fields) == 6 and 'libcontroller_manager.so' in fields[5]:
                    environment = dict(item.split(b'=',1) for item in (process/'environ').read_bytes().split(b'\0')
                                       if b'=' in item)
                    if environment.get(b'GZ_PARTITION') != partition.encode():
                        raise ValueError('Controller-manager process has another Gazebo partition')
                    actual = Path(fields[5]).resolve()
                    if actual != expected_path:
                        raise ValueError('Owned simulator loaded an unpinned controller-manager library')
                    loaded.append(pid)
        except (ProcessLookupError, FileNotFoundError):
            continue
    if not loaded:
        raise ValueError('Pinned controller-manager library not found in owned simulator')
    return dict(contract_id=CLOCK_CONTRACT, library=str(expected_path),
                sha256=expected['sha256'], owned_processes=sorted(set(loaded)),
                ownership='launch_descendant_and_exact_gazebo_partition',
                actual_loaded_mapping_verified=True)
