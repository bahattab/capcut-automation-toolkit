from types import SimpleNamespace
from PIL import Image,ImageDraw
import pytest
import capcut_windows.vision as module
from capcut_windows.vision import WindowsVision,View,Box,shortcut_field
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['valid','extra-modifier','second-binding','clipped','unbounded'])
def test_shortcut_field_rejects_extra_or_clipped_key_content(case):
    image=Image.new('RGB',(200,40),(18,18,18));draw=ImageDraw.Draw(image)
    field=Box(10,10,190,30);pills=[Box(150,10,175,30)]
    draw.rectangle((155,15,169,25),fill='white')
    if case=='extra-modifier':draw.rectangle((110,15,130,25),fill='white')
    if case=='second-binding':draw.rectangle((177,15,180,25),fill='white')
    if case=='clipped':draw.rectangle((148,15,160,25),fill='white')
    if case=='unbounded':field=Box(-1,10,190,30)
    if case=='valid':shortcut_field(image,field,pills)
    else:
        with pytest.raises(BridgeError):shortcut_field(image,field,pills)


@pytest.mark.parametrize('case',['stable','other-selection','no-selection','changed-playhead','playing'])
def test_marker_rechecks_same_selection_and_paused_playhead_after_modal(tmp_path,monkeypatch,case):
    driver=WindowsVision(Settings(tmp_path));state={'modal_closed':False}
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    clips=[SimpleNamespace(index=0,rectangle=(0,0,10,10)),SimpleNamespace(index=1,rectangle=(20,0,30,10))]
    driver.require_profile=lambda *args:(9,5,0,4050)
    driver.active_draft=lambda:'Trial'
    driver.capture=lambda:view
    driver._clip_views=lambda:(view,clips)
    driver.point=lambda *args:(700,10)
    def paused():
        if state['modal_closed'] and case=='playing':raise BridgeError('Playback changed')
        return True
    driver.paused=paused
    driver.playhead=lambda:('00:00:00:01' if state['modal_closed'] and case=='changed-playhead' else '00:00:00:00','00:00:03:00')
    def binding(command,project):
        assert (command,project)==('marker','Trial')
        state['modal_closed']=True
        return 'm'
    driver.timeline_binding=binding
    def selected(image,rectangle):
        if state['modal_closed'] and case=='no-selection':return False
        wanted=1 if state['modal_closed'] and case=='other-selection' else 0
        return rectangle==clips[wanted].rectangle
    monkeypatch.setattr(module,'selection_border',selected)
    keys=[];driver.key=lambda key:keys.append(key)
    if case=='stable':assert driver.action('marker')=='marker-requested'
    else:
        with pytest.raises(BridgeError):driver.action('marker')
    assert keys==(['m'] if case=='stable' else [])
