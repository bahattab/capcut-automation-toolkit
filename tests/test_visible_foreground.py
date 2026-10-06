import sys
from types import SimpleNamespace
import pytest
import psutil
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision


def test_hidden_capcut_foreground_cannot_be_captured(tmp_path,monkeypatch):
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        GetForegroundWindow=lambda:11,IsWindowVisible=lambda handle:False))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(
        GetWindowThreadProcessId=lambda handle:(1,7)))
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(name=lambda:'CapCut.exe'))
    with pytest.raises(BridgeError,match='lost focus'):
        driver.foreground(False)


def test_disabled_main_cannot_replace_active_export_dialog(tmp_path,monkeypatch):
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        GetForegroundWindow=lambda:11,IsWindowVisible=lambda handle:True,
        IsWindowEnabled=lambda handle:False))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(
        GetWindowThreadProcessId=lambda handle:(1,7)))
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(name=lambda:'CapCut.exe'))
    with pytest.raises(BridgeError,match='lost focus'):driver.foreground(False)


def test_restore_selects_enabled_export_instead_of_disabled_parent(tmp_path,monkeypatch):
    driver=WindowsVision(Settings(tmp_path))
    selected=[]
    driver.handles=lambda:[11,12]
    driver.foreground=lambda restore:selected[-1]
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(
        GetWindowThreadProcessId=lambda handle:(1,7)))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        IsWindowEnabled=lambda handle:handle==12,GetClassName=lambda handle:'Qt622QWindowIcon',
        GetWindowText=lambda handle:'CapCut' if handle==11 else 'Export-Trial',
        GetWindowRect=lambda handle:(0,0,1680,1050) if handle==11 else (0,0,720,663),
        IsIconic=lambda handle:False,SetForegroundWindow=lambda handle:selected.append(handle)))
    driver.activate()
    assert selected==[12]


@pytest.mark.parametrize('actual',[11,13])
def test_restore_rejects_unchanged_or_wrong_owned_foreground(tmp_path,monkeypatch,actual):
    driver=WindowsVision(Settings(tmp_path))
    driver.handles=lambda:[12]
    driver.foreground=lambda restore:actual
    driver._set_foreground=lambda handle:None
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        IsWindowEnabled=lambda handle:True,GetClassName=lambda handle:'Qt622QWindowIcon',
        GetWindowText=lambda handle:'CapCut',GetWindowRect=lambda handle:(0,0,1680,1050),
        IsIconic=lambda handle:False))
    with pytest.raises(BridgeError,match='did not receive focus'):driver.activate()
