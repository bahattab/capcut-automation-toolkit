import json
from pathlib import Path
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box, Word


@pytest.mark.parametrize('case',['occluded-wrong-third-digit','shifted-reading','one-reading'])
def test_native_ruler_regression_requires_independent_consistent_three_anchor_readings(tmp_path,case):
    fixture=json.loads((Path(__file__).parent/'fixtures/native-ruler.json').read_text())
    driver=WindowsVision(Settings(tmp_path))
    def words(view,region,scale,contrast):
        row=next(row for row in fixture if row['scale']==scale and row['contrast']==contrast)
        selected=row['words']
        # A playhead can obscure the middle anchor, leaving two plausible but
        # incorrect anchors when OCR reads 30 as 50. Two alone must never pass.
        if not contrast and scale==4:selected=[word for word in selected if word['line'][1]!=3]
        result=[]
        for word in selected:
            box=Box(*word['box'])
            confidence=word['conf']
            if case=='shifted-reading' and contrast and scale==4:
                box=Box(box.left+5,box.top,box.right+5,box.bottom)
            if case=='one-reading' and contrast:confidence=40
            result.append(Word(word['text'],confidence,box,tuple(word['line'])))
        return result
    driver.words=words
    guards=[]
    driver.point=lambda *args:guards.append(True)
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    if case=='occluded-wrong-third-digit':
        origin,spacing,y=driver.ruler(view)
        for seconds,x in ((0,183),(10,427),(20,671),(30,916),(50,1405)):
            assert abs(origin+seconds*spacing-x)<=1
        assert y==626 and guards==[True]
    else:
        with pytest.raises(BridgeError):driver.ruler(view)
        assert guards==[]
