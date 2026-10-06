"""Typed CLI boundary; validation and edits are performed in backend modules."""
import argparse
import json
import logging
import sys
from typing import Sequence
from .drafts import DraftStore
from .environment import Settings, launch, processes, quit_app
from .errors import BridgeError, LOG, backend
from .ui import WindowsUI


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="CapCut Kit for Windows")
    result.add_argument("--draft-root")
    result.add_argument("--exe")
    result.add_argument("--projects-root")
    result.add_argument("--allow-close",action="store_true",help="Allow graceful close; never force terminate")
    result.add_argument("--backend",choices=("auto","uia","vision"),default="auto",help="Automatically use the verified optical profile for supported CapCut versions; optical commands require local Tesseract")
    sub = result.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor")
    for command in ("ls","launch","quit","clips","playhead","play","trim-left","trim-right","undo","redo","marker","zoomfit","save"):
        sub.add_parser(command)
    replay = sub.add_parser("replay")
    replay.add_argument("job")
    replay.add_argument("--name")
    for command in ("open","graphics","add-overlay","add-text","remove","transform","keyframe","clear-keyframes"):
        item = sub.add_parser(command)
        item.add_argument("draft")
        if command=="graphics":
            item.add_argument("job")
        if command in {"add-overlay","add-text"}:
            item.add_argument("media" if command=="add-overlay" else "text")
            item.add_argument("--at",type=float,default=0)
            item.add_argument("--dur",type=float,default=3 if command=="add-text" else None)
            item.add_argument("--ri",type=int,default=1 if command=="add-text" else None)
            item.add_argument("--force",action="store_true")
        if command=="add-overlay":
            item.add_argument("--src",type=float,default=0)
            item.add_argument("--layer",type=int,default=1)
            item.add_argument("--mute",action="store_true")
        if command in {"remove","transform","keyframe","clear-keyframes"}:
            item.add_argument("--track",choices=("main","text","overlay"),default="main")
            item.add_argument("--index",type=int,default=0)
        if command in {"transform","keyframe"}:
            for flag in ("scale","x","y","rotate","opacity"):
                item.add_argument("--"+flag,type=float)
        if command=="keyframe":
            item.add_argument("--at",type=float,required=True)
            item.add_argument("--curve",default="Line")
    seek = sub.add_parser("seek")
    seek.add_argument("seconds",type=float)
    seek.add_argument("--draft")
    split = sub.add_parser("split")
    split.add_argument("seconds",type=float,nargs="?")
    split.add_argument("--draft")
    for command in ("select","delete","del"):
        sub.add_parser(command).add_argument("index",type=int)
    state = sub.add_parser("state")
    state.add_argument("--draft")
    sub.add_parser("dump").add_argument("needle",nargs="?")
    sub.add_parser("click").add_argument("needle")
    click = sub.add_parser("clickxy")
    click.add_argument("x",type=float)
    click.add_argument("y",type=float)
    click.add_argument("--clicks",type=int,choices=(1,2),default=1)
    scroll = sub.add_parser("scroll")
    scroll.add_argument("x",type=float)
    scroll.add_argument("y",type=float)
    scroll.add_argument("steps",type=int)
    key = sub.add_parser("key")
    key.add_argument("combo")
    key.add_argument("--times",type=int,default=1)
    sub.add_parser("shot").add_argument("output",nargs="?",default="capcut.png")
    export = sub.add_parser("export")
    export.add_argument("--to")
    export.add_argument("--timeout",type=float,default=900)
    export.add_argument("--toggle-sync",action="store_true")
    return result


@backend
def use_optical_backend(settings: Settings, requested: str, command: str) -> bool:
    """Select the installed executable profile without sending desktop input."""
    if requested in {"uia","vision"}:
        return requested=="vision"
    if requested!="auto":
        raise BridgeError("Choose auto, uia or vision as the desktop backend.")
    desktop_commands={"open","clips","playhead","state","seek","select","key","shot","play","save","export","undo","redo","split","delete","del","trim-left","trim-right","dump","click","clickxy","scroll","marker","zoomfit"}
    if command not in desktop_commands or not settings.executable:
        return False
    import win32api
    info=win32api.GetFileVersionInfo(str(settings.executable),'\\')
    version=(info['FileVersionMS']>>16,info['FileVersionMS']&65535,
             info['FileVersionLS']>>16,info['FileVersionLS']&65535)
    return version in {(9,4,0,4015),(9,5,0,4050)}


