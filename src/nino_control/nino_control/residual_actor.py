"""Portable deterministic MLP actor. NumPy only; no learner on the Pi."""
import hashlib
import json
from pathlib import Path
import numpy as np


class PortableActor:
    def __init__(self,folder,abi_sha256):
        root=Path(folder);self.metadata=json.loads((root/'actor.json').read_text())
        m=self.metadata
        if m.get('abi_sha256')!=abi_sha256:raise ValueError('Actor ABI mismatch; legacy/checkpoint conversion prohibited')
        path=root/'actor.npz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=m['weights_sha256']:raise ValueError('Actor weights hash mismatch')
        self.weights=dict(np.load(path,allow_pickle=False));self.size=int(m['observation_size'])
        if self.size<=0 or not m.get('layers'):raise ValueError('Invalid actor schema')
        for a in self.weights.values():
            if not np.all(np.isfinite(a)):raise ValueError('Invalid actor weights')

    def __call__(self,observation):
        x=np.asarray(observation,dtype=np.float32)
        if x.shape!=(self.size,) or not np.all(np.isfinite(x)):raise ValueError('Actor observation shape/finite check failed')
        for layer in self.metadata['layers']:
            kind=layer['kind']
            if kind=='linear':x=self.weights[layer['weight']]@x+self.weights[layer['bias']]
            elif kind=='tanh':x=np.tanh(x)
            elif kind=='relu':x=np.maximum(x,0.)
            else:raise ValueError('Unsupported actor layer')
        if x.shape!=(2,) or not np.all(np.isfinite(x)):raise ValueError('Invalid actor output')
        return np.clip(x,-1.,1.).astype(np.float32)


def export_actor(model,algorithm,folder,contract,purpose='software_smoke'):
    import torch
    from torch import nn
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    if algorithm=='TD3':network=list(model.policy.actor.mu.children())
    elif algorithm=='PPO':network=list(model.policy.mlp_extractor.policy_net.children())+[model.policy.action_net]
    else:raise ValueError('Portable exporter supports TD3/PPO only')
    layers=[];weights={}
    for i,layer in enumerate(network):
        if isinstance(layer,nn.Linear):
            w,b='w'+str(i),'b'+str(i)
            weights[w]=layer.weight.detach().cpu().numpy().astype(np.float32)
            weights[b]=layer.bias.detach().cpu().numpy().astype(np.float32)
            layers.append(dict(kind='linear',weight=w,bias=b))
        elif isinstance(layer,nn.ReLU):layers.append(dict(kind='relu'))
        elif isinstance(layer,nn.Tanh):layers.append(dict(kind='tanh'))
        else:raise ValueError('Unsupported portable actor layer: '+str(type(layer)))
    np.savez(root/'actor.npz',**weights)
    metadata=dict(schema_version=1,algorithm=algorithm,abi_sha256=contract['abi_sha256'],
                  source_fingerprint=contract['source_fingerprint'],observation_size=contract['observation_size'],
                  layers=layers,purpose=purpose,hardware_authorized=False,
                  weights_sha256=hashlib.sha256((root/'actor.npz').read_bytes()).hexdigest())
    (root/'actor.json').write_text(json.dumps(metadata,indent=2)+'\n')
    actor=PortableActor(root,contract['abi_sha256'])
    rng=np.random.default_rng(1204);max_error=0.
    for row in rng.uniform(-1.,1.,size=(12,contract['observation_size'])).astype(np.float32):
        expected,_=model.predict(row,deterministic=True)
        max_error=max(max_error,float(np.max(np.abs(actor(row)-expected))))
    if max_error>1e-5:raise RuntimeError('Portable/SB3 deterministic inference mismatch')
    return dict(max_inference_error=max_error,numpy_only=True,hardware_authorized=False)
