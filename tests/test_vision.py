"""Optical recognition uncertainty must never become an unchecked mouse target."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from capcut_windows.vision import Box,Word,View,WindowsVision,label_box,identifier_box,unique_project_name,verify_timing,clock_pair,ruler_mapping,parse_tsv,template_box,text_bands
import capcut_windows.vision as vision_module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


def word(text: str,x: int,confidence: float = 95,line: int = 1) -> Word:
    return Word(text,confidence,Box(x,20,x+30,35),(1,1,1,line))


def test_repeated_export_buttons_require_explicit_region() -> None:
    with pytest.raises(BridgeError,match='ambiguous'):
        label_box([word('Export',10),word('Export',60,line=2)],'Export')


def test_uncertain_text_cannot_be_clicked() -> None:
    with pytest.raises(BridgeError,match='uncertain'):
        label_box([word('Export',10,42)],'Export')


def test_phrase_must_not_cross_unrelated_lines() -> None:
    with pytest.raises(BridgeError):
        label_box([word('Create',10),word('project',50,line=2)],'Create project')


def test_phrase_boxes_follow_actual_words() -> None:
    assert label_box([word('Create',10),word('project',50)],'CREATE project')==Box(10,20,80,35)


def test_project_prefix_cannot_identify_another_project() -> None:
    with pytest.raises(BridgeError):
        identifier_box([word('Demo',10),word('Other',45)],'Demo')


def test_case_insensitive_duplicate_project_titles_are_ambiguous() -> None:
    with pytest.raises(BridgeError):
        identifier_box([word('Demo',10),word('DEMO',10,line=2)],'Demo')


def test_large_gap_does_not_hide_a_title_suffix() -> None:
    with pytest.raises(BridgeError):
        identifier_box([word('Demo',10),word('Other',110)],'Demo')


@pytest.mark.parametrize('names',[['Demo','Demo Other'],['Demo','DEMO'],['Demo','Demo\nOther']])
def test_known_duplicate_wrapped_or_clipped_prefix_is_rejected(names: list[str]) -> None:
    with pytest.raises(BridgeError):
        unique_project_name('Demo',names)


def test_open_keeps_ocr_view_for_stale_pixel_guard(monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    import capcut_windows.drafts as drafts
    import capcut_windows.environment as environment
    driver=WindowsVision(Settings(tmp_path))
    recognized=View(11,Box(0,0,100,100),Image.new('RGB',(100,100),'black'))
    changed=View(11,Box(0,0,100,100),Image.new('RGB',(100,100),'white'))
    captures=iter([recognized,changed])
    monkeypatch.setattr(drafts.DraftStore,'load',lambda self,name:None)
    monkeypatch.setattr(drafts.DraftStore,'listings',lambda self:[{'name':'Demo'}])
    monkeypatch.setattr(environment,'launch',lambda settings:None)
    monkeypatch.setattr(driver,'prepare',lambda:None)
    def not_active():
        raise BridgeError('Home is not an active project')
    monkeypatch.setattr(driver,'active_draft',not_active)
    clock=iter([0,1000])
    monkeypatch.setattr(vision_module.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(driver,'capture',lambda:next(captures))
    monkeypatch.setattr(driver,'words',lambda *args,**kwargs:[word('Demo',10)])
    def guarded_click(view: View,box: Box,clicks: int) -> None:
        assert view is recognized
        raise BridgeError('The visual control changed since recognition. No input was sent.')
    monkeypatch.setattr(driver,'click_box',guarded_click)
    with pytest.raises(BridgeError,match='changed since recognition'):
        driver.open('Demo')


def test_ocr_coordinates_are_mapped_to_crop_and_scale() -> None:
    tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t2\t1\t3\t9\t12\t31\t17\t93.5\tExport\n'
    words=parse_tsv(tsv,3,(100,200))
    assert words[0].box==Box(103,204,114,210)
    assert words[0].line==(1,2,1,3)


def test_nonfinite_confidence_is_ignored() -> None:
    tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t2\t1\t3\t9\t12\t31\t17\tnan\tExport\n'
    assert parse_tsv(tsv)==[]


@pytest.mark.parametrize('index',[0,1,2,3])
@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf'),0])
def test_invalid_expected_or_probed_timing_cannot_pass(index: int,value: float) -> None:
    values=[24,3,24,3.018]
    values[index]=value
    with pytest.raises(BridgeError):
        verify_timing(*values)


def test_valid_container_audio_padding_is_within_two_video_frames() -> None:
    verify_timing(24,3,24,3.018)


def test_player_clock_is_ordered_by_position_and_validates_frames() -> None:
    assert clock_pair([word('00:00:03:00',80,83),word('00:00:01:12',10,83)],24)[:2]==('00:00:01:12','00:00:03:00')


@pytest.mark.parametrize('case',['uncertain','different-lines','duplicate','invalid-frames','beyond-end','source-burn'])
def test_ambiguous_or_invalid_counter_evidence_is_rejected(case: str) -> None:
    current = word('00:00:00:00',10,74 if case=='uncertain' else 90)
    total = word('00:00:03:00',80,line=2 if case=='different-lines' else 1)
    if case=='invalid-frames':
        current=word('00:00:00:24',10)
    elif case=='beyond-end':
        current=word('00:00:04:00',10)
    elif case=='source-burn':
        current=word('00:00:01.000',10)
    words=[current,total]
    if case=='duplicate':
        words.append(word('00:00:00:00',130,line=2))
    with pytest.raises(BridgeError):
        clock_pair(words,24)


def ruler_tick(seconds: int,x: int,line: int) -> list[Word]:
    key=(1,line,1,1)
    return [Word('|',90,Box(x,20,x+2,30),key),
            Word(f'00:{seconds:02}',90,Box(x+5,20,x+35,30),key)]


def test_ruler_geometry_comes_from_actual_labeled_ticks() -> None:
    origin,spacing,y=ruler_mapping(ruler_tick(2,508,1)+ruler_tick(3,671,2)+ruler_tick(4,834,3))
    assert (origin,spacing,y)==(183,163,25)


@pytest.mark.parametrize('case',['duplicate-time','nonlinear','reverse','missing-tick','two-only'])
def test_invalid_ruler_geometry_is_not_used_for_mouse_input(case: str) -> None:
    words=ruler_tick(2,508,1)+ruler_tick(3,671,2)
    if case=='duplicate-time':
        words+=ruler_tick(2,834,3)
    elif case=='nonlinear':
        words+=ruler_tick(4,900,3)
    elif case=='reverse':
        words=ruler_tick(2,671,1)+ruler_tick(3,508,2)
    elif case=='missing-tick':
        words=[item for item in words if item.text!='|']
    with pytest.raises(BridgeError):
        ruler_mapping(words)


@pytest.mark.parametrize('case',['fourth-batch','reverse-step','no-step','moving-at-target','changed-project','zero','end'])
def test_seek_verifies_effects_before_reporting_success(case: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    import capcut_windows.drafts as drafts
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setattr(driver,'require_profile',lambda *args:None)
    monkeypatch.setattr(driver,'active_draft',lambda:'Demo')
    monkeypatch.setattr(drafts.DraftStore,'load',lambda self,name:{'fps':24})
    monkeypatch.setattr(driver,'paused',lambda:True)
    target=0 if case=='zero' else 3 if case=='end' else 1.5
    frames={'fourth-batch':[0,0,1,2,3,4,5,6,7,36,36],
            'reverse-step':[0,24,23], 'no-step':[0,24,24],
            'moving-at-target':[36,37], 'changed-project':[0,24],
            'zero':[0,0], 'end':[72,72]}[case]
    samples=iter(frames)
    def read() -> tuple[str,str]:
        frame=next(samples)
        return f'00:00:{frame//24:02}:{frame%24:02}','00:00:03:00'
    monkeypatch.setattr(driver,'playhead',read)
    view=View(11,Box(0,0,1680,1050),Image.new('RGB',(1680,1050),'black'))
    monkeypatch.setattr(driver,'capture',lambda:view)
    monkeypatch.setattr(driver,'words',lambda *args,**kwargs:ruler_tick(2,508,1)+ruler_tick(3,671,2)+ruler_tick(4,834,3))
    monkeypatch.setattr(driver,'recognize_label',lambda *args,**kwargs:Box(10,10,60,30))
    points={'count':0}
    def guard(*args: object) -> tuple[int,int]:
        points['count']+=1
        if case=='changed-project' and points['count']==2:
            raise BridgeError('The title changed; no input was sent.')
        return 20,20
    monkeypatch.setattr(driver,'point',guard)
    keys: list[tuple[str,int]]=[]
    monkeypatch.setattr(driver,'key',lambda key,times:keys.append((key,times)))
    monkeypatch.setattr(driver,'click_box',lambda *args:None)
    if case in {'fourth-batch','zero','end'}:
        assert driver.seek(target,24)==target
        if case=='fourth-batch':
            assert keys[-1]==('right',29)
    else:
        with pytest.raises(BridgeError):
            driver.seek(target,24)
        if case=='changed-project':
            assert keys==[]


@pytest.mark.parametrize('change',['none','inside','outside','scale','window'])
def test_ocr_cache_requires_identical_source_pixels_and_configuration(change: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setattr(driver,'tesseract',lambda:tmp_path/'tesseract.exe')
    calls={'count':0}
    tsv='level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t4\t4\t12\t12\t95\tExport\n'
    def run(*args: object,**kwargs: object) -> SimpleNamespace:
        calls['count']+=1
        return SimpleNamespace(stdout=tsv)
    monkeypatch.setattr(vision_module.subprocess,'run',run)
    image=Image.new('RGB',(50,50),'black')
    first=View(11,Box(0,0,50,50),image)
    region=Box(0,0,20,20)
    driver.words(first,region,scale=4)
    second=image.copy()
    if change in {'inside','outside'}:
        second.putpixel((5,5) if change=='inside' else (40,40),(255,255,255))
    view=View(12 if change=='window' else 11,Box(0,0,50,50),second)
    driver.words(view,region,scale=3 if change=='scale' else 4)
    assert calls['count']==(1 if change in {'none','outside'} else 2)


@pytest.mark.parametrize('version,controls,accepted',[
    ((9,4,0,4015),'editor',True),((9,5,0,1),'editor',False),
    ((9,5,0,4050),'editor',False),((9,5,0,4050),'playback',True),
    ((9,5,0,4050),'seek',True),((9,5,0,4050),'clips',True),
    ((9,5,0,4050),'split',True),((9,5,0,4050),'history',True),
    ((9,5,0,4050),'trim',True),((9,5,0,4050),'delete',True),
    ((9,5,0,4050),'export',True),((9,5,0,4050),'home',True),
    ((9,5,0,4050),'unknown',False)])
def test_profile_uses_file_version_instead_of_directory_name(version: tuple[int,int,int,int],controls: str,accepted: bool,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    driver=WindowsVision(Settings(tmp_path,tmp_path/'9.4.0.4015'/'CapCut.exe'))
    monkeypatch.setitem(sys.modules,'win32api',SimpleNamespace(GetFileVersionInfo=lambda *args:{
        'FileVersionMS':version[0]*65536+version[1],'FileVersionLS':version[2]*65536+version[3]}))
    if accepted:
        driver.require_profile(controls)
    else:
        with pytest.raises(BridgeError):
            driver.require_profile(controls)


@pytest.mark.parametrize('change',['focus','resize','occlusion','pixels','none'])
def test_visual_target_requires_current_owned_unchanged_evidence(change: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setattr(driver,'foreground',lambda restore=True:12 if change=='focus' else 11)
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(
        GetWindowRect=lambda handle:(0,0,20,20) if change=='resize' else (0,0,10,10),
        WindowFromPoint=lambda point:99,GetAncestor=lambda handle,flag:11))
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda handle:(0,999 if change=='occlusion' else 7)))
    monkeypatch.setattr(vision_module,'processes',lambda:[SimpleNamespace(pid=7)])
    monkeypatch.setattr(vision_module.ImageGrab,'grab',lambda **kwargs:Image.new('RGB',(10,10),'white' if change=='pixels' else 'black'))
    view=View(11,Box(0,0,10,10),Image.new('RGB',(10,10),'black'))
    if change=='none':
        assert driver.point(view,Box(1,1,5,5))==(3,3)
    else:
        with pytest.raises(BridgeError):
            driver.point(view,Box(1,1,5,5))


def icon(background: str) -> Image.Image:
    image=Image.new('RGB',(6,6),background)
    for point in ((1,1),(1,4),(4,1),(4,4)):
        image.putpixel(point,(255,255,255))
    return image


def test_icon_geometry_survives_hover_background() -> None:
    image=Image.new('RGB',(20,20),'black')
    image.paste(icon('#404040'),(8,7))
    assert template_box(image,icon('black'),Box(0,0,20,20))==Box(8,7,14,13)


def test_duplicate_icons_are_not_a_unique_control() -> None:
    image=Image.new('RGB',(20,20),'black')
    image.paste(icon('black'),(1,1)); image.paste(icon('black'),(10,10))
    with pytest.raises(BridgeError,match='ambiguous'):
        template_box(image,icon('black'),Box(0,0,20,20))


def test_actual_ink_rows_are_used_instead_of_ocr_blank_padding() -> None:
    image=Image.new('RGB',(60,30),'black')
    for y in range(15,22):
        for x in range(10,31):
            image.putpixel((x,y),(220,220,220))
    bands=text_bands(image,Box(8,2,35,24))
    assert len(bands)==1
    assert bands[0].top==12 and bands[0].bottom==25


@pytest.mark.parametrize('case',['agreement','different','uncertain','ambiguous'])
def test_identifier_refinement_requires_exact_consensus(case: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    name='AMA-Windows-Test-1005'
    driver=WindowsVision(Settings(tmp_path))
    view=View(11,Box(0,0,100,100),Image.new('RGB',(100,100),'black'))
    coarse=[word(name,10,62)]
    if case=='ambiguous':
        coarse.append(word(name,50,62,line=2))
    monkeypatch.setattr(vision_module,'text_bands',lambda image,box:[Box(10,10,80,40)])
    def recognize(view: View,region: Box,scale: int,psm: int) -> list[Word]:
        text='1003' if case=='different' and scale==3 else name
        confidence=40 if case=='uncertain' else 81
        return [word(text,10,confidence)]
    monkeypatch.setattr(driver,'words',recognize)
    if case=='agreement':
        assert driver.recognize_label(view,coarse,name)==Box(10,20,40,35)
    else:
        with pytest.raises(BridgeError):
            driver.recognize_label(view,coarse,name)


@pytest.mark.parametrize('case',['valid','covered','wrong-caption','wrong-readback'])
def test_native_folder_picker_requires_exact_path_and_owned_button(case: str,monkeypatch: pytest.MonkeyPatch,tmp_path: Path) -> None:
    import pywinauto
    import pywinauto.mouse
    clicks: list[tuple[int,int]] = []
    value = {'text':''}
    field = SimpleNamespace(is_visible=lambda:True,is_enabled=lambda:True,
        set_edit_text=lambda text:value.update(text=text),
        window_text=lambda:'another directory' if case=='wrong-readback' else value['text'])
    button = SimpleNamespace(handle=22,is_visible=lambda:True,is_enabled=lambda:True,
        window_text=lambda:'Delete' if case=='wrong-caption' else '&Select Folder',
        rectangle=lambda:SimpleNamespace(left=0,top=0,right=20,bottom=20))
    dialog = SimpleNamespace(child_window=lambda **kwargs:SimpleNamespace(
        wrapper_object=lambda:field if kwargs['control_id']==1152 else button))
    application = SimpleNamespace(connect=lambda **kwargs:SimpleNamespace(window=lambda **kwargs:dialog))
    monkeypatch.setattr(pywinauto,'Application',lambda **kwargs:application)
    def physical(point,guard):
        guard()
        clicks.append(point)
    monkeypatch.setattr(vision_module,'physical_click',physical)
    monkeypatch.setitem(sys.modules,'win32gui',SimpleNamespace(GetClassName=lambda handle:'#32770',
        GetWindowText=lambda handle:'Select exporting path',
        WindowFromPoint=lambda point:99 if case=='covered' else 22,
        GetAncestor=lambda handle,flag:11,IsWindowVisible=lambda handle:False))
    driver=WindowsVision(Settings(tmp_path))
    monkeypatch.setattr(driver,'foreground',lambda restore=True:11)
    if case=='wrong-caption':
        clock = iter([0,16])
        monkeypatch.setattr(vision_module.time,'monotonic',lambda:next(clock))
    if case=='valid':
        assert driver.export_folder(str(tmp_path))==str(tmp_path.resolve())
        assert clicks==[(10,10)]
    else:
        with pytest.raises(BridgeError):
            driver.export_folder(str(tmp_path))
        assert clicks==[]
