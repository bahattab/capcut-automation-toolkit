from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word


@pytest.mark.parametrize('case',['base','suffix','spaced-suffix','wrong-project','zero','negative','path','uncertain','disagree','clipped'])
def test_export_filename_requires_project_family_and_two_confident_reads(tmp_path,case):
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(100,100,820,763),Image.new('RGB',(720,663)))
    names={'base':'Trial','suffix':'Trial(1)','spaced-suffix':'Trial (2)',
        'wrong-project':'Other(1)','zero':'Trial(0)','negative':'Trial(-1)',
        'path':'Trial/../file','uncertain':'Trial(1)','disagree':'Trial(1)','clipped':'Trial(1)'}
    calls=[]
    def words(captured,region,scale,**kwargs):
        confidence=70 if case=='uncertain' else 96
        text='Trial(2)' if case=='disagree' and scale==4 else names[case]
        return [Word(text,confidence,Box(472,96,704 if case=='clipped' else 611,107),(1,1,1,1))]
    driver.words=words
    driver.point=lambda *args:calls.append('fresh-owned-pixels')
    if case in {'base','suffix','spaced-suffix'}:
        assert driver.export_filename(view,'Trial')==(names[case],Box(472,96,611,107))
        assert calls==['fresh-owned-pixels']
    else:
        with pytest.raises(BridgeError):driver.export_filename(view,'Trial')
        assert calls==[]

@pytest.mark.parametrize('case',['agrees','uncertain','wrong-name','moved','confident-conflict'])
def test_filename_polarity_fallback_requires_confident_full_field_agreement(tmp_path,case):
    driver=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,720,663),Image.new('RGB',(720,663)))
    reads=[];points=[]
    def words(captured,region,scale,**kwargs):
        assert region==Box(464,90,704,112)
        invert=kwargs.get('invert',False);reads.append((scale,invert))
        name='Trial';confidence=95;offset=0
        if scale==4:
            name='Triai';confidence=95 if case=='confident-conflict' else 40
        if invert:
            if case=='wrong-name':name='Other'
            if case=='uncertain':confidence=80
            if case=='moved':offset=5
        if case=='uncertain' and not (scale==3 and not invert and kwargs.get('contrast')):
            confidence=80
        return [Word(name,confidence,Box(472+offset,96,511+offset,107),(1,1,1,1))]
    driver.words=words;driver.point=lambda *args:points.append(1)
    if case=='agrees':
        assert driver.export_filename(view,'Trial')[0]=='Trial'
        assert reads==[(3,False),(4,False),(3,True)] and points==[1]
    else:
        with pytest.raises(BridgeError):driver.export_filename(view,'Trial')
        assert points==[]

def test_filename_can_start_with_an_uncertain_primary_then_two_strong_reads(tmp_path):
    driver=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,720,663),Image.new('RGB',(720,663)))
    reads=[]
    def words(captured,region,scale,**kwargs):
        invert=kwargs.get('invert',False);reads.append((scale,invert))
        confidence=40 if scale==3 and not invert else 95
        return [Word('Trial',confidence,Box(472,96,511,107),(1,1,1,1))]
    driver.words=words;driver.point=lambda *args:None
    assert driver.export_filename(view,'Trial')[0]=='Trial'
    assert reads==[(3,False),(4,False),(3,True)]
