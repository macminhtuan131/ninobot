"""Fresh instance per episode, with close-before-start and fail-closed ownership.

An epoch is the unique artifact namespace + GZ partition + local estimator
epoch. Source simulation stamps may repeat across launches; caches never do.
"""
from copy import deepcopy
from pathlib import Path

from .joint_reliability_candidate import ReliableBoundaryBackend
from .residual_joint_boundary import IndependentProcess
from .joint_boundary_observer import graph
from .residual_workflow import save


class EpisodeLifecycle:
    residual_contract_id = ReliableBoundaryBackend.residual_contract_id
    kind = ReliableBoundaryBackend.kind
    calibrated_to_hardware = False
    def __init__(self, config, directory, world, guidance, task, condition, protocol,
                 backend_factory=ReliableBoundaryBackend, observer_factory=IndependentProcess):
        self.config, self.gconf = deepcopy(config), deepcopy(guidance)
        self.protocol, self.condition = deepcopy(task), deepcopy(condition)
        self.directory, self.world = Path(directory), world
        self.directory.mkdir(parents=True, exist_ok=True)
        self.p = deepcopy(protocol)
        self.backend_factory, self.observer_factory = backend_factory, observer_factory
        self.current = self.observer = None
        self.index, self.tick = -1, 0
        self.namespace = None
        self.failed = self.closed = False
        self.events = []

    def event(self, phase, **fields):
        self.events.append(dict(index=len(self.events), episode=self.index,
                                namespace=self.namespace, phase=phase, **fields))
        save(self.directory / 'lifecycle.json', self.events)

    def _close_current(self):
        errors = []
        if self.current is not None:
            backend, observer = self.current, self.observer
            thread, launch = getattr(backend, 'thread', None), getattr(backend, 'launch', None)
            try:
                backend.close()
                if thread is not None and thread.is_alive():
                    raise RuntimeError('Old ROS executor thread remains alive')
                if launch is not None and launch.poll() is None:
                    raise RuntimeError('Old Gazebo launch remains alive')
            except BaseException as exc:
                errors.append('primary/backend: ' + repr(exc))
            try:
                observer.close()
            except BaseException as exc:
                errors.append('independent observer: ' + repr(exc))
            # Never reuse an instance even when closure fails.
            self.current = self.observer = None
            self.event('closed' if not errors else 'closure_failed', errors=errors)
        if errors:
            self.failed = True
            raise RuntimeError('; '.join(errors))

    def reset(self, seed=None):
        if self.closed or self.failed:
            raise RuntimeError('Closed/failed lifecycle cannot reset')
        try:
            self._close_current()
            self.index += 1
            if self.index >= self.p['training_episodes_per_seed_maximum']:
                raise ValueError('Episode launch budget exhausted')
            self.namespace = 'episode_' + str(self.index)
            target = self.directory / self.namespace
            target.mkdir()  # no overwrite/reuse of prior epoch artifact
            self.observer = self.observer_factory(target / 'independent', self.p)
            self.current = self.backend_factory(deepcopy(self.config), target / 'backend', self.world,
                deepcopy(self.gconf), deepcopy(self.protocol), deepcopy(self.condition), self.observer)
            if self.current.primary_count or self.current.primary_last is not None or self.current.boundaries:
                raise ValueError('New primary contains previous-epoch support')
            self.event('created', partition=self.current.partition, primary_count=0,
                       primary_last=None, boundary_count=0)
            ready = self.observer.start(self.current.environment)
            # IndependentProcess validates ready.json itself; return value is
            # None in the frozen implementation. Persist the actual ACK file.
            ready_file = target / 'independent/ready.json'
            if ready_file.exists():
                import json
                ready = json.loads(ready_file.read_text())
            self.event('observer_ready', ready=ready)
            view, info = self.current.reset(seed=seed)
            endpoints = graph(self.current.node)
            save(target / 'primary_graph.json', endpoints)
            if len(endpoints) != 1 or endpoints[0]['qos']['reliability'] != 1:
                raise ValueError('Expected one RELIABLE joint publisher per fresh epoch')
            self.current.phase, self.current.control_tick, self.tick = 'control', 0, 0
            epoch = dict(namespace=self.namespace, partition=self.current.partition,
                         local_estimator_epoch=self.current.estimator.epoch,
                         fresh_primary_and_independent=True, old_support_reused=False)
            save(target / 'epoch.json', epoch)
            self.event('reset_complete', epoch=epoch)
            return view, dict(info, learner_episode_epoch=epoch)
        except BaseException as exc:
            self.failed = True
            self.event('failed', error=repr(exc))
            try:
                self._close_current()
            except BaseException as cleanup:
                self.event('cleanup_failed', error=repr(cleanup))
            raise

    def advance_reference(self, *args, **kwargs):
        if self.current is None or self.closed or self.failed:
            raise RuntimeError('No active healthy episode')
        self.current.control_tick = self.tick
        try:
            result = self.current.advance_reference(*args, **kwargs)
            self.tick += 1
            return result
        except BaseException as exc:
            self.failed = True
            self.event('control_failed', tick=self.tick, error=repr(exc))
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._close_current()

    def __getattr__(self, name):
        current = self.__dict__.get('current')
        if current is None:
            raise AttributeError(name)
        return getattr(current, name)
