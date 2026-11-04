"""Flush this completed session only; never repair or promote a failed capture."""
from pathlib import Path
import os

def sync_session(directory):
    directory=Path(directory)
    if not directory.is_dir():raise FileNotFoundError(directory)
    for file in directory.rglob('*'):
        if file.is_file():
            with file.open('rb') as stream:os.fsync(stream.fileno())
    folders=sorted((p for p in directory.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True)
    for folder in [*folders,directory]:
        fd=os.open(folder,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
