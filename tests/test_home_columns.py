import pytest
from capcut_windows.errors import BridgeError
from capcut_windows.vision import Box, Word, View, WindowsVision, home_name_region
from capcut_windows.environment import Settings
from PIL import Image


@pytest.mark.parametrize('case',['valid','reversed','different-row','duplicate-name','missing-duration'])
def test_native_home_column_excludes_metadata_and_rejects_ambiguous_headers(case):
    projects=Box(240,492,300,504)
    words=[Word('Name',95,Box(300,532,330,545),(1,1,1,1)),
           Word('Size',95,Box(1304,532,1326,545),(1,1,1,1)),
           Word('Duration',95,Box(1424,533,1468,543),(1,1,1,1))]
    if case=='reversed':words[1]=Word('Size',95,Box(250,532,272,545),(1,1,1,1))
    if case=='different-row':words[2]=Word('Duration',95,Box(1424,550,1468,560),(1,1,1,1))
    if case=='duplicate-name':words.append(Word('Name',95,Box(500,532,530,545),(1,2,1,1)))
    if case=='missing-duration':words=words[:2]
    if case=='valid':
        assert home_name_region(words,projects,1680,1050)==Box(296,549,1292,1038)
    else:
        with pytest.raises(BridgeError):home_name_region(words,projects,1680,1050)


@pytest.mark.parametrize('size,heading_top',[((1680,1050),75),((1680,1050),335),((1680,1050),492),
                                           ((1680,1050),850),((1600,900),694)])
def test_home_list_tracks_heading_after_native_page_scroll(tmp_path,size,heading_top):
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(0,0,*size),Image.new('RGB',size))
    projects=Box(240,heading_top,300,heading_top+12)
    headers=[Word('Name',95,Box(300,heading_top+40,330,heading_top+53),(1,1,1,1)),
             Word('Size',95,Box(1304,heading_top+40,1326,heading_top+53),(1,1,1,1)),
             Word('Duration',95,Box(1424,heading_top+41,1468,heading_top+51),(1,1,1,1))]
    driver.require_profile=lambda feature:(9,5,0,4050)
    driver.capture=lambda:view
    driver.point=lambda current,box:box.center
    def words(current,region,**options):
        candidates=headers if options.get('psm')==11 else [Word('Projects',95,projects,(1,1,1,1))]
        for word in candidates:
            assert region.left<=word.box.left<word.box.right<=region.right
            assert region.top<=word.box.top<word.box.bottom<=region.bottom
        return candidates
    driver.words=words
    assert driver.home_list()==Box(296,heading_top+57,1292,size[1]-12)
