"""Windows discovery with explicit overrides for portable installations."""
from dataclasses import dataclass
import os
from pathlib import Path
import platform
import subprocess
import time
import psutil
from .errors import BridgeError, backend


@dataclass(frozen=True)
class Settings:
    root: Path
    executable: Path | None = None
    projects: Path = Path("projects")
    allow_close: bool = False

    @classmethod
    @backend
    def discover(cls, root: str | None = None, executable: str | None = None,
                 projects: str | None = None, allow_close: bool = False) -> "Settings":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        draft_root = Path(root or os.environ.get("CAPCUT_DRAFT_ROOT", str(local / "CapCut/User Data/Projects/com.lveditor.draft"))).expanduser().resolve()
        exe_value = executable or os.environ.get("CAPCUT_EXE")
        exe = Path(exe_value).expanduser().resolve() if exe_value else None
        if exe is None:
            candidates = list((local / "CapCut/Apps").glob("*/CapCut.exe"))
            if candidates:
                available = {candidate.resolve() for candidate in candidates}
                running: set[Path] = set()
                for active in processes():
                    try:
                        path = Path(active.exe()).resolve()
                        if path in available:
                            running.add(path)
                    except (psutil.NoSuchProcess,psutil.AccessDenied):
                        continue
                if len(running)>1:
                    raise BridgeError('Multiple CapCut installations are running. Choose --exe explicitly.')
                exe = next(iter(running)) if running else max(candidates, key=lambda p: tuple(int(v) if v.isdigit() else 0 for v in p.parent.name.split(".")))
        project_root = Path(projects or os.environ.get("CAPCUT_PROJECTS_ROOT", "projects")).expanduser().resolve()
        return cls(draft_root, exe, project_root, allow_close)


@backend
def processes() -> list[psutil.Process]:
    found = []
    for process in psutil.process_iter(["name"]):
        try:
            name = process.info.get("name") or process.name()
            if name.lower() == "capcut.exe":
                found.append(process)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise BridgeError("Process ownership could not be checked safely. No draft files were changed.") from error
    return found


@backend
def launch(settings: Settings) -> int:
    if platform.system() != "Windows":
        raise BridgeError("Desktop commands require Windows.")
    current = processes()
    if current:
        return current[0].pid
    if settings.executable is None or not settings.executable.is_file():
        raise BridgeError("CapCut Desktop was not found. Set CAPCUT_EXE to its executable.")
    environment = os.environ.copy()
    environment["QT_ACCESSIBILITY"] = "1"
    process = subprocess.Popen([str(settings.executable)],env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    return process.pid


@backend
def require_closed() -> None:
    if processes():
        raise BridgeError("Save your work and close CapCut before editing draft files.")


@backend
def quit_app(settings: Settings, timeout: float = 120) -> None:
    current = processes()
    if not current:
        return
    if not settings.allow_close:
        raise BridgeError("Save your work first, then use --allow-close to request a graceful close.")
    original = {(p.pid,p.create_time()) for p in current}
    import win32gui
    import win32process
    def main_roots(active: list[psutil.Process]) -> list[int]:
        ids = {p.pid for p in active}
        found: list[int] = []
        def collect(handle: int, unused: object) -> None:
            if (win32process.GetWindowThreadProcessId(handle)[1] in ids and win32gui.IsWindowVisible(handle)
                    and win32gui.GetWindow(handle,4)==0
                    and 'QWindowIcon' in win32gui.GetClassName(handle)
                    and win32gui.GetWindowText(handle)=='CapCut'):
                found.append(handle)
        win32gui.EnumWindows(collect,None)
        return found
    handles = main_roots(current)
    if not handles:
        raise BridgeError("The CapCut main window could not be identified. Close it manually after saving.")
    if len(handles)!=1:
        raise BridgeError("Multiple CapCut main windows are open. Close the intended window manually after saving.")
    for handle in handles:
        # Only main roots receive WM_CLOSE. Owned dialogs may contain save
        # decisions and must remain available for the user to resolve.
        win32gui.PostMessage(handle,0x0010,0,0)
    requested = set(handles)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = processes()
        if not current:
            return
        active = [p for p in current if (p.pid,p.create_time()) in original]
        if not active:
            raise BridgeError('The original CapCut session exited and another session is running. It was left open.')
        handles = main_roots(active)
        if len(handles)>1:
            raise BridgeError('Multiple CapCut main windows appeared during graceful close. Close the intended window manually.')
        # CapCut first closes its editor and creates a new Home root. Close that
        # new main root once; never repeat against an ignored request or prompt.
        if len(handles)==1 and handles[0] not in requested:
            if len(requested)>=3:
                raise BridgeError('CapCut continued creating main windows. Close it manually.')
            win32gui.PostMessage(handles[0],0x0010,0,0)
            requested.add(handles[0])
        time.sleep(0.25)
    raise BridgeError("CapCut is still open. Resolve any save prompt and close it manually.")

