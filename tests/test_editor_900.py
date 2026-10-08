from pathlib import Path

from PIL import Image
import pytest

import capcut_windows.vision as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import Box, View, Word, WindowsVision, editor_geometry


@pytest.mark.parametrize('case',['initial','reopened','missing','duplicate-initial','duplicate-reopened','both'])
def test_cover_variants_remain_unique_across_the_whole_measured_region(case):
    canvas=Image.new('RGB',(1616,916),'black')
    templates=Path(module.__file__).with_name('templates')
    names=('capcut-9.5-cover-900.png','capcut-9.5-cover-900-reopened.png')
    for index,name in enumerate(names):
        if case in {('initial','reopened')[index],'duplicate-'+('initial','reopened')[index],'both'}:
            with Image.open(templates/name) as icon:
                canvas.paste(icon,(137,620+index*95))
                if case.startswith('duplicate'):canvas.paste(icon,(137,805))
    matches=set()
    for name in names:
        with Image.open(templates/name) as icon:
            matches.update(module.template_matches(canvas,icon,Box(130,570,195,900)))
    assert len(matches)==(0 if case=='missing' else 2 if case.startswith('duplicate') or case=='both' else 1)


@pytest.mark.parametrize('case',['valid','raster-rounding','version','size','title','missing','cloud','duplicate','uncertain','moved','conflict','pixels','scroll-endpoint'])
def test_local_export_footer_requires_complete_measured_profile(tmp_path,monkeypatch,case):
    import win32gui
    driver=WindowsVision(Settings(tmp_path))
    driver.require_profile=lambda *args:(9,4,0,4015) if case=='version' else (9,5,0,4050)
    monkeypatch.setattr(win32gui,'GetWindowText',lambda handle:'CapCut' if case=='title' else 'Export-Trial')
    size=(720,664) if case=='size' else (720,663)
    view=View(1,Box(440,118,440+size[0],118+size[1]),Image.new('RGB',size))
    with Image.open(Path(module.__file__).with_name('templates')/'capcut-9.5-local-export-footer.png') as template:
        view.image.paste(template,(345,180))
    if case in {'pixels','scroll-endpoint'}:
        view.image.putpixel((699,570) if case=='scroll-endpoint' else (450,540),(0,255,255))
    if case=='raster-rounding':
        r,g,b=view.image.getpixel((450,540))
        view.image.putpixel((450,540),(r,g,b+1))
    points=[]
    driver.point=lambda *args:points.append(True)
    def words(captured,region,scale,**kwargs):
        if region==Box(345,240,690,588):
            return [Word('Sync',99,Box(360,562,390,572),(1,1,1,1))] if case=='cloud' else []
        labels={249:'Audio',342:'Export GIF',436:'Captions',555:'Check copyright?'}
        if case=='missing' and region.top==436:return []
        offset=10 if case=='moved' else 5 if case=='conflict' and scale==3 else 0
        tokens=labels[region.top].split()
        result=[Word(token,70 if case=='uncertain' else 99,
                     Box(region.left+i*25,region.top+5+offset,region.left+i*25+20,region.top+15+offset),
                     (1,1,1,1)) for i,token in enumerate(tokens)]
        if case=='duplicate':
            result.extend(Word(word.text,word.confidence,word.box,(1,1,1,2)) for word in list(result))
        return result
    driver.words=words
    if case in {'valid','raster-rounding'}:
        driver.verify_local_export_footer(view)
        assert len(points)==5
    else:
        with pytest.raises(BridgeError):driver.verify_local_export_footer(view)
        assert not points


@pytest.mark.parametrize('case',['valid','negative-origin','large','small','moved','lost-focus','ambiguous','clipped'])
def test_editor_verification_never_resizes_any_monitor(tmp_path,monkeypatch,case):
    import win32gui
    driver=WindowsVision(Settings(tmp_path))
    size=(1920,1080) if case=='large' else (1280,720) if case=='small' else (1600,900)
    origin=(-1600,-96) if case=='negative-origin' else (0,0)
    view=View(1,Box(*origin,origin[0]+size[0],origin[1]+size[1]),Image.new('RGB',size))
    driver.capture=lambda:view
    checked=[]
    def geometry(captured):
        if case in {'ambiguous','clipped'}:raise BridgeError('Uncertain layout')
        return editor_geometry(View(1,Box(0,0,1616,916),Image.new('RGB',(1616,916))))
    driver.geometry=geometry
    def point(*args):
        if case in {'moved','lost-focus'}:raise BridgeError('Window changed')
        checked.append(True)
    driver.point=point
    monkeypatch.setattr(win32gui,'MoveWindow',lambda *args:pytest.fail('Editor resizing is forbidden'))
    if case in {'moved','lost-focus','ambiguous','clipped'}:
        with pytest.raises(BridgeError):driver.restore_measured_editor()
        assert not checked
    else:
        driver.restore_measured_editor();assert checked==[True]


