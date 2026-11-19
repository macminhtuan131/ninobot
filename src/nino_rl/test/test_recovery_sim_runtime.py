import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nino_rl import recovery_sim_runtime as runtime


def overlay(tmp_path):
    library = tmp_path/'install/lib/libcontroller_manager.so'
    library.parent.mkdir(parents=True)
    library.write_bytes(b'fixture library identity, not executable')
    manifest = dict(contract_id=runtime.CLOCK_CONTRACT, library=str(library.relative_to(tmp_path)),
        sha256=hashlib.sha256(library.read_bytes()).hexdigest(), source_commit=runtime.SOURCE_COMMIT,
        patch_sha256=hashlib.sha256(runtime.PATCH.read_bytes()).hexdigest(), package_version='4.48.0')
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    return runtime.dependency_identity(tmp_path)


def test_missing_overlay_is_explicit_and_live_configuration_is_rejected(tmp_path, monkeypatch):
    assert runtime.dependency_identity(tmp_path)['available'] is False
    monkeypatch.setattr(runtime,'dependency_identity',lambda:dict(available=False))
    with pytest.raises(ValueError,match='Build and pin'):
        runtime.configure_dependency({},dict(available=False))


def test_binary_hash_and_manifest_path_are_verified(tmp_path):
    identity = overlay(tmp_path)
    Path(identity['resolved_library']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        runtime.dependency_identity(tmp_path)
    manifest = json.loads((tmp_path/'manifest.json').read_text())
    manifest['library'] = '../libcontroller_manager.so'
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        runtime.dependency_identity(tmp_path)


def test_only_pinned_dependency_enters_launch_environment(tmp_path, monkeypatch):
    identity = overlay(tmp_path)
    monkeypatch.setattr(runtime,'dependency_identity',lambda:identity)
    original = dict(LD_LIBRARY_PATH='/opt/ros/jazzy/lib')
    result = runtime.configure_dependency(original,identity)
    assert result['LD_LIBRARY_PATH'].startswith(str(Path(identity['resolved_library']).parent)+':')
    assert original['LD_LIBRARY_PATH'] == '/opt/ros/jazzy/lib'
    with pytest.raises(ValueError,match='Build and pin'):
        runtime.configure_dependency(original,dict(identity,sha256='c'*64))


def test_owned_process_must_map_exact_pinned_library(tmp_path, monkeypatch):
    identity = overlay(tmp_path/'overlay')
    monkeypatch.setattr(runtime,'dependency_identity',lambda:identity)
    proc = tmp_path/'proc'
    for pid,parent in ((100,1),(84,100),(42,84),(999,1)):
        (proc/str(pid)).mkdir(parents=True)
        (proc/str(pid)/'status').write_text('PPid:\t'+str(parent)+'\n')
        (proc/str(pid)/'maps').write_text('')
        (proc/str(pid)/'environ').write_bytes(b'GZ_PARTITION=owned-partition\0')
    (proc/'999/maps').write_text('1000-2000 r--p 00000000 00:01 9 /opt/ros/jazzy/lib/libcontroller_manager.so\n')
    maps = proc/'42/maps'
    maps.write_text('1000-2000 r--p 00000000 00:01 9 '+identity['resolved_library']+'\n')
    loaded = runtime.verify_loaded_dependency(SimpleNamespace(pid=100),identity,
        partition='owned-partition',proc_root=proc)
    assert loaded['actual_loaded_mapping_verified'] is True
    assert loaded['owned_processes'] == [42]
    (proc/'42/environ').write_bytes(b'GZ_PARTITION=other\0')
    with pytest.raises(ValueError,match='another Gazebo partition'):
        runtime.verify_loaded_dependency(SimpleNamespace(pid=100),identity,
            partition='owned-partition',proc_root=proc)
    (proc/'42/environ').write_bytes(b'GZ_PARTITION=owned-partition\0')
    maps.write_text('1000-2000 r--p 00000000 00:01 9 /opt/ros/jazzy/lib/libcontroller_manager.so\n')
    with pytest.raises(ValueError,match='unpinned'):
        runtime.verify_loaded_dependency(SimpleNamespace(pid=100),identity,
            partition='owned-partition',proc_root=proc)
    maps.write_text('')
    with pytest.raises(ValueError,match='not found'):
        runtime.verify_loaded_dependency(SimpleNamespace(pid=100),identity,
            partition='owned-partition',proc_root=proc)
