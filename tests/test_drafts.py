import json
from pathlib import Path
import pytest
from capcut_windows.drafts import DraftStore, folder_name, number, validate
from capcut_windows import drafts
from capcut_windows.errors import BridgeError


@pytest.mark.parametrize("name",["../outside","..","x/y","x\\y","CON","NUL.txt","draft.","draft ","a:b",""])
def test_invalid_names(name: str) -> None:
    with pytest.raises(BridgeError):
        folder_name(name)


@pytest.mark.parametrize("value",[None,True,"5",float("nan"),float("inf"),-1])
def test_numbers(value: object) -> None:
    with pytest.raises(BridgeError):
        number(value,"value")


def test_transform_and_backup(store: DraftStore) -> None:
    store.transform("test","main",0,{"scale":1.5,"x":-.2,"opacity":.7})
    clip = store.load("test")["tracks"][0]["segments"][0]["clip"]
    assert clip["scale"]=={"x":1.5,"y":1.5}
    assert clip["transform"]["x"]==-.2
    assert clip["alpha"]==.7
    backups = list((store.root / ".capcut-kit-backups").iterdir())
    assert len(backups)==1
    assert (backups[0] / "test/Timelines/state.bin").read_bytes()==b"native cache sentinel"
    assert not (store.folder("test") / "Timelines").exists()


def test_invalid_transform_rolls_back(store: DraftStore) -> None:
    before = store.content_path("test").read_bytes()
    with pytest.raises(BridgeError):
        store.transform("test","main",-1,{"scale":2})
    assert store.content_path("test").read_bytes()==before
    assert (store.folder("test") / "Timelines/state.bin").is_file()
    assert not (store.root / ".capcut-kit.lock").exists()


def test_failed_mutation_preserves_everything(store: DraftStore) -> None:
    original = store.content_path("test").read_bytes()
    registry = (store.root / "root_meta_info.json").read_bytes()
    def fail(draft: dict, folder: Path) -> None:
        draft["duration"]=999
        (folder / "Resources").mkdir()
        (folder / "Resources/orphan.bin").write_bytes(b"invalid")
        raise RuntimeError("raw database secret should not reach user")
    with pytest.raises(BridgeError,match="unexpected error"):
        store.edit("test",fail)
    assert store.content_path("test").read_bytes()==original
    assert (store.root / "root_meta_info.json").read_bytes()==registry
    assert not (store.folder("test") / "Resources").exists()
    assert (store.folder("test") / "Timelines/state.bin").is_file()


def test_keyframes_use_source_offsets_and_both_scale_axes(store: DraftStore) -> None:
    store.keyframe("test","main",0,1,{"scale":1.2,"opacity":.5})
    frames = store.load("test")["tracks"][0]["segments"][0]["common_keyframes"]
    assert {f["property_type"] for f in frames}=={"KFTypeScaleX","KFTypeScaleY","KFTypeAlpha"}
    assert all(f["keyframe_list"][0]["time_offset"]==3_000_000 for f in frames)
    store.keyframe("test","main",0,1,{"opacity":.9})
    frames = store.load("test")["tracks"][0]["segments"][0]["common_keyframes"]
    alpha = next(f for f in frames if f["property_type"]=="KFTypeAlpha")
    assert len(alpha["keyframe_list"])==1
    assert alpha["keyframe_list"][0]["values"]==[.9]
    store.clear_keyframes("test","main",0)
    assert store.load("test")["tracks"][0]["segments"][0]["common_keyframes"]==[]


def test_text_unicode_null_source_and_dedup(store: DraftStore) -> None:
    store.text("test","Hello مرحبا 😀",0,3)
    draft = store.load("test")
    text = draft["materials"]["texts"][0]
    content = json.loads(text["content"])
    assert content["text"]=="Hello مرحبا 😀"
    assert content["styles"][0]["range"][1]==len("Hello مرحبا 😀".encode("utf-16-le"))//2
    with pytest.raises(BridgeError,match="already exists"):
        store.text("test","Hello مرحبا 😀",0,3)
    assert len(store.load("test")["materials"]["texts"])==1


