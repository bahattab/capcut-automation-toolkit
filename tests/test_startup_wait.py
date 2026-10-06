from types import SimpleNamespace
import sys
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision
import capcut_windows.vision as module

@pytest.mark.parametrize('ready',[True,False])
def test_prepare_waits_for_native_root_without_relaunch_or_input(tmp_path,monkeypatch,ready):
    driver=WindowsVision(Settings(tmp_path));events=[];polls=[]
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(
        GetMonitorInfo=lambda h:{'Work':(0,0,1680,1050)},MonitorFromWindow=lambda *a:1))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        IsWindowEnabled=lambda h:True,GetClassName=lambda h:'Qt622QWindowIcon',
        GetWindowText=lambda h:'CapCut',GetWindowRect=lambda h:(0,0,1680,1050),
        ShowWindow=lambda *a:events.append('restore'),MoveWindow=lambda *a:events.append('move')))
    def handles():
        polls.append(1)
        return [11] if ready and len(polls)>1 else []
    driver.handles=handles
    driver._set_foreground=lambda h:events.append('focus')
    driver.foreground=lambda prepare:11
    ticks=iter([0,1,2,100])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    if ready:
        driver.prepare();assert len(polls)==2 and events==['restore','move','focus']
    else:
        with pytest.raises(BridgeError,match='became ready'):driver.prepare()
        assert events==[]
