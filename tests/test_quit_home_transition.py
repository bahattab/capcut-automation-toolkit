import sys
from types import SimpleNamespace
import pytest
import capcut_windows.environment as module
from capcut_windows.environment import Settings, quit_app
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['home','owned-prompt','multiple-home','new-session','reused-pid'])
def test_graceful_editor_to_home_transition_preserves_owned_prompts(tmp_path,monkeypatch,case):
    sent=[]
    def roots():
        if not sent:return [10]
        if case=='owned-prompt':return [10,12]
        return [20,21] if case=='multiple-home' else [20,12]
    gui=SimpleNamespace(EnumWindows=lambda callback,arg:[callback(h,arg) for h in roots()],
                        IsWindowVisible=lambda h:True,GetWindow=lambda h,flag:20 if h==12 else 0,
                        GetClassName=lambda h:'Qt622QWindowIcon',GetWindowText=lambda h:'CapCut',
                        PostMessage=lambda h,*args:sent.append(h))
    monkeypatch.setitem(sys.modules,'win32gui',gui)
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda h:(0,1)))
    def processes():
        if 20 in sent:return []
        pid=2 if sent and case=='new-session' else 1
        created=2.0 if sent and case in {'new-session','reused-pid'} else 1.0
        return [SimpleNamespace(pid=pid,create_time=lambda:created)]
    monkeypatch.setattr(module,'processes',processes)
    ticks=iter(range(100))
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    if case=='home':
        quit_app(Settings(tmp_path,allow_close=True),timeout=5)
        assert sent==[10,20]
    else:
        with pytest.raises(BridgeError):quit_app(Settings(tmp_path,allow_close=True),timeout=5)
        assert sent==[10]
