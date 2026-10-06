from types import SimpleNamespace
import pytest
import capcut_windows.clipboard as module
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case', ['success', 'wrong-type', 'read-failure', 'external', 'prepare-failure', 'initial-change', 'restore-failure', 'copy-raises', 'owner-race','recovery-failure'])
def test_copy_restores_owned_data_and_preserves_external_changes(monkeypatch, case):
    events=[]
    class Fake:
        def __init__(self):
            self.sequence=10
            self.api=SimpleNamespace(CF_UNICODETEXT=13,
                GetClipboardSequenceNumber=lambda:self.sequence,
                GetClipboardOwner=lambda:100 if case=='owner-race' and self.sequence>10 else 99,
                CloseClipboard=lambda:events.append('unlock'),
                GetClipboardData=self.read)
        def snapshot(self):return {13:b'original',50:b'opaque'},self.sequence
        def prepare(self,data):
            events.append('prepare')
            if case=='prepare-failure':raise BridgeError('allocation failed')
            if case=='initial-change':self.sequence+=1
        def open(self):
            events.append('lock')
            if case=='owner-race':self.sequence+=1
        def recover(self):
            events.append('recovery')
            if case=='recovery-failure':raise RuntimeError('write failed')
        def discard_recovery(self):events.append('discard')
        def read(self,format_id):
            if case=='read-failure':raise RuntimeError('read failed')
            if case=='external':self.sequence+=1
            return 123 if case=='wrong-type' else 'Trial'
        def restore(self,sequence):
            events.append('restore')
            return self.sequence==sequence and case!='restore-failure'
        def close(self):events.append('close')
    clipboard=Fake()
    monkeypatch.setattr(module,'MemoryClipboard',lambda:clipboard)
    import win32process
    monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda handle:(1,123 if handle==99 else 456))
    def copy():
        events.append('copy');clipboard.sequence+=1
        if case=='copy-raises':raise RuntimeError('modifier cleanup failed')
    if case=='success':assert module.copy_native_text(copy,123)=='Trial'
    else:
        with pytest.raises(BridgeError):module.copy_native_text(copy,123)
    assert events[-1]=='close'
    if case in {'prepare-failure','initial-change','owner-race','recovery-failure'}:
        assert 'restore' not in events
        if case!='owner-race':assert 'copy' not in events
    else:assert 'restore' in events


@pytest.mark.parametrize('case',['transient','persistent','external'])
def test_restore_retries_without_emptying_again_and_recovers_persistent_failure(monkeypatch,case):
    events=[];attempts={13:0,50:0}
    clipboard=object.__new__(module.MemoryClipboard)
    clipboard.hidden=99;clipboard.buffers={13:100,50:200}
    clipboard.open=lambda handle:events.append('lock')
    clipboard.recover=lambda:events.append('encrypted-recovery')
    clipboard.api=SimpleNamespace(GetClipboardSequenceNumber=lambda:12 if case=='external' else 11,
        EmptyClipboard=lambda:events.append('empty'),CloseClipboard=lambda:events.append('unlock'))
    def write(format_id,handle):
        attempts[format_id]+=1;events.append(('write',format_id))
        if format_id==13 and (case=='persistent' or attempts[13]==1):return 0
        return handle
    clipboard.user=SimpleNamespace(SetClipboardData=write)
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    if case=='persistent':
        with pytest.raises(BridgeError):clipboard.restore(11)
        assert attempts=={13:3,50:1} and clipboard.buffers=={13:100}
        assert 'encrypted-recovery' in events
    elif case=='external':
        assert clipboard.restore(11) is False
        assert 'empty' not in events and attempts=={13:0,50:0}
    else:
        assert clipboard.restore(11) is True
        assert attempts=={13:2,50:1} and not clipboard.buffers
    assert events.count('empty')==(0 if case=='external' else 1)
    assert events[-1]=='unlock'


def test_emergency_recovery_is_user_encrypted_and_roundtrips_all_formats(tmp_path,monkeypatch):
    import win32crypt,json,base64
    clipboard=object.__new__(module.MemoryClipboard)
    clipboard.original={13:b'synthetic text',50:b'\x00\xffopaque'}
    clipboard.recovery_path=None
    monkeypatch.setattr(module.tempfile,'gettempdir',lambda:str(tmp_path))
    clipboard.recover()
    paths=list(tmp_path.glob('capcut-kit-clipboard-recovery-*.dpapi'))
    assert len(paths)==1
    encrypted=paths[0].read_bytes()
    assert b'synthetic text' not in encrypted and b'opaque' not in encrypted
    _,payload=win32crypt.CryptUnprotectData(encrypted,None,None,None,1)
    restored={int(k):base64.b64decode(v) for k,v in json.loads(payload).items()}
    assert restored==clipboard.original
