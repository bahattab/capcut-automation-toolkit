"""Windows UI Automation driver. Unknown UI layouts fail without blind input."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from typing import Any

from .environment import Settings, launch, processes
from .errors import BridgeError, LOG, backend


@dataclass
class Element:
    control: Any  # pywinauto wrapper, loaded only on Windows desktop commands.
    name: str
    automation_id: str
    kind: str
    rectangle: tuple[int, int, int, int]

    def matches(self, needle: str) -> bool:
        return needle.lower() in (self.name + " " + self.automation_id).lower()


ALIASES = {
    "split": ["cutoff", "Split"], "delete": ["del", "Delete"],
    "trim-left": ["cutLeft", "Delete left"], "trim-right": ["cutRight", "Delete right"],
    "undo": ["undo", "Undo"], "redo": ["redo", "Redo"],
    "marker": ["mark", "Add marker"], "zoomfit": ["quicklyAdjustZoomFit", "Zoom to fit"],
    "export": ["MainWindowTitleBarExportBtn", "Export"],
    "play": ["PlayerPlayBtn", "PlayerPauseBtn", "Play", "Pause"],
}


@backend
def timecode(text: str, fps: float) -> float:
    match = re.search(r"(\d{2}):(\d{2}):(\d{2})[:.](\d{2})",text)
    if not match or not math.isfinite(fps) or fps<=0:
        raise BridgeError("CapCut did not expose a readable frame timecode.")
    hours,minutes,seconds,frames = map(int,match.groups())
    if minutes>=60 or seconds>=60 or frames>=math.ceil(fps):
        raise BridgeError("CapCut exposed an invalid frame timecode.")
    return hours*3600+minutes*60+seconds+frames/fps


class WindowsUI:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @backend
    def windows(self) -> list[Any]:
        from pywinauto import Desktop
        import win32gui
        import win32process
        ids = {p.pid for p in processes()}
        if not ids:
            raise BridgeError("CapCut is not running. Use launch first.")
        handles: list[int] = []
        def collect(handle: int, unused: object) -> None:
            if win32process.GetWindowThreadProcessId(handle)[1] in ids and win32gui.IsWindowVisible(handle):
                handles.append(handle)
        win32gui.EnumWindows(collect,None)
        # Avoid COM inspection of every unrelated desktop window.
        windows = []
        for handle in handles:
            try:
                windows.append(Desktop(backend="uia").window(handle=handle).wrapper_object())
            except Exception:
                # Qt tooltip windows can disappear between enumeration and COM
                # inspection. Keep inspecting the surviving owned windows.
                LOG.exception("Could not inspect CapCut window %s",handle)
                if win32gui.IsWindow(handle) and win32gui.IsWindowVisible(handle):
                    raise BridgeError("A CapCut window could not be inspected safely. No input was sent.")
        if not windows:
            raise BridgeError("CapCut has no visible desktop window. Desktop automation is unavailable.")
        return windows

    @backend
    def window(self) -> Any:
        windows = self.windows()
        if not windows:
            raise BridgeError("CapCut has no visible desktop window. Desktop automation is unavailable.")
        return max(windows,key=lambda w:w.rectangle().width()*w.rectangle().height())

    @backend
    def elements(self, needle: str | None = None) -> list[Element]:
        found = []
        for window in self.windows():
            for control in [window]+window.descendants():
                info = control.element_info
                rect = info.rectangle
                element = Element(control,info.name or "",info.automation_id or "",info.control_type or "",
                                  (rect.left,rect.top,rect.width(),rect.height()))
                if needle is None or element.matches(needle):
                    found.append(element)
        return found

    @backend
    def find(self, needles: str | list[str], timeout: float = 5, kinds: tuple[str,...] = (), exact_only: bool = False) -> Element:
        aliases = [needles] if isinstance(needles,str) else needles
        deadline = time.monotonic()+timeout
        while True:
            candidates = self.elements()
            for needle in aliases:
                exact = [e for e in candidates if needle.lower() in {e.name.lower(),e.automation_id.lower()}]
                hits = exact if exact_only else exact or [e for e in candidates if e.matches(needle)]
                hits = [e for e in hits if e.rectangle[2]>0 and e.rectangle[3]>0 and (not kinds or e.kind in kinds)]
                hits = [e for e in hits if e.control is None or e.control.is_visible()]
                if len(hits)==1:
                    return hits[0]
                if len(hits)>1:
                    raise BridgeError("More than one control matches. Use an exact automation ID.")
            if time.monotonic()>=deadline:
                raise BridgeError("The required CapCut control is unavailable in this version or screen.")
            time.sleep(0.25)

    @backend
    def foreground(self) -> Any:
        from pywinauto import Desktop
        import win32gui
        import win32process
        windows = self.windows()
        current = win32gui.GetForegroundWindow()
        ids = {p.pid for p in processes()}
        pid = win32process.GetWindowThreadProcessId(current)[1] if current else 0
        if pid not in ids:
            window = self.window()
            if win32gui.IsIconic(window.handle):
                win32gui.ShowWindow(window.handle,9)  # SW_RESTORE, only this CapCut window.
            window.set_focus()
            time.sleep(0.2)
        foreground = win32gui.GetForegroundWindow()
        pid = win32process.GetWindowThreadProcessId(foreground)[1] if foreground else 0
        if pid not in ids:
            raise BridgeError("CapCut could not take focus. No keyboard or mouse input was sent.")
        return Desktop(backend="uia").window(handle=foreground).wrapper_object()

    @backend
    def guarded_control(self, element: Element) -> Any:
        active = self.foreground()
        if element.control.top_level_parent().handle!=active.handle:
            raise BridgeError("A different CapCut window or modal is active. No input was sent.")
        if not element.control.is_visible() or not element.control.is_enabled():
            raise BridgeError("The CapCut control is unavailable.")
        return element.control

    @backend
    def point_owned_by_active(self, x: float, y: float, active: Any) -> None:
        import win32gui
        import win32process
        handle = win32gui.WindowFromPoint((round(x),round(y)))
        ids = {p.pid for p in processes()}
        if (not handle or win32process.GetWindowThreadProcessId(handle)[1] not in ids
                or win32gui.GetAncestor(handle,2)!=active.handle):
            raise BridgeError("Another window covers that point. No mouse input was sent.")

    @backend
    def click_xy(self, x: float, y: float, clicks: int = 1) -> None:
        from pywinauto import mouse
        if not all(math.isfinite(v) for v in (x,y)) or clicks not in {1,2}:
            raise BridgeError("Use finite coordinates and one or two clicks.")
        window = self.foreground()
        rectangle = window.rectangle()
        if not rectangle.left<=x<rectangle.right or not rectangle.top<=y<rectangle.bottom:
            raise BridgeError("The click is outside the active CapCut window.")
        self.point_owned_by_active(x,y,window)
        if clicks==2:
            mouse.double_click(button="left",coords=(round(x),round(y)))
        else:
            mouse.click(button="left",coords=(round(x),round(y)))

    @backend
    def scroll(self, x: float, y: float, steps: int) -> None:
        from pywinauto import mouse
        if not all(math.isfinite(v) for v in (x,y)) or not -100<=steps<=100 or steps==0:
            raise BridgeError("Use finite coordinates and a nonzero wheel-step count between -100 and 100.")
        window = self.foreground()
        rectangle = window.rectangle()
        if not rectangle.left<=x<rectangle.right or not rectangle.top<=y<rectangle.bottom:
            raise BridgeError("The scroll position is outside the active CapCut window.")
        self.point_owned_by_active(x,y,window)
        mouse.scroll(coords=(round(x),round(y)),wheel_dist=steps)

    @backend
    def click(self, needles: str | list[str], clicks: int = 1, timeout: float = 5) -> str:
        element = self.find(needles,timeout,exact_only=True)
        control = self.guarded_control(element)
        rect = control.rectangle()
        self.point_owned_by_active((rect.left+rect.right)/2,(rect.top+rect.bottom)/2,self.foreground())
        # Scope the click to the matched control; avoid guessed macOS offsets.
        if clicks==2:
            element.control.double_click_input()
        else:
            element.control.click_input()
        return element.name or element.automation_id

    @backend
    def key(self, combo: str, times: int = 1) -> None:
        from pywinauto.keyboard import send_keys
        keys = {"space":"{SPACE}","return":"{ENTER}","enter":"{ENTER}","escape":"{ESC}","delete":"{DELETE}",
                "backspace":"{BACKSPACE}","tab":"{TAB}","left":"{LEFT}","right":"{RIGHT}","up":"{UP}",
                "down":"{DOWN}","home":"{HOME}","end":"{END}"}
        modifiers = {"ctrl":"^","cmd":"^","shift":"+","alt":"%"}
        parts = combo.lower().split("+")
        base = parts[-1]
        if not 1<=times<=1000 or any(p not in modifiers for p in parts[:-1]):
            raise BridgeError("Use a supported key combination and repeat count from 1 to 1000.")
        if base in keys:
            key = keys[base]
        elif len(base)==1 and base.isascii() and base.isalnum():
            key = base
        else:
            raise BridgeError("That key is not supported.")
        sequence = "".join(modifiers[p] for p in parts[:-1])+key
        for _ in range(times):
            self.foreground()  # Never cache focus across commands or individual frame steps.
            send_keys(sequence,pause=0.06)

    @backend
    def playhead(self) -> tuple[str,str]:
        current = self.find(["currentProgress","Current time"],timeout=0)
        total = self.find(["totalProgress","Total time"],timeout=0)
        self.guarded_control(current)
        self.guarded_control(total)
        def text(element: Element) -> str:
            values = [element.name,element.automation_id,element.control.window_text()]
            try:
                values.append(str(element.control.iface_value.CurrentValue))
            except (AttributeError,RuntimeError):
                pass
            for value in values:
                match = re.search(r"\d{2}:\d{2}:\d{2}[:.]\d{2}",value)
                if match:
                    return match.group(0)
            raise BridgeError("CapCut did not expose its playhead timecode.")
        return text(current),text(total)

    @backend
    def clips(self) -> list[Element]:
        clips = [e for e in self.elements() if any(token in e.name+" "+e.automation_id for token in ("MTLSVideoP","VideoSegment"))
                 and e.rectangle[2]>0 and e.rectangle[3]>0]
        return sorted(clips,key=lambda e:(e.rectangle[1],e.rectangle[0]))

    @backend
    def select(self, index: int) -> str:
        clips = self.clips()
        if index<0 or index>=len(clips):
            raise BridgeError("The live clip index is unavailable or outside the visible timeline.")
        clip = clips[index]
        active = self.foreground()
        if clip.control.top_level_parent().handle != active.handle:
            raise BridgeError("The requested timeline belongs to a different CapCut window.")
        window = active.rectangle()
        x,y,width,height = clip.rectangle
        left,right = max(x,window.left),min(x+width,window.right)
        top,bottom = max(y,window.top),min(y+height,window.bottom)
        if left>=right or top>=bottom:
            raise BridgeError("The clip is outside the visible timeline. Zoom to fit first.")
        self.click_xy((left+right)/2,(top+bottom)/2)
        return clip.name or clip.automation_id

    @backend
    def seek(self, seconds: float, fps: float = 30, tolerance_frames: int = 0) -> float:
        if not math.isfinite(seconds) or seconds<0 or not math.isfinite(fps) or fps<=0 or tolerance_frames<0:
            raise BridgeError("Use a non-negative finite seek time and positive frame rate.")
        # Home + paced frame steps are independent of macOS ruler geometry.
        current,total = self.playhead()
        if seconds>timecode(total,fps):
            raise BridgeError("The seek target is beyond the timeline duration.")
        target_frame = round(seconds*fps)
        for _ in range(12):
            current,_ = self.playhead()
            frame = round(timecode(current,fps)*fps)
            error = target_frame-frame
            if abs(error)<=tolerance_frames:
                return frame/fps
            self.key("right" if error>0 else "left",min(abs(error),200))
            time.sleep(0.15)
        raise BridgeError("CapCut did not reach the requested frame. Seek was not verified.")

    @backend
    def action(self, command: str) -> str:
        if command not in ALIASES:
            raise BridgeError("Unknown live editing command.")
        return self.click(ALIASES[command])

    @backend
    def open(self, name: str) -> None:
        launch(self.settings)
        tile = self.find(["HomePageDraftTitle:"+name,name],timeout=40,exact_only=True)
        if tile.name!=name and tile.automation_id!="HomePageDraftTitle:"+name:
            raise BridgeError("The requested draft tile could not be identified.")
        self.click([tile.automation_id or tile.name],clicks=2)
        self.find(["MainTimeLineRoot","Timeline"],timeout=40)
        if self.active_draft()!=name:
            raise BridgeError("CapCut did not confirm the requested draft as open.")

    @backend
    def active_draft(self) -> str:
        element = self.find(["MainWindowTitleBarDraftName","DraftName","ProjectName"],timeout=0,exact_only=True)
        self.guarded_control(element)
        value = element.control.window_text().strip()
        if not value:
            try:
                value = str(element.control.iface_value.CurrentValue).strip()
            except (AttributeError,RuntimeError):
                pass
        if not value:
            raise BridgeError("CapCut did not expose its active draft name.")
        return value

    @backend
    def screenshot(self, target: str) -> str:
        path = Path(target).expanduser().resolve()
        path.parent.mkdir(parents=True,exist_ok=True)
        self.foreground().capture_as_image().save(path)
        if not path.is_file() or path.stat().st_size==0:
            raise BridgeError("CapCut screenshot was not created.")
        return str(path)

    @backend
    def export(self, directory: str | None = None, timeout: float = 900, toggle_sync: bool = False) -> str:
        if not math.isfinite(timeout) or timeout<=0:
            raise BridgeError("Export timeout must be finite and positive.")
        tool = shutil.which("ffprobe")
        if not tool:
            raise BridgeError("Install FFmpeg before exporting so the output can be verified.")
        from .drafts import DraftStore
        saved = DraftStore(self.settings).load(self.active_draft())
        fps = float(saved.get("fps",0))
        _,total = self.playhead()
        expected_duration = timecode(total,fps)
        canvas = saved.get("canvas_config") or {}
        expected_size = (canvas.get("width"),canvas.get("height"))
        if expected_duration<=0 or not all(isinstance(v,int) and v>0 for v in expected_size):
            raise BridgeError("Timeline duration and canvas dimensions must be verified before export.")
        directory_path = Path(directory).expanduser().resolve() if directory else Path.home()/"Downloads"
        directory_path.mkdir(parents=True,exist_ok=True)
        filename = "capcut-kit-"+uuid.uuid4().hex
        target = directory_path / (filename+".mp4")
        self.click(ALIASES["export"])
        # Explicit accessible path input is mandatory. Never merely poll a different folder.
        path = self.find(["ExportPath","Export path","Save to","Location"],timeout=15,kinds=("Edit",),exact_only=True)
        self.foreground()
        self.guarded_control(path).set_edit_text(str(directory_path))
        actual = path.control.get_value() if hasattr(path.control,"get_value") else path.control.window_text()
        if Path(actual).expanduser().resolve()!=directory_path:
            raise BridgeError("The export destination could not be verified.")
        name = self.find(["ExportName","File name","Name"],kinds=("Edit",),exact_only=True)
        self.guarded_control(name).set_edit_text(filename)
        actual_name = name.control.get_value() if hasattr(name.control,"get_value") else name.control.window_text()
        if actual_name!=filename:
            raise BridgeError("The export filename could not be verified.")
        sync = self.find(["Sync exported videos to space","Sync to cloud"],kinds=("CheckBox",),exact_only=True)
        self.guarded_control(sync)
        if toggle_sync:
            sync.control.toggle()
        elif sync.control.get_toggle_state()!=0:
            raise BridgeError("Disable cloud sync in the export dialog before local export.")
        self.click(["ExportDialogExportBtn","Start export","Export"],timeout=15)
        deadline = time.monotonic()+timeout
        previous: tuple[str,int,int] | None = None
        stable = 0
        while time.monotonic()<deadline:
            time.sleep(min(2,max(0,deadline-time.monotonic())))
            if not target.is_file():
                continue
            measurement = (str(target),target.stat().st_size,target.stat().st_mtime_ns)
            stable = stable+1 if measurement==previous and measurement[1]>0 else 0
            previous = measurement
            if stable>=3:
                # Require readable video and full decoder validation; file presence is insufficient.
                result = subprocess.run([tool,"-v","error","-show_streams","-show_format","-of","json",str(target)],capture_output=True,text=True,timeout=60,check=True)
                data = json.loads(result.stdout)
                video = next((s for s in data.get("streams",[]) if s.get("codec_type")=="video"),None)
                duration = float(data.get("format",{}).get("duration",0))
                if not video or duration<=0:
                    raise BridgeError("The exported file is not a valid video.")
                if abs(duration-expected_duration)>max(2/fps,.1) or (video.get("width"),video.get("height"))!=expected_size:
                    raise BridgeError("The exported video does not match the verified timeline duration and canvas dimensions.")
                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg:
                    raise BridgeError("FFmpeg is required for complete export verification.")
                subprocess.run([ffmpeg,"-v","error","-xerror","-i",str(target),"-f","null","-"],capture_output=True,timeout=max(60,timeout),check=True)
                if (target.stat().st_size,target.stat().st_mtime_ns)!=measurement[1:]:
                    raise BridgeError("The exported file changed during validation.")
                self.key("escape")  # Never click TikTok/YouTube share or publish controls.
                return str(target)
        raise BridgeError("Export timed out without a stable, verified video.")
