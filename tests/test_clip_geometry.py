from PIL import Image, ImageDraw
import pytest
from capcut_windows.errors import BridgeError
from capcut_windows.vision import Box, VisualClip, clip_bars, selection_border


def drawing(runs, color=(0,77,82)):
    image = Image.new('RGB',(200,30),(41,41,41))
    draw = ImageDraw.Draw(image)
    for left,right in runs:
        draw.rectangle((left,10,right-1,12),fill=color)
    return image


@pytest.mark.parametrize('selected',[False,True])
def test_all_boundaries_and_selected_color(selected):
    image=drawing([(22,78),(82,118)])
    if selected:
        ImageDraw.Draw(image).line((20,10,80,10),fill='white')
    assert clip_bars(image,Box(10,10,190,13),[(20,80),(80,120)])==[(22,78),(82,118)]


@pytest.mark.parametrize('runs,expected',[
    ([(22,78)],[(20,80),(80,120)]),
    ([(22,78),(82,118),(140,170)],[(20,80),(80,120)]),
    ([(28,78),(82,118)],[(20,80),(80,120)]),
    ([(22,68),(72,118)],[(20,80),(80,120)]),
    ([(22,118)],[(20,80),(80,120)]),
    ([(22,28)],[(20,30)]),
    ([(22,78),(82,118)],[(20,120),(80,120)]),
    ([(22,78)],[(0,80)]),
])
def test_ambiguous_narrow_scrolled_or_stale_geometry_rejected(runs,expected):
    with pytest.raises(BridgeError):
        clip_bars(drawing(runs),Box(10,10,190,13),expected)


def test_one_pixel_gap_is_preserved_and_isolated_playhead_ignored():
    image = drawing([(20,80),(81,120),(150,152)])
    assert clip_bars(image,Box(10,10,190,13),[(20,80),(81,120)])==[(20,80),(81,120)]


def test_unsupported_bar_color_is_rejected():
    with pytest.raises(BridgeError):
        clip_bars(drawing([(20,80)],(180,0,0)),Box(10,10,190,13),[(20,80)])


def test_unicode_names_are_explicitly_metadata_not_visual_identity():
    clip = VisualClip('مرحبا 😀',(20,10,80,25),0,Box(1,1,5,5))
    assert clip.name_source=='saved_metadata'


@pytest.mark.parametrize('shape',['horizontal','vertical','complete','narrow'])
def test_selection_requires_tall_connected_sides(shape):
    image=Image.new('RGB',(200,100),'black')
    draw=ImageDraw.Draw(image)
    rectangle=(20,20,80,80) if shape!='narrow' else (20,20,32,80)
    if shape in {'horizontal','complete','narrow'}:
        draw.line((rectangle[0],20,rectangle[2],20),fill='white')
    if shape in {'vertical','complete','narrow'}:
        for x in (rectangle[0],rectangle[2]):
            draw.line((x,20,x,80),fill='white')
    assert selection_border(image,rectangle)==(shape=='complete')
