import sys
from types import SimpleNamespace
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision


@pytest.mark.parametrize('case',['direct','attached','already-restored','held-key','attach-failed','retry-failed','changed-foreground','disabled','target-reused','target-hidden','detach-failed'])
def test_focus_binding_is_bounded_and_detached_before_any_input(tmp_path,monkeypatch,case):
    driver=WindowsVision(Settings(tmp_path))
    driver.handles=lambda:[7]
    state={'foreground':100,'attempts':0}
    bindings=[]
    def focus(handle):
        state['attempts']+=1
        if case=='direct':state['foreground']=handle;return
        if state['attempts']==1:
            if case=='already-restored':state['foreground']=handle
            raise OSError('Simulated native foreground denial')
        if case=='retry-failed':raise OSError('Retry denied')
        state['foreground']=handle
    def attach(current,thread,enabled):
        bindings.append((current,thread,enabled))
        if enabled and case=='attach-failed':raise OSError('Queue binding failed')
        if enabled and case=='changed-foreground':state['foreground']=101
        if not enabled and case=='detach-failed':raise OSError('Queue detach failed')
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        IsWindowEnabled=lambda handle:case!='disabled',IsWindowVisible=lambda handle:case!='target-hidden',SetForegroundWindow=focus,
        GetForegroundWindow=lambda:state['foreground']))
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(
        GetAsyncKeyState=lambda key:0x8000 if case=='held-key' and key==17 else 0,
        GetCurrentThreadId=lambda:5))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(
        GetWindowThreadProcessId=lambda handle:(10,21) if handle==7 and bindings and case=='target-reused' else (10,20),AttachThreadInput=attach))
    if case in {'direct','attached','already-restored'}:
        driver._set_foreground(7)
        assert state['foreground']==7
    else:
        with pytest.raises(BridgeError):driver._set_foreground(7)
    if case in {'attached','retry-failed','changed-foreground','target-reused','target-hidden','detach-failed'}:
        assert bindings==[(5,10,True),(5,10,False)]
    elif case=='attach-failed':assert bindings==[(5,10,True)]
    else:assert bindings==[]
    assert state['attempts']==(0 if case=='disabled' else 2 if case in {'attached','retry-failed','detach-failed'} else 1)