@pytest.mark.parametrize('size',[(1600,900),(1616,915),(1680,916),(1920,1080)])
def test_unmeasured_layouts_reject_before_input(size):
    view=View(1,Box(-8,-8,size[0]-8,size[1]-8),Image.new('RGB',size))
    with pytest.raises(BridgeError,match='native verification'):
        editor_geometry(view)


@pytest.mark.parametrize('state',['play','missing','old-decoy','duplicate'])
def test_900_playback_uses_footer_only_and_rejects_ambiguity(tmp_path,state):
    image=Image.new('RGB',(1616,916),'black')
    with Image.open(Path(module.__file__).with_name('templates')/'capcut-9.4-play.png') as icon:
        if state in {'play','duplicate'}:
            image.paste(icon,(822,477))
        if state=='duplicate':
            image.paste(icon,(922,477))
        if state=='old-decoy':
            image.paste(icon,(872,551))
    view=View(1,Box(-8,-8,1608,908),image)
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda v:editor_geometry(v)
    driver.capture=lambda:view
    driver.require_profile=lambda *args:(9,5,0,4050)
    points=[]
    driver.point=lambda captured,box:points.append(box)
    if state=='play':
        assert driver.paused()
        assert points[0].top==477
    else:
        with pytest.raises(BridgeError):driver.paused()
        assert not points


@pytest.mark.parametrize('case',['valid','shifted-group','missing','old-decoy','duplicate'])
def test_900_toolbar_locates_exact_glyph_without_guessing(tmp_path,case):
    image=Image.new('RGB',(1616,916),'black')
    with Image.open(Path(module.__file__).with_name('templates')/'capcut-9.4-split.png') as icon:
        if case in {'valid','duplicate','shifted-group'}:
            image.paste(icon,(166 if case=='shifted-group' else 238,519))
        if case=='duplicate':image.paste(icon,(310,519))
        if case=='old-decoy':image.paste(icon,(199,594))
    view=View(1,Box(-8,-8,1608,908),image)
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda v:editor_geometry(v)
    driver.require_profile=lambda *args:(9,5,0,4050)
    driver.point=lambda *args:pytest.fail('Unrecognized toolbar must not guess a pointer target')
    if case in {'valid','shifted-group'}:
        captured,box=driver.toolbar_target('split',view)
        assert captured is view and box.top==519
    else:
        with pytest.raises(BridgeError):driver.toolbar_target('split',view)


def test_900_profile_rejects_legacy_version(tmp_path):
    view=View(1,Box(-8,-8,1608,908),Image.new('RGB',(1616,916)))
    driver=WindowsVision(Settings(tmp_path))
    driver.require_profile=lambda *args:(9,4,0,4015)
    with pytest.raises(BridgeError,match='9.5.0.4050'):
        driver.geometry(view)


@pytest.mark.parametrize('case',['valid','disagree','extra-clock','uncertain','different-line',
                                 'refine','refine-conflict','refine-uncertain','refine-extra','refine-shift'])
