from types import SimpleNamespace
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word
import capcut_windows.drafts as drafts


@pytest.mark.parametrize('case',['valid','uncertain','unknown','conflict','shift','duplicate','old-version'])
def test_native_title_fallback_requires_two_complete_registered_names(tmp_path,monkeypatch,case):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    v.capture=lambda:view;points=[];v.point=lambda *args:points.append(1)
    v.require_profile=lambda feature:(9,4,0,1) if case=='old-version' else (9,5,0,4050)
    rows=[{'name':'Trial'},{'name':'Other'}]
    if case=='duplicate':rows.append({'name':'Trial'})
    monkeypatch.setattr(drafts,'DraftStore',lambda settings:SimpleNamespace(listings=lambda:rows))
    def words(current,region,scale,**kwargs):
        if kwargs.get('psm')!=7:return []
        confidence=70 if scale==4 or case=='uncertain' else 95
        name='Unregistered' if case=='unknown' else ('Other' if case=='conflict' and scale==2 else 'Trial')
        offset=5 if case=='shift' and scale==2 else 0
        return [Word(name,confidence,Box(728+offset,12,860+offset,22),(1,1,1,1))]
    v.words=words
    if case=='valid':assert v.active_draft()=='Trial' and points==[1]
    else:
        with pytest.raises(BridgeError):v.active_draft()
        assert not points
