from pathlib import Path

import pytest

from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('filename',['root_meta_info.json','draft_meta_info.json'])
def test_linked_metadata_rejected_before_mutation(store,monkeypatch,filename):
    path=store.root/filename if filename.startswith('root') else store.folder('test')/filename
    before=store.content_path('test').read_bytes()
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda self:self==path or original(self))
    with pytest.raises(BridgeError,match='Linked project metadata'):
        store.edit('test',lambda *args:pytest.fail('Linked metadata must be refused before mutation'))
    assert store.content_path('test').read_bytes()==before


def test_newly_linked_registry_is_not_followed_during_recovery(store,monkeypatch):
    registry=store.root/'root_meta_info.json'
    before=store.content_path('test').read_bytes()
    original=Path.is_symlink
    state={'linked':False}
    monkeypatch.setattr(Path,'is_symlink',lambda self:(self==registry and state['linked']) or original(self))
    def fail(*args):
        state['linked']=True
        raise OSError('Mutation failed after registry changed')
    with pytest.raises(BridgeError,match='Linked project metadata'):
        store.edit('test',fail)
    assert store.content_path('test').read_bytes()==before


def test_nested_junction_rejected_before_backup_or_mutation(store,monkeypatch):
    cache=store.folder('test')/'Timelines'
    original=Path.is_junction
    monkeypatch.setattr(Path,'is_junction',lambda self:self==cache or original(self))
    before=store.content_path('test').read_bytes()
    with pytest.raises(BridgeError,match='Nested linked folders'):
        store.edit('test',lambda *args:pytest.fail('A nested junction must not be traversed'))
    assert store.content_path('test').read_bytes()==before


@pytest.mark.parametrize('speed',[
    {'speed':2,'mode':0,'curve_speed':None},
    {'speed':1,'mode':1,'curve_speed':None},
    {'speed':1,'mode':0,'curve_speed':{'points':[1,2]}},
])
def test_keyframe_rejects_retiming_hidden_in_referenced_material(store,speed):
    import json
    path=store.content_path('test')
    draft=store.load('test')
    speed['id']='variable-speed'
    draft['materials']['speeds']=[speed]
    draft['tracks'][0]['segments'][0].setdefault('extra_material_refs',[]).append(speed['id'])
    path.write_text(json.dumps(draft),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(BridgeError,match='retimed'):
        store.keyframe('test','main',0,1,{'scale':1.2})
    assert path.read_bytes()==before
