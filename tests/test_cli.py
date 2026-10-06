import json
import pytest
from capcut_windows.cli import main,parser
from capcut_windows.ui import timecode


@pytest.mark.parametrize("command",[
    ["ls"],["launch"],["quit"],["doctor"],["replay","job","--name","test"],
    ["add-overlay","test","file.mp4","--at","0","--src","1","--mute"],
    ["add-text","test","مرحبا","--at","0"],["graphics","test","job"],
    ["transform","test","--scale","1.2"],["remove","test"],
    ["keyframe","test","--at","1","--opacity","0.5"],["clear-keyframes","test"],
    ["open","test"],["seek","1","--draft","test"],["select","0"],["split","1"],
    ["delete","0"],["del","0"],["trim-left"],["trim-right"],["undo"],["redo"],
    ["marker"],["zoomfit"],["save"],["play"],["playhead"],["clips"],
    ["state","--draft","test"],["dump"],["click","name"],["clickxy","1","2"],
    ["key","ctrl+s","--times","1"],["shot","out.png"],["export","--to","out"],
    ["scroll","10","20","-3"],
])
def test_command_parity(command: list[str]) -> None:
    assert parser().parse_args(command).command==command[0]


def test_error_is_generic(tmp_path,capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--draft-root",str(tmp_path),"remove","missing"])==1
    result = json.loads(capsys.readouterr().out)
    assert result["success"] is False
    assert "schema" not in result["error"].lower()
    assert str(tmp_path) not in result["error"]


def test_timecode_fractional_fps() -> None:
    assert timecode("currentProgress|00:00:01:12",24)==1.5


@pytest.mark.parametrize("value",["?","00:60:00:00","00:00:00:99"])
def test_timecode_invalid(value: str) -> None:
    from capcut_windows.errors import BridgeError
    with pytest.raises(BridgeError):
        timecode(value,30)


def test_optical_cloud_toggle_never_dispatches_export(tmp_path,monkeypatch,capsys):
    from capcut_windows.environment import Settings
    import capcut_windows.vision as optical
    class Driver:
        def __init__(self,settings):
            pass
        def export(self,*args):
            pytest.fail('Cloud toggle must be rejected before export input')
    monkeypatch.setattr(optical,'WindowsVision',Driver)
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    assert main(['--backend','vision','export','--to',str(tmp_path),'--toggle-sync'])==1
    assert json.loads(capsys.readouterr().out)['success'] is False


def test_optical_selection_labels_saved_metadata(tmp_path,monkeypatch,capsys):
    from capcut_windows.environment import Settings
    import capcut_windows.vision as optical
    class Driver:
        def __init__(self,settings):
            pass
        def select(self,index):
            assert index==0
            return 'مرحبا 😀.mp4'
    monkeypatch.setattr(optical,'WindowsVision',Driver)
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    assert main(['--backend','vision','select','0'])==0
    result=json.loads(capsys.readouterr().out)['result']
    assert result=={'selected':'مرحبا 😀.mp4','name_source':'saved_metadata'}


@pytest.mark.parametrize('backend',['uia','vision'])
def test_state_does_not_mix_projects(tmp_path,monkeypatch,capsys,backend):
    from capcut_windows.environment import Settings
    import capcut_windows.cli as cli
    import capcut_windows.vision as optical
    class Driver:
        def __init__(self,settings):
            pass
        def active_draft(self):
            return 'Another project'
        def playhead(self):
            pytest.fail('Do not combine another project with requested saved state')
    monkeypatch.setattr(optical,'WindowsVision',Driver)
    monkeypatch.setattr(cli,'WindowsUI',Driver)
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    monkeypatch.setattr(cli.DraftStore,'state',lambda *args:{'duration':3})
    monkeypatch.setattr(cli,'processes',lambda:[object()])
    assert main(['--backend',backend,'state','--draft','Expected project'])==1
    assert json.loads(capsys.readouterr().out)['success'] is False


def test_split_without_time_still_guards_requested_draft(tmp_path,monkeypatch,capsys):
    from capcut_windows.environment import Settings
    import capcut_windows.cli as cli
    class Driver:
        def __init__(self,settings):
            pass
        def active_draft(self):
            return 'Another project'
        def action(self,command):
            pytest.fail('Do not split another active project')
    monkeypatch.setattr(cli,'WindowsUI',Driver)
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    assert main(['split','--draft','Expected project'])==1
    assert json.loads(capsys.readouterr().out)['success'] is False
