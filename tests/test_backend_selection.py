import sys
from types import SimpleNamespace

import pytest

from capcut_windows.cli import main, parser, use_optical_backend
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('version,expected',[
    ((9,4,0,4015),True),((9,5,0,4050),True),
    ((9,5,0,4051),False),((10,0,0,1),False),
])
def test_auto_routes_only_the_exact_verified_executable_versions(tmp_path,monkeypatch,version,expected):
    executable=tmp_path/'CapCut.exe'
    executable.touch()
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(GetFileVersionInfo=lambda *args:{
        'FileVersionMS':(version[0]<<16)|version[1],
        'FileVersionLS':(version[2]<<16)|version[3]}))
    assert use_optical_backend(Settings(tmp_path,executable),'auto','scroll') is expected


@pytest.mark.parametrize('requested,command,expected',[
    ('vision','scroll',True),('uia','scroll',False),('auto','replay',False),
    ('auto','doctor',False),('auto','scroll',False),
])
def test_explicit_choice_and_offline_commands_need_no_native_version_lookup(tmp_path,monkeypatch,requested,command,expected):
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(
        GetFileVersionInfo=lambda *args:pytest.fail('No version lookup is required')))
    assert use_optical_backend(Settings(tmp_path),requested,command) is expected


def test_auto_is_default_and_scroll_reaches_optical_driver(tmp_path,monkeypatch,capsys):
    import capcut_windows.cli as cli
    import capcut_windows.vision as vision
    assert parser().parse_args(['scroll','10','20','-3']).backend=='auto'
    calls=[]
    class Driver:
        def __init__(self,settings):pass
        def scroll(self,x,y,steps):calls.append((x,y,steps))
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    monkeypatch.setattr(cli,'use_optical_backend',lambda settings,requested,command:True)
    monkeypatch.setattr(vision,'WindowsVision',Driver)
    assert main(['scroll','10','20','-3'])==0
    assert calls==[(10,20,-3)]


def test_unexpected_version_read_error_uses_backend_error_boundary(tmp_path,monkeypatch):
    def broken(*args):raise OSError('Sensitive executable detail')
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(GetFileVersionInfo=broken))
    with pytest.raises(BridgeError,match='An unexpected error occurred'):
        use_optical_backend(Settings(tmp_path,tmp_path/'CapCut.exe'),'auto','open')


def test_closed_capcut_saved_state_needs_no_desktop_backend(tmp_path,monkeypatch,capsys):
    import json
    import capcut_windows.cli as cli
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path,tmp_path/'CapCut.exe'))
    monkeypatch.setattr(cli,'processes',lambda:[])
    monkeypatch.setattr(cli,'use_optical_backend',lambda *args:pytest.fail('Saved state needs no executable version or OCR'))
    monkeypatch.setattr(cli.DraftStore,'state',lambda *args:{'duration':3})
    assert main(['state','--draft','Trial'])==0
    assert json.loads(capsys.readouterr().out)['result']=={'saved':{'duration':3}}
