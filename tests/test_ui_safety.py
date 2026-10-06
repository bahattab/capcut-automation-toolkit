from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from capcut_windows.ui import WindowsUI,Element
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
import capcut_windows.ui as ui_module


@pytest.mark.parametrize('alive',[False,True])
def test_inspection_failure_cannot_hide_live_modal(alive: bool,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    surviving = object()
    def wrapper(handle: int) -> object:
        if handle == 1:
            raise RuntimeError('Window disappeared during COM inspection')
        return surviving
    desktop = SimpleNamespace(window=lambda handle:SimpleNamespace(wrapper_object=lambda:wrapper(handle)))
    monkeypatch.setitem(sys.modules,'pywinauto',SimpleNamespace(Desktop=lambda **kwargs:desktop))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        IsWindowVisible=lambda handle:True,
        IsWindow=lambda handle:alive if handle==1 else True,
        EnumWindows=lambda callback,context:[callback(handle,context) for handle in (1,2)]))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda handle:(0,42)))
    monkeypatch.setattr(ui_module,'processes',lambda:[SimpleNamespace(pid=42)])
    if alive:
        with pytest.raises(BridgeError,match='inspected safely'):
            WindowsUI(Settings(tmp_path)).windows()
    else:
        assert WindowsUI(Settings(tmp_path)).windows()==[surviving]


@pytest.mark.parametrize('command',['click','scroll'])
def test_topmost_other_application_blocks_mouse_input(command: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    sent: list[object] = []
    mouse = SimpleNamespace(click=lambda **kwargs:sent.append(kwargs),scroll=lambda **kwargs:sent.append(kwargs))
    monkeypatch.setitem(sys.modules,'pywinauto',SimpleNamespace(mouse=mouse))
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(WindowFromPoint=lambda point:99,GetAncestor=lambda handle,flag:99))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda handle:(0,100)))
    monkeypatch.setattr(ui_module,'processes',lambda:[SimpleNamespace(pid=42)])
    ui = WindowsUI(Settings(tmp_path))
    active = SimpleNamespace(handle=7,rectangle=lambda:SimpleNamespace(left=0,top=0,right=100,bottom=100))
    monkeypatch.setattr(ui,'foreground',lambda:active)
    with pytest.raises(BridgeError,match='covers'):
        ui.click_xy(50,50) if command=='click' else ui.scroll(50,50,1)
    assert sent==[]


def test_ambiguous_element_is_rejected(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    elements = [Element(None,"Export","","Button",(10,10,20,20)),Element(None,"Export","","Button",(40,40,20,20))]
    monkeypatch.setattr(ui,"elements",lambda:elements)
    with pytest.raises(BridgeError,match="More than one"):
        ui.find("Export",timeout=0)


def test_exact_id_wins_over_substrings(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    expected = Element(None,"","ExportDialogExportBtn","Button",(10,10,20,20))
    monkeypatch.setattr(ui,"elements",lambda:[expected,Element(None,"Export","ExportOther","Button",(40,40,20,20))])
    assert ui.find("ExportDialogExportBtn",timeout=0) is expected


def test_negative_clip_selection_is_rejected(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    monkeypatch.setattr(ui,"clips",lambda:[Element(None,"clip","","",(1,1,1,1))])
    with pytest.raises(BridgeError,match="outside"):
        ui.select(-1)


def test_seek_never_claims_nonconvergence(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    monkeypatch.setattr(ui,"playhead",lambda:("00:00:00:00","00:00:10:00"))
    monkeypatch.setattr(ui,"key",lambda *args:None)
    with pytest.raises(BridgeError,match="not verified"):
        ui.seek(1,30)


def test_seek_verifies_frame(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    monkeypatch.setattr(ui,"playhead",lambda:("00:00:01:12","00:00:10:00"))
    assert ui.seek(1.5,24)==1.5


def test_seek_outside_duration_sends_no_keys(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    ui = WindowsUI(Settings(tmp_path))
    monkeypatch.setattr(ui,"playhead",lambda:("00:00:00:00","00:00:01:00"))
    sent = []
    monkeypatch.setattr(ui,"key",lambda *args:sent.append(args))
    with pytest.raises(BridgeError,match="beyond"):
        ui.seek(2)
    assert sent==[]
