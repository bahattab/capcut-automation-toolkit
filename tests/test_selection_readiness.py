from PIL import Image
import pytest
import capcut_windows.vision as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,VisualClip


@pytest.mark.parametrize('case',['delayed','other-clip','changed-window'])
def test_selection_waits_for_paint_without_repeating_input(tmp_path,monkeypatch,case):
    driver=WindowsVision(Settings(tmp_path))
    view=View(11,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    clips=[VisualClip('A',(183,800,509,876),0,Box(700,12,800,25)),
           VisualClip('B',(509,800,672,876),1,Box(700,12,800,25))]
    driver._clip_views=lambda:(view,clips)
    driver.point=lambda *args:None
    clicks=[]
    driver.click_box=lambda *args:clicks.append(args)
    captures={'count':0}
    def capture():
        captures['count']+=1
        return View(12,view.box,view.image) if case=='changed-window' else view
    driver.capture=capture
    monkeypatch.setattr(module,'clip_bars',lambda *args:None)
    monkeypatch.setattr(module.time,'sleep',lambda *args:None)
    monkeypatch.setattr(module,'selection_border',lambda image,rect:
        (captures['count']>=2 and rect==clips[0].rectangle) if case=='delayed' else rect==clips[1].rectangle)
    if case=='delayed':
        assert driver.select(0)=='A'
        assert captures['count']==2
    else:
        with pytest.raises(BridgeError):driver.select(0)
        assert captures['count']==1
    assert len(clicks)==1
