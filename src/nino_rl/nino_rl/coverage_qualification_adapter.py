"""Prepared metadata correction for a FUTURE runner; no job/physics release.

The failed V1 worker and its fingerprint remain frozen. This proxy adds only
declared condition metadata before the unchanged row validator receives it.
"""
from . import residual_coverage_study as failed_v1


def condition_metadata(info, arm, seed, source_stop_s):
    p=failed_v1.protocol()
    if arm not in p['arms'] or seed not in p['seeds'] or source_stop_s not in (6.,8.):
        raise ValueError('Undeclared training condition')
    condition=dict(arm=arm,seed=seed,source_stop_s=float(source_stop_s))
    if 'qualification_condition' in info and info['qualification_condition']!=condition:
        raise ValueError('Conflicting qualification metadata; do not overwrite')
    return dict(info,qualification_condition=condition)


class QualifiedBackend:
    """Delegate lifecycle/commands unchanged; label source plan, never GT."""
    def __init__(self, backend, arm, seed):
        object.__setattr__(self,'_backend',backend)
        object.__setattr__(self,'_arm',arm)
        object.__setattr__(self,'_seed',seed)

    def __getattr__(self, name):
        return getattr(self._backend,name)

    def __setattr__(self, name, value):
        if name.startswith('_'):object.__setattr__(self,name,value)
        else:setattr(self._backend,name,value)

    def advance_reference(self,*args,**kwargs):
        # Validate declared plan before forwarding a control request.
        stop=self._backend.protocol['command_until_s']
        condition=condition_metadata({},self._arm,self._seed,stop)['qualification_condition']
        view,labels,term,trunc,info=self._backend.advance_reference(*args,**kwargs)
        return view,labels,term,trunc,condition_metadata(info,**dict(arm=self._arm,
            seed=self._seed,source_stop_s=condition['source_stop_s']))


def prepared_training_environment(backend,out,arm,seed):
    return failed_v1.training_environment(QualifiedBackend(backend,arm,seed),out,arm,seed)
