from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box, VisualClip


@pytest.mark.parametrize('case',['valid','lost-selection','changed-project'])
def test_delete_clears_keyframe_context_and_rechecks_clip_identity(tmp_path,monkeypatch,case):
    import capcut_windows.vision as module
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    clip=VisualClip('trial.mp4',(183,800,509,876),0,Box(720,12,880,25))
    phases=[]; clicks=[]
    driver.require_profile=lambda *args:None
    driver.paused=lambda:True
    driver.active_draft=lambda:'Other' if phases and case=='changed-project' else 'Trial'
    driver._clip_views=lambda:(view,[clip])
    monkeypatch.setattr(module,'selection_border',lambda *args:not(phases and case=='lost-selection'))
    driver.select=lambda index:phases.append(index)
    button=Box(307,593,323,609)
    driver.toolbar_target=lambda command,captured:(captured,button)
    driver.point=lambda *args:None
    driver.click_box=lambda captured,target:clicks.append(target)
    if case=='valid':
        assert driver.action('delete',expected_index=0,expected_draft='Trial')=='delete-requested'
        assert clicks==[button]
    else:
        with pytest.raises(BridgeError):driver.action('delete',expected_index=0,expected_draft='Trial')
        assert clicks==[]
    assert phases==[0]
