from pathlib import Path
import math
import pytest
from PIL import Image
from capcut_windows.vision import Box,View,WindowsVision,adaptive_geometry,template_matches
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
import capcut_windows.vision as module

def canvas(size=(1280,760),row=410,track=560,case='valid'):
 image=Image.new('RGB',size,(25,25,25));folder=Path(module.__file__).with_name('templates')
 for i,name in enumerate(('split','trim-left','trim-right','delete')):
  if case=='missing' and i==2:continue
  with Image.open(folder/f'capcut-9.4-{name}.png') as icon:
   image.paste(icon,(170+i*36,row+(10 if case=='row-conflict' and i==2 else 0)))
   if case=='duplicate' and i==0:image.paste(icon,(450,row+90))
 with Image.open(folder/'capcut-9.5-cover-900.png') as icon:
  image.paste(icon,(135,track))
  if case=='duplicate-cover':image.paste(icon,(235,track))
 return View(1,Box(-1280,-96,size[0]-1280,size[1]-96),image)

@pytest.mark.parametrize('size,row,track',[((1100,650),300,470),((1280,720),360,530),((1600,900),500,690),((1920,1080),580,760),((2560,1440),700,950),((3840,2160),1100,1450)])
def test_adaptive_regions_follow_observed_panels_not_screen_ratios(size,row,track):
 v=canvas(size,row,track);g=adaptive_geometry(v)
 assert g.toolbar.top==row-9
 assert g.counters[0].top==row-49
 assert g.ruler.right==size[0]-8
 assert g.cover.bottom==size[1]-8
 assert g.ruler.left==178

@pytest.mark.parametrize('case',['missing','duplicate','row-conflict','duplicate-cover'])
def test_adaptive_layout_rejects_uncorroborated_or_duplicate_anchors(case):
 with pytest.raises(BridgeError):adaptive_geometry(canvas(case=case))

@pytest.mark.parametrize('size',[(799,760),(1280,499),(8193,900)])
def test_adaptive_layout_rejects_clipped_or_unbounded_capture(size):
 with pytest.raises(BridgeError):adaptive_geometry(canvas(size=size))

@pytest.mark.parametrize('factor',[1,1.25,1.5,1.75,2,2.5,3,4])
def test_dpi_coordinates_are_physical_and_keep_negative_monitor_origin(tmp_path,factor):
 logical=Image.new('RGB',(1280,720));raw=Image.new('RGB',(round(1280*factor),round(720*factor)))
 v=View(1,Box(-3200,-96,-3200+raw.width,-96+raw.height),logical,factor,raw)
 b=Box(100,200,120,220);physical=v.physical(b)
 assert physical.left==int(100*factor) and physical.bottom==int(220*factor)
 d=WindowsVision(Settings(tmp_path));p=d.absolute_pixel(v,-3200+110*factor,-96+210*factor)
 assert p.left==math.floor((round(-3200+110*factor)+3200)/factor)
 assert p.top==math.floor((round(-96+210*factor)+96)/factor)
 assert v.raster(raw).size==logical.size

@pytest.mark.parametrize('case',['valid','stale-physical-pixel','foreign-window','missing-raw'])
def test_dpi_point_checks_raw_physical_pixels_and_ownership(tmp_path,monkeypatch,case):
 import win32gui,win32process
 from types import SimpleNamespace
 factor=1.5;logical=Image.new('RGB',(1280,720),'black');raw=Image.new('RGB',(1920,1080),'black')
 view=View(1,Box(-1920,-96,0,984),logical,factor,None if case=='missing-raw' else raw)
 d=WindowsVision(Settings(tmp_path));d.foreground=lambda *args:1
 monkeypatch.setattr(module,'window_scale',lambda handle:factor)
 monkeypatch.setattr(win32gui,'GetWindowRect',lambda h:view.box.tuple())
 monkeypatch.setattr(win32gui,'WindowFromPoint',lambda p:3 if case=='foreign-window' else 1)
 monkeypatch.setattr(win32gui,'GetAncestor',lambda h,n:1)
 monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda h:(1,999 if h==3 else 20))
 monkeypatch.setattr(module,'processes',lambda:[SimpleNamespace(pid=20)])
 latest=raw.copy()
 if case=='stale-physical-pixel':latest.putpixel((151,301),(255,255,255))
 monkeypatch.setattr(module.ImageGrab,'grab',lambda **kwargs:latest)
 if case=='valid':assert d.point(view,Box(100,200,120,220))==(-1755,219)
 else:
  with pytest.raises(BridgeError):d.point(view,Box(100,200,120,220))


