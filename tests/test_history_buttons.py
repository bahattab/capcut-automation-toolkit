from pathlib import Path
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.vision import WindowsVision, View, Box
import capcut_windows.vision as module


@pytest.mark.parametrize('command',['undo','redo'])
@pytest.mark.parametrize('hovered',[False,True])
def test_history_uses_owned_button_instead_of_global_hotkey(tmp_path,command,hovered):
    driver=WindowsVision(Settings(tmp_path))
    suffix='-hover' if hovered else ''
    with Image.open(Path(module.__file__).with_name('templates')/f'capcut-9.4-{command}{suffix}.png') as template:
        image=Image.new('RGB',(1680,1050),'black')
        left=127 if command=='undo' else 164
        image.paste(template,(left,593))
        expected=Box(left,593,left+template.width,593+template.height)
    view=View(123,Box(3360,0,5040,1050),image)
    title=Box(720,12,880,25)
    calls=[]
    driver.require_profile=lambda *args:None
    driver.active_draft=lambda:'Disposable'
    driver.paused=lambda:True
    driver.capture=lambda:view
    driver.words=lambda *args,**kwargs:[]
    driver.recognize_label=lambda *args,**kwargs:title
    driver.point=lambda captured,box:calls.append(('guard',captured,box))
    driver.click_box=lambda captured,box:calls.append(('click',captured,box))
    driver.key=lambda *args,**kwargs:pytest.fail('History must avoid global hotkeys')
    assert driver.action(command)==command+'-requested'
    assert calls==[('guard',view,title),('click',view,expected)]
