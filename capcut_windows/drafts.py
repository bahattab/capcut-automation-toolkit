"""Validated draft transactions. Live app ownership is never bypassed."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Iterator

from .environment import Settings, require_closed
from .errors import BridgeError, backend, LOG
from . import schema

Json = dict[str, Any]  # CapCut's evolving JSON schema; validated at the boundary.


@backend
def number(value: object, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeError(f"{name} must be a number.")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise BridgeError(f"{name} must be finite and at least {minimum}.")
    return result


@backend
def folder_name(name: str) -> str:
    if not name or name in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((" ", ".")):
        raise BridgeError("Use a valid Windows draft name without path separators.")
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise BridgeError("That name is reserved by Windows.")
    return name


@backend
def read_json(path: Path) -> Json:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise BridgeError("Expected a JSON object.")
    return value


@backend
def atomic_json(path: Path, value: Json) -> None:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{schema.uid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@backend
def probe(path: Path) -> tuple[int, int, int, bool]:
    if not path.is_file():
        raise BridgeError("The media file does not exist.")
    tool = shutil.which("ffprobe")
    if not tool:
        raise BridgeError("Install FFmpeg and make ffprobe available on PATH.")
    result = subprocess.run([tool, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True, timeout=60)
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise BridgeError("The media must contain a video stream.")
    duration = video.get("duration") or data.get("format", {}).get("duration")
    seconds = number(float(duration), "Media duration", 0.000001)
    return int(video["width"]), int(video["height"]), round(seconds * 1_000_000), any(s.get("codec_type") == "audio" for s in data.get("streams", []))


@backend
def validate(draft: Json) -> None:
    tracks = draft.get("tracks")
    materials = draft.get("materials")
    if not isinstance(tracks, list) or not isinstance(materials, dict):
        raise BridgeError("This draft format is not supported.")
    ids = {m["id"] for collection in materials.values() if isinstance(collection, list)
           for m in collection if isinstance(m, dict) and isinstance(m.get("id"), str)}
    for track in tracks:
        if not isinstance(track, dict) or not isinstance(track.get("segments"), list):
            raise BridgeError("This draft contains an invalid track.")
        for segment in track["segments"]:
            if not isinstance(segment, dict) or segment.get("material_id") not in ids:
                raise BridgeError("This draft contains a segment without its material.")
            target = segment.get("target_timerange")
            if not isinstance(target, dict):
                raise BridgeError("This draft contains an invalid time range.")
            number(target.get("start"), "Segment start")
            number(target.get("duration"), "Segment duration", 1)


class DraftStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.root

    @backend
    def safe_file(self, folder: Path, filename: str) -> Path:
        path=folder/filename
        if path.is_symlink() or path.is_junction() or path.resolve().parent!=folder.resolve():
            raise BridgeError("Linked project metadata cannot be used safely.")
        return path

    @backend
    def check_tree(self, folder: Path) -> None:
        for parent,dirs,_ in os.walk(folder,followlinks=False):
            for name in dirs:
                if (Path(parent)/name).is_junction():
                    raise BridgeError("Nested linked folders require manual recovery review.")

    @backend
    def folder(self, name: str) -> Path:
        original = self.root / folder_name(name)
        if original.is_symlink() or original.is_junction():
            raise BridgeError("Linked draft folders cannot be edited safely.")
        folder = original.resolve()
        if folder.parent != self.root.resolve():
            raise BridgeError("The draft folder must remain inside the configured project root.")
        return folder

    @backend
    def content_path(self, name: str) -> Path:
        folder = self.folder(name)
        for filename in ("draft_content.json", "draft_info.json"):
            if (folder / filename).is_file():
                if (folder / filename).resolve().parent != folder:
                    raise BridgeError("Linked draft files cannot be edited safely.")
                return folder / filename
        raise BridgeError("The draft was not found or its format is unsupported.")

    @backend
    def load(self, name: str) -> Json:
        draft = read_json(self.content_path(name))
        validate(draft)
        return draft

    @backend
    def listings(self) -> list[Json]:
        path = self.safe_file(self.root,"root_meta_info.json")
        if not path.exists():
            return []
        rows = read_json(path).get("all_draft_store", [])
        if not isinstance(rows, list):
            raise BridgeError("The draft registry has an unsupported format.")
        return [{"name":r.get("draft_name", "Untitled"), "duration":(r.get("tm_duration") or 0) / 1e6,
                 "folder":r.get("draft_fold_path", "")} for r in rows if isinstance(r, dict)]

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".capcut-kit.lock"
        try:
            handle = path.open("x", encoding="utf-8")
        except FileExistsError as error:
            raise BridgeError("Another draft operation is in progress. Check the lock before retrying.") from error
        try:
            with handle:
                handle.write(str(os.getpid()))
            require_closed()
            yield
        except Exception:
            LOG.exception("Draft transaction failed")
            raise
        finally:
            path.unlink(missing_ok=True)

    @backend
    def platform(self) -> Json:
        # Read only non-identifying compatibility fields from a native draft.
        for path in self.root.glob("*/draft_content.json"):
            try:
                native = read_json(path).get("platform", {})
                if native.get("os") == "windows":
                    return {k:v for k,v in native.items() if k in {"os", "os_version", "app_id", "app_version", "app_source"}}
            except BridgeError:
                continue
        return {"os":"windows", "os_version":"", "app_id":359289, "app_version":"", "app_source":"cc"}

    @backend
    def backup(self, folder: Path | None = None) -> Path:
        registry = self.safe_file(self.root,"root_meta_info.json")
        if folder:
            self.check_tree(folder)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.root / ".capcut-kit-backups"
        if destination.is_symlink() or destination.is_junction() or destination.resolve().parent != self.root.resolve():
            raise BridgeError("Linked backup folders cannot be used safely.")
        backup = destination / (stamp + "-" + schema.uid())
        backup.mkdir(parents=True)
        if registry.exists():
            shutil.copy2(registry, backup / registry.name)
        if folder:
            shutil.copytree(folder, backup / folder.name,symlinks=True)
        return backup

    @backend
    def local_media(self, folder: Path, source: Path) -> Path:
        source = source.expanduser().resolve(strict=True)
        resources = folder / "Resources"
        if resources.is_symlink() or resources.is_junction() or resources.resolve().parent != folder.resolve():
            raise BridgeError("Linked media folders cannot be edited safely.")
        resources.mkdir(exist_ok=True)
        # Full file digest prevents basename collisions and accidental media reuse.
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        target = resources / (digest[:16] + "-" + source.name)
        if target.is_symlink() or target.resolve().parent != resources.resolve():
            raise BridgeError("Linked media files cannot be edited safely.")
        if not target.exists():
            shutil.copy2(source, target)
        return target

    @backend
    def replay(self, job: str, name: str | None = None) -> Json:
        job_folder = Path(job).expanduser()
        if not job_folder.is_dir():
            job_folder = self.settings.projects / folder_name(job)
        job_folder = job_folder.resolve()
        cuts = read_json(job_folder / "transcript/cuts.json")
        spans = cuts.get("segments")
        if not isinstance(spans, list) or not spans:
            raise BridgeError("The edit decision list must contain at least one segment.")
        fps = number(cuts.get("fps", 30), "Frame rate", 1)
        clip = cuts.get("clip") or spans[0].get("clip")
        if not isinstance(clip, str) or Path(clip).name != clip or "\\" in clip:
            raise BridgeError("The source clip must be a filename inside the job's raw folder.")
        source = (job_folder / "raw" / clip).resolve()
        if source.parent != (job_folder / "raw").resolve():
            raise BridgeError("The source clip must remain inside the job's raw folder.")
        width, height, media_duration, audio = probe(source)
        validated = []
        for span in spans:
            if not isinstance(span, dict) or span.get("clip", clip) != clip:
                raise BridgeError("Every segment must reference the same source clip.")
            start, end = number(span.get("start"), "Cut start"), number(span.get("end"), "Cut end")
            if end <= start or round(end * 1e6) > media_duration:
                raise BridgeError("Cut ranges must have positive duration and fit inside the source video.")
            validated.append((round(start * 1e6), round((end-start) * 1e6)))
        draft_name = folder_name(name or job_folder.name)
        folder = self.folder(draft_name)
        with self.lock():
            if folder.exists():
                raise BridgeError("A draft with this name already exists. Choose a new name.")
            self.backup()
            registry_path = self.safe_file(self.root,"root_meta_info.json")
            old_registry = registry_path.read_bytes() if registry_path.exists() else None
            try:
                folder.mkdir()
                local = self.local_media(folder, source)
                materials = {category:[] for category in schema.EMPTY_MATERIAL_CATS}
                mid = schema.uid()
                materials["videos"].append(schema.video_material(mid, local.as_posix(), width, height, media_duration, audio))
                segments = []
                cursor = 0
                for start, duration in validated:
                    segments.append(schema.segment(mid, start, duration, cursor, schema.segment_extras(materials)))
                    cursor += duration
                platform = self.platform()
                draft,_,_,_ = schema.build_draft(draft_name,local.as_posix(),cuts,width,height,
                                               (width,height,media_duration,audio),platform)
                draft.update(name=draft_name,fps=fps,new_version="185.0.0",materials=materials,duration=cursor)
                draft["tracks"][0]["segments"] = segments
                draft["materials"]["videos"][0]["material_name"] = source.name
                validate(draft)
                atomic_json(folder / "draft_content.json", draft)
                now = time.time_ns() // 1000
                meta = schema.meta_entry(draft_name, folder, draft["id"], local, media_duration, width, height, cursor, now)
                meta["draft_root_path"] = self.root.as_posix()
                atomic_json(folder / "draft_meta_info.json", meta)
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg:
                    subprocess.run([ffmpeg,"-v","error","-ss",str(validated[0][0]/1e6),"-i",str(local),"-frames:v","1","-vf","scale=480:-2",str(folder / "draft_cover.jpg")],check=True,timeout=60,capture_output=True)
                registry_path = self.safe_file(self.root,"root_meta_info.json")
                registry = read_json(registry_path) if registry_path.exists() else {"all_draft_store":[],"draft_ids":0,"root_path":self.root.as_posix()}
                row = schema.registry_entry(draft_name,folder,draft["id"],cursor,now)
                row["draft_root_path"] = self.root.as_posix()
                row["draft_json_file"] = (folder / "draft_content.json").as_posix()
                registry.setdefault("all_draft_store",[]).insert(0,row)
                registry["draft_ids"] = len(registry["all_draft_store"])
                require_closed()
                registry_path = self.safe_file(self.root,"root_meta_info.json")
                atomic_json(registry_path,registry)
            except Exception:
                LOG.exception("Rolling back draft creation")
                # A concurrently started app owns the files now. Leave the backup
                # for explicit recovery rather than clobbering its state.
                require_closed()
                registry_path = self.safe_file(self.root,"root_meta_info.json")
                if self.folder(draft_name) != folder or folder.parent != self.root.resolve():
                    raise BridgeError("Recovery needs manual review of the project folder.")
                shutil.rmtree(folder)
                if old_registry is None:
                    registry_path.unlink(missing_ok=True)
                else:
                    registry_path.write_bytes(old_registry)
                raise
        return {"name":draft_name,"segments":len(segments),"duration":cursor/1e6}

    @backend
    def edit(self, name: str, mutate: Callable[[Json, Path], None]) -> Json:
        folder = self.folder(name)
        with self.lock():
            path = self.content_path(name)
            self.safe_file(folder,"draft_meta_info.json")
            draft = self.load(name)
            backup = self.backup(folder)
            try:
                mutate(draft,folder)
                for track in draft["tracks"]:
                    for segment in track["segments"]:
                        if segment.get("source_timerange") is None:
                            segment["source_timerange"] = {"start":0,"duration":segment["target_timerange"]["duration"]}
                draft["duration"] = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"] for t in draft["tracks"] for s in t["segments"]),default=0)
                validate(draft)
                require_closed()
                atomic_json(path,draft)
                # Preserve native cache by moving it to the full transaction backup.
                cache = folder / "Timelines"
                if cache.exists():
                    if cache.is_symlink() or cache.is_junction() or cache.resolve().parent != folder:
                        raise BridgeError("Linked timeline caches cannot be edited safely.")
                    shutil.rmtree(cache)
                meta_path = self.safe_file(folder,"draft_meta_info.json")
                if meta_path.exists():
                    meta = read_json(meta_path)
                    meta.update(tm_duration=draft["duration"],tm_draft_modified=time.time_ns()//1000)
                    atomic_json(meta_path,meta)
                registry_path = self.safe_file(self.root,"root_meta_info.json")
                if registry_path.exists():
                    registry = read_json(registry_path)
                    for row in registry.get("all_draft_store",[]):
                        if Path(row.get("draft_fold_path", "")).resolve() == folder:
                            row.update(tm_duration=draft["duration"],tm_draft_modified=time.time_ns()//1000)
                    atomic_json(registry_path,registry)
            except Exception:
                LOG.exception("Restoring failed edit from backup")
                require_closed()
                registry_path = self.safe_file(self.root,"root_meta_info.json")
                if self.folder(name) != folder or folder.parent != self.root.resolve():
                    raise BridgeError("Recovery needs manual review of the project folder.")
                self.check_tree(folder)
                self.check_tree(backup / folder.name)
                shutil.rmtree(folder)
                shutil.copytree(backup / folder.name,folder,symlinks=True)
                saved_registry = backup / "root_meta_info.json"
                if saved_registry.exists():
                    shutil.copy2(saved_registry,registry_path)
                raise
        return draft

    @backend
    def segment(self, draft: Json, role: str, index: int) -> Json:
        if role not in {"main","text","overlay"} or index < 0:
            raise BridgeError("Choose a valid track role and a non-negative segment index.")
        flag = {"main":0,"text":1,"overlay":2}[role]
        kind = "text" if role=="text" else "video"
        segments = [s for t in draft["tracks"] if t.get("flag",0)==flag and t.get("type")==kind for s in t["segments"]]
        if index >= len(segments):
            raise BridgeError("The segment index is outside this track.")
        return segments[index]

    @backend
    def overlay(self, name: str, media: str, at: float, duration: float | None = None,
                source_start: float = 0, layer: int = 1, render_index: int | None = None,
                mute: bool = False, force: bool = False) -> Json:
        at = number(at,"Overlay start")
        source_start = number(source_start,"Source start")
        if layer < 1 or (render_index is not None and render_index < 0):
            raise BridgeError("Overlay layer must be positive and render index non-negative.")
        original = Path(media).expanduser().resolve()
        width,height,media_duration,audio = probe(original)
        duration = number(duration if duration is not None else media_duration/1e6-source_start,"Overlay duration",0.000001)
        if round((source_start+duration)*1e6) > media_duration:
            raise BridgeError("The overlay source range exceeds the media duration.")
        def mutate(draft: Json, folder: Path) -> None:
            if not force:
                for track in draft["tracks"]:
                    for seg in track["segments"]:
                        if track.get("flag")==2 and seg["target_timerange"]["start"]==round(at*1e6):
                            mat = next((m for m in draft["materials"]["videos"] if m["id"]==seg["material_id"]),{})
                            if mat.get("material_name")==original.name:
                                raise BridgeError("This overlay already exists at that time. Use --force to add another.")
            local = self.local_media(folder,original)
            mid = schema.uid()
            mat = schema.video_material(mid,local.as_posix(),width,height,media_duration,audio)
            mat["material_name"] = original.name
            draft["materials"]["videos"].append(mat)
            seg = schema.segment(mid,round(source_start*1e6),round(duration*1e6),round(at*1e6),schema.segment_extras(draft["materials"]))
            seg["render_index"] = render_index if render_index is not None else layer
            seg["track_render_index"] = layer
            if mute:
                seg["volume"] = 0
            track = next((t for t in draft["tracks"] if t.get("flag")==2 and t.get("type")=="video"
                          and any(s.get("track_render_index")==layer for s in t.get("segments",[]))),None)
            if track is None:
                track = {"id":schema.uid(),"type":"video","flag":2,"attribute":0,"name":f"Overlay {layer}","segments":[]}
                draft["tracks"].append(track)
            track["segments"].append(seg)
        return self.edit(name,mutate)

    @backend
    def text(self, name: str, text: str, at: float, duration: float = 3,
             render_index: int = 1, force: bool = False) -> Json:
        at,duration = number(at,"Text start"),number(duration,"Text duration",0.000001)
        if not text.strip() or render_index < 0:
            raise BridgeError("Text must not be empty and render index must be non-negative.")
        def mutate(draft: Json, folder: Path) -> None:
            for track in draft["tracks"]:
                for seg in track["segments"]:
                    if not force and track.get("type")=="text" and seg["target_timerange"]["start"]==round(at*1e6):
                        material = next((m for m in draft["materials"].get("texts",[]) if m["id"]==seg["material_id"]),{})
                        if json.loads(material.get("content","{}" )).get("text")==text:
                            raise BridgeError("This text already exists at that time. Use --force to add another.")
            # Standard system font avoids unavailable or licensed font assets.
            font = Path(os.environ.get("WINDIR","C:/Windows")) / "Fonts/arial.ttf"
            mid = schema.uid()
            content = {"text":text,"styles":[{"range":[0,len(text.encode('utf-16-le'))//2],"size":8.0,
                       "fill":{"content":{"solid":{"color":[1.0,1.0,1.0]}}},"font":{"path":font.as_posix(),"id":""}}]}
            material = {"id":mid,"type":"text","content":json.dumps(content,ensure_ascii=False),"font_path":font.as_posix(),
                        "font_name":"Arial","font_size":8.0,"text_color":"#ffffff","alignment":1,"bold_width":0.0,
                        "border_width":0.0,"check_flag":7,"line_spacing":0.02,"letter_spacing":0.0,"text_alpha":1.0,
                        "shadow_alpha":0.0,"background_alpha":0.0,"font_id":"","font_title":"Arial","text_size":30,
                        "typesetting":0,"underline":False,"italic":False,"is_rich_text":True,"add_type":0}
            draft["materials"].setdefault("texts",[]).append(material)
            seg = schema.segment(mid,0,round(duration*1e6),round(at*1e6),[])
            seg["render_index"] = seg["track_render_index"] = render_index
            track = next((t for t in draft["tracks"] if t.get("flag")==1 and t.get("type")=="text"),None)
            if track is None:
                track = {"id":schema.uid(),"type":"text","flag":1,"attribute":0,"name":"Text","segments":[]}
                draft["tracks"].append(track)
            track["segments"].append(seg)
        return self.edit(name,mutate)

    @backend
    def remove(self, name: str, role: str, index: int) -> Json:
        def mutate(draft: Json, folder: Path) -> None:
            selected = self.segment(draft,role,index)
            for track in draft["tracks"]:
                track["segments"] = [seg for seg in track["segments"] if seg["id"] != selected["id"]]
        return self.edit(name,mutate)

    @backend
    def transform(self, name: str, role: str, index: int, values: Json) -> Json:
        clean: Json = {}
        for key,value in values.items():
            if value is None:
                continue
            if key not in {"scale","x","y","rotation","opacity"}:
                raise BridgeError("Unknown transform property.")
            clean[key] = number(value,key,0 if key in {"scale","opacity"} else -1e9)
        if clean.get("scale",1)<=0 or clean.get("opacity",1)>1:
            raise BridgeError("Scale must be positive; opacity must be between zero and one.")
        if not clean:
            raise BridgeError("Supply at least one transform property.")
        def mutate(draft: Json, folder: Path) -> None:
            clip = self.segment(draft,role,index).setdefault("clip",{})
            if "scale" in clean:
                clip["scale"] = {"x":clean["scale"],"y":clean["scale"]}
                # Native value is the X/Y aspect ratio, not the scale amount.
                self.segment(draft,role,index)["uniform_scale"] = {"on":True,"value":1.0}
            if "rotation" in clean:
                clip["rotation"] = clean["rotation"]
            if "opacity" in clean:
                clip["alpha"] = clean["opacity"]
            for key in ("x","y"):
                if key in clean:
                    clip.setdefault("transform",{})[key] = clean[key]
        return self.edit(name,mutate)

    @backend
    def keyframe(self, name: str, role: str, index: int, at: float, values: Json, curve: str = "Line") -> Json:
        at = number(at,"Keyframe time")
        if curve != "Line":
            raise BridgeError("Only the validated Line keyframe curve is supported.")
        types = {"scale":("KFTypeScaleX","KFTypeScaleY"),"x":("KFTypePositionX",),"y":("KFTypePositionY",),"rotation":("KFTypeRotation",),"opacity":("KFTypeAlpha",)}
        clean = {key:number(value,key,0 if key in {"scale","opacity"} else -1e9) for key,value in values.items() if value is not None and key in types}
        if not clean or clean.get("scale",1)<=0 or clean.get("opacity",1)>1:
            raise BridgeError("Supply valid keyframe values; opacity must be in [0, 1] and scale positive.")
        def mutate(draft: Json, folder: Path) -> None:
            seg = self.segment(draft,role,index)
            if "scale" in clean:
                seg["uniform_scale"]={"on":True,"value":1.0}
            target = seg["target_timerange"]
            relative = round(at*1e6)-target["start"]
            if not 0 <= relative <= target["duration"]:
                raise BridgeError("The keyframe time must fall inside the selected segment.")
            if seg.get("speed",1)!=1 or seg.get("reverse"):
                raise BridgeError("Keyframes on retimed or reversed clips require native-schema verification.")
            references=set(seg.get("extra_material_refs") or [])
            speeds=[material for material in draft.get("materials",{}).get("speeds",[])
                    if material.get("id") in references]
            if any(material.get("speed",1)!=1 or material.get("curve_speed")
                   or material.get("mode",0)!=0 for material in speeds):
                raise BridgeError("Keyframes on retimed or reversed clips require native-schema verification.")
            offset = (seg.get("source_timerange") or {}).get("start",0)+relative
            frames = seg.setdefault("common_keyframes",[])
            for key,value in clean.items():
                for property_type in types[key]:
                    entry = next((f for f in frames if f.get("property_type")==property_type),None)
                    if entry is None:
                        entry = {"id":schema.uid(),"property_type":property_type,"material_id":"","keyframe_list":[]}
                        frames.append(entry)
                    point = {"id":schema.uid(),"curveType":"Line","time_offset":offset,"values":[value],
                             "left_control":{"x":0,"y":0},"right_control":{"x":0,"y":0},"graphID":"","string_value":""}
                    entry["keyframe_list"] = sorted([p for p in entry["keyframe_list"] if p["time_offset"]!=offset]+[point],key=lambda p:p["time_offset"])
        return self.edit(name,mutate)

    @backend
    def clear_keyframes(self, name: str, role: str, index: int) -> Json:
        def mutate(draft: Json, folder: Path) -> None:
            self.segment(draft,role,index)["common_keyframes"] = []
        return self.edit(name,mutate)

    @backend
    def graphics(self, name: str, job: str) -> Json:
        job_folder = Path(job) if Path(job).is_dir() else self.settings.projects / folder_name(job)
        plan = read_json(job_folder / "graphics-plan.json")
        rows = plan.get("graphics") or plan.get("beats")
        if not isinstance(rows,list) or not rows:
            raise BridgeError("The graphics plan must contain overlays.")
        # All assets are validated before the first commit; keep missing assets explicit.
        queued = []
        for row in rows:
            if not isinstance(row,dict):
                raise BridgeError("Each graphic must be a JSON object.")
            filename = row.get("file") or (str(row["id"])+".mov" if row.get("id") else None)
            if not isinstance(filename,str) or Path(filename).name != filename or "\\" in filename:
                raise BridgeError("Graphic files must be filenames inside the assets folder.")
            start = next((row[k] for k in ("start","t","time") if row.get(k) is not None),None)
            start = number(start,"Graphic start")
            media = (job_folder / "assets" / filename).resolve()
            if media.parent != (job_folder / "assets").resolve():
                raise BridgeError("The graphic must remain inside its assets folder.")
            queued.append((media,start,probe(media)))
        def mutate(draft: Json, folder: Path) -> None:
            track = {"id":schema.uid(),"type":"video","flag":2,"attribute":0,"name":"Graphics","segments":[]}
            for media,start,(width,height,duration,audio) in queued:
                local = self.local_media(folder,media)
                mid = schema.uid()
                draft["materials"]["videos"].append(schema.video_material(mid,local.as_posix(),width,height,duration,audio))
                seg = schema.segment(mid,0,duration,round(start*1e6),schema.segment_extras(draft["materials"]))
                seg["render_index"] = seg["track_render_index"] = 1
                track["segments"].append(seg)
            draft["tracks"].append(track)
        return self.edit(name,mutate)

    @backend
    def state(self, name: str) -> Json:
        draft = self.load(name)
        materials = {m["id"]:m for category in draft["materials"].values() if isinstance(category,list) for m in category if isinstance(m,dict) and "id" in m}
        return {"duration":draft["duration"]/1e6,"fps":draft.get("fps",30),"tracks":[{
            "type":t.get("type","unknown"),"flag":t.get("flag",0),"segments":[{
                "index":i,"start":s["target_timerange"]["start"]/1e6,"duration":s["target_timerange"]["duration"]/1e6,
                "material":materials.get(s["material_id"],{}).get("material_name",materials.get(s["material_id"],{}).get("type","Unknown"))
            } for i,s in enumerate(t["segments"])]} for t in draft["tracks"]]}
