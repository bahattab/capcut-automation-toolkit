"""Real FFmpeg/probe integration in isolated folders; no native importer claim."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from capcut_windows import drafts
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tool = shutil.which("ffmpeg")
    if not tool or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg integration requires ffmpeg and ffprobe")
    target = tmp_path_factory.mktemp("real-media") / "synthetic.mp4"
    subprocess.run([tool,"-v","error","-f","lavfi","-i","testsrc2=size=320x180:rate=24",
                    "-f","lavfi","-i","sine=frequency=440:sample_rate=48000","-t","6",
                    "-c:v","libx264","-preset","ultrafast","-threads","1","-c:a","aac",str(target)],
                   capture_output=True,check=True,timeout=120)
    return target


def test_actual_probe(media: Path) -> None:
    width,height,duration,audio = drafts.probe(media)
    assert (width,height)==(320,180)
    assert abs(duration-6_000_000)<100_000
    assert audio is True


def test_real_media_full_file_command_flow(media: Path,tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    # Only process ownership is substituted, because this root is disposable and
    # is not the installed app's registry. All JSON/media operations are real.
    monkeypatch.setattr(drafts,"require_closed",lambda:None)
    job = tmp_path / "job"
    (job / "raw").mkdir(parents=True)
    (job / "transcript").mkdir()
    (job / "assets").mkdir()
    shutil.copy2(media,job / "raw/source.mp4")
    shutil.copy2(media,job / "assets/card.mp4")
    (job / "transcript/cuts.json").write_text(json.dumps({"clip":"source.mp4","fps":24,"segments":[{"start":1,"end":3},{"start":4,"end":5}]}))
    store = drafts.DraftStore(Settings(tmp_path / "isolated-drafts"))
    store.replay(str(job),"integration")
    assert store.load("integration")["fps"]==24
    assert (store.folder("integration") / "draft_cover.jpg").stat().st_size>0
    store.overlay("integration",str(media),0,duration=2,source_start=1,layer=3,render_index=7,mute=True)
    overlay = store.load("integration")["tracks"][1]["segments"][0]
    assert (overlay["render_index"],overlay["track_render_index"])==(7,3)
    store.text("integration","مرحبا Windows 😀",0,2)
    store.transform("integration","main",0,{"scale":1.2,"rotation":10,"x":-.1,"y":.2,"opacity":.8})
    main = store.load("integration")["tracks"][0]["segments"][0]
    assert main["uniform_scale"]=={"on":True,"value":1.0}
    store.keyframe("integration","main",0,1,{"scale":1.1,"x":.1,"y":-.2,"rotation":2,"opacity":.9})
    store.clear_keyframes("integration","main",0)
    (job / "graphics-plan.json").write_text(json.dumps({"beats":[{"file":"card.mp4","start":0}]}))
    store.graphics("integration",str(job))
    store.remove("integration","text",0)
    assert store.state("integration")["duration"]==6
    assert store.listings()[0]["name"]=="integration"
    for material in store.load("integration")["materials"]["videos"]:
        assert drafts.probe(Path(material["path"]))[:2]==(320,180)
    assert len(list((store.root / ".capcut-kit-backups").iterdir()))==8
