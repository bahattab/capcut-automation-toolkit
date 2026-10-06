import sys
from types import SimpleNamespace
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision,View,Box,Word,physical_wheel


@pytest.mark.parametrize('case',['up','down','drift','ownership-change','invalid'])
def test_physical_wheel_never_uses_normalized_movement_or_unowned_input(monkeypatch,case):
    cursor={'position':(0,0)}
    events=[]
    def move(point):cursor['position']=(point[0]+1,point[1]) if case=='drift' else point
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(SetCursorPos=move,
        GetCursorPos=lambda:cursor['position'],mouse_event=lambda *args:events.append(args)))
    checks={'count':0}
    def guard():
        checks['count']+=1
        if case=='ownership-change' and checks['count']==2:raise BridgeError('Covered by another window')
    steps=-3 if case=='down' else 0 if case=='invalid' else 2
    if case in {'up','down'}:
        physical_wheel((4100,700),guard,steps)
        assert events==[(0x0800,0,0,steps*120)]
        assert checks['count']==2
    else:
        with pytest.raises(BridgeError):physical_wheel((4100,700),guard,steps)
        assert events==[]


@pytest.mark.parametrize('point',[(5039.6,500),(3359.6,500),(float('nan'),500),(True,500),(5000,1050)])
def test_absolute_coordinates_are_validated_after_rounding(tmp_path,point):
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(3360,0,5040,1050),Image.new('RGB',(1680,1050)))
    if point==(3359.6,500):
        assert driver.absolute_pixel(view,*point)==Box(0,500,1,501)
    else:
        with pytest.raises(BridgeError):driver.absolute_pixel(view,*point)


def test_inventory_reports_ocr_text_without_fabricated_native_ids(tmp_path):
    driver=WindowsVision(Settings(tmp_path))
    view=View(1,Box(3360,0,5040,1050),Image.new('RGB',(1680,1050)))
    driver.capture=lambda:view
    driver.words=lambda *args,**kwargs:[Word('Media',96,Box(16,60,50,72),(1,1,1,1)),
        Word('uncertain',40,Box(500,200,560,220),(1,2,1,1))]
    rows=driver.elements('media')
    assert len(rows)==1
    assert rows[0].name=='Media' and rows[0].rectangle==(3376,60,34,12)
    assert rows[0].automation_id=='' and rows[0].kind=='Text' and rows[0].text_source=='ocr'
