import json
from types import SimpleNamespace
import pytest
from capcut_windows.cli import main
from capcut_windows.environment import Settings
import capcut_windows.vision as optical


@pytest.mark.parametrize('command',[['dump','Media'],['click','Menu'],['clickxy','3393','51'],['scroll','4810','470','-4']])
def test_optical_cli_routes_generic_inputs_and_labels_evidence(tmp_path,monkeypatch,capsys,command):
    calls=[]
    class Driver:
        def __init__(self,settings):pass
        def elements(self,needle):
            calls.append(('dump',needle))
            return [SimpleNamespace(name='Media',automation_id='',kind='Text',rectangle=(3378,62,30,8),text_source='ocr')]
        def click(self,needle):
            calls.append(('click',needle))
            return needle
        def click_xy(self,x,y,clicks):calls.append(('clickxy',x,y,clicks))
        def scroll(self,x,y,steps):calls.append(('scroll',x,y,steps))
    monkeypatch.setattr(optical,'WindowsVision',Driver)
    monkeypatch.setattr(Settings,'discover',lambda *args:Settings(tmp_path))
    assert main(['--backend','vision',*command])==0
    result=json.loads(capsys.readouterr().out)['result']
    assert len(calls)==1 and calls[0][0]==command[0]
    if command[0]=='dump':
        assert result[0]['automation_id']=='' and result[0]['text_source']=='ocr'
        assert result[0]['type']=='Text'
    else:
        assert result['effect_verified'] is False and result['status']=='dispatched'
