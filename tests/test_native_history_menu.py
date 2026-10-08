from PIL import Image
import pytest
import capcut_windows.vision as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word


@pytest.mark.parametrize('case',['valid','disabled','changed-project','project-after-menu','ocr-disagreement','bottom-extension','shifted-window'])
def test_native_history_menu_rejects_uncertain_or_disabled_items(tmp_path,monkeypatch,case):
    import win32api,win32gui,win32process
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda view:module.editor_geometry(view)
    image=Image.new('RGB',(1680,1050),'white')
    if case=='disabled':
        for x in range(250,280):
            for y in range(105,115):image.putpixel((x,y),(70,70,70))
    view=View(1,Box(3360,0,5040,1050),image)
    driver.require_profile=lambda *args:(9,5,0,4050)
    driver.active_draft=lambda:'Other' if case=='changed-project' else 'Trial'
    captures={'count':0}
    def capture():
        captures['count']+=1
        if captures['count']>1 and case in {'bottom-extension','shifted-window'}:
            return View(2,Box(3360 if case=='bottom-extension' else 3359,0,5040,1060),
                        Image.new('RGB',(1680,1060),'white'))
        return view
    driver.capture=capture
    driver.point=lambda *args:None
    phases=['Menu','Edit','Recovery']
    clicks=[]
    def recognize(*args,**kwargs):
        if case=='project-after-menu' and clicks:
            raise BridgeError('Project title changed after opening Menu')
        return Box(720,12,800,25)
    driver.recognize_label=recognize
    def words(captured,region,scale,**kwargs):
        if region.left==560:return []
        phase=len(clicks)
        label='Undo' if case=='ocr-disagreement' and phase==2 and scale==3 else phases[phase]
        return [Word(label,96,Box(250,105,280,115) if phase==2 else Box(100,12+phase*64,125,22+phase*64),(1,1,1,1))]
    driver.words=words
    driver.click_box=lambda *args:clicks.append(phases[len(clicks)])
    driver.key=lambda *args:pytest.fail('Native menu history must avoid global shortcuts')
    monkeypatch.setattr(win32api,'MonitorFromWindow',lambda *args:1)
    monkeypatch.setattr(win32api,'GetMonitorInfo',lambda *args:{'Monitor':(3360,0,5040,1050)})
    monkeypatch.setattr(win32gui,'GetWindowRect',lambda handle:view.box.tuple())
    monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda handle:(10,20))
    clock=iter(range(100))
    monkeypatch.setattr(module.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(module.time,'sleep',lambda *args:None)
    if case in {'valid','bottom-extension'}:
        driver.history_menu('redo','Trial')
        assert clicks==phases
    else:
        with pytest.raises(BridgeError):driver.history_menu('redo','Trial')
        assert clicks==([] if case in {'changed-project','shifted-window'} else phases[:1] if case=='project-after-menu' else phases[:2])
