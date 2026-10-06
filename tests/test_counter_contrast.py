from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Word, Box


@pytest.mark.parametrize('agree',[True,False])
def test_counter_contrast_fallback_still_requires_dual_scale_agreement(tmp_path,monkeypatch,agree):
    import capcut_windows.drafts as drafts
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    driver.require_profile=lambda *args:None
    driver.active_draft=lambda:'Trial'
    driver.capture=lambda:view
    monkeypatch.setattr(drafts.DraftStore,'load',lambda *args:{'fps':24})
    reads=[]; points=[]
    def words(captured,region,scale,psm,contrast):
        reads.append((scale,contrast))
        if not contrast:
            return []
        current=region.left==469
        value='00:00:01:00' if current else '00:00:03:00'
        if not agree and current and scale==3:
            value='00:00:01:01'
        return [Word(value,95,Box(472,552,535,562) if current else Box(548,552,613,562),(1,1,1,1))]
    driver.words=words
    driver.point=lambda captured,box:points.append((captured,box))
    if agree:
        assert driver.playhead()==('00:00:01:00','00:00:03:00')
        assert points==[(view,Box(472,552,613,562))]
    else:
        with pytest.raises(BridgeError):
            driver.playhead()
        assert points==[]
    assert (4,True) in reads and (3,True) in reads