@pytest.mark.parametrize('factor',[.75,1,1.25,1.5,1.75,2,2.5,3,4])
def test_adaptive_anchors_match_native_scaled_assets(factor):
 size=(1280,760);raw=Image.new('RGB',(round(size[0]*factor),round(size[1]*factor)),(25,25,25))
 folder=Path(module.__file__).with_name('templates')
 for i,name in enumerate(('split','trim-left','trim-right','delete')):
  with Image.open(folder/f'capcut-9.4-{name}.png') as icon:
   raw.paste(icon.resize((round(icon.width*factor),round(icon.height*factor)),Image.Resampling.NEAREST),(round((172+i*36)*factor),round(412*factor)))
 with Image.open(folder/'capcut-9.5-cover-900.png') as icon:
  raw.paste(icon.resize((round(icon.width*factor),round(icon.height*factor)),Image.Resampling.NEAREST),(round(136*factor),round(560*factor)))
 logical=raw.resize(size,Image.Resampling.LANCZOS)
 view=View(1,Box(-3200,-96,-3200+raw.width,-96+raw.height),logical,factor,raw)
 g=adaptive_geometry(view)
 assert abs(g.toolbar.top-403)<=1
 assert abs(g.ruler.left-179)<=1

@pytest.mark.parametrize('factor',[1.25,1.5,1.75,2])
def test_physical_click_target_never_roundtrips_through_logical_coordinates(tmp_path,monkeypatch,factor):
 d=WindowsVision(Settings(tmp_path))
 raw=Image.new('RGB',(1920,1080));logical=raw.resize((round(1920/factor),round(1080/factor)))
 v=View(1,Box(-1920,-96,0,984),logical,factor,raw);d.capture=lambda:v
 checks=[];clicks=[]
 d.physical_point=lambda view,point:checks.append(point)
 monkeypatch.setattr(module,'physical_click',lambda point,guard,count:(guard(),clicks.append((point,count))))
 d.click_xy(-1701,217)
 assert clicks==[((-1701,217),1)] and checks==[(-1701,217)]


@pytest.mark.parametrize('case',['primary','secondary','shadow-18','shadow-too-large','foreign-process','wrong-root','moved-editor','moved-title','duplicate','disagree'])
def test_native_history_accepts_only_owned_monitor_compositor_with_stable_editor(tmp_path,monkeypatch,case):
 import win32api,win32gui,win32process
 from capcut_windows.vision import Word
 x,y=(1600,-96) if case=='secondary' else (0,0)
 initial=View(1,Box(x,y,x+1280,y+760),Image.new('RGB',(1280,760),'white'))
 popup=View(2,Box(x+20 if case=='wrong-root' else x,y,x+1920,y+1080+(18 if case=='shadow-18' else 40 if case=='shadow-too-large' else 10)),Image.new('RGB',(1920,1090),'white'))
 d=WindowsVision(Settings(tmp_path));clicks=[]
 d.capture=lambda:popup if clicks else initial;d.point=lambda *args:None
 d.click_box=lambda *args:clicks.append(True)
 d.recognize_label=lambda *args,**kwargs:Box(652+(8 if case=='moved-title' and clicks else 0),12,674,22)
 def words(view,region,scale,**kwargs):
  phase=len(clicks);text=('Menu','Edit','Undo')[phase]
  b=(Box(100,12,130,22),Box(98,70,118,80),Box(240,70,268,80))[phase]
  if case=='disagree' and phase==2 and scale==3:text='Recovery'
  result=[Word(text,99,b,(1,1,1,1))]
  if case=='duplicate' and phase==1:result.append(Word(text,99,Box(98,110,118,120),(1,2,1,1)))
  return result
 d.words=words
 monkeypatch.setattr(win32api,'MonitorFromWindow',lambda *args:1)
 monkeypatch.setattr(win32api,'GetMonitorInfo',lambda *args:{'Monitor':(x,y,x+1920,y+1080)})
 monkeypatch.setattr(win32gui,'GetWindowRect',lambda h:(x,y+5,x+1280,y+765) if case=='moved-editor' else initial.box.tuple())
 monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda h:(10,21 if case=='foreign-process' and h==2 else 20))
 ticks=iter(range(100));monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks));monkeypatch.setattr(module.time,'sleep',lambda *args:None)
 if case in {'primary','secondary','shadow-18'}:
  d.adaptive_history('undo','Trial',initial);assert len(clicks)==3
 else:
  with pytest.raises(BridgeError):d.adaptive_history('undo','Trial',initial)
  assert len(clicks)<3

