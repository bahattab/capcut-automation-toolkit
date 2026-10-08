import subprocess
from types import SimpleNamespace

import capcut_windows.environment as module
from capcut_windows.environment import Settings,launch


def test_native_gui_cannot_retain_or_contaminate_cli_capture_pipes(tmp_path,monkeypatch):
    executable=tmp_path/'CapCut.exe'
    executable.write_bytes(b'fixture')
    monkeypatch.setattr(module.platform,'system',lambda:'Windows')
    monkeypatch.setattr(module,'processes',lambda:[])
    captured={}
    def spawn(argv,**options):
        captured.update(argv=argv,**options)
        return SimpleNamespace(pid=123)
    monkeypatch.setattr(module.subprocess,'Popen',spawn)
    assert launch(Settings(tmp_path,executable=executable))==123
    assert captured['argv']==[str(executable)]
    assert captured['creationflags']==subprocess.CREATE_NO_WINDOW
    assert captured['env']['QT_ACCESSIBILITY']=='1'
    assert all(captured[stream]==subprocess.DEVNULL for stream in ('stdin','stdout','stderr'))
    assert captured['close_fds'] is True