def test_remove_and_duration_registry(store: DraftStore) -> None:
    store.text("test","End card",5,3)
    assert store.state("test")["duration"]==8
    assert store.listings()[0]["duration"]==8
    store.remove("test","text",0)
    assert store.state("test")["duration"]==4
    assert store.listings()[0]["duration"]==4


def test_locked_operation_refuses(store: DraftStore) -> None:
    (store.root / ".capcut-kit.lock").write_text("another owner")
    with pytest.raises(BridgeError,match="in progress"):
        store.remove("test","main",0)
    assert (store.root / ".capcut-kit.lock").read_text()=="another owner"


def test_active_app_guard_prevents_writes(store: DraftStore,monkeypatch: pytest.MonkeyPatch) -> None:
    before = store.content_path("test").read_bytes()
    def active() -> None:
        raise BridgeError("Save your work and close CapCut")
    monkeypatch.setattr(drafts,"require_closed",active)
    with pytest.raises(BridgeError,match="close CapCut"):
        store.remove("test","main",0)
    assert store.content_path("test").read_bytes()==before
    assert not (store.root / ".capcut-kit.lock").exists()


def test_overlay_bounds_and_copy(store: DraftStore,tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    media = tmp_path / "media.mov"
    media.write_bytes(b"synthetic media")
    monkeypatch.setattr(drafts,"probe",lambda p:(640,360,5_000_000,False))
    store.overlay("test",str(media),0,source_start=1,mute=True)
    draft = store.load("test")
    segment = draft["tracks"][1]["segments"][0]
    assert segment["source_timerange"]=={"start":1_000_000,"duration":4_000_000}
    assert segment["volume"]==0
    with pytest.raises(BridgeError,match="exceeds"):
        store.overlay("test",str(media),0,duration=5,source_start=1)


def test_graphics_at_zero_atomic_failure(store: DraftStore,tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    job = tmp_path / "job"
    (job / "assets").mkdir(parents=True)
    (job / "assets/first.mov").write_bytes(b"asset")
    (job / "graphics-plan.json").write_text(json.dumps({"graphics":[{"file":"first.mov","start":0}]}))
    monkeypatch.setattr(drafts,"probe",lambda p:(640,360,2_000_000,False))
    store.graphics("test",str(job))
    assert store.load("test")["tracks"][1]["segments"][0]["target_timerange"]["start"]==0


def test_replay_fps_and_no_overwrite(store: DraftStore,tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    job = tmp_path / "job"
    (job / "transcript").mkdir(parents=True)
    (job / "raw").mkdir()
    (job / "raw/raw.mp4").write_bytes(b"asset")
    (job / "transcript/cuts.json").write_text(json.dumps({"clip":"raw.mp4","fps":24,"segments":[{"start":1,"end":3},{"start":4,"end":5}]}))
    monkeypatch.setattr(drafts,"probe",lambda p:(640,360,6_000_000,False))
    monkeypatch.setattr(drafts.shutil,"which",lambda name:None)
    result = store.replay(str(job),"new")
    assert result["duration"]==3
    assert store.load("new")["fps"]==24
    with pytest.raises(BridgeError,match="already exists"):
        store.replay(str(job),"new")
    assert store.load("new")["duration"]==3_000_000


def test_invalid_cut_prevents_new_project(store: DraftStore,tmp_path: Path,monkeypatch: pytest.MonkeyPatch) -> None:
    job = tmp_path / "bad"
    (job / "transcript").mkdir(parents=True)
    (job / "raw").mkdir()
    (job / "raw/raw.mp4").write_bytes(b"asset")
    (job / "transcript/cuts.json").write_text(json.dumps({"clip":"raw.mp4","segments":[{"start":0,"end":10}]}))
    monkeypatch.setattr(drafts,"probe",lambda p:(640,360,6_000_000,False))
    with pytest.raises(BridgeError):
        store.replay(str(job),"bad")
    assert not store.folder("bad").exists()
