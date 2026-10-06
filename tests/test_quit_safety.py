import sys
from types import SimpleNamespace
import pytest
import capcut_windows.environment as module
from capcut_windows.environment import Settings, quit_app
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['single','absent','multiple'])
def test_graceful_quit_never_closes_owned_save_dialogs(tmp_path,monkeypatch,case):
    sent=[]
    rows={11:('Save changes',10,'Qt622QWindowIcon',1),
          12:('CapCut',10,'Qt622QWindowToolSaveBits',1),
          13:('Another app',0,'Qt622QWindowIcon',2)}
    if case!='absent':
        rows[10]=('CapCut',0,'Qt622QWindowIcon',1)
    if case=='multiple':
        rows[14]=('CapCut',0,'Qt622QWindowIcon',1)
    monkeypatch.setattr(module,'processes',lambda:[] if sent else [SimpleNamespace(pid=1,create_time=lambda:1.0)])
    gui=SimpleNamespace(
        EnumWindows=lambda callback,arg:[callback(h,arg) for h in rows],
        IsWindowVisible=lambda h:True,
        GetWindow=lambda h,flag:rows[h][1],
        GetClassName=lambda h:rows[h][2],
        GetWindowText=lambda h:rows[h][0],
        PostMessage=lambda h,*args:sent.append(h))
    monkeypatch.setitem(sys.modules,'win32gui',gui)
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda h:(0,rows[h][3])))
    settings=Settings(tmp_path,allow_close=True)
    if case=='single':
        quit_app(settings)
        assert sent==[10]
    else:
        with pytest.raises(BridgeError):
            quit_app(settings)
        assert sent==[]
