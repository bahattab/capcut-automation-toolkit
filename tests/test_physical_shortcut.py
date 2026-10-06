import sys
from types import SimpleNamespace
import pytest
import pywinauto.keyboard as keyboard
import capcut_windows.vision as module
from capcut_windows.vision import WindowsVision
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['valid','base-failed','focus-changed','held-modifier','held-left-win','held-right-win','release-failed'])
def test_ascii_shortcut_uses_physical_keys_and_releases_all_modifiers(tmp_path,monkeypatch,case):
    events=[]
    class Action:
        def __init__(self,key,down=True,up=True):self.value=(key,down,up)
        def run(self):
            events.append(self.value)
            if case=='base-failed' and self.value==(90,True,False):raise OSError('Native injection failed')
            if case=='release-failed' and self.value==(16,False,True):raise OSError('Shift release failed')
    monkeypatch.setattr(keyboard,'VirtualKeyAction',Action)
    monkeypatch.setattr(keyboard,'send_keys',lambda *args,**kwargs:pytest.fail('Do not map Latin shortcut text through the Arabic layout'))
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(GetAsyncKeyState=lambda code:
        0x8000 if case=='held-modifier' or case=='held-left-win' and code==91 or case=='held-right-win' and code==92 else 0))
    monkeypatch.setattr(module.time,'sleep',lambda *args:None)
    driver=WindowsVision(Settings(tmp_path))
    driver.foreground=lambda *args:12 if case=='focus-changed' and events else 11
    if case=='valid':driver.key('ctrl+shift+z')
    else:
        with pytest.raises(BridgeError):driver.key('ctrl+shift+z')
    if case in {'held-modifier','held-left-win','held-right-win'}:assert events==[]
    else:
        assert events[:2]==[(17,True,False),(16,True,False)]
        assert events[-2:]==[(16,False,True),(17,False,True)]
        assert ((90,True,False) in events)==(case!='focus-changed')
        assert ((90,False,True) in events)==(case!='focus-changed')


@pytest.mark.parametrize('combo,expected',[
    ('ctrl+minus',[(17,True,False),(189,True,False),(189,False,True),(17,False,True)]),
    ('ctrl+plus',[(17,True,False),(16,True,False),(187,True,False),(187,False,True),(16,False,True),(17,False,True)]),
    ('escape',[(27,True,False),(27,False,True)]),
])
def test_special_shortcut_keys_do_not_depend_on_text_parser_names(tmp_path,monkeypatch,combo,expected):
    events=[]
    class Action:
        def __init__(self,key,down=True,up=True):self.value=(key,down,up)
        def run(self):events.append(self.value)
    monkeypatch.setattr(keyboard,'VirtualKeyAction',Action)
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(GetAsyncKeyState=lambda code:0))
    monkeypatch.setattr(module.time,'sleep',lambda *args:None)
    driver=WindowsVision(Settings(tmp_path));driver.foreground=lambda *args:11
    driver.key(combo)
    assert events==expected
