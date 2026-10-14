import pytest
from nino_pi.map_validation import validate_map


def test_real_map_relative_image_and_missing_file(tmp_path):
    path = tmp_path/"map.yaml"
    path.write_text('image: floor.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\n')
    with pytest.raises(ValueError,match="image does not exist"):
        validate_map(path)
    (tmp_path/"floor.pgm").write_bytes(b'P5\n1 1\n255\n\xff')
    assert validate_map(path) == str(path.resolve())


def test_world_and_absent_map_rejected(tmp_path):
    with pytest.raises(ValueError,match="does not exist"):
        validate_map(tmp_path/"absent.yaml")
    world = tmp_path/"factory.sdf"
    world.write_text('<sdf version="1.9"><world name="factory"/></sdf>')
    with pytest.raises(ValueError,match="occupancy-map"):
        validate_map(world)
