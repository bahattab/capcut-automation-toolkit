from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word

@pytest.mark.parametrize('case',['valid','wrong-fps','weak','heading','row','geometry','size','version','title','foreign'])
def test_fps30_requires_two_exact_owned_row_readings(tmp_path,monkeypatch,case):
    import win32gui
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(0,0,720,663),Image.new('RGB',(721,663) if case=='size' else (720,663)))
    monkeypatch.setattr(win32gui,'GetWindowText',lambda handle:'Other' if case=='title' else 'Export-Trial')
    driver.require_profile=lambda *args:(9,4,0,3696) if case=='version' else (9,5,0,4050)
    calls=[]
    def words(captured,region,scale,**kwargs):
        assert kwargs=={'psm':7,'contrast':True}
        if region.left==350:
            return [Word('Wrong' if case=='heading' else 'Frame',96,Box(360,378,391,388),(1,1,1,1)),Word('rate',96,Box(394,378,415,388),(1,1,1,1))]
        offset=5 if case=='geometry' and scale==3 else 0
        y=390 if case=='row' else 378
        return [Word('24fps' if case=='wrong-fps' else '30fps',80 if case=='weak' else 96,Box(472+offset,y,503+offset,y+11),(1,1,1,1))]
    driver.words=words
    def point(*args):
        if case=='foreign':raise BridgeError('Changed owner')
        calls.append(1)
    driver.point=point
    if case=='valid':
        driver.verify_export_fps30(view)
        assert calls==[1,1]
    else:
        with pytest.raises(BridgeError):driver.verify_export_fps30(view)
        assert calls==[]
