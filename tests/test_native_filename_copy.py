from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word
import capcut_windows.clipboard as clipboard


@pytest.mark.parametrize('case',['base','suffix','wrong-name','wrong-title','wrong-size','wrong-version','uncertain-label','label-disagreement'])
def test_native_filename_copy_requires_owned_profile_label_and_project_name(tmp_path,monkeypatch,case):
    import win32gui,win32process
    driver=WindowsVision(Settings(tmp_path))
    size=(720,633) if case=='wrong-size' else (720,663)
    view=View(1,Box(0,0,*size),Image.new('RGB',size))
    driver.require_profile=lambda feature:(9,4,0,1) if case=='wrong-version' else (9,5,0,4050)
    monkeypatch.setattr(win32gui,'GetWindowText',lambda handle:'Export-Other' if case=='wrong-title' else 'Export-Trial')
    monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda handle:(1,123))
    events=[]
    def words(captured,region,scale,**kwargs):
        offset=5 if case=='label-disagreement' and scale==3 else 0
        return [Word('Name',70 if case=='uncertain-label' else 96,Box(360+offset,96,390+offset,105),(1,1,1,1))]
    driver.words=words
    driver.point=lambda *args:events.append('point')
    driver.click_box=lambda *args:events.append('click')
    driver.key=lambda combo:events.append(combo)
    def copy(callback,pid):
        assert pid==123
        callback()
        return 'Other' if case=='wrong-name' else ('Trial (2)' if case=='suffix' else 'Trial')
    monkeypatch.setattr(clipboard,'copy_native_text',copy)
    if case in {'base','suffix'}:
        text,box=driver.export_filename_copy(view,'Trial')
        assert text==('Trial' if case=='base' else 'Trial (2)')
        assert box==Box(680,95,689,106)
        assert events==['point','click','ctrl+a','ctrl+c','point','point']
    else:
        with pytest.raises(BridgeError):driver.export_filename_copy(view,'Trial')
        if case!='wrong-name':assert not events
