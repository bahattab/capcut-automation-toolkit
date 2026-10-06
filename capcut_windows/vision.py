"""Native Win32 and local OCR fallback for Qt controls without UIA metadata.

Coordinates come from freshly recognized labels, never from macOS geometry.
OCR is observational evidence; actions still require native ownership checks.
"""
from dataclasses import dataclass
import csv
from datetime import datetime
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import statistics
import tempfile
import time
from typing import Any, Callable

from PIL import Image, ImageGrab, ImageOps

from .environment import Settings, processes
from .errors import BridgeError, backend, LOG

# Qt can add one bottom border pixel after restoring this native work area.
EDITOR_SIZES=frozenset({(1680,1050),(1680,1051)})


@backend
def physical_click(point: tuple[int,int], guard: Callable[[],None], clicks: int = 1) -> None:
    """Send exact physical button events after a caller's native ownership guard."""
    import win32api
    if not isinstance(clicks,int) or isinstance(clicks,bool) or clicks not in (1,2):
        raise BridgeError('Use one or two clicks.')
    guard()
    win32api.SetCursorPos(point)
    if win32api.GetCursorPos()!=point:
        raise BridgeError('The cursor did not reach the verified control.')
    # Qt must process the physical pointer transition before its press/release
    # pair. A zero-duration pair can be ignored by native tab controls.
    time.sleep(.15)
    down,up = (0x0008,0x0010) if win32api.GetSystemMetrics(23) else (0x0002,0x0004)
    for index in range(clicks):
        guard()
        if win32api.GetCursorPos()!=point:
            raise BridgeError('The cursor changed before the click.')
        try:
            win32api.mouse_event(down,0,0,0)
            time.sleep(.1)
        finally:
            win32api.mouse_event(up,0,0,0)
        if index+1<clicks:
            time.sleep(.08)