@pytest.mark.parametrize('case',['valid','foreign-owner','foreign-class','duplicate','disagree','stale'])
def test_split_tutorial_requires_complete_dual_reading_native_owner_and_raw_pixels(tmp_path,monkeypatch,case):
 import win32gui,win32process
 from capcut_windows.vision import Word
 d=WindowsVision(Settings(tmp_path));view=View(1,Box(0,0,1280,760),Image.new('RGB',(1280,760),'white'))
 tip=Box(500,300,650,380);d.handles=lambda:[2];d.foreground=lambda *args:1
 monkeypatch.setattr(win32gui,'GetClassName',lambda h:'Foreign' if case=='foreign-class' else 'Qt622QWindowToolSaveBits')
 monkeypatch.setattr(win32gui,'GetWindowText',lambda h:'CapCut')
 monkeypatch.setattr(win32gui,'GetWindow',lambda h,n:3 if case=='foreign-owner' else 1)
 monkeypatch.setattr(win32gui,'GetWindowRect',lambda h:tip.tuple() if h==2 else view.box.tuple())
 monkeypatch.setattr(win32gui,'WindowFromPoint',lambda p:2)
 monkeypatch.setattr(win32gui,'GetAncestor',lambda h,n:2)
 monkeypatch.setattr(win32process,'GetWindowThreadProcessId',lambda h:(10,20))
 def words(v,region,scale,**kwargs):
  result=[]
  for i,text in enumerate(('One-click to help you','cut long videos apart','OK')):
   for j,token in enumerate(text.split()):result.append(Word(token,99,Box(505+j*20,310+i*20+(8 if case=='disagree' and scale==3 else 0),523+j*20,320+i*20+(8 if case=='disagree' and scale==3 else 0)),(1,i+1,1,1)))
  if case=='duplicate':result.append(Word('OK',99,Box(605,365,620,375),(1,4,1,1)))
  return result
 d.words=words;latest=view.image.copy()
 if case=='stale':latest.putpixel((550,330),(0,0,0))
 monkeypatch.setattr(module.ImageGrab,'grab',lambda **kwargs:latest)
 clicks=[];monkeypatch.setattr(module,'physical_click',lambda point,guard:(guard(),clicks.append(point)))
 monkeypatch.setattr(module.time,'sleep',lambda *args:None)
 if case=='valid':d.dismiss_timeline_tip(view);assert len(clicks)==1
 else:
  with pytest.raises(BridgeError):d.dismiss_timeline_tip(view)
  assert not clicks


@pytest.mark.parametrize('case',['normal-duplicate-with-hover','hover-duplicate-with-normal','both-single','unique'])
def test_toolbar_requires_unique_union_of_all_native_glyph_variants(tmp_path,case):
 folder=Path(module.__file__).with_name('templates');v=canvas();region=adaptive_geometry(v).toolbar
 image=v.image
 with Image.open(folder/'capcut-9.4-undo.png') as normal,Image.open(folder/'capcut-9.4-undo-hover.png') as hover:
  image.paste(normal,(100,410))
  if case=='normal-duplicate-with-hover':image.paste(normal,(130,410))
  if case!='unique':image.paste(hover,(340,410))
  if case=='hover-duplicate-with-normal':image.paste(hover,(380,410))
 d=WindowsVision(Settings(tmp_path));d.geometry=lambda current:adaptive_geometry(current)
 if case=='unique':assert d.toolbar_target('undo',v)[1].left==100
 else:
  with pytest.raises(BridgeError):d.toolbar_target('undo',v)


@pytest.mark.parametrize('case',['two-play-one-pause','one-play-two-pause','one-each'])
def test_paused_requires_one_state_across_the_entire_footer(tmp_path,case):
 v=canvas();folder=Path(module.__file__).with_name('templates');g=adaptive_geometry(v)
 for i,state in enumerate(('play','pause')):
  with Image.open(folder/f'capcut-9.4-{state}.png') as icon:
   v.image.paste(icon,(600+i*40,g.playback.top+8))
   if case=='two-play-one-pause' and state=='play' or case=='one-play-two-pause' and state=='pause':v.image.paste(icon,(720,g.playback.top+8))
 d=WindowsVision(Settings(tmp_path));d.capture=lambda:v;d.require_profile=lambda *args:(9,5,0,4050)
 d.geometry=lambda view:adaptive_geometry(view);d.point=lambda *args:pytest.fail('Ambiguous state must not dispatch input')
 with pytest.raises(BridgeError):d.paused()
