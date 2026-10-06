from types import SimpleNamespace
from PIL import Image
from capcut_windows.environment import Settings
from capcut_windows.vision import WindowsVision,View,Box
from capcut_windows.errors import BridgeError
import capcut_windows.drafts as drafts
import capcut_windows.environment as environment


def test_native_95_open_uses_verified_name_column_without_banner_ocr(tmp_path,monkeypatch):
    v=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    column=Box(296,549,1292,1038);events=[];opened=False
    monkeypatch.setattr(drafts,'DraftStore',lambda settings:SimpleNamespace(load=lambda name:{},listings=lambda:[{'name':'Trial'}]))
    monkeypatch.setattr(environment,'launch',lambda settings:events.append('launch'))
    def active():
        if opened:return 'Trial'
        raise BridgeError('Home has no active project')
    v.active_draft=active;v.prepare=lambda:events.append('prepare');v.capture=lambda:view
    v.require_profile=lambda feature:(9,5,0,4050)
    v.home_list=lambda:column
    def hover(box):
        assert box==(900,5,1000,25)
        events.append('neutral-hover')
    v.hover_box=hover
    def target(current,region,name):
        assert current is view and region==column and name=='Trial'
        events.append('verified-row');return Box(308,755,438,765)
    v.home_project_row=target
    def click(current,box,count):
        nonlocal opened
        assert current is view and box==Box(308,755,438,765) and count==2
        events.append('owned-click');opened=True
    v.click_box=click
    v.words=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('Unnecessary banner OCR'))
    v.open('Trial')
    assert events==['launch','prepare','neutral-hover','verified-row','owned-click']
