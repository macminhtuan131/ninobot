"""Checked append-only ROS payload capture. No ROS, interpolation or scoring code."""
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid
import zlib

TOPICS={1:"/joint_states",2:"/ground_truth/odom",3:"/nino/governor/episode"}
HEADER=struct.Struct("<4sIBQqqqI")
CRC=struct.Struct("<I")
MAX_PAYLOAD=16*1024*1024


def atomic_json(path,data):
    temp=path.with_suffix(path.suffix+".tmp")
    with temp.open("w") as stream:
        json.dump(data,stream,indent=2,allow_nan=False);stream.write("\n")
        stream.flush();os.fsync(stream.fileno())
    temp.replace(path)


class FrameWriter:
    def __init__(self,directory,*,maximum_bytes=512*1024*1024,metadata=None):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=False)
        self.stream=(self.directory/"joint_gt.frames").open("xb",buffering=1024*1024)
        self.maximum_bytes=maximum_bytes
        self.sequence=0;self.bytes=0;self.counts={};self.error=None;self.closed=False
        self.digest=hashlib.sha256()
        self.metadata=dict(schema="isolated_joint_gt_frames_v1",capture_id=str(uuid.uuid4()),
            complete=False,maximum_bytes=maximum_bytes,topic_ids=TOPICS,**(metadata or {}))
        self._manifest(False)

    def _manifest(self,complete):
        result=dict(self.metadata,complete=complete,frames=self.sequence,bytes=self.bytes,
                    counts=self.counts,sha256=self.digest.hexdigest(),error=self.error)
        atomic_json(self.directory/"capture_manifest.json",result)
        return result

    def append(self,topic,payload,source_ns,receipt_sim_ns,receipt_mono_ns,epoch):
        if self.closed or self.error:
            raise RuntimeError("Capture is closed or failed; no retry/overwrite")
        try:
            if topic not in TOPICS or not 0<=len(payload)<=MAX_PAYLOAD:
                raise ValueError("Unknown topic or excessive frame length")
            header=HEADER.pack(b"NJC1",len(payload),topic,self.sequence+1,
                source_ns,receipt_sim_ns,receipt_mono_ns,epoch)
            packet=header+payload
            packet+=CRC.pack(zlib.crc32(packet))
            if self.bytes+len(packet)>self.maximum_bytes:
                raise OverflowError("Capture byte budget exhausted; no eviction")
            if self.stream.write(packet)!=len(packet):
                raise OSError("Short capture write")
            self.digest.update(packet);self.bytes+=len(packet);self.sequence+=1
            self.counts[TOPICS[topic]]=self.counts.get(TOPICS[topic],0)+1
        except BaseException as error:
            self.error=f"{type(error).__name__}: {error}"
            raise

    def close(self,*,complete=True):
        if self.closed:
            return json.loads((self.directory/"capture_manifest.json").read_text())
        try:
            self.stream.flush();os.fsync(self.stream.fileno())
        except BaseException as error:
            self.error=self.error or f"{type(error).__name__}: {error}"
        finally:
            try:self.stream.close()
            except BaseException as error:self.error=self.error or f"{type(error).__name__}: {error}"
            self.closed=True
        return self._manifest(bool(complete and not self.error))


def read_frames(directory):
    directory=Path(directory)
    meta=json.loads((directory/"capture_manifest.json").read_text())
    if meta.get("schema")!="isolated_joint_gt_frames_v1" or not meta.get("complete") or meta.get("error"):
        raise ValueError("Incomplete/failed capture")
    digest=hashlib.sha256();sequence=0;size=0;counts={}
    with (directory/"joint_gt.frames").open("rb") as stream:
        while True:
            header=stream.read(HEADER.size)
            if not header:break
            if len(header)!=HEADER.size:raise ValueError("Truncated frame header")
            magic,length,topic,number,stamp,receipt,mono,epoch=HEADER.unpack(header)
            if magic!=b"NJC1" or topic not in TOPICS or length>MAX_PAYLOAD or number!=sequence+1:
                raise ValueError("Invalid header/topic/sequence")
            payload=stream.read(length);tail=stream.read(CRC.size)
            if len(payload)!=length or len(tail)!=CRC.size:raise ValueError("Truncated frame")
            packet=header+payload
            if zlib.crc32(packet)!=CRC.unpack(tail)[0]:raise ValueError("Frame checksum mismatch")
            digest.update(packet+tail);size+=len(packet)+len(tail);sequence=number
            counts[TOPICS[topic]]=counts.get(TOPICS[topic],0)+1
            yield dict(sequence=number,topic=TOPICS[topic],source_ns=stamp,
                receipt_sim_ns=receipt,receipt_monotonic_ns=mono,epoch=epoch,payload=payload)
    if sequence!=meta["frames"] or size!=meta["bytes"] or digest.hexdigest()!=meta["sha256"] or counts!=meta["counts"]:
        raise ValueError("Capture manifest/hash/count mismatch")


def validate_episode(frames,markers,run_id,attempt,start_ns,end_ns):
    """Never admit rows from an earlier epoch, even if source clock was reused."""
    selected=[m for m in markers if m.get("run_id")==run_id and m.get("attempt")==attempt]
    resets=[m for m in selected if m.get("event")=="reset"]
    ends=[m for m in selected if m.get("event")=="end"]
    if len(resets)!=1 or len(ends)!=1 or not start_ns<end_ns:
        raise ValueError("Missing/ambiguous lifecycle or window")
    reset,end=resets[0],ends[0]
    if reset["sequence"]>=end["sequence"] or reset["epoch"]!=end["epoch"] or reset["source_ns"]>start_ns or end["source_ns"]<end_ns:
        raise ValueError("Lifecycle does not cover requested episode")
    count={name:0 for name in (TOPICS[1],TOPICS[2])};previous={}
    for f in frames:
        if f["topic"] not in count:continue
        if start_ns<=f["source_ns"]<=end_ns:
            if f["epoch"]!=reset["epoch"] or f["sequence"]<=reset["sequence"]:
                raise ValueError("Pre-reset/late-marker or wrong-epoch data in requested window")
            if f["source_ns"]<previous.get(f["topic"],f["source_ns"]):
                raise ValueError("Clock regression/ambiguous ordering inside requested epoch")
            previous[f["topic"]]=f["source_ns"];count[f["topic"]]+=1
    if not all(count.values()):raise ValueError("Missing required joint/GT stream")
    return dict(valid=True,epoch=reset["epoch"],counts=count,
        qualification="Epoch/identity only; does not replace native timestamps, gap/coverage tests or prove DDS loss-free delivery")