@backend
def physical_wheel(point: tuple[int,int], guard: Callable[[],None], steps: int) -> None:
    """Send a bounded wheel event at an owned physical pixel, without a MOVE event."""
    import win32api
    if not isinstance(steps,int) or isinstance(steps,bool) or not -100<=steps<=100 or steps==0:
        raise BridgeError('Use a nonzero wheel-step count between -100 and 100.')
    guard()
    win32api.SetCursorPos(point)
    if win32api.GetCursorPos()!=point:
        raise BridgeError('The cursor did not reach the verified scroll position.')
    guard()
    if win32api.GetCursorPos()!=point:
        raise BridgeError('The cursor changed before scrolling.')
    # pywin32 converts dwData through signed C long. Negative wheel deltas
    # must remain signed here; masking them to DWORD raises OverflowError.
    win32api.mouse_event(0x0800,0,0,steps*120)


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int,int]:
        return ((self.left+self.right)//2,(self.top+self.bottom)//2)

    def tuple(self) -> tuple[int,int,int,int]:
        return self.left,self.top,self.right,self.bottom


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float
    box: Box  # relative to the captured window
    line: tuple[int,int,int,int]


@dataclass
class View:
    handle: int
    box: Box  # absolute desktop coordinates
    image: Image.Image


@dataclass(frozen=True)
class VisualClip:
    name: str
    rectangle: tuple[int,int,int,int]
    index: int
    project_box: Box
    name_source: str = 'saved_metadata'


@dataclass(frozen=True)
class OpticalElement:
    name: str
    automation_id: str
    kind: str
    rectangle: tuple[int,int,int,int]  # absolute left, top, width, height
    text_source: str = 'ocr'


@backend
def clip_bars(image: Image.Image, region: Box, expected: list[tuple[int,int]]) -> list[tuple[int,int]]:
    """Verify native primary-row runs against every saved timing boundary.

    This identifies ordinal geometry, not source-media identity. Names remain
    explicitly sourced from saved metadata, including Unicode names.
    """
    if not expected or not (0<=region.left<region.right<=image.width
                            and 0<=region.top<region.bottom<=image.height):
        raise BridgeError('The main clip geometry region is invalid.')
    rgb = image.convert('RGB')
    def foreground(x: int) -> bool:
        for y in range(region.top,region.bottom):
            r,g,b = rgb.getpixel((x,y))
            # Selection edges and playhead strokes are neutral, so including
            # them could bridge the dark separator between adjacent clips.
            if g-r>=15 and b-r>=15 and min(g,b)>=70:
                return True
        return False
    runs: list[tuple[int,int]] = []
    start: int | None = None
    for x in range(region.left,region.right+1):
        occupied = x<region.right and foreground(x)
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            if x-start>=4:  # isolated playhead strokes are not clips
                runs.append((start,x))
            start = None
    if len(runs)!=len(expected):
        raise BridgeError('The live main clip count differs from saved metadata.')
    previous = region.left
    for observed,(left,right) in zip(runs,expected):
        if (not region.left<=left<right<=region.right or right-left<24
                or left<previous or max(abs(observed[0]-left),abs(observed[1]-right))>3):
            raise BridgeError('The live clip boundaries cannot be verified. Fit the timeline or wait for autosave.')
        previous = right
    return runs


def selection_border(image: Image.Image, rectangle: tuple[int,int,int,int]) -> bool:
    """Require a horizontal edge connected to both tall side edges."""
    left,top,right,bottom = rectangle
    if right-left<24 or bottom-top<24 or not (3<=left<right<image.width-3 and 3<=top<bottom<image.height-3):
        return False
    rgb = image.convert('RGB')
    def white(x: int,y: int) -> bool:
        r,g,b = rgb.getpixel((x,y))
        return min(r,g,b)>190 and max(r,g,b)-min(r,g,b)<20
    horizontal = any(sum(white(x,y) for x in range(left+4,right-4))>=.85*(right-left-8)
                     for y in range(top-3,top+4))
    sides = [any(sum(white(x,y) for y in range(top+5,bottom-5))>=.8*(bottom-top-10)
                 for x in range(edge-3,edge+4)) for edge in (left,right)]
    return horizontal and all(sides)


def normalize(value: str) -> str:
    return ' '.join(value.casefold().split())


@backend
def tooltip_label(words: list[Word], expected: str, confidence: float = 75) -> Box:
    """Verify the action name; a displayed keyboard binding is not dispatched."""
    if not math.isfinite(confidence) or not 0<=confidence<=100:
        raise BridgeError('Use a finite tooltip confidence threshold.')
    if not words or any(not math.isfinite(word.confidence) or word.confidence<confidence for word in words):
        raise BridgeError('The native toolbar tooltip is uncertain.')
    lines = {word.line for word in words}
    ordered = sorted(words,key=lambda word:word.box.left)
    text = ' '.join(word.text for word in ordered).split('(',1)[0].strip()
    if len(lines)!=1 or normalize(text)!=normalize(expected):
        raise BridgeError('The native tooltip names another toolbar action.')
    return Box(min(w.box.left for w in words),min(w.box.top for w in words),
               max(w.box.right for w in words),max(w.box.bottom for w in words))


@backend
def parse_tsv(value: str, scale: int = 3, offset: tuple[int,int] = (0,0)) -> list[Word]:
    if scale<1:
        raise BridgeError('OCR scale must be positive.')
    words: list[Word] = []
    for row in csv.DictReader(io.StringIO(value),delimiter='\t'):
        text = row.get('text','').strip()
        if not text or row.get('level')!='5':
            continue
        confidence = float(row['conf'])
        if not math.isfinite(confidence):
            continue
        left,top,width,height = (int(row[key]) for key in ('left','top','width','height'))
        box = Box(offset[0]+left//scale,offset[1]+top//scale,
                  offset[0]+math.ceil((left+width)/scale),offset[1]+math.ceil((top+height)/scale))
        words.append(Word(text,confidence,box,tuple(int(row[key]) for key in ('page_num','block_num','par_num','line_num'))))
    return words


@backend
def label_box(words: list[Word], label: str, confidence: float = 75) -> Box:
    expected = normalize(label).split()
    if not expected:
        raise BridgeError('Use a nonempty control label.')
    lines: dict[tuple[int,int,int,int],list[Word]] = {}
    for word in words:
        lines.setdefault(word.line,[]).append(word)
    matches: list[Box] = []
    for line in lines.values():
        line.sort(key=lambda word:word.box.left)
        for index in range(len(line)-len(expected)+1):
            group = line[index:index+len(expected)]
            if ([normalize(word.text) for word in group]==expected
                    and all(word.confidence>=confidence for word in group)):
                matches.append(Box(min(w.box.left for w in group),min(w.box.top for w in group),
                                   max(w.box.right for w in group),max(w.box.bottom for w in group)))
    if len(matches)!=1:
        raise BridgeError('The visual control is missing, uncertain or ambiguous. No input was sent.')
    return matches[0]


@backend
def identifier_box(words: list[Word], name: str, confidence: float = 85) -> Box:
    """Match the entire OCR line, never a prefix or spaced suffix."""
    lines: dict[tuple[int,int,int,int],list[Word]] = {}
    for word in words:
        lines.setdefault(word.line,[]).append(word)
    matches: list[Box] = []
    for line in lines.values():
        for group in [sorted(line,key=lambda item:item.box.left)]:
            if normalize(' '.join(word.text for word in group))==normalize(name) and all(word.confidence>=confidence for word in group):
                matches.append(Box(min(w.box.left for w in group),min(w.box.top for w in group),
                                   max(w.box.right for w in group),max(w.box.bottom for w in group)))
    if len(matches)!=1:
        raise BridgeError('The complete text identifier is missing, uncertain or ambiguous.')
    return matches[0]


@backend
def unique_project_name(name: str, names: list[str]) -> None:
    expected = normalize(name)
    actual = [normalize(item) for item in names]
    if actual.count(expected)!=1 or any(item.startswith(expected+' ') for item in actual if item!=expected):
        raise BridgeError('The project name has a duplicate or longer matching title. Use a unique full title.')


@backend
def verify_frame_count(value: object, fps: float, duration: float) -> int:
    if not isinstance(value,str) or not value.isdecimal():
        raise BridgeError('The exported video frame count could not be verified.')
    if not math.isfinite(fps) or not math.isfinite(duration) or fps<=0 or duration<=0:
        raise BridgeError('Video timing must be finite and positive.')
    decoded=int(value)
    if decoded<=0 or abs(decoded-round(duration*fps))>1:
        raise BridgeError('The exported video frame count disagrees with the timeline.')
    return decoded


@backend
def verify_timing(expected_fps: float, expected_duration: float, actual_fps: float, actual_duration: float) -> None:
    if any(not math.isfinite(value) or value<=0 for value in
           (expected_fps,expected_duration,actual_fps,actual_duration)):
        raise BridgeError('Video timing must be finite and positive.')
    if abs(actual_fps-expected_fps)>.001 or abs(actual_duration-expected_duration)>max(2/expected_fps,.1):
        raise BridgeError('The export timing does not match the saved timeline.')


@backend
def clock_pair(words: list[Word], fps: float) -> tuple[str,str,Box]:
    from .ui import timecode
    counters = [word for word in words if re.fullmatch(r'\d{2}:\d{2}:\d{2}:\d{2}',word.text)]
    if len(counters)!=2 or counters[0].line!=counters[1].line or any(word.confidence<75 for word in counters):
        raise BridgeError('The player counters could not be read uniquely and confidently.')
    counters.sort(key=lambda word:word.box.left)
    current,total = (word.text for word in counters)
    if timecode(total,fps)<=0 or timecode(current,fps)>timecode(total,fps):
        raise BridgeError('The player counters contain invalid timeline timing.')
    return current,total,Box(counters[0].box.left,min(word.box.top for word in counters),
                             counters[1].box.right,max(word.box.bottom for word in counters))


@backend
def ruler_mapping(words: list[Word]) -> tuple[float,float,int]:
    """Infer timeline pixels from labeled native ticks, not stored coordinates."""
    marks: list[tuple[float,int,int]] = []
    for word in words:
        match = re.fullmatch(r'(\d{2}):(\d{2})',word.text)
        if not match or word.confidence<75:
            continue
        minutes,seconds = map(int,match.groups())
        if seconds>=60:
            continue
        ticks = [tick for tick in words if tick.line==word.line and tick.text=='|'
                 and tick.confidence>=75 and 0<word.box.left-tick.box.right<=12]
        if len(ticks)==1:
            marks.append((minutes*60+seconds,ticks[0].box.center[0],ticks[0].box.center[1]))
    marks.sort()
    if len(marks)<3 or len({mark[0] for mark in marks})!=len(marks):
        raise BridgeError('Three distinct labeled timeline ticks could not be verified.')
    first,last = marks[0],marks[-1]
    spacing = (last[1]-first[1])/(last[0]-first[0])
    origin = first[1]-first[0]*spacing
    if spacing<=0 or any(abs(x-(origin+seconds*spacing))>2 or abs(y-first[2])>3 for seconds,x,y in marks):
        raise BridgeError('Timeline tick spacing is inconsistent.')
    return origin,spacing,first[2]


@backend
def ruler_tick(image: Image.Image, label: Box) -> Box:
    """Locate one narrow, continuous grey native tick beside a clock label."""
    left,right=max(0,label.left-12),label.left-1
    top,bottom=max(0,label.top-3),min(image.height,label.bottom+2)
    pixels=image.convert('RGB')
    columns=[]
    for x in range(left,right):
        rows=[]
        for y in range(top,bottom):
            pixel=pixels.getpixel((x,y))
            if 65<=min(pixel)<=max(pixel)<=120 and max(pixel)-min(pixel)<=4:
                rows.append(y)
        if 8<=len(rows)<=14 and rows[-1]-rows[0]+1==len(rows):
            columns.append((x,rows[0],rows[-1]+1))
    if (not 1<=len(columns)<=2 or columns[-1][0]-columns[0][0]+1!=len(columns)
            or len({row[1] for row in columns})!=1
            or max(row[2] for row in columns)-min(row[2] for row in columns)>1):
        raise BridgeError('A unique native timeline tick could not be verified beside its label.')
    return Box(columns[0][0],columns[0][1],columns[-1][0]+1,max(row[2] for row in columns))


@backend
def home_name_region(words: list[Word], projects: Box, width: int, height: int) -> Box:
    """Derive the project-name column from native List headers, excluding metadata."""
    name,size,duration = (label_box(words,label,85) for label in ('Name','Size','Duration'))
    if (not projects.left<=name.left<name.right+24<size.left<size.right+20<duration.left<duration.right<=width
            or max(name.center[1],size.center[1],duration.center[1])-min(name.center[1],size.center[1],duration.center[1])>4
            or not projects.bottom+5<=name.top<name.bottom<=projects.bottom+65
            or size.left-name.left<90):
        raise BridgeError('The native project List columns could not be verified.')
    return Box(name.left-4,name.bottom+4,size.left-12,height-12)


@backend
def shortcut_field(image: Image.Image, field: Box, pills: list[Box]) -> None:
    if (not pills or not 0<=field.left<field.right<=image.width
            or not 0<=field.top<field.bottom<=image.height
            or any(not (field.left<=p.left<p.right<=field.right and field.top<=p.top<p.bottom<=field.bottom) for p in pills)):
        raise BridgeError('The complete shortcut field could not be bounded safely.')
    pixels=image.convert('L')
    for y in range(field.top,field.bottom):
        for x in range(field.left,field.right):
            if pixels.getpixel((x,y))>=160 and not any(p.left<=x<p.right and p.top<=y<p.bottom for p in pills):
                raise BridgeError('The shortcut field contains an additional or clipped binding.')


@backend
def template_box(image: Image.Image, template: Image.Image, region: Box, threshold: int = 150) -> Box:
    """Exact icon geometry after thresholding; hover background is ignored."""
    if not isinstance(threshold,int) or isinstance(threshold,bool) or not 1<=threshold<=254:
        raise BridgeError('The icon threshold must be a bounded integer.')
    search = image.crop(region.tuple()).convert('L').point(lambda value:255 if value>=threshold else 0)
    pattern = template.convert('L').point(lambda value:255 if value>=threshold else 0)
    data = search.tobytes()
    expected = pattern.tobytes()
    pixels = list(expected)
    # A bright foreground pixel gives far fewer candidates than dark background.
    if not any(pixels) or all(pixels):
        raise BridgeError('The icon template has no distinct foreground geometry.')
    index = pixels.index(255)
    anchor = bytes([255])
    anchor_x,anchor_y = index%pattern.width,index//pattern.width
    matches: list[Box] = []
    start = 0
    while True:
        position = data.find(anchor,start)
        if position<0:
            break
        start = position+1
        pixel = position
        x,y = pixel%search.width-anchor_x,pixel//search.width-anchor_y
        if x<0 or y<0 or x+pattern.width>search.width or y+pattern.height>search.height:
            continue
        if search.crop((x,y,x+pattern.width,y+pattern.height)).tobytes()==expected:
            matches.append(Box(region.left+x,region.top+y,region.left+x+pattern.width,region.top+y+pattern.height))
    if len(matches)!=1:
        raise BridgeError('The versioned CapCut icon is missing or ambiguous. No input was sent.')
    return matches[0]


@backend
def text_bands(image: Image.Image, box: Box) -> list[Box]:
    """Find actual ink rows inside an OCR box, which may contain blank padding."""
    left,top = max(0,box.left-3),max(0,box.top-3)
    right,bottom = min(image.width,box.right+3),min(image.height,box.bottom+3)
    crop = image.crop((left,top,right,bottom)).convert('L')
    pixels = crop.load()
    border = [pixels[x,0] for x in range(crop.width)]+[pixels[x,crop.height-1] for x in range(crop.width)]
    background = statistics.median(border)
    rows = [y for y in range(crop.height)
            if sum(abs(pixels[x,y]-background)>=50 for x in range(crop.width))>=max(2,crop.width//100)]
    groups: list[list[int]] = []
    for row in rows:
        if not groups or row-groups[-1][-1]>2:
            groups.append([row])
        else:
            groups[-1].append(row)
    return [Box(left,max(0,top+group[0]-3),right,min(image.height,top+group[-1]+4)) for group in groups]


class WindowsVision:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ocr_cache: dict[tuple[object,...],list[Word]] = {}

    @backend
    def require_profile(self, controls: str = 'editor') -> tuple[int,int,int,int]:
        import win32api
        if not self.settings.executable:
            raise BridgeError('The CapCut executable could not be verified.')
        info = win32api.GetFileVersionInfo(str(self.settings.executable),'\\')
        version = (info['FileVersionMS']>>16,info['FileVersionMS']&65535,
                   info['FileVersionLS']>>16,info['FileVersionLS']&65535)
        verified_95 = {'home','playback','seek','clips','split','trim','delete','history','export','save','marker','zoomfit'}
        if controls not in {'editor'} | verified_95:
            raise BridgeError('The requested visual control profile is unknown.')
        if version==(9,5,0,4050) and controls in verified_95:
            return version
        if version!=(9,4,0,4015):
            raise BridgeError('This visual profile requires CapCut 9.4.0.4015.')
        return version

    @backend
    def tesseract(self) -> Path:
        import shutil
        configured = os.environ.get('CAPCUT_TESSERACT')
        candidates = [Path(configured)] if configured else []
        found = shutil.which('tesseract')
        if found:
            candidates.append(Path(found))
        candidates.extend(Path(os.environ.get(key,''))/'Tesseract-OCR/tesseract.exe'
                          for key in ('ProgramFiles','ProgramFiles(x86)'))
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise BridgeError('Install Tesseract OCR or set CAPCUT_TESSERACT for visual automation.')

    @backend
    def handles(self) -> list[int]:
        import win32gui
        import win32process
        ids = {p.pid for p in processes()}
        handles: list[int] = []
        def collect(handle: int, unused: object) -> None:
            if win32process.GetWindowThreadProcessId(handle)[1] in ids and win32gui.IsWindowVisible(handle):
                handles.append(handle)
        win32gui.EnumWindows(collect,None)
        return handles

    @backend
    def foreground(self, restore: bool = True) -> int:
        import ctypes
        # Physical pixels on monitors with different scaling, confined to this
        # automation thread; no Windows display preferences are changed.
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        import psutil
        import win32gui
        import win32process
        handle = win32gui.GetForegroundWindow()
        pid = win32process.GetWindowThreadProcessId(handle)[1] if handle else 0
        process = psutil.Process(pid) if pid else None
        if (not process or process.name().lower()!='capcut.exe' or not win32gui.IsWindowVisible(handle)
                or not win32gui.IsWindowEnabled(handle)):
            if restore:
                self.activate()
                return self.foreground(False)
            raise BridgeError('CapCut lost focus. No input was sent.')
        if self.settings.executable and Path(process.exe()).resolve()!=self.settings.executable.resolve():
            raise BridgeError('The foreground CapCut executable does not match this installation.')
        if win32gui.IsIconic(handle):
            raise BridgeError('Restore CapCut before visual automation.')
        return handle

    @backend
    def _set_foreground(self, handle: int) -> None:
        """Restore an owned window; detach temporary input queues before return."""
        import psutil
        import win32api
        import win32gui
        import win32process
        if handle not in self.handles() or not win32gui.IsWindowEnabled(handle):
            raise BridgeError('The focus target is no longer an enabled CapCut window.')
        owner=win32process.GetWindowThreadProcessId(handle)
        if self.settings.executable:
            pid=win32process.GetWindowThreadProcessId(handle)[1]
            if Path(psutil.Process(pid).exe()).resolve()!=self.settings.executable.resolve():
                raise BridgeError('The focus target belongs to another CapCut installation.')
        try:
            win32gui.SetForegroundWindow(handle)
            return
        except Exception:
            LOG.exception('Direct native foreground restoration was denied')
        origin=win32gui.GetForegroundWindow()
        if origin==handle:
            return
        if any(win32api.GetAsyncKeyState(key)&0x8000 for key in range(1,256)):
            raise BridgeError('Release held keys or mouse buttons before restoring CapCut.')
        if not origin:
            raise BridgeError('The foreground input queue could not be identified.')
        thread=win32process.GetWindowThreadProcessId(origin)[0]
        current=win32api.GetCurrentThreadId()
        attached=False
        try:
            if thread!=current:
                win32process.AttachThreadInput(current,thread,True)
                attached=True
            if win32gui.GetForegroundWindow()!=origin:
                raise BridgeError('Foreground changed during focus restoration. No input was sent.')
            if (win32process.GetWindowThreadProcessId(handle)!=owner
                    or not win32gui.IsWindowVisible(handle) or not win32gui.IsWindowEnabled(handle)):
                raise BridgeError('The owned focus target changed during restoration.')
            win32gui.SetForegroundWindow(handle)
        finally:
            if attached:
                win32process.AttachThreadInput(current,thread,False)

    @backend
    def activate(self) -> None:
        import win32gui
        roots = [h for h in self.handles() if win32gui.IsWindowEnabled(h) and (
            ('QWindowIcon' in win32gui.GetClassName(h) and
             (win32gui.GetWindowText(h) in {'CapCut','Shortcuts'} or win32gui.GetWindowText(h).startswith('Export-')))
            or (win32gui.GetClassName(h)=='#32770' and win32gui.GetWindowText(h)=='Select exporting path'))]
        if not roots:
            raise BridgeError('No supported enabled CapCut window is available.')
        def area(handle: int) -> int:
            l,t,r,b = win32gui.GetWindowRect(handle)
            return (r-l)*(b-t)
        handle = max(roots,key=area)
        if win32gui.IsIconic(handle):
            win32gui.ShowWindow(handle,9)
        self._set_foreground(handle)
        time.sleep(.2)
        if self.foreground(False)!=handle:
            raise BridgeError('The requested CapCut window did not receive focus.')

    @backend
    def prepare(self) -> None:
        """Restore one native main window without inspecting custom Qt controls."""
        import win32api
        import win32gui
        deadline=time.monotonic()+90
        while True:
            roots = [h for h in self.handles() if win32gui.IsWindowEnabled(h)
                     and 'QWindowIcon' in win32gui.GetClassName(h) and win32gui.GetWindowText(h)=='CapCut']
            if roots:
                break
            if time.monotonic()>=deadline:
                raise BridgeError('No CapCut main window became ready. Try again after startup finishes.')
            time.sleep(.5)
        def area(handle: int) -> int:
            l,t,r,b = win32gui.GetWindowRect(handle)
            return (r-l)*(b-t)
        handle = max(roots,key=area)
        win32gui.ShowWindow(handle,9)
        # Use the current monitor work area. No taskbar or Windows setting changes.
        work = win32api.GetMonitorInfo(win32api.MonitorFromWindow(handle,2))['Work']
        win32gui.MoveWindow(handle,work[0],work[1],work[2]-work[0],work[3]-work[1],True)
        self._set_foreground(handle)
        time.sleep(.3)
        if self.foreground(False)!=handle:
            raise BridgeError('CapCut focus could not be verified.')

    @backend
    def capture(self) -> View:
        import win32gui
        handle = self.foreground()
        box = Box(*win32gui.GetWindowRect(handle))
        if box.right<=box.left or box.bottom<=box.top:
            raise BridgeError('CapCut has no usable capture area.')
        image = ImageGrab.grab(bbox=box.tuple(),all_screens=True)
        if self.foreground(False)!=handle or Box(*win32gui.GetWindowRect(handle))!=box:
            raise BridgeError('The CapCut window changed during capture. Try again.')
        return View(handle,box,image)

    @backend
    def screenshot(self, target: str) -> str:
        path = Path(target).expanduser().resolve()
        path.parent.mkdir(parents=True,exist_ok=True)
        self.capture().image.save(path)
        if not path.is_file() or path.stat().st_size==0:
            raise BridgeError('CapCut screenshot was not created.')
        return str(path)

    @backend
    def save(self) -> dict[str,str | bool]:
        """Confirm CapCut's native autosave and stable saved timeline, without a guessed key."""
        from .drafts import DraftStore
        self.require_profile('save')
        self.paused()
        name = self.active_draft()
        view = self.capture()
        if view.image.size not in EDITOR_SIZES:
            raise BridgeError('The autosave layout requires native verification.')
        region = Box(180,0,325,32)
        readings = [self.words(view,region,scale=scale,psm=7,contrast=True) for scale in (4,3)]
        clocks: list[str] = []
        labels: list[Box] = []
        for words in readings:
            labels.append(label_box(words,'Auto saved:',80))
            autos = [word for word in words if normalize(word.text)=='auto' and word.confidence>=80]
            if len(autos)!=1:
                raise BridgeError('The native autosave label is ambiguous.')
            found = [word for word in words if re.fullmatch(r'\d{2}:\d{2}:\d{2}',word.text)
                     and word.confidence>=80 and word.line==autos[0].line]
            if len(found)!=1:
                raise BridgeError('The native autosave time could not be verified.')
            clock = found[0].text
            hour,minute,second = map(int,clock.split(':'))
            if hour>=24 or minute>=60 or second>=60:
                raise BridgeError('The native autosave time is invalid.')
            clocks.append(clock)
        if clocks[0]!=clocks[1] or max(abs(a-b) for a,b in zip(labels[0].tuple(),labels[1].tuple()))>3:
            raise BridgeError('The two native autosave readings disagree.')
        store = DraftStore(self.settings)
        path = store.content_path(name)
        before = path.read_bytes()
        saved_clock = datetime.fromtimestamp(path.stat().st_mtime).strftime('%H:%M:%S')
        to_seconds = lambda clock: sum(int(value)*factor for value,factor in zip(clock.split(':'),(3600,60,1)))
        delta = abs(to_seconds(saved_clock)-to_seconds(clocks[0]))
        if min(delta,86400-delta)>2:
            raise BridgeError('The saved draft timestamp disagrees with the native autosave indicator.')
        self._clip_views()  # Correlate every visible primary boundary and duration with saved JSON.
        time.sleep(.3)
        if self.active_draft()!=name or path.read_bytes()!=before:
            raise BridgeError('The project changed while confirming native autosave. Try again.')
        self.point(view,labels[0])
        return {'active_draft':name,'status':'native_autosave_confirmed','effect_verified':False,
                'verification_scope':'autosave_record_and_primary_geometry','latest_full_state_verified':False}

    @backend
    def words(self, view: View, region: Box | None = None, scale: int = 3,
              psm: int = 11, whitelist: str | None = None, contrast: bool = False,
              invert: bool = False) -> list[Word]:
        if scale not in (2,3,4) or psm not in (6,7,11,13):
            raise BridgeError('Unsupported OCR configuration.')
        region = region or Box(0,0,view.image.width,view.image.height)
        if not (0<=region.left<region.right<=view.image.width and 0<=region.top<region.bottom<=view.image.height):
            raise BridgeError('The OCR region is outside the captured window.')
        exe = self.tesseract()
        image = view.image.crop(region.tuple())
        cache_key = (view.handle,view.box,region,scale,psm,whitelist,contrast,invert,image.mode,image.size,image.tobytes())
        cacheable = image.width*image.height<=250_000
        if cacheable and cache_key in self._ocr_cache:
            return list(self._ocr_cache[cache_key])
        if contrast:
            image = ImageOps.autocontrast(image.convert('L'))
        if invert:
            image = ImageOps.invert(image.convert('L'))
        image = image.resize((image.width*scale,image.height*scale))
        environment = os.environ.copy()
        environment['OMP_THREAD_LIMIT']='1'
        with tempfile.TemporaryDirectory(prefix='capcut-ocr-') as folder:
            path = Path(folder)/'window.png'
            image.save(path)
            command = [str(exe),str(path),'stdout','--tessdata-dir',str(exe.parent/'tessdata'),
                       '-l','eng','--psm',str(psm)]
            if whitelist:
                command.extend(['-c','tessedit_char_whitelist='+whitelist])
            command.append('tsv')
            result = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',check=True,timeout=45,env=environment)
        words = parse_tsv(result.stdout,scale,(region.left,region.top))
        if cacheable:
            if len(self._ocr_cache)>=32:
                self._ocr_cache.pop(next(iter(self._ocr_cache)))
            self._ocr_cache[cache_key] = words
        return list(words)

    @backend
    def point(self, view: View, box: Box) -> tuple[int,int]:
        import win32gui
        import win32process
        if self.foreground(False)!=view.handle or Box(*win32gui.GetWindowRect(view.handle))!=view.box:
            raise BridgeError('CapCut moved or lost focus. No input was sent.')
        x,y = box.center
        if not (all(isinstance(v,int) and not isinstance(v,bool) for v in box.tuple())
                and 0<=box.left<box.right<=view.image.width and 0<=box.top<box.bottom<=view.image.height):
            raise BridgeError('The visual control is outside CapCut.')
        absolute = view.box.left+x,view.box.top+y
        handle = win32gui.WindowFromPoint(absolute)
        if (not handle or win32process.GetWindowThreadProcessId(handle)[1] not in {p.pid for p in processes()}
                or win32gui.GetAncestor(handle,2)!=view.handle):
            raise BridgeError('Another window covers the visual control. No input was sent.')
        latest = ImageGrab.grab(bbox=view.box.tuple(),all_screens=True)
        if latest.crop(box.tuple()).tobytes()!=view.image.crop(box.tuple()).tobytes():
            raise BridgeError('The visual control changed since recognition. No input was sent.')
        return absolute

    @backend
    def playhead(self) -> tuple[str,str]:
        from .drafts import DraftStore
        self.require_profile('playback')
        fps = float(DraftStore(self.settings).load(self.active_draft()).get('fps',0))
        view = self.capture()
        if view.image.size not in EDITOR_SIZES:
            raise BridgeError('The player layout requires native verification at this window size.')
        # This profile locates counters in the player footer, outside the video
        # image where a source can contain its own burned-in timecode.
        regions = (Box(469,548,540,568),Box(545,548,616,568))
        for contrast in (False,True):
            try:
                first = clock_pair([word for region in regions for word in self.words(view,region,scale=4,psm=7,contrast=contrast)],fps)
                second = clock_pair([word for region in regions for word in self.words(view,region,scale=3,psm=7,contrast=contrast)],fps)
                if first[:2]!=second[:2] or max(abs(a-b) for a,b in zip(first[2].tuple(),second[2].tuple()))>3:
                    raise BridgeError('The two player-counter readings disagree.')
            except BridgeError:
                continue
            self.point(view,first[2])
            return first[0],first[1]
        raise BridgeError('The player counters did not agree across two independent readings.')

    @backend
    def paused(self) -> bool:
        self.require_profile('playback')
        view = self.capture()
        if view.image.size not in EDITOR_SIZES:
            raise BridgeError('The player layout requires native verification at this window size.')
        with Image.open(Path(__file__).with_name('templates')/'capcut-9.4-play.png') as image:
            button = template_box(view.image,image,Box(650,535,1000,578))
        self.point(view,button)
        return True

    @backend
    def ruler(self, view: View) -> tuple[float,float,int]:
        """Require independent three-anchor readings of the visible ruler."""
        region = Box(140,610,1600,641)
        readings: list[tuple[float,float,int]] = []
        candidates: list[Word] = []
        for contrast in (False,True):
            for scale in (4,3):
                words=self.words(view,region,scale=scale,contrast=contrast)
                if not candidates:
                    candidates=[word for word in words if re.fullmatch(r'\d{2}:\d{2}',word.text)]
                try:
                    readings.append(ruler_mapping(words))
                except BridgeError:
                    continue
        if len(readings)<2:
            # OCR can assign the tiny pipe's uncertainty to its adjacent clock.
            # Refine clock text independently; validate the pipe from pixels.
            for scale in (4,3):
                refined: list[Word] = []
                for index,word in enumerate(candidates):
                    crop=Box(word.box.left-1,max(region.top,word.box.top-4),
                             min(region.right,word.box.right+3),min(region.bottom,word.box.bottom+5))
                    try:
                        label=identifier_box(self.words(view,crop,scale=scale,psm=7,contrast=True),word.text,85)
                        tick=ruler_tick(view.image,label)
                    except BridgeError:
                        continue
                    line=(1,index+1,1,1)
                    refined.extend((Word(word.text,85,label,line),Word('|',100,tick,line)))
                try:
                    readings.append(ruler_mapping(refined))
                except BridgeError:
                    continue
        if len(readings)<2:
            raise BridgeError('The timeline ruler lacks two independent three-anchor readings.')
        first = readings[0]
        end = (region.right-first[0])/first[1]
        if any(abs(origin-first[0])>2 or abs(origin+end*spacing-region.right)>2 or abs(y-first[2])>3
               for origin,spacing,y in readings[1:]):
            raise BridgeError('The independent timeline ruler readings disagree.')
        self.point(view,region)
        return statistics.mean(item[0] for item in readings),statistics.mean(item[1] for item in readings),round(statistics.median(item[2] for item in readings))

    @backend
    def seek(self, seconds: float, fps: float) -> float:
        from .drafts import DraftStore
        from .ui import timecode
        if not math.isfinite(seconds) or seconds<0 or not math.isfinite(fps) or fps<=0:
            raise BridgeError('Choose a finite nonnegative time and positive frame rate.')
        self.require_profile('seek')
        name = self.active_draft()
        saved = DraftStore(self.settings).load(name)
        if float(saved.get('fps',0))!=fps:
            raise BridgeError('The requested frame rate differs from the active draft.')
        self.paused()
        current,total = self.playhead()
        total_seconds = timecode(total,fps)
        if seconds>total_seconds:
            raise BridgeError('The requested time is beyond the timeline.')
        wanted = round(seconds*fps)
        if round(timecode(current,fps)*fps)==wanted:
            self.paused()
            if round(timecode(self.playhead()[0],fps)*fps)==wanted:
                return wanted/fps
            raise BridgeError('The requested frame did not remain stable.')
        identity = self.capture()
        title_box = self.recognize_label(identity,self.words(identity,Box(0,0,identity.image.width,65),scale=4),name,identifier=True)
        view = self.capture()
        origin,spacing,y = self.ruler(view)
        x = round(origin+wanted/fps*spacing)
        if wanted==0:
            # OCR tick centers can round one pixel outside the timeline at
            # zero. Click just inside, then verify/correct exact frame zero.
            x = math.ceil(origin+2)
        if not 140<x<1600:
            raise BridgeError('The requested time is outside the visible ruler. Fit the timeline first.')
        self.point(identity,title_box)
        self.click_box(view,Box(x-2,y-3,x+3,y+4))
        time.sleep(.15)
        for _ in range(4):
            current,total = self.playhead()
            actual = round(timecode(current,fps)*fps)
            difference = wanted-actual
            if difference==0:
                self.point(identity,title_box)
                self.paused()
                if round(timecode(self.playhead()[0],fps)*fps)==wanted:
                    return actual/fps
                raise BridgeError('The requested frame did not remain stable.')
            if abs(difference)>min(1000,math.ceil(fps*2)):
                raise BridgeError('The ruler click did not produce the expected nearby time.')
            self.point(identity,title_box)
            # A single frame step is verified first. Only then may a bounded
            # remainder be sent; each batch is followed by a fresh counter read.
            key = 'right' if difference>0 else 'left'
            self.key(key,1)
            stepped = round(timecode(self.playhead()[0],fps)*fps)
            if stepped!=actual+(1 if difference>0 else -1):
                raise BridgeError('The native frame-step key did not advance exactly one frame.')
            remaining = wanted-stepped
            if remaining:
                self.point(identity,title_box)
                self.key('right' if remaining>0 else 'left',abs(remaining))
        self.point(identity,title_box)
        self.paused()
        final = round(timecode(self.playhead()[0],fps)*fps)
        if final==wanted and round(timecode(self.playhead()[0],fps)*fps)==wanted:
            return final/fps
        raise BridgeError('The requested frame could not be verified after correction.')

    @backend
    def _clip_views(self) -> tuple[View,list[VisualClip]]:
        from .drafts import DraftStore
        from .ui import timecode
        self.require_profile('clips')
        name = self.active_draft()
        saved = DraftStore(self.settings).load(name)
        fps = float(saved.get('fps',0))
        segments = [segment for track in saved.get('tracks',[]) if track.get('type')=='video'
                    and track.get('flag',0)==0 for segment in track.get('segments',[])]
        if not segments:
            raise BridgeError('The empty main timeline still requires native verification.')
        segments.sort(key=lambda segment:float(segment['target_timerange']['start']))
        _,total = self.playhead()
        saved_duration = float(saved.get('duration',0))/1e6
        if not math.isfinite(saved_duration) or saved_duration<=0:
            raise BridgeError('The saved timeline duration must be finite and positive.')
        if abs(timecode(total,fps)-saved_duration)>1/fps:
            raise BridgeError('The live timeline differs from its saved metadata. Wait for autosave.')
        view = self.capture()
        title_box = self.recognize_label(view,self.words(view,Box(0,0,view.image.width,65),scale=4),name,identifier=True)
        with Image.open(Path(__file__).with_name('templates')/'capcut-9.4-cover.png') as image:
            cover = template_box(view.image,image,Box(130,645,180,1000))
        self.point(view,cover)
        origin,spacing,_ = self.ruler(view)
        materials = {item['id']:item for item in (saved.get('materials') or {}).get('videos',[])}
        expected: list[tuple[int,int]] = []
        names: list[str] = []
        for segment in segments:
            timing = segment['target_timerange']
            start = float(timing['start'])/1e6
            duration = float(timing['duration'])/1e6
            if not math.isfinite(start) or not math.isfinite(duration) or start<0 or duration<=0:
                raise BridgeError('Main clip timing must be finite and positive.')
            expected.append((round(origin+start*spacing),round(origin+(start+duration)*spacing)))
            names.append(str(materials.get(segment['material_id'],{}).get('material_name','Untitled clip')))
        region = Box(180,cover.top-19,1600,cover.top-16)
        clip_bars(view.image,region,expected)
        self.point(view,region)
        clips = [VisualClip(label,(left,cover.top-19,right,cover.bottom+17),index,title_box)
                 for index,((left,right),label) in enumerate(zip(expected,names))]
        self.point(view,title_box)
        return view,clips

    @backend
    def clips(self) -> list[VisualClip]:
        return self._clip_views()[1]

    @backend
    def select(self, index: int) -> str:
        if not isinstance(index,int) or isinstance(index,bool) or index<0:
            raise BridgeError('Choose a nonnegative main clip index.')
        view,clips = self._clip_views()
        if index>=len(clips):
            raise BridgeError('The main clip index is outside the live timeline.')
        clip = clips[index]
        left,top,right,bottom = clip.rectangle
        # Select the name header, avoiding trim handles and keyframe diamonds
        # inside the thumbnail body. Deletion follows the current selection.
        self.point(view,clip.project_box)
        self.click_box(view,Box(left+4,top+4,right-4,top+15))
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            time.sleep(.2)
            selected = self.capture()
            if selected.handle!=view.handle or selected.box!=view.box:
                raise BridgeError('The editor moved during clip selection.')
            self.point(view,clip.project_box)
            clip_bars(selected.image,Box(180,top,1600,top+3),
                      [(item.rectangle[0],item.rectangle[2]) for item in clips])
            selected_indices = [candidate.index for candidate in clips
                                if selection_border(selected.image,candidate.rectangle)]
            if selected_indices==[index]:
                return clip.name
            if selected_indices:
                raise BridgeError('A different main clip was selected. No further input was sent.')
        raise BridgeError('The main clip selection border could not be verified.')

    @backend
    def click_box(self, view: View, box: Box, clicks: int = 1) -> None:
        import win32gui
        if not isinstance(clicks,int) or isinstance(clicks,bool) or clicks not in (1,2):
            raise BridgeError('Use one or two clicks.')
        point = self.point(view,box)
        def guard() -> None:
            if (self.foreground(False)!=view.handle
                    or Box(*win32gui.GetWindowRect(view.handle))!=view.box
                    or win32gui.GetAncestor(win32gui.WindowFromPoint(point),2)!=view.handle):
                raise BridgeError('The cursor or active window changed before the click.')
        physical_click(point,guard,clicks)

    @backend
    def hover_box(self, box: tuple[int,int,int,int]) -> None:
        import win32api
        view = self.capture()
        point = self.point(view,Box(*box))
        win32api.SetCursorPos(point)
        if win32api.GetCursorPos()!=point or self.foreground(False)!=view.handle:
            raise BridgeError('The cursor did not reach the verified hover control.')

    @backend
    def key(self, combo: str, times: int = 1) -> None:
        from pywinauto.keyboard import VirtualKeyAction
        import win32api
        keys = {'space':32,'enter':13,'return':13,'escape':27,'delete':46,
                'backspace':8,'tab':9,'left':37,'right':39,'up':38,'down':40,
                'home':36,'end':35,'minus':189,'equal':187,'plus':187}
        modifier_codes={'ctrl':17,'cmd':17,'shift':16,'alt':18}
        if not isinstance(combo,str) or not combo:
            raise BridgeError('Use a supported key combination.')
        parts = combo.casefold().split('+')
        base = parts[-1]
        if (not isinstance(times,int) or isinstance(times,bool) or not 1<=times<=1000
                or any(part not in modifier_codes for part in parts[:-1])):
            raise BridgeError('Use a supported key combination and repeat count.')
        if base in keys:
            key = keys[base]
        elif len(base)==1 and base.isascii() and base.isalnum():
            key = ord(base.upper())
        else:
            raise BridgeError('That key is not supported.')
        root=self.foreground()
        codes=[modifier_codes[part] for part in parts[:-1]]
        if len(codes)!=len(set(codes)):
            raise BridgeError('Do not repeat shortcut modifiers.')
        if base=='plus' and 16 not in codes:
            codes.append(16)
        for _ in range(times):
            if self.foreground(False)!=root:
                raise BridgeError('The active window changed before keyboard input.')
            if any(win32api.GetAsyncKeyState(code)&0x8000 for code in (16,17,18,91,92)):
                raise BridgeError('Release held shortcut modifiers before keyboard input.')
            held: list[int]=[]
            try:
                for code in codes:
                    held.append(code)
                    VirtualKeyAction(code,up=False).run()
                if self.foreground(False)!=root or any(win32api.GetAsyncKeyState(code)&0x8000 for code in (91,92)):
                    raise BridgeError('The active window changed during keyboard input.')
                # Physical virtual keys preserve Arabic layout and Num Lock.
                try:
                    VirtualKeyAction(key,up=False).run()
                finally:
                    VirtualKeyAction(key,down=False).run()
            finally:
                release_error: Exception | None=None
                for code in reversed(held):
                    try:
                        VirtualKeyAction(code,down=False).run()
                    except Exception as error:
                        LOG.exception('Native shortcut modifier release failed')
                        release_error=error
                if release_error is not None:
                    raise BridgeError('An unexpected error occurred. Please try again later.') from release_error
            time.sleep(.06)

    @backend
    def elements(self, needle: str | None = None) -> list[OpticalElement]:
        """Inventory visible OCR text; do not invent native control IDs or roles."""
        if needle is not None and not isinstance(needle,str):
            raise BridgeError('Use a text filter for the visible inventory.')
        view = self.capture()
        lines: dict[tuple[int,int,int,int],list[Word]] = {}
        for word in self.words(view,scale=2):
            if word.confidence>=85:
                lines.setdefault(word.line,[]).append(word)
        result: list[OpticalElement] = []
        for words in lines.values():
            words.sort(key=lambda word:word.box.left)
            name = ' '.join(word.text for word in words)
            if needle is not None and needle.casefold() not in name.casefold():
                continue
            left,top = min(word.box.left for word in words),min(word.box.top for word in words)
            right,bottom = max(word.box.right for word in words),max(word.box.bottom for word in words)
            result.append(OpticalElement(name,'','Text',
                (view.box.left+left,view.box.top+top,right-left,bottom-top)))
        return sorted(result,key=lambda element:(element.rectangle[1],element.rectangle[0]))

    @backend
    def click(self, needle: str, clicks: int = 1) -> str:
        if not isinstance(needle,str) or not needle.strip():
            raise BridgeError('Use a nonempty visible text label.')
        self.click_label(needle,clicks=clicks)
        return needle

    @backend
    def absolute_pixel(self, view: View, x: float, y: float) -> Box:
        if not all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
                   for value in (x,y)):
            raise BridgeError('Use finite physical screen coordinates.')
        local_x,local_y = round(x)-view.box.left,round(y)-view.box.top
        if not (0<=local_x<view.image.width and 0<=local_y<view.image.height):
            raise BridgeError('The requested physical pixel is outside CapCut.')
        return Box(local_x,local_y,local_x+1,local_y+1)

    @backend
    def click_xy(self, x: float, y: float, clicks: int = 1) -> None:
        view = self.capture()
        self.click_box(view,self.absolute_pixel(view,x,y),clicks)

    @backend
    def scroll(self, x: float, y: float, steps: int) -> None:
        import win32gui
        if not isinstance(steps,int) or isinstance(steps,bool) or not -100<=steps<=100 or steps==0:
            raise BridgeError('Use a nonzero wheel-step count between -100 and 100.')
        view = self.capture()
        point = self.point(view,self.absolute_pixel(view,x,y))
        def guard() -> None:
            if (self.foreground(False)!=view.handle
                    or Box(*win32gui.GetWindowRect(view.handle))!=view.box
                    or win32gui.GetAncestor(win32gui.WindowFromPoint(point),2)!=view.handle):
                raise BridgeError('The scroll position is no longer owned by the active CapCut window.')
        physical_wheel(point,guard,steps)

    @backend
    def click_label(self, label: str, region: Box | None = None, clicks: int = 1) -> None:
        view = self.capture()
        self.click_box(view,self.recognize_label(view,self.words(view,region),label),clicks)

    @backend
    def recognize_label(self, view: View, words: list[Word], label: str,
                        confidence: float = 85, identifier: bool = False) -> Box:
        match = identifier_box if identifier else label_box
        try:
            return match(words,label,confidence)
        except BridgeError:
            # A whole-panel OCR pass can merge a title with the smaller metadata
            # row beneath it. Re-read actual ink lines. A lower-confidence exact
            # identifier is accepted only when two scales agree, never when the
            # name is truncated or the low-confidence location is ambiguous.
            box = match(words,label,0)
            matches: list[Box] = []
            for region in text_bands(view.image,box):
                try:
                    first = self.words(view,region,scale=4,psm=7)
                    try:
                        matches.append(match(first,label,confidence))
                        continue
                    except BridgeError:
                        agreed = match(first,label,75)
                    second = match(self.words(view,region,scale=3,psm=7),label,75)
                    if max(abs(a-b) for a,b in zip(agreed.tuple(),second.tuple()))<=3:
                        matches.append(agreed)
                except BridgeError:
                    continue
            if len(matches)!=1:
                raise BridgeError('The complete label could not be verified in a single text line.')
            return matches[0]

    @backend
    def describe(self, region: tuple[int,int,int,int] | None = None, scale: int = 3,
                 psm: int = 11, contrast: bool = False) -> list[dict[str,Any]]:
        view = self.capture()
        area = Box(*region) if region is not None else None
        return [{'text':w.text,'confidence':w.confidence,'rectangle':w.box.tuple()}
                for w in self.words(view,area,scale=scale,psm=psm,contrast=contrast)]

    @backend
    def export_folder(self, destination: str) -> str:
        """Use the native folder picker, with exact field readback before submit."""
        import win32gui
        from pywinauto import Application
        folder = Path(destination).resolve(strict=True)
        if not folder.is_dir():
            raise BridgeError('Choose an existing export directory.')
        handle = self.foreground(False)
        if win32gui.GetClassName(handle)!='#32770' or win32gui.GetWindowText(handle)!='Select exporting path':
            raise BridgeError('The native CapCut export folder picker is not active.')
        dialog = Application(backend='win32').connect(handle=handle).window(handle=handle)
        field = dialog.child_window(control_id=1152,class_name='Edit').wrapper_object()
        if not field.is_visible() or not field.is_enabled():
            raise BridgeError('The export folder field is unavailable.')
        self.foreground(False)
        field.set_edit_text(str(folder))
        if field.window_text()!=str(folder) or self.foreground(False)!=handle:
            raise BridgeError('The export directory could not be read back exactly.')
        button = dialog.child_window(control_id=1,class_name='Button').wrapper_object()
        ready_deadline = time.monotonic()+15
        while normalize(button.window_text().replace('&',''))!='select folder':
            if time.monotonic()>=ready_deadline:
                raise BridgeError('The native folder selection button could not be verified.')
            self.foreground(False)
            time.sleep(.2)
        # This is a standard native button, so use its HWND and caption rather
        # than treating its animated focus border as an optical identity.
        rect = button.rectangle()
        point = ((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
        def guard() -> None:
            if (self.foreground(False)!=handle or field.window_text()!=str(folder)
                    or button.rectangle()!=rect or win32gui.WindowFromPoint(point)!=button.handle
                    or win32gui.GetAncestor(button.handle,2)!=handle
                    or not button.is_enabled() or not button.is_visible()):
                raise BridgeError('The verified native folder button moved or became covered.')
        physical_click(point,guard)
        deadline = time.monotonic()+10
        while time.monotonic()<deadline and win32gui.IsWindowVisible(handle):
            time.sleep(.1)
        if win32gui.IsWindowVisible(handle):
            raise BridgeError('CapCut did not confirm the selected export folder.')
        return str(folder)

    @backend
    def active_draft(self) -> str:
        from .drafts import DraftStore
        view = self.capture()
        header = self.words(view,Box(view.image.width//3,0,view.image.width*2//3,min(65,view.image.height)),scale=4)
        matches: list[str] = []
        rows=DraftStore(self.settings).listings()
        for row in rows:
            name = row['name']
            if normalize(name) not in normalize(' '.join(word.text for word in header)):
                continue
            try:
                box = self.recognize_label(view,header,name,85,identifier=True)
                self.point(view,box)  # the title itself must belong to this window
                matches.append(name)
            except BridgeError:
                continue
        if not matches and view.image.size in EDITOR_SIZES and self.require_profile('home')==(9,5,0,4050):
            title_region=Box(view.image.width//3,0,view.image.width*2//3,35)
            accepted:tuple[str,Box]|None=None
            for scale in (4,3,2):
                readings=self.words(view,title_region,scale=scale,psm=7,contrast=True)
                if not readings or any(word.confidence<85 for word in readings):
                    continue
                candidate=' '.join(word.text for word in sorted(readings,key=lambda word:word.box.left))
                names=[row['name'] for row in rows if normalize(row['name'])==normalize(candidate)]
                if len(names)!=1:
                    raise BridgeError('The complete native title does not uniquely identify a registered project.')
                current=identifier_box(readings,names[0],85)
                if accepted is None:
                    accepted=(names[0],current)
                    continue
                if names[0]!=accepted[0] or max(abs(a-b) for a,b in zip(accepted[1].tuple(),current.tuple()))>3:
                    raise BridgeError('The complete native title readings disagree.')
                self.point(view,accepted[1])
                return accepted[0]
        if len(matches)!=1:
            raise BridgeError('The active project name could not be read uniquely from the CapCut title bar.')
        return matches[0]

    @backend
    def home_project_row(self, view: View, column: Box, name: str) -> Box:
        """Locate one complete name, then independently read its padded native row."""
        words=self.words(view,column,scale=4,psm=11)
        ink=identifier_box(words,name,0)
        row=Box(column.left,max(column.top,ink.top-10),column.right,
                min(column.bottom,ink.bottom+10))
        tight=Box(max(column.left,ink.left-8),row.top,min(column.right,ink.right+8),row.bottom)
        accepted:tuple[Box,int]|None=None
        configurations=[(row,scale,contrast,False) for scale,contrast in ((4,False),(3,False),(4,True),(3,True),(2,True))]
        configurations += [(tight,scale,contrast,False) for scale,contrast in ((4,False),(3,False),(2,False),(4,True),(3,True),(2,True))]
        configurations += [(tight,scale,True,True) for scale in (4,3,2)]
        # One pixel of blank left padding changes small-font raster alignment.
        # Keep at least six pixels before the complete, independently located ink.
        if ink.left-tight.left>=7:
            shifted=Box(tight.left+1,tight.top,tight.right,tight.bottom)
            configurations += [(shifted,scale,contrast,False) for contrast in (False,True) for scale in (4,3,2)]
        for region,scale,contrast,invert in configurations:
            options:dict[str,bool]={}
            if contrast:options['contrast']=True
            if invert:options['invert']=True
            readings=self.words(view,region,scale=scale,psm=7,**options)
            if not readings or any(word.confidence<85 for word in readings):
                continue
            # A confident conflicting full row must never be bypassed.
            current=identifier_box(readings,name,85)
            if accepted is None:
                accepted=(current,scale)
                continue
            if max(abs(a-b) for a,b in zip(accepted[0].tuple(),current.tuple()))>3:
                raise BridgeError('The native project row readings disagree.')
            if scale!=accepted[1]:
                return accepted[0]
        raise BridgeError('The native project name needs two confident complete row readings.')

    @backend
    def home_list(self) -> Box | None:
        """Expand full draft names using a verified Home-view icon and List label."""
        version = self.require_profile('home')
        view = self.capture()
        width,height = view.image.size
        # Home scrolls its banner and heading together. Locate the heading
        # throughout the content area, then verify all three List columns.
        projects = label_box(self.words(view,Box(180,35,width//2,min(height,height*2//3)),scale=2),'Projects',85)
        header = Box(projects.left,projects.bottom+5,width,min(height,projects.bottom+65))
        try:
            first = home_name_region(self.words(view,header,scale=4,psm=11,contrast=True),projects,width,height)
            second = home_name_region(self.words(view,header,scale=3,psm=11,contrast=True),projects,width,height)
            if max(abs(a-b) for a,b in zip(first.tuple(),second.tuple()))>3:
                raise BridgeError('The native project-name column readings disagree.')
            self.point(view,projects)
            self.point(view,header)
            return first
        except BridgeError:
            pass
        if version==(9,5,0,4050):
            raise BridgeError('Use the native List project view before opening this project.')
        template = Image.open(Path(__file__).with_name('templates')/'capcut-9.4-home-view.png')
        icon = template_box(view.image,template,Box(width//2,max(0,projects.top-30),width,min(height,projects.bottom+20)))
        self.click_box(view,icon)
        dropdown = self.capture()
        if dropdown.image.width<500:
            region = None
        else:
            region = Box(max(0,view.box.left+icon.left-80-dropdown.box.left),
                         max(0,view.box.top+icon.bottom-dropdown.box.top),
                         min(dropdown.image.width,view.box.left+icon.right+160-dropdown.box.left),
                         min(dropdown.image.height,view.box.top+icon.bottom+150-dropdown.box.top))
        self.click_label('List',region)

    @backend
    def history_menu(self, command: str, project: str) -> None:
        """Use observed 9.5 native menu labels, avoiding global history hotkeys."""
        if self.require_profile('history')!=(9,5,0,4050) or command not in {'undo','redo'}:
            raise BridgeError('The native history menu profile is unavailable.')
        if self.active_draft()!=project:
            raise BridgeError('The history project changed before menu input.')
        initial = self.capture()
        if initial.image.size not in EDITOR_SIZES:
            raise BridgeError('Close other menus before using native history.')

        def menu_target(label: str, region: Box) -> tuple[View,Box]:
            deadline = time.monotonic()+8
            last_error: BridgeError | None = None
            while time.monotonic()<deadline:
                try:
                    view = self.capture()
                    # Native menu roots extend their lower edge beyond the
                    # editor. All recognized controls remain in the original
                    # viewport; retain its exact origin and width instead of
                    # treating the changing bottom shadow as a layout change.
                    if (view.image.width!=initial.image.width or view.image.height<initial.image.height
                            or (view.box.left,view.box.top,view.box.right)
                            !=(initial.box.left,initial.box.top,initial.box.right)):
                        raise BridgeError('The native menu layout changed.')
                    title = self.recognize_label(view,self.words(view,Box(560,0,1120,65),scale=4),project,identifier=True)
                    boxes = [label_box(self.words(view,region,scale=scale,psm=7,contrast=True),label,85)
                             for scale in (4,3)]
                    if max(abs(a-b) for a,b in zip(boxes[0].tuple(),boxes[1].tuple()))>3:
                        raise BridgeError('The native menu label readings disagree.')
                    if view.image.crop(boxes[0].tuple()).convert('L').getextrema()[1]<150:
                        raise BridgeError('The requested native menu item is disabled.')
                    self.point(view,title)
                    self.point(view,boxes[0])
                    return view,boxes[0]
                except BridgeError as error:
                    last_error = error
                    time.sleep(.2)
            if last_error is not None:
                raise last_error
            raise BridgeError('The native history menu did not become ready.')

        for label,region in (('Menu',Box(90,6,124,29)),('Edit',Box(90,65,210,96)),
                             ('Undo' if command=='undo' else 'Recovery',
                              Box(242,65,327,96) if command=='undo' else Box(242,97,327,128))):
            view,target = menu_target(label,region)
            self.click_box(view,target)

    @backend
    def toolbar_target(self, command: str, view: View) -> tuple[View,Box]:
        """Exact glyph first, then an owned, spatially associated native tooltip."""
        import win32gui
        import win32process
        import win32api
        labels = {'undo':('Undo',134),'redo':('Reset',171),'split':('Split',207),
                  'trim-left':('Delete left',243),'trim-right':('Delete right',279),'delete':('Delete',315)}
        if command not in labels or view.image.size not in EDITOR_SIZES:
            raise BridgeError('The native toolbar profile could not be verified.')
        label,x = labels[command]
        region = Box(x-18,588,x+18,614)
        for suffix in ('','-hover'):
            with Image.open(Path(__file__).with_name('templates')/f'capcut-9.4-{command}{suffix}.png') as icon:
                try:
                    return view,template_box(view.image,icon,region)
                except BridgeError:
                    pass
        button = Box(x-10,590,x+10,612)
        if view.image.crop(button.tuple()).convert('L').getextrema()[1]<150:
            raise BridgeError('The requested toolbar button appears disabled.')
        point = self.point(view,button)
        # SetCursorPos uses physical pixels in this DPI-aware thread. Normalized
        # mouse input rounds positions on wide, multiple-monitor desktops.
        win32api.SetCursorPos(point)
        if win32api.GetCursorPos()!=point:
            raise BridgeError('The cursor did not reach the verified toolbar button.')
        pid = win32process.GetWindowThreadProcessId(view.handle)[1]
        deadline = time.monotonic()+3
        candidates: list[tuple[int,Box]] = []
        while time.monotonic()<deadline:
            candidates = []
            def each(handle: int, unused: object) -> None:
                if (win32gui.IsWindowVisible(handle)
                        and win32gui.GetClassName(handle)=='Qt622QWindowToolTipSaveBits'
                        and win32process.GetWindowThreadProcessId(handle)[1]==pid):
                    absolute = Box(*win32gui.GetWindowRect(handle))
                    relative = Box(absolute.left-view.box.left,absolute.top-view.box.top,
                                   absolute.right-view.box.left,absolute.bottom-view.box.top)
                    if (relative.left<=x<relative.right and button.bottom+4<=relative.top<=button.bottom+24
                            and 16<=relative.right-relative.left<=250 and 12<=relative.bottom-relative.top<=50
                            and 0<=relative.left<relative.right<=view.image.width
                            and 0<=relative.top<relative.bottom<=view.image.height):
                        candidates.append((handle,relative))
            win32gui.EnumWindows(each,None)
            if len(candidates)==1:
                break
            time.sleep(.1)
        if len(candidates)!=1:
            raise BridgeError('A unique native tooltip did not appear below this toolbar button.')
        handle,tip = candidates[0]
        hovered = self.capture()
        if hovered.handle!=view.handle or hovered.box!=view.box:
            raise BridgeError('The editor changed while recognizing its toolbar.')
        words = self.words(hovered,tip,scale=4,psm=7,contrast=True)
        try:
            first = tooltip_label(words,label)
            second = tooltip_label(self.words(hovered,tip,scale=3,psm=7,contrast=True),label)
        except BridgeError:
            # Bindings may contain small keycap glyphs. Only refine a full
            # reading that already names this exact action, never truncate a
            # different action such as Delete right into Delete.
            tooltip_label(words,label,0)
            widths = {'Undo':30,'Reset':34,'Split':28,'Delete':38,'Delete left':62,'Delete right':70}
            name_field = Box(tip.left+3,tip.top+1,min(tip.right-1,tip.left+3+widths[label]+6),tip.bottom-1)
            first = tooltip_label(self.words(hovered,name_field,scale=4,psm=7,contrast=True),label)
            second = tooltip_label(self.words(hovered,name_field,scale=3,psm=7,contrast=True),label)
        if max(abs(a-b) for a,b in zip(first.tuple(),second.tuple()))>3:
            raise BridgeError('The two toolbar tooltip readings disagree.')
        observed = (win32gui.IsWindowVisible(handle), win32gui.GetClassName(handle),
                    win32api.GetCursorPos(), win32process.GetWindowThreadProcessId(handle)[1],
                    Box(*win32gui.GetWindowRect(handle)))
        expected = (True, 'Qt622QWindowToolTipSaveBits', point, pid,
                    Box(view.box.left+tip.left,view.box.top+tip.top,view.box.left+tip.right,view.box.top+tip.bottom))
        if observed != expected:
            LOG.error('Toolbar tooltip changed: observed=%r expected=%r', observed, expected)
            raise BridgeError('The native tooltip changed during recognition.')
        latest = ImageGrab.grab(bbox=hovered.box.tuple(),all_screens=True)
        if latest.crop(tip.tuple()).tobytes()!=hovered.image.crop(tip.tuple()).tobytes():
            raise BridgeError('The toolbar tooltip changed since recognition.')
        self.point(hovered,button)
        return hovered,button

    @backend
    def timeline_binding(self, command: str, project: str) -> str:
        """Read the active native shortcut panel; never assume stored keymaps."""
        import win32gui
        import win32process
        if command not in {'marker','zoomfit'} or self.require_profile(command)!=(9,5,0,4050):
            raise BridgeError('The native timeline shortcut profile is unavailable.')
        if self.active_draft()!=project:
            raise BridgeError('The timeline project changed before shortcut inspection.')
        editor=self.capture()
        if editor.image.size not in EDITOR_SIZES:
            raise BridgeError('The shortcut-button layout requires native verification.')
        with Image.open(Path(__file__).with_name('templates')/'capcut-9.5-shortcuts.png') as icon:
            button=template_box(editor.image,icon,Box(1334,3,1365,32),threshold=100)
        self.click_box(editor,button)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try:
                panel=self.capture()
                if (win32gui.GetWindowText(panel.handle)=='Shortcuts' and panel.image.size==(720,646)
                        and win32gui.GetWindow(panel.handle,4)==editor.handle
                        and win32process.GetWindowThreadProcessId(panel.handle)[1]==win32process.GetWindowThreadProcessId(editor.handle)[1]):
                    break
            except BridgeError:
                pass
            time.sleep(.2)
        else:
            raise BridgeError('The owned native shortcut panel did not become ready.')

        def read(view: View, text: str, region: Box) -> Box:
            boxes=[identifier_box(self.words(view,region,scale=scale,psm=7,contrast=True),text,85) for scale in (4,3)]
            if max(abs(a-b) for a,b in zip(boxes[0].tuple(),boxes[1].tuple()))>3:
                raise BridgeError('The two native shortcut readings disagree.')
            self.point(view,boxes[0])
            return boxes[0]

        try:
            ready=time.monotonic()+10
            while time.monotonic()<ready:
                panel=self.capture()
                if (win32gui.GetWindowText(panel.handle)!='Shortcuts'
                        or win32gui.GetWindow(panel.handle,4)!=editor.handle):
                    raise BridgeError('The shortcut panel changed while waiting for its controls.')
                try:
                    timeline=read(panel,'Timeline',Box(14,52,84,76))
                    break
                except BridgeError:
                    time.sleep(.2)
            else:
                raise BridgeError('The native Timeline shortcut tab did not become ready.')
            self.click_box(panel,timeline)
            time.sleep(.3)
            label='Add marker' if command=='marker' else 'Zoom to fit timeline'
            for attempt in range(7):
                panel=self.capture()
                if panel.handle==editor.handle or win32gui.GetWindowText(panel.handle)!='Shortcuts':
                    raise BridgeError('The shortcut panel closed during recognition.')
                region=Box(30,88,285,575) if command=='marker' else Box(375,88,602,575)
                words=self.words(panel,region,scale=4,contrast=True)
                try:
                    candidate=identifier_box(words,label,85)
                    if candidate.top<94 or candidate.bottom>571:
                        raise BridgeError('The shortcut row is clipped.')
                    row=Box(region.left,candidate.top-6,region.right,candidate.bottom+6)
                    observed=read(panel,label,row)
                    break
                except BridgeError:
                    if attempt==6:
                        raise BridgeError('The requested native shortcut row could not be verified.')
                    point=self.point(panel,Box(348,350,360,365))
                    physical_wheel(point,lambda:self.point(panel,Box(348,350,360,365)), -2)
                    time.sleep(.3)
            keys=(('M',300,333),) if command=='marker' else (('Shift',611,647),('Z',650,668))
            pills=[]
            for text,left,right in keys:
                pill=Box(left,observed.top-8,right,observed.bottom+8)
                read(panel,text,pill)
                pills.append(pill)
            field=Box(180 if command=='marker' else 520,observed.top-8,
                      338 if command=='marker' else 705,observed.bottom+8)
            shortcut_field(panel.image,field,pills)
            binding='m' if command=='marker' else 'shift+z'
        finally:
            current=self.capture()
            if current.handle!=panel.handle or win32gui.GetWindowText(current.handle)!='Shortcuts':
                raise BridgeError('The native shortcut panel changed before cancellation.')
            cancel=read(current,'Cancel',Box(632,602,707,636))
            self.click_box(current,cancel)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try:
                if self.foreground(False)==editor.handle and self.active_draft()==project:
                    return binding
            except BridgeError:
                pass
            time.sleep(.2)
        raise BridgeError('The original timeline did not regain focus after shortcut inspection.')

    @backend
    def action(self, command: str, expected_index: int | None = None, expected_draft: str | None = None) -> str:
        if expected_index is not None and (command!='delete' or not isinstance(expected_index,int)
                                           or isinstance(expected_index,bool) or expected_index<0):
            raise BridgeError('Use a nonnegative expected main index for deletion.')
        if expected_draft is not None and (command not in {'split','delete','trim-left','trim-right'}
                                           or not isinstance(expected_draft,str) or not expected_draft.strip()):
            raise BridgeError('Use a nonempty expected project name for editing.')
        if command in {'marker','zoomfit'}:
            self.require_profile(command)
            name=self.active_draft()
            self.paused()
            before=self.playhead()
            _,clips=self._clip_views()
            selected_index=None
            if command=='marker':
                view=self.capture()
                selected=[clip for clip in clips if selection_border(view.image,clip.rectangle)]
                if len(selected)!=1:
                    raise BridgeError('Select exactly one main clip before adding a clip marker.')
                selected_index=selected[0].index
            binding=self.timeline_binding(command,name)
            if self.active_draft()!=name or self.playhead()!=before:
                raise BridgeError('The project or playhead changed during shortcut inspection.')
            self.paused()
            if command=='marker':
                view,clips=self._clip_views()
                selected=[clip.index for clip in clips if selection_border(view.image,clip.rectangle)]
                if selected!=[selected_index]:
                    raise BridgeError('The selected clip changed during shortcut inspection.')
            current=self.capture()
            self.point(current,Box(700,5,710,25))
            self.key(binding)
            return command+'-requested'
        if command=='play':
            import win32api
            self.require_profile('playback')
            name = self.active_draft()
            view = self.capture()
            if view.image.size not in EDITOR_SIZES:
                raise BridgeError('The playback layout requires native verification.')
            title = self.recognize_label(view,self.words(view,Box(view.image.width//3,0,view.image.width*2//3,65),scale=4),name,identifier=True)
            # Hover an observed empty header patch, avoiding both the playback
            # button animation and the editable project-name hover effect.
            neutral = Box(title.left-24,title.top,title.left-12,title.bottom)
            if neutral.left<view.image.width//3 or len(view.image.crop(neutral.tuple()).getcolors() or [])!=1:
                raise BridgeError('An empty native header patch could not be verified.')
            title_point = self.point(view,neutral)
            win32api.SetCursorPos(title_point)
            if win32api.GetCursorPos()!=title_point:
                raise BridgeError('The cursor did not reach the verified playback title.')
            time.sleep(.25)
            refreshed = self.capture()
            if refreshed.handle!=view.handle or refreshed.box!=view.box:
                raise BridgeError('The editor changed while preparing playback.')
            # Hovering a project name can change its native appearance. Verify
            # the identifier again in the fresh capture instead of comparing
            # pixels from before that deliberate hover.
            fresh_title = self.recognize_label(refreshed,self.words(refreshed,Box(refreshed.image.width//3,0,refreshed.image.width*2//3,65),scale=4),name,identifier=True)
            if max(abs(a-b) for a,b in zip(title.tuple(),fresh_title.tuple()))>3:
                raise BridgeError('The project title moved while preparing playback.')
            self.point(refreshed,fresh_title)
            # Classify after OCR: playback can reach its end while recognition
            # runs. The last capture and pixel guard decide the actual toggle.
            final = self.capture()
            if final.handle!=refreshed.handle or final.box!=refreshed.box:
                raise BridgeError('The editor changed before playback input.')
            self.point(refreshed,fresh_title)
            matches: list[tuple[str,Box]] = []
            for state in ('play','pause'):
                with Image.open(Path(__file__).with_name('templates')/f'capcut-9.4-{state}.png') as icon:
                    try:
                        matches.append((state,template_box(final.image,icon,Box(650,535,1000,578))))
                    except BridgeError:
                        pass
            if len(matches)!=1:
                raise BridgeError('A unique native playback button could not be verified.')
            state,button = matches[0]
            self.click_box(final,button)
            # Clear the button's hover state so a subsequent paused-state
            # check sees the independently observed normal icon.
            resting_point = self.point(final,neutral)
            win32api.SetCursorPos(resting_point)
            if win32api.GetCursorPos()!=resting_point:
                raise BridgeError('The cursor did not leave the playback control.')
            time.sleep(.25)
            return state+'-requested'
        if command in {'split','delete','trim-left','trim-right'}:
            from .drafts import DraftStore
            from .ui import timecode
            self.require_profile('split' if command=='split' else 'delete' if command=='delete' else 'trim')
            name = self.active_draft()
            if expected_draft is not None and name!=expected_draft:
                raise BridgeError('The requested editing project is no longer active.')
            self.paused()
            view,clips = self._clip_views()
            if self.active_draft()!=name:
                raise BridgeError('The active project changed during clip inspection.')
            selected = [clip for clip in clips if selection_border(view.image,clip.rectangle)]
            if len(selected)!=1:
                raise BridgeError('Select exactly one visible main clip before editing.')
            clip = selected[0]
            if expected_index is not None and clip.index!=expected_index:
                raise BridgeError('The selected clip differs from the requested deletion index.')
            if command=='delete':
                # A clip border can coexist with a selected keyframe. Explicitly
                # select its name header before using context-sensitive Delete.
                self.select(clip.index)
                view,clips = self._clip_views()
                selected = [item for item in clips if selection_border(view.image,item.rectangle)]
                if len(selected)!=1 or selected[0].index!=clip.index or self.active_draft()!=name:
                    raise BridgeError('The primary clip changed while clearing keyframe selection.')
                clip = selected[0]
            if command!='delete':
                saved = DraftStore(self.settings).load(name)
                segments = sorted([s for t in saved['tracks'] if t['type']=='video' and t.get('flag',0)==0
                                   for s in t['segments']],key=lambda s:s['target_timerange']['start'])
                fps = float(saved['fps'])
                current,_ = self.playhead()
                seconds = timecode(current,fps)
                timing = segments[clip.index]['target_timerange']
                start = float(timing['start'])/1e6
                end = start+float(timing['duration'])/1e6
                if seconds-start<1/fps-1e-8 or end-seconds<1/fps-1e-8:
                    raise BridgeError('Place the paused playhead inside the selected clip, at least one frame from either edge.')
            target_view,button = self.toolbar_target(command,view)
            self.point(view,clip.project_box)
            self.point(view,Box(*clip.rectangle))
            self.click_box(target_view,button)
            return command+'-requested'
        if command in {'undo','redo'}:
            profile = self.require_profile('history')
            name = self.active_draft()
            self.paused()
            if profile==(9,5,0,4050):
                self.history_menu(command,name)
                return command+'-requested'
            view = self.capture()
            title_box = self.recognize_label(view,self.words(view,Box(0,0,view.image.width,65),scale=4),name,identifier=True)
            target_view,button = self.toolbar_target(command,view)
            self.point(view,title_box)
            self.click_box(target_view,button)
            return command+'-requested'
        if command in {'dismiss-guidance','dismiss-keyframe-guidance'}:
            import win32gui
            import win32process
            self.require_profile()
            self.active_draft()
            view = self.capture()
            if view.image.size not in EDITOR_SIZES:
                raise BridgeError('The guidance layout requires native verification.')
            if command=='dismiss-guidance':
                region = Box(456,495,630,575)
                instructions = ('Describe what to add,','remove, or change in your')
                button_text = 'Got it'
            else:
                region = Box(250,710,445,805)
                instructions = ('Right-click the keyframe to','create variable speed')
                button_text = 'OK'
            words = self.words(view,region,scale=4)
            labels = [label_box(words,text,90) for text in instructions]
            labels.append(self.recognize_label(view,words,button_text,90))
            def tool_point(box: Box, check_pixels: bool = True) -> tuple[int,int]:
                if self.foreground(False)!=view.handle or Box(*win32gui.GetWindowRect(view.handle))!=view.box:
                    raise BridgeError('The editor changed while checking its guidance.')
                x,y = box.center
                point = view.box.left+x,view.box.top+y
                handle = win32gui.GetAncestor(win32gui.WindowFromPoint(point),2)
                if (win32gui.GetClassName(handle)!='Qt622QWindowToolSaveBits'
                        or win32gui.GetWindowText(handle)!='CapCut'
                        or win32gui.GetWindow(handle,4)!=view.handle
                        or win32process.GetWindowThreadProcessId(handle)[1]!=win32process.GetWindowThreadProcessId(view.handle)[1]):
                    raise BridgeError('The guidance is not owned by the verified editor.')
                if check_pixels:
                    latest = ImageGrab.grab(bbox=view.box.tuple(),all_screens=True)
                    if latest.crop(box.tuple()).tobytes()!=view.image.crop(box.tuple()).tobytes():
                        raise BridgeError('The guidance changed since recognition.')
                return point
            for label in labels:
                tool_point(label)
            def guard() -> None:
                tool_point(labels[-1],False)
            physical_click(tool_point(labels[-1]),guard)
            return 'guidance-dismiss-requested'
        if command=='export':
            self.require_profile('export')
            self.active_draft()
            view = self.capture()
            region = Box(view.image.width*3//4,0,view.image.width,min(70,view.image.height))
            try:
                target = self.recognize_label(view,self.words(view,region,scale=4),'Export')
            except BridgeError:
                with Image.open(Path(__file__).with_name('templates')/'capcut-9.4-export.png') as image:
                    target = template_box(view.image,image,region)
            self.click_box(view,target)
            return 'export-dialog-requested'
        raise BridgeError('This visual editing action still requires native verification.')

    @backend
    def export_filename_copy(self, view: View, project: str) -> tuple[str,Box]:
        """Read the exact native field with a fully restored clipboard transaction."""
        import win32gui,win32process
        from .clipboard import copy_native_text
        if (self.require_profile('export')!=(9,5,0,4050) or view.image.size!=(720,663)
                or win32gui.GetWindowText(view.handle)!='Export-'+project):
            raise BridgeError('The native export-field profile could not be verified.')
        labels=[label_box(self.words(view,Box(355,90,419,114),scale=scale,
                                     psm=7,contrast=True),'Name',85) for scale in (4,3)]
        if max(abs(a-b) for a,b in zip(labels[0].tuple(),labels[1].tuple()))>3:
            raise BridgeError('The native export-field labels disagree.')
        target=Box(680,95,689,106)
        def copy() -> None:
            self.point(view,labels[0])
            self.click_box(view,target)
            self.key('ctrl+a')
            self.key('ctrl+c')
        text=copy_native_text(copy,win32process.GetWindowThreadProcessId(view.handle)[1])
        if (not text or re.search(r'[<>:"/\\|?*\x00-\x1f]',text)
                or not re.fullmatch(re.escape(project)+r'(?: ?\([1-9][0-9]*\))?',text,re.IGNORECASE)):
            raise BridgeError('The copied export filename does not identify the active project.')
        self.point(view,labels[0])
        self.point(view,target)
        return text,target

    @backend
    def export_filename(self, view: View, project: str) -> tuple[str,Box]:
        """Read the project-derived native filename, including conflict suffixes."""
        field=Box(464,90,704,112)
        accepted: tuple[str,Box] | None=None
        for scale,contrast,invert in ((3,True,False),(4,True,False),(3,True,True),
                                     (4,True,True),(3,False,False),(4,False,False),
                                     (2,True,False),(2,True,True)):
            words=self.words(view,field,scale=scale,psm=7,contrast=contrast,invert=invert)
            if not words or any(word.confidence<85 for word in words):
                continue
            candidate=' '.join(word.text for word in sorted(words,key=lambda word:word.box.left))
            if (not project or re.search(r'[<>:"/\\|?*\x00-\x1f]',candidate)
                    or not re.fullmatch(re.escape(project)+r'(?: ?\([1-9][0-9]*\))?',candidate,re.IGNORECASE)):
                raise BridgeError('The export filename does not identify the active project.')
            ink=identifier_box(words,candidate,85)
            if (ink.left<field.left+2 or ink.right>field.right-2
                    or ink.top<field.top+2 or ink.bottom>field.bottom-2):
                raise BridgeError('The export filename touches its field boundary and may be clipped.')
            if accepted is None:
                accepted=(candidate,ink)
                continue
            if (normalize(candidate)!=normalize(accepted[0])
                    or max(abs(a-b) for a,b in zip(accepted[1].tuple(),ink.tuple()))>3):
                raise BridgeError('Confident export filename readings disagree.')
            self.point(view,accepted[1])
            return accepted
        return self.export_filename_copy(view,project)

    @backend
    def verify_export_fps30(self, view: View) -> None:
        """Verify the native 30 fps row with two independent tight OCR reads."""
        import win32gui
        if self.require_profile('export')!=(9,5,0,4050) or view.image.size!=(720,663) or not win32gui.GetWindowText(view.handle).startswith('Export-'):
            raise BridgeError('The supported frame rate row could not be verified.')
        readings: list[tuple[Box,Box]]=[]
        for scale in (4,3):
            heading=identifier_box(self.words(view,Box(350,365,455,400),scale=scale,psm=7,contrast=True),'Frame rate')
            value=identifier_box(self.words(view,Box(464,368,560,399),scale=scale,psm=7,contrast=True),'30fps')
            if heading.right>=value.left or abs(heading.center[1]-value.center[1])>3:
                raise BridgeError('The frame rate label and value do not share the supported row.')
            readings.append((heading,value))
        if any(abs(a-b)>3 for first,second in zip(readings[0],readings[1]) for a,b in zip(first.tuple(),second.tuple())):
            raise BridgeError('The frame rate readings do not agree.')
        for box in readings[0]:
            self.point(view,box)

    @backend
    def export(self, directory: str, timeout: float = 600) -> str:
        """Verified native layout: exact folder, local settings and decoded output."""
        import shutil
        import win32gui
        from fractions import Fraction
        from .drafts import DraftStore
        if not math.isfinite(timeout) or not 1<=timeout<=3600:
            raise BridgeError('Use a finite export timeout between 1 and 3600 seconds.')
        self.require_profile('export')
        folder = Path(directory).resolve(strict=True)
        if not folder.is_dir():
            raise BridgeError('Choose an existing export directory.')
        probe,decoder = shutil.which('ffprobe'),shutil.which('ffmpeg')
        if not probe or not decoder:
            raise BridgeError('Install FFmpeg before export verification.')
        view = self.capture()
        title = win32gui.GetWindowText(view.handle)
        if not title.startswith('Export-'):
            expected_title='Export-'+self.active_draft()
            self.action('export')
            ready_deadline=time.monotonic()+15
            while time.monotonic()<ready_deadline:
                try:
                    view=self.capture()
                    title=win32gui.GetWindowText(view.handle)
                    if title==expected_title and view.image.size==(720,663):
                        break
                except BridgeError:
                    pass
                time.sleep(.2)
            else:
                raise BridgeError('The requested export dialog did not become ready.')
        name = title.removeprefix('Export-')
        unique_project_name(name,[row['name'] for row in DraftStore(self.settings).listings()])
        saved = DraftStore(self.settings).load(name)
        if title!='Export-'+name or view.image.size!=(720,663):
            raise BridgeError('The supported export dialog layout could not be verified.')
        filename_deadline=time.monotonic()+90
        while True:
            try:
                output_name,name_box=self.export_filename(view,name)
                break
            except BridgeError:
                if time.monotonic()>=filename_deadline:
                    raise
                time.sleep(.3)
                view=self.capture()
                if win32gui.GetWindowText(view.handle)!=title or view.image.size!=(720,663):
                    raise BridgeError('The export dialog changed before filename verification.')
        target = folder/(output_name+'.mp4')
        if target.exists():
            raise BridgeError('The export target already exists. Choose another directory.')
        fps = float(saved.get('fps',0))
        duration = float(saved.get('duration',0))/1_000_000
        if fps not in {24,30} or not math.isfinite(duration) or duration<=0:
            raise BridgeError('This export profile requires a positive 24 or 30 fps draft.')
        frame_rate_label=f'{fps:g}fps'
        # The native settings pane remembers its scroll position. Scroll its
        # blank label/field gap, never a dropdown, before reading fixed rows.
        self.scroll(view.box.left+440,view.box.top+260,8)
        time.sleep(.3)
        view=self.capture()
        if win32gui.GetWindowText(view.handle)!=title or view.image.size!=(720,663):
            raise BridgeError('The export dialog changed while restoring its settings pane.')
        if self.export_filename(view,name)[0]!=output_name:
            raise BridgeError('The export filename changed while restoring its settings pane.')
        for region,label in ((Box(460,215,700,246),'1080P'),(Box(460,292,700,322),'H.264'),
                             (Box(460,330,700,360),'mp4'),(Box(460,368,700,399),frame_rate_label)):
            if fps==30 and label==frame_rate_label:
                self.verify_export_fps30(view)
            else:
                self.recognize_label(view,self.words(view,region,scale=4),label)
        # Select the directory on every export; a remembered truncated path is
        # never accepted as proof of destination.
        with Image.open(Path(__file__).with_name('templates')/'capcut-9.4-folder.png') as image:
            folder_button = template_box(view.image,image,Box(670,120,710,156))
        self.click_box(view,folder_button)
        folder_deadline = time.monotonic()+20
        while time.monotonic()<folder_deadline:
            try:
                handle = self.foreground(False)
            except BridgeError:
                # Opening a modal temporarily leaves its disabled parent as
                # foreground. Observe readiness; never click that parent.
                time.sleep(.2)
                continue
            if win32gui.GetClassName(handle)=='#32770' and win32gui.GetWindowText(handle)=='Select exporting path':
                break
            time.sleep(.2)
        else:
            raise BridgeError('The native export folder picker did not become ready.')
        self.export_folder(str(folder))
        return_deadline = time.monotonic()+10
        while time.monotonic()<return_deadline:
            try:
                returned_title=win32gui.GetWindowText(self.foreground(False))
            except BridgeError:
                time.sleep(.2)
                continue
            if returned_title==title:
                break
            time.sleep(.2)
        view = self.capture()
        if win32gui.GetWindowText(view.handle)!=title or view.image.size!=(720,663):
            raise BridgeError('CapCut did not return to the verified export dialog.')
        sync_region=Box(345,525,565,555) if fps==30 else Box(345,440,565,500)
        sync_label = self.recognize_label(view,self.words(view,sync_region,scale=4),'Sync exported videos to space')
        checkbox = Box(sync_label.left-16,sync_label.center[1]-6,sync_label.left-4,sync_label.center[1]+6)
        def checked(image: Image.Image) -> bool:
            pixels = list(image.crop(checkbox.tuple()).convert('RGB').getdata())
            cyan = sum(g>120 and b>120 and r<80 for r,g,b in pixels)
            grey = sum(40<=r<=100 and abs(r-g)<12 and abs(g-b)<12 for r,g,b in pixels)
            if cyan>=30 and grey<20:
                return True
            if grey>=30 and cyan==0:
                return False
            raise BridgeError('The cloud sync checkbox state is uncertain.')
        if checked(view.image):
            self.click_box(view,checkbox)
            view = self.capture()
        if checked(view.image):
            raise BridgeError('Cloud sync must be disabled before local export.')
        current_output,name_box=self.export_filename(view,name)
        if current_output!=output_name:
            raise BridgeError('The export filename changed during destination selection.')
        self.point(view,name_box)
        self.point(view,checkbox)
        for region,label in ((Box(460,215,700,246),'1080P'),(Box(460,292,700,322),'H.264'),
                             (Box(460,330,700,360),'mp4'),(Box(460,368,700,399),frame_rate_label)):
            if fps==30 and label==frame_rate_label:
                self.verify_export_fps30(view)
            else:
                self.point(view,self.recognize_label(view,self.words(view,region,scale=4),label))
        if target.exists():
            raise BridgeError('The export target appeared before export. No overwrite was requested.')
        button = self.recognize_label(view,self.words(view,Box(545,615,630,652),scale=4),'Export')
        self.click_box(view,button)
        deadline = time.monotonic()+timeout
        previous: tuple[int,int] | None = None
        stable = 0
        while time.monotonic()<deadline:
            time.sleep(1)
            if not target.is_file():
                continue
            stat = target.stat()
            measurement = stat.st_size,stat.st_mtime_ns
            stable = stable+1 if measurement==previous and stat.st_size>0 else 0
            previous = measurement
            if stable<3:
                continue
            result = subprocess.run([probe,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(target)],
                                    capture_output=True,text=True,check=True,timeout=60)
            data = json.loads(result.stdout)
            video = next((stream for stream in data.get('streams',[]) if stream.get('codec_type')=='video'),None)
            if not video or video.get('codec_name')!='h264' or (video.get('width'),video.get('height'))!=(1920,1080):
                raise BridgeError('The export dimensions do not match the verified settings.')
            actual_fps = float(Fraction(video.get('avg_frame_rate','0')))
            actual_duration = float(data.get('format',{}).get('duration',0))
            verify_timing(fps,duration,actual_fps,actual_duration)
            verify_frame_count(video.get('nb_read_frames'),fps,duration)
            subprocess.run([decoder,'-v','error','-xerror','-i',str(target),'-f','null','-'],
                           capture_output=True,check=True,timeout=timeout)
            final = target.stat()
            if (final.st_size,final.st_mtime_ns)!=measurement:
                raise BridgeError('The export changed during validation.')
            return str(target)
        raise BridgeError('Export did not produce a stable verified video before the timeout.')

    @backend
    def open(self, name: str) -> None:
        from .drafts import DraftStore
        from .environment import launch
        store = DraftStore(self.settings)
        store.load(name)  # validate path and registered source before any input
        unique_project_name(name,[row['name'] for row in store.listings()])
        launch(self.settings)
        try:
            if self.active_draft()==name:
                return
        except BridgeError:
            pass
        self.prepare()
        view = self.capture()
        try:
            version=self.require_profile('home')
        except BridgeError:
            version=None
        if version==(9,5,0,4050):
            name_region=self.home_list()
            if name_region is None:
                raise BridgeError('The native List project-name column could not be verified.')
            # Hover highlighting changes the small project-name font contrast.
            # Use the verified Home header before taking the name snapshot.
            self.hover_box((900,5,1000,25))
            view=self.capture()
            target=self.home_project_row(view,name_region,name)
        else:
            # The legacy Home layout may show tiles. Avoid its animated banner.
            words = self.words(view,Box(0,view.image.height//2,view.image.width,
                                        min(view.image.height,view.image.height//2+230)),scale=2)
            try:
                target = self.recognize_label(view,words,name,85,identifier=True)
            except BridgeError:
                words = self.words(view,Box(0,view.image.height//2,view.image.width,
                                            min(view.image.height,view.image.height//2+230)),scale=3)
                try:
                    target = self.recognize_label(view,words,name,85,identifier=True)
                except BridgeError:
                    name_region = self.home_list()
                    view = self.capture()
                    words = self.words(view,name_region or Box(0,view.image.height//2,view.image.width,
                                                min(view.image.height,view.image.height//2+230)),scale=4,contrast=True)
                    try:
                        target = self.recognize_label(view,words,name,85,identifier=True)
                    except BridgeError:
                        if name_region is None:
                            raise BridgeError('The full project name could not be verified on the Home page.')
                        target=self.home_project_row(view,name_region,name)
        # Preserve the screenshot used for recognition; fresh pixels must match
        # that evidence rather than rebasing an old target onto a new capture.
        open_error: BridgeError | None = None
        try:
            self.click_box(view,target,2)
        except BridgeError as error:
            # A List row can open on the first click. The second-click guard
            # then stops when the editor replaces Home. Never repeat input;
            # independently observe whether the requested project opened.
            open_error = error
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            try:
                if self.active_draft()==name:
                    return
            except BridgeError:
                pass
            time.sleep(.5)
        if open_error is not None:
            raise open_error
        raise BridgeError('CapCut did not confirm the requested project as open.')