def test_900_counter_pair_requires_consensus_and_ignores_preview(tmp_path,monkeypatch,case):
    import capcut_windows.drafts as drafts
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda v:editor_geometry(v)
    view=View(1,Box(-8,-8,1608,908),Image.new('RGB',(1616,916)))
    driver.capture=lambda:view
    driver.require_profile=lambda *args:(9,5,0,4050)
    driver.active_draft=lambda:'Trial'
    monkeypatch.setattr(drafts.DraftStore,'load',lambda *args:{'fps':24})
    checked=[]
    driver.point=lambda *args:checked.append(True)
    def words(captured,region,scale,**kwargs):
        broad=region==Box(450,470,1100,502)
        if not broad:assert region.top==473 and region.bottom==495 and 450<=region.left<region.right<=1100
        current='00:00:02:00' if (case=='disagree' or case=='refine-conflict' and not broad) and scale==3 else '00:00:03:00'
        confidence=70 if case=='uncertain' or case.startswith('refine') and broad or case=='refine-uncertain' else 95
        offset=5 if case=='refine-shift' and not broad and scale==3 else 0
        result=[Word(current,confidence,Box(570+offset,479,632+offset,488),(1,1,1,1)),
                Word('00:00:06:00',95,Box(646,479,711,488),(1,2,1,1) if case=='different-line' else (1,1,1,1))]
        if case=='extra-clock':result.append(Word('00:00:04:00',95,Box(920,479,980,488),(1,1,1,1)))
        if not broad:
            result=[word for word in result if region.left<=word.box.left<=region.right]
            if case=='refine-extra':result.append(Word('00:00:05:00',95,Box(region.left,479,region.right,488),(1,1,1,1)))
        return result
    driver.words=words
    if case in {'valid','refine'}:
        assert driver.playhead()==('00:00:03:00','00:00:06:00')
        assert checked==[True]
    else:
        with pytest.raises(BridgeError):driver.playhead()
        assert not checked


def test_900_guidance_refuses_legacy_version_before_ocr_or_input(tmp_path):
    driver=WindowsVision(Settings(tmp_path))
    driver.capture=lambda:View(1,Box(-8,-8,1608,908),Image.new('RGB',(1616,916)))
    driver.active_draft=lambda:'Trial'
    driver.require_profile=lambda *args:(9,4,0,4015)
    driver.words=lambda *args,**kwargs:pytest.fail('No unverified guidance recognition')
    driver.click_box=lambda *args:pytest.fail('No unverified guidance input')
    with pytest.raises(BridgeError,match='9.5.0.4050'):
        driver.action('dismiss-guidance')


@pytest.mark.parametrize('case',['valid','wrong-process','shifted','too-tall','disagree'])
def test_900_history_accepts_only_bounded_same_process_menu_transition(tmp_path,monkeypatch,case):
    import sys
    import win32api,win32gui
    from types import SimpleNamespace
    original=View(1,Box(-8,-8,1608,908),Image.new('RGB',(1616,916),'white'))
    menu=View(2,Box(1 if case=='shifted' else 0,0,1600,940 if case=='too-tall' else 903),
              Image.new('RGB',(1600,940 if case=='too-tall' else 903),'white'))
    driver=WindowsVision(Settings(tmp_path))
    driver.geometry=lambda v:editor_geometry(v)
    driver.require_profile=lambda *args:(9,5,0,4050)
    driver.active_draft=lambda:'Trial'
    clicks=[]
    driver.capture=lambda:menu if clicks else original
    driver.recognize_label=lambda captured,*args,**kwargs:Box(720,12,780,22) if captured is original else Box(712,4,772,14)
    driver.point=lambda *args:None
    driver.click_box=lambda *args:clicks.append(True)
    phases=['Menu','Edit','Recovery']
    def words(view,region,scale,**kwargs):
        if region.left==560:return []
        phase=len(clicks)
        text='Undo' if case=='disagree' and phase==2 and scale==3 else phases[phase]
        box=Box(250,105,280,115) if phase==2 else Box(100,12+phase*57,125,22+phase*57)
        return [Word(text,96,box,(1,1,1,1))]
    driver.words=words
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(
        GetWindowThreadProcessId=lambda handle:(10,21 if case=='wrong-process' and handle==2 else 20)))
    monkeypatch.setattr(win32api,'MonitorFromWindow',lambda *args:1)
    monkeypatch.setattr(win32api,'GetMonitorInfo',lambda *args:{'Monitor':(0,0,1600,900)})
    monkeypatch.setattr(win32gui,'GetWindowRect',lambda handle:original.box.tuple())
    ticks=iter(range(100))
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda *args:None)
    if case=='valid':
        driver.history_menu('redo','Trial')
        assert len(clicks)==3
    else:
        with pytest.raises(BridgeError):driver.history_menu('redo','Trial')
        assert len(clicks)==(2 if case=='disagree' else 1)
