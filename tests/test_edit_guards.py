from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box, VisualClip


@pytest.mark.parametrize('case',['expected-project','changed-project','multiple-selected','wrong-index'])
def test_native_edits_stop_before_input_on_identity_or_selection_changes(tmp_path,monkeypatch,case):
    import capcut_windows.vision as module
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    clips=[VisualClip('synthetic.mp4',(183,800,509,876),0,Box(720,12,880,25)),
           VisualClip('synthetic.mp4',(509,800,672,876),1,Box(720,12,880,25))]
    names=iter(['Trial','Changed'] if case=='changed-project' else ['Trial','Trial'])
    driver.require_profile=lambda *args:None
    driver.active_draft=lambda:next(names)
    driver.paused=lambda:True
    driver._clip_views=lambda:(view,clips)
    driver.click_box=lambda *args:pytest.fail('No editing input may follow an identity/selection mismatch')
    monkeypatch.setattr(module,'selection_border',lambda image,rectangle:case=='multiple-selected' or rectangle==clips[0].rectangle)
    kwargs={'expected_draft':'Other'} if case=='expected-project' else {'expected_index':1} if case=='wrong-index' else {}
    with pytest.raises(BridgeError):
        driver.action('delete',**kwargs)
