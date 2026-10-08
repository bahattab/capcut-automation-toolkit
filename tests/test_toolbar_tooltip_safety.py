import itertools
import sys
from types import SimpleNamespace
from PIL import Image
import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box, Word


@pytest.mark.parametrize('case',['valid','foreign-process','wrong-action','cursor-moved','changed-pixels','reused-window-class'])
def test_toolbar_never_guesses_missing_glyph_even_with_tooltip_hints(tmp_path,monkeypatch,case):
    import capcut_windows.vision as module
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda view:module.editor_geometry(view)
    image=Image.new('RGB',(1680,1050),(38,38,38))
    image.putpixel((134,601),(200,200,200))
    view=View(1,Box(3360,0,5040,1050),image)
    absolute_tip=(3458,620,3534,637)
    reads=[]; moves=[]
    classes=[]
    def window_class(handle):
        classes.append(handle)
        return 'ChangedClass' if case=='reused-window-class' and len(classes)>1 else 'Qt622QWindowToolTipSaveBits'
    gui=SimpleNamespace(EnumWindows=lambda callback,arg:callback(2,arg),IsWindowVisible=lambda h:True,
                        GetClassName=window_class,GetWindowRect=lambda h:absolute_tip)
    process=SimpleNamespace(GetWindowThreadProcessId=lambda h:(0,900 if h==2 and case=='foreign-process' else 5036))
    cursor_reads=[]
    def cursor_position():
        cursor_reads.append(True)
        return (3495,601) if case=='cursor-moved' and len(cursor_reads)>1 else (3494,601)
    api=SimpleNamespace(GetCursorPos=cursor_position,SetCursorPos=lambda point:moves.append(point))
    monkeypatch.setitem(sys.modules,'win32gui',gui)
    monkeypatch.setitem(sys.modules,'win32process',process)
    monkeypatch.setitem(sys.modules,'win32api',api)
    monkeypatch.setitem(sys.modules,'pywinauto',SimpleNamespace(mouse=SimpleNamespace(move=lambda **kwargs:moves.append(kwargs))))
    def missing(*args):
        raise BridgeError('No exact glyph')
    monkeypatch.setattr(module,'template_box',missing)
    ticks=itertools.count()
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    driver.point=lambda captured,box:(3360+box.center[0],box.center[1])
    driver.capture=lambda:view
    def words(captured,region,**kwargs):
        reads.append(kwargs['scale'])
        label='Reset(Ctrl+Shift+Z)' if case=='wrong-action' else 'Undo(Ctrl+Z)'
        return [Word(label,95,Box(102,623,170,634),(1,1,1,1))]
    driver.words=words
    latest=image.copy()
    if case=='changed-pixels':
        latest.putpixel((104,624),(255,255,255))
    monkeypatch.setattr(module.ImageGrab,'grab',lambda **kwargs:latest)
    with pytest.raises(BridgeError):driver.toolbar_target('undo',view)
    assert moves==[] and reads==[]
