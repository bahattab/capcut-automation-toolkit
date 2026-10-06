from types import SimpleNamespace
import pytest
import capcut_windows.environment as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['running-old','none','multiple','explicit','unrelated'])
def test_discovery_prefers_running_installation_without_guessing_multiple_versions(tmp_path,monkeypatch,case):
    old=tmp_path/'CapCut/Apps/9.4.0.4015/CapCut.exe'
    new=tmp_path/'CapCut/Apps/9.5.0.4050/CapCut.exe'
    for path in (old,new):
        path.parent.mkdir(parents=True)
        path.touch()
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.delenv('CAPCUT_EXE',raising=False)
    paths=[] if case=='none' else [old,new] if case=='multiple' else [tmp_path/'unrelated/CapCut.exe'] if case=='unrelated' else [old]
    monkeypatch.setattr(module,'processes',lambda:[SimpleNamespace(exe=lambda path=path:str(path)) for path in paths])
    if case=='multiple':
        with pytest.raises(BridgeError):Settings.discover()
    else:
        result=Settings.discover(executable=str(new) if case=='explicit' else None)
        assert result.executable==(new if case in {'none','explicit','unrelated'} else old).resolve()