def run(args: argparse.Namespace) -> object:
    settings = Settings.discover(args.draft_root,args.exe,args.projects_root,args.allow_close)
    drafts = DraftStore(settings)
    ui = WindowsUI(settings)
    command = args.command
    state_running = processes() if command=="state" else None
    optical = (use_optical_backend(settings,getattr(args,"backend","auto"),command)
               if command!="state" or state_running else False)
    if optical:
        from .vision import WindowsVision
        live_commands = {"open","clips","playhead","state","seek","select","key","shot","play","save","export","undo","redo","split","delete","del","trim-left","trim-right","dump","click","clickxy","scroll","marker","zoomfit"}
        unverified_commands: set[str] = set()
        if command in unverified_commands:
            raise BridgeError("This optical command still requires native acceptance. No input was sent.")
        if command in live_commands:
            ui = WindowsVision(settings)
    if command=="doctor":
        import platform
        import shutil
        return {"platform":platform.system(),"capcut_installed":bool(settings.executable and settings.executable.is_file()),
                "draft_root_exists":settings.root.is_dir(),"ffmpeg":bool(shutil.which("ffmpeg")),"ffprobe":bool(shutil.which("ffprobe")),
                "capcut_running":bool(processes()),"full_functionality_verified":False}
    if command=="replay":
        return drafts.replay(args.job,args.name)
    if command=="ls":
        return drafts.listings()
    if command=="add-overlay":
        drafts.overlay(args.draft,args.media,args.at,args.dur,args.src,args.layer,args.ri,args.mute,args.force)
    elif command=="add-text":
        drafts.text(args.draft,args.text,args.at,args.dur,args.ri,args.force)
    elif command=="remove":
        drafts.remove(args.draft,args.track,args.index)
    elif command in {"transform","keyframe"}:
        values = {key:getattr(args,flag) for key,flag in (("scale","scale"),("x","x"),("y","y"),("rotation","rotate"),("opacity","opacity"))}
        if command=="transform":
            drafts.transform(args.draft,args.track,args.index,values)
        else:
            drafts.keyframe(args.draft,args.track,args.index,args.at,values,args.curve)
    elif command=="clear-keyframes":
        drafts.clear_keyframes(args.draft,args.track,args.index)
    elif command=="graphics":
        drafts.graphics(args.draft,args.job)
    elif command=="launch":
        return {"pid":launch(settings),"status":"launch_requested","desktop_ready_verified":False}
    elif command=="quit":
        quit_app(settings)
    elif command=="open":
        ui.open(args.draft)
    elif command=="dump":
        if optical:
            return [{"name":e.name,"automation_id":e.automation_id,"type":e.kind,"rectangle":e.rectangle,
                     "text_source":e.text_source} for e in ui.elements(args.needle)]
        return [{"name":e.name,"automation_id":e.automation_id,"type":e.kind,"rectangle":e.rectangle} for e in ui.elements(args.needle)]
    elif command=="click":
        if optical:
            return {"clicked":ui.click(args.needle),"status":"dispatched","effect_verified":False,"text_source":"ocr"}
        return {"clicked":ui.click(args.needle)}
    elif command=="clickxy":
        ui.click_xy(args.x,args.y,args.clicks)
    elif command=="scroll":
        ui.scroll(args.x,args.y,args.steps)
    elif command=="key":
        ui.key(args.combo,args.times)
    elif command=="shot":
        return {"file":ui.screenshot(args.output)}
    elif command=="export":
        if optical:
            if args.toggle_sync:
                raise BridgeError("Optical export requires cloud synchronization to remain off.")
            if not args.to:
                raise BridgeError("Choose an explicit export directory with --to.")
            return {"file":ui.export(args.to,args.timeout)}
        return {"file":ui.export(args.to,args.timeout,args.toggle_sync)}
    elif command=="clips":
        if optical:
            return [{"name":e.name,"name_source":e.name_source,"rectangle":e.rectangle,"index":e.index} for e in ui.clips()]
        return [{"name":e.name,"rectangle":e.rectangle} for e in ui.clips()]
    elif command=="playhead":
        current,total = ui.playhead()
        return {"current":current,"total":total}
    elif command=="state":
        result = {"saved":drafts.state(args.draft)} if args.draft else {}
        if state_running:
            active = ui.active_draft()
            if args.draft and args.draft!=active:
                raise BridgeError("The requested draft is not the active CapCut draft.")
            result["active_draft"] = active
            current,total = ui.playhead()
            result.update(playhead=current,total=total,live_clip_count=len(ui.clips()))
        return result
    elif command=="seek":
        active = ui.active_draft()
        if args.draft and args.draft!=active:
            raise BridgeError("The requested draft is not the active CapCut draft.")
        fps = drafts.load(active).get("fps",0)
        return {"seconds":ui.seek(args.seconds,fps)}
    elif command=="select":
        if optical:
            return {"selected":ui.select(args.index),"name_source":"saved_metadata"}
        return {"selected":ui.select(args.index)}
    elif command in {"delete","del"}:
        if optical:
            active = ui.active_draft()
        ui.select(args.index)
        if optical:
            ui.action("delete",expected_index=args.index,expected_draft=active)
        else:
            ui.action("delete")
    elif command=="split":
        if args.seconds is not None or args.draft or optical:
            active = ui.active_draft()
            if args.draft and args.draft!=active:
                raise BridgeError("The requested draft is not the active CapCut draft.")
        if args.seconds is not None:
            fps = drafts.load(active).get("fps",0)
            ui.seek(args.seconds,fps)
        if optical:
            ui.action("split",expected_draft=active)
        else:
            ui.action("split")
    elif command=="save":
        if optical:
            return ui.save()
        ui.key("ctrl+s")
    elif command in {"play","trim-left","trim-right","undo","redo","marker","zoomfit"}:
        if optical and command in {"trim-left","trim-right"}:
            ui.action(command,expected_draft=ui.active_draft())
        else:
            ui.action(command)
    else:
        raise BridgeError("Unknown command.")
    is_live = command in {"clickxy","scroll","key","delete","del","split","save","play","trim-left","trim-right","undo","redo","marker","zoomfit"}
    return {"command":command,"status":"dispatched" if is_live else "completed", "effect_verified":not is_live}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.ERROR,stream=sys.stderr,format="%(levelname)s %(message)s")
    try:
        args = parser().parse_args(argv)
        result = run(args)
        print(json.dumps({"success":True,"result":result},ensure_ascii=False,allow_nan=False,indent=2))
        return 0
    except BridgeError as error:
        LOG.exception("Command failed")
        print(json.dumps({"success":False,"error":str(error)},ensure_ascii=False))
        return 1
    except Exception:
        LOG.exception("Unexpected command failure")
        print(json.dumps({"success":False,"error":"An unexpected error occurred. Please try again later."}))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
