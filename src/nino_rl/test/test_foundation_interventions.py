import importlib.util
from pathlib import Path
import struct
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from prepare_rough_foundations import scaled_mesh, immutable
from run_crossing_authority import target_scale, scripted_scale


def test_binary_collision_and_visual_mesh_scaling(tmp_path):
    source=tmp_path/'source.stl'
    vertices=[0.,0.,0.,1.,0.,.2,0.,1.,-.1]
    source.write_bytes(b'original'.ljust(80,b'\0')+struct.pack('<I',1)+
                      struct.pack('<12fH',0.,0.,1.,*vertices,0))
    original=source.read_bytes()
    result,stats=scaled_mesh(source,.5)
    assert source.read_bytes()==original
    data=struct.unpack_from('<12fH',result,84)
    assert data[3:12]==pytest.approx([0.,0.,0.,1.,0.,.1,0.,1.,-.05])
    assert np.linalg.norm(data[:3])==pytest.approx(1.)
    assert stats['triangles']==1


def test_immutable_inputs_cannot_be_silently_replaced(tmp_path):
    path=tmp_path/'contract.json'
    immutable(path,'original')
    with pytest.raises(ValueError):immutable(path,'changed')
    assert path.read_text()=='original'


def test_anticipation_and_reference_ramp_use_estimated_pose(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('NINO_AUTHORITY_PROFILE','anticipatory')
    env=SimpleNamespace(ros=SimpleNamespace(snapshot=lambda:SimpleNamespace(x=1.9)))
    assert target_scale(1.9,'anticipatory')==.6
    assert target_scale(3.3,'anticipatory')==1.
    assert scripted_scale(env,1.)==pytest.approx(.96)
    assert scripted_scale(env,.60)==pytest.approx(.60)
    assert target_scale(0.,'constant')==.7
