#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from urllib.request import urlopen
import uuid
import xml.etree.ElementTree as ET

COMMIT = 'cdbc1127521074c2c5d19b4af2b73591e69d762b'
ARCHIVE_SHA256 = '943281e8223df8f53cfe9f459c5caf7cd00b026a706e5b76dd084411e3e6618d'


def main():
    parser = argparse.ArgumentParser(description='Build the pinned simulator-only controller clock overlay.')
    parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(root/'src/nino_rl'))
    from nino_rl.recovery_sim_runtime import CLOCK_CONTRACT, OVERLAY, dependency_identity
    if (OVERLAY/'manifest.json').exists():
        print(json.dumps(dependency_identity(),indent=2))
        return
    version = ET.parse('/opt/ros/jazzy/share/controller_manager/package.xml').getroot().findtext('version')
    if version != '4.48.0' or '/opt/ros/jazzy' not in os.environ.get('AMENT_PREFIX_PATH',''):
        raise RuntimeError('Source ROS Jazzy with controller_manager 4.48.0 before building this overlay')
    workspace = OVERLAY/'builds'/uuid.uuid4().hex
    workspace.mkdir(parents=True)
    archive = workspace/'ros2_control.tar.gz'
    with urlopen('https://codeload.github.com/ros-controls/ros2_control/tar.gz/'+COMMIT,timeout=60) as reply:
        archive.write_bytes(reply.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Pinned upstream source archive hash differs')
    destination = workspace/'src/controller_manager'
    with tarfile.open(archive) as source:
        prefix = 'ros2_control-'+COMMIT+'/controller_manager/'
        for member in source:
            if not member.name.startswith(prefix):
                continue
            relative = Path(member.name[len(prefix):])
            path = destination/relative
            if relative.is_absolute() or '..' in relative.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Unsupported upstream archive member')
            if member.isdir():
                path.mkdir(parents=True,exist_ok=True)
            else:
                path.parent.mkdir(parents=True,exist_ok=True)
                with source.extractfile(member) as stream:
                    path.write_bytes(stream.read())
                path.chmod(member.mode & 0o777)
    patch = root/'src/nino_rl/runtime/controller_manager_4.48.0_sim_time.patch'
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(patch)],cwd=workspace/'src',check=True)
    subprocess.run(['colcon','--log-base','log','build','--packages-select','controller_manager',
        '--cmake-args','-DBUILD_TESTING=OFF','-DCMAKE_BUILD_TYPE=Release'],cwd=workspace,
        env=dict(os.environ,CMAKE_BUILD_PARALLEL_LEVEL='4',MAKEFLAGS='-j4'),check=True)
    library = OVERLAY/'install/lib/libcontroller_manager.so'
    library.parent.mkdir(parents=True,exist_ok=True)
    if library.exists():
        raise ValueError('Unmanifested library already exists; preserve and inspect it before rebuilding')
    temporary = library.with_suffix('.so.pending')
    shutil.copyfile(workspace/'install/controller_manager/lib/libcontroller_manager.so',temporary)
    temporary.replace(library)
    manifest = dict(contract_id=CLOCK_CONTRACT,library=str(library.relative_to(OVERLAY)),
        sha256=hashlib.sha256(library.read_bytes()).hexdigest(),source_commit=COMMIT,
        patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest(),package_version=version)
    temporary = OVERLAY/'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest,indent=2)+'\n')
    temporary.replace(OVERLAY/'manifest.json')
    print(json.dumps(dependency_identity(),indent=2))


if __name__ == '__main__':
    main()
