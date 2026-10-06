import sys
from types import SimpleNamespace
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box
import capcut_windows.vision as module


@pytest.mark.parametrize('case',['normal','swapped','double','cursor','focus','covered','moved-window','press-failed','double-root-change'])
def test_physical_click_preserves_exact_coordinates_ownership_and_release(tmp_path,monkeypatch,case):
    driver=WindowsVision(Settings(tmp_path))
    view=View(10,Box(3360,0,5040,1050),Image.new('RGB',(1680,1050)))
    target=Box(307,593,323,609)
    moves=[]; events=[]
    def event(flags,x,y,data):
        events.append((flags,x,y,data))
        if case=='press-failed' and flags==2:
            raise OSError('simulated injection failure')
    api=SimpleNamespace(SetCursorPos=lambda point:moves.append(point),
                        GetCursorPos=lambda:(3676,601) if case=='cursor' else (3675,601),
                        GetSystemMetrics=lambda index:case=='swapped',mouse_event=event)
    gui=SimpleNamespace(GetWindowRect=lambda handle:(3360,0,5039,1050) if case=='moved-window' else view.box.tuple(),
                        WindowFromPoint=lambda point:11 if case=='covered' else 10,
                        GetAncestor=lambda handle,flag:handle)
    monkeypatch.setitem(sys.modules,'win32api',api)
    monkeypatch.setitem(sys.modules,'win32gui',gui)
    driver.point=lambda captured,box:(3675,601)
    driver.foreground=lambda prepare:11 if case=='focus' or (case=='double-root-change' and len(events)>=2) else 10
    clicks=2 if case in {'double','double-root-change'} else 1
    if case in {'cursor','focus','covered','moved-window','press-failed','double-root-change'}:
        with pytest.raises(BridgeError):driver.click_box(view,target,clicks)
    else:
        driver.click_box(view,target,clicks)
    assert moves==([] if case in {'focus','covered','moved-window'} else [(3675,601)])
    if case in {'cursor','focus','covered','moved-window'}:
        assert events==[]
    else:
        down,up=(8,16) if case=='swapped' else (2,4)
        assert events==[(down,0,0,0),(up,0,0,0)]*(1 if case=='double-root-change' else clicks)
        assert all(flags & 0x8001==0 for flags,_,_,_ in events)


@pytest.mark.parametrize('case',['cursor-during-dwell','interrupted-hold'])
def test_dwell_rechecks_cursor_and_always_releases_pressed_button(monkeypatch,case):
    position={'point':(0,0)}
    events=[]
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(
        SetCursorPos=lambda point:position.update(point=point),
        GetCursorPos=lambda:position['point'],GetSystemMetrics=lambda index:0,
        mouse_event=lambda *args:events.append(args)))
    def sleep(seconds):
        if seconds==.15 and case=='cursor-during-dwell':position['point']=(101,100)
        if seconds==.1 and case=='interrupted-hold':raise OSError('Interrupted native press wait')
    monkeypatch.setattr(module.time,'sleep',sleep)
    with pytest.raises(BridgeError):module.physical_click((100,100),lambda:None)
    assert events==([] if case=='cursor-during-dwell' else [(2,0,0,0),(4,0,0,0)])
