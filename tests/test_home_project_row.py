import pytest
from PIL import Image
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word

@pytest.mark.parametrize('case',['valid','duplicate','prefix','uncertain','disagree','shift'])
def test_project_row_needs_unique_complete_name_and_independent_reads(tmp_path,case):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    column=Box(296,549,1292,1038);calls=[]
    def words(current,region,scale,psm,contrast=False,invert=False):
        assert current is view;calls.append((region,scale,psm))
        if psm==11:
            result=[Word('Full-Trial-Name',40,Box(308,755,438,765),(1,1,1,1))]
            if case=='duplicate':result.append(Word('Full-Trial-Name',40,Box(308,801,438,811),(1,1,2,1)))
            if case=='prefix':result[0]=Word('Full-Trial-Name Copy',95,Box(308,755,478,765),(1,1,1,1))
            return result
        assert region in {Box(296,745,1292,775),Box(300,745,446,775),Box(301,745,446,775)}
        name='Other-Name' if case=='disagree' and scale==3 else 'Full-Trial-Name'
        offset=5 if case=='shift' and scale==3 else 0
        return [Word(name,70 if case=='uncertain' else 95,Box(308+offset,755,438+offset,765),(1,1,1,1))]
    v.words=words
    if case=='valid':
        assert v.home_project_row(view,column,'Full-Trial-Name')==Box(308,755,438,765)
        assert [scale for _,scale,psm in calls if psm==7]==[4,3]
    else:
        with pytest.raises(BridgeError):v.home_project_row(view,column,'Full-Trial-Name')


def test_project_row_can_use_two_strong_contrast_reads_after_uncertain_normal_reads(tmp_path):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    calls=[]
    def words(current,region,scale,psm,contrast=False):
        calls.append((scale,psm,contrast))
        confidence=95 if psm==11 or contrast and scale in {3,2} else 80
        return [Word('Trial',confidence,Box(308,755,438,765),(1,1,1,1))]
    v.words=words
    assert v.home_project_row(view,Box(296,549,1292,1038),'Trial')==Box(308,755,438,765)
    assert calls[-1]==(2,7,True)


def test_project_row_can_confirm_tight_complete_name_at_two_distinct_scales(tmp_path):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    calls=[];tight=Box(300,745,446,775)
    def words(current,region,scale,psm,contrast=False):
        calls.append((region,scale,psm))
        confidence=95 if psm==11 or region==tight and scale in {4,2} else 70
        return [Word('Trial',confidence,Box(308,755,438,765),(1,1,1,1))]
    v.words=words
    assert v.home_project_row(view,Box(296,549,1292,1038),'Trial')==Box(308,755,438,765)
    assert calls[-1]==(tight,2,7)


def test_project_row_opposite_polarity_still_needs_different_scales_and_full_name(tmp_path):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    tight=Box(300,745,446,775);calls=[]
    def words(current,region,scale,psm,contrast=False,invert=False):
        calls.append((region,scale,invert))
        strong=psm==11 or region==tight and (scale==4 and not invert or scale==2 and invert)
        return [Word('Trial',95 if strong else 70,Box(308,755,438,765),(1,1,1,1))]
    v.words=words
    assert v.home_project_row(view,Box(296,549,1292,1038),'Trial')==Box(308,755,438,765)
    assert calls[-1]==(tight,2,True)


def test_project_row_one_pixel_blank_padding_fallback_preserves_full_name_and_scale_agreement(tmp_path):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    wide=Box(296,745,1292,775);shifted=Box(301,745,446,775);calls=[]
    def words(current,region,scale,psm,contrast=False,invert=False):
        calls.append((region,scale))
        strong=psm==11 or region==wide and scale==2 or region==shifted and scale==4
        return [Word('Trial',95 if strong else 70,Box(308,755,438,765),(1,1,1,1))]
    v.words=words
    assert v.home_project_row(view,Box(296,549,1292,1038),'Trial')==Box(308,755,438,765)
    assert calls[-1]==(shifted,4)
