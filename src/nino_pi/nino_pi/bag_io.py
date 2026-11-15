"""Read original rosbag2 payloads without rewriting clocks or filling gaps."""
from pathlib import Path
import sqlite3
import yaml


def sqlite_readonly(path):
    """Read a finalized DB without creating SHM files or ignoring pending writes."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Linked SQLite storage is not accepted')
    for suffix in ('-wal', '-journal'):
        pending = path.with_name(path.name + suffix)
        if pending.exists() and (pending.is_symlink() or pending.stat().st_size):
            raise ValueError('Unfinalized SQLite sidecar: ' + pending.name)
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)


def metadata_topic_mismatches(meta, counts):
    """None means old metadata has no topic counts; it does not mean verified."""
    entries = meta.get('topics_with_message_count')
    if entries is None:
        return None
    expected = {}
    for entry in entries:
        name = entry['topic_metadata']['name']
        count = entry['message_count']
        if not isinstance(name, str) or name in expected or type(count) is not int or count < 0:
            raise ValueError('Invalid/duplicate metadata topic counts')
        expected[name] = count
    return {name: dict(metadata=expected.get(name, 0), recorded=counts.get(name, 0))
            for name in expected.keys() | counts.keys()
            if expected.get(name, 0) != counts.get(name, 0)}


def metadata(directory):
    root = Path(directory)
    value = yaml.safe_load((root/'metadata.yaml').read_text())['rosbag2_bagfile_information']
    paths = value['relative_file_paths']
    if not paths or any(not isinstance(p, str) or Path(p).name != p for p in paths):
        raise ValueError('Invalid bag storage paths')
    if value['storage_identifier'] not in ('sqlite3', 'mcap'):
        raise ValueError('Unsupported bag storage')
    for p in paths:
        if not (root/p).is_file() or (root/p).is_symlink():
            raise ValueError('Missing/linked storage file: '+p)
    return value


def records(directory):
    """Yield topic, ROS type, receipt nanoseconds, raw CDR. No resampling."""
    root = Path(directory)
    meta = metadata(root)
    if meta['storage_identifier'] == 'sqlite3':
        for name in meta['relative_file_paths']:
            with sqlite_readonly(root/name) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('SQLite integrity failed')
                for topic, typ, stamp, payload in db.execute(
                        'SELECT t.name,t.type,m.timestamp,m.data FROM messages m JOIN topics t ON m.topic_id=t.id ORDER BY m.id'):
                    yield topic, typ, stamp, payload
    else:
        import rosbag2_py
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(root), storage_id='mcap'),
                    rosbag2_py.ConverterOptions('', ''))
        types = {t.name: t.type for t in reader.get_all_topics_and_types()}
        while reader.has_next():
            topic, payload, stamp = reader.read_next()
            yield topic, types[topic], stamp, payload


def decoded(directory):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    types = {}
    for topic, typ, stamp, payload in records(directory):
        if typ not in types:
            types[typ] = get_message(typ)
        yield topic, typ, stamp, deserialize_message(payload, types[typ])


def source_header(message):
    header = getattr(message, 'header', None)
    if header is None:
        return None, None
    stamp = header.stamp.sec*10**9+header.stamp.nanosec
    return stamp, header.frame_id
