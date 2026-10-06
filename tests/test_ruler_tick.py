from PIL import Image,ImageDraw
import pytest
from capcut_windows.vision import Box,ruler_tick
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize('case',['valid','two-pixel','bright-neutral','antialiased-end','unequal-height','white','missing','two-ticks','broken','colored','short'])
def test_ruler_tick_requires_one_continuous_neutral_stroke(case):
    image=Image.new('RGB',(120,40),(38,38,38));draw=ImageDraw.Draw(image)
    if case!='missing':draw.line((96,10,96,14 if case=='short' else 20),fill=(20,90,90) if case=='colored' else (76,76,76))
    if case=='two-pixel':draw.line((97,10,97,20),fill=(75,75,75))
    if case=='bright-neutral':draw.line((96,10,96,20),fill=(113,113,113))
    if case=='antialiased-end':draw.line((97,10,97,19),fill=(80,80,80))
    if case=='unequal-height':draw.line((97,10,97,18),fill=(80,80,80))
    if case=='white':draw.line((96,10,96,20),fill=(220,220,220))
    if case=='two-ticks':draw.line((91,10,91,20),fill=(76,76,76))
    if case=='broken':image.putpixel((96,15),(38,38,38))
    label=Box(100,12,118,20)
    if case in {'valid','two-pixel','bright-neutral','antialiased-end'}:
        assert ruler_tick(image,label)==Box(96,10,98 if case in {'two-pixel','antialiased-end'} else 97,21)
    else:
        with pytest.raises(BridgeError):ruler_tick(image,label)
