from pathlib import Path
import sys
from types import SimpleNamespace
from PIL import Image
import pytest
import capcut_windows.vision as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box


@pytest.mark.parametrize('state',['play','pause','missing','ambiguous'])
def test_playback_requires_one_owned_native_control(tmp_path,state,monkeypatch):
    driver=WindowsVision(Settings(tmp_path))
    image=Image.new('RGB',(1680,1050),'black')
    for index,name in enumerate(('play','pause')):
        if state in {name,'ambiguous'}:
            with Image.open(Path(module.__file__).with_name('templates')/f'capcut-9.4-{name}.png') as icon:
                image.paste(icon,(872+index*30,551))
    view=View(1,Box(3360,0,5040,1050),image)
    driver.require_profile=lambda *args:None
    driver.active_draft=lambda:'Trial'
    driver.capture=lambda:view
    driver.words=lambda *args,**kwargs:[]
    driver.recognize_label=lambda *args,**kwargs:Box(720,12,880,25)
    driver.point=lambda *args:(4160,18)
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(SetCursorPos=lambda point:None,GetCursorPos=lambda:(4160,18)))
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    clicks=[]
    driver.click_box=lambda captured,box:clicks.append(box)
    driver.key=lambda *args:pytest.fail('Playback must use the verified native control')
    if state in {'play','pause'}:
        assert driver.action('play')==state+'-requested'
        assert len(clicks)==1
    else:
        with pytest.raises(BridgeError):driver.action('play')
        assert clicks==[]


def test_playback_rejects_title_changed_during_hover(tmp_path,monkeypatch):
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(3360,0,5040,1050),Image.new('RGB',(1680,1050),'black'))
    driver.require_profile=lambda *args:None
    driver.active_draft=lambda:'Trial'
    driver.capture=lambda:view
    driver.words=lambda *args,**kwargs:[]
    titles=iter([Box(720,12,880,25),Box(725,12,885,25)])
    driver.recognize_label=lambda *args,**kwargs:next(titles)
    driver.point=lambda *args:(4060,18)
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(SetCursorPos=lambda point:None,GetCursorPos=lambda:(4060,18)))
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    driver.click_box=lambda *args:pytest.fail('Changed project identity must prevent clicks')
    with pytest.raises(BridgeError,match='title moved'):
        driver.action('play')
