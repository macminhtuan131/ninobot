"""Qt process adapter. One job at a time, motor-free fixed command allowlist."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from PyQt5 import QtCore as C
from .collection_recipes import validate_connection
from .studio_transport import remote_command
from .studio_remote import PREFIX


def command(action, connection, metadata=None, session=None, output=None):
    host=connection['host'];key=str(Path(connection['key']).expanduser())
    validate_connection(host,key)
    if connection.get('domain',0)!=0:
        raise ValueError('Current observer bundle maps domain 0; another domain needs a reviewed mapping')
    if action in ('deploy','fetch','export'):
        python='/usr/bin/python3'
        if action=='export':
            # RL venv is only an optional local export dependency; never used to drive hardware.
            candidate=Path(os.environ.get('NINO_REPO',Path(__file__).resolve().parents[3]))/'.venv/bin/python'
            if candidate.exists():python=str(candidate)
        args=[python,'-u','-m','nino_pi.studio_transport',action,'--host',host,'--key',key]
        if session:args+=['--session',session]
        if output:args+=['--output',str(output)]
        return args
    if action not in ('discover','record'):raise ValueError('Unknown Studio job')
    payload=base64.urlsafe_b64encode(json.dumps(metadata,ensure_ascii=False,allow_nan=False).encode()).decode()
    return ['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=3',
            '-o','ServerAliveCountMax=2','-i',key,host,remote_command(action,payload)]


class StudioRunner(C.QObject):
    job_event=C.pyqtSignal(dict)
    closed=C.pyqtSignal()

    def __init__(self,parent=None,demo=False):
        super().__init__(parent);self.process=None;self.action=None;self.buffer='';self.demo=demo;self.final=None
        self.timer=C.QTimer(self);self.timer.timeout.connect(self.pulse);self.timer.start(500)

    @property
    def busy(self):return self.process is not None

    def start(self,action,connection,metadata=None,session=None,output=None):
        if self.busy:raise ValueError('Wait for current Studio process to close')
        if self.demo:
            self.job_event.emit(dict(state='DEMO',message='DEMO only; no connection, files, QC promotion or motor commands.'))
            return
        argv=command(action,connection,metadata,session,output)
        self.final=None;self.action=action;self.buffer=''
        self.process=C.QProcess(self)
        env=C.QProcessEnvironment.systemEnvironment()
        paths=[str(Path(__file__).resolve().parents[1]),'/opt/ros/jazzy/lib/python3.12/site-packages']
        env.insert('PYTHONPATH',':'.join(paths)+':'+env.value('PYTHONPATH'))
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.finished.connect(self.finish)
        self.process.errorOccurred.connect(self.error)
        self.process.start(argv[0],argv[1:])
        self.job_event.emit(dict(state='STARTING',action=action))

    def pulse(self):
        if self.busy and self.action=='record':self.write(dict(command='pulse'))

    def write(self,value):
        if self.busy:self.process.write((json.dumps(value,ensure_ascii=False)+'\n').encode())

    def stop_recording(self):
        if self.busy and self.action=='record':self.write(dict(command='stop-recorder'))

    def read(self):
        self.buffer+=bytes(self.process.readAllStandardOutput()).decode(errors='replace')
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1)
            if line.startswith(PREFIX):
                try:
                    value=json.loads(line[len(PREFIX):])
                    if value['state'] in ('CLOSED','FETCHED','EXPORTED','INSTALLED'):self.final=value
                    self.job_event.emit(value)
                except (ValueError,KeyError):self.job_event.emit(dict(state='LOG',message=line))
            else:self.job_event.emit(dict(state='LOG',message=line))

    def read_error(self):
        self.job_event.emit(dict(state='LOG',message=bytes(self.process.readAllStandardError()).decode(errors='replace')))

    def error(self,error):
        self.job_event.emit(dict(state='ERROR',message=self.process.errorString()))
        if error==C.QProcess.FailedToStart:self.finish(-1,C.QProcess.CrashExit)

    def finish(self,code,status):
        if not self.process:return
        self.read();self.read_error()
        p=self.process;self.process=None;p.deleteLater()
        # State CLOSED printed by remote is not sufficient; only real QProcess closure unlocks next actions.
        self.job_event.emit(dict(state='PROCESS_CLOSED',action=self.action,returncode=code,final=self.final))
        self.action=None;self.closed.emit()
