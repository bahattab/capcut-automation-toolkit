from pathlib import Path
import pytest
from capcut_windows import drafts
from capcut_windows.drafts import DraftStore
from capcut_windows.errors import BridgeError


def test_app_started_during_edit_never_triggers_destructive_rollback(store: DraftStore,monkeypatch: pytest.MonkeyPatch) -> None:
    original = store.content_path("test").read_bytes()
    calls = 0
    def race() -> None:
        nonlocal calls
        calls+=1
        if calls>=2:
            raise BridgeError("Save your work and close CapCut")
    monkeypatch.setattr(drafts,"require_closed",race)
    with pytest.raises(BridgeError,match="close CapCut"):
        store.transform("test","main",0,{"scale":2})
    assert store.content_path("test").read_bytes()==original
    assert (store.folder("test") / "Timelines/state.bin").read_bytes()==b"native cache sentinel"
    assert len(list((store.root / ".capcut-kit-backups").iterdir()))==1


def test_audio_is_not_addressed_as_main_video(store: DraftStore) -> None:
    draft = store.load("test")
    audio = {"id":"audio-track","type":"audio","flag":0,"segments":[{"id":"audio-segment","material_id":"audio"}]}
    draft["tracks"].insert(0,audio)
    assert store.segment(draft,"main",0)["id"]=="segment"


def test_retimed_keyframes_refuse_without_writes(store: DraftStore) -> None:
    store.edit("test",lambda draft,folder:draft["tracks"][0]["segments"][0].update(speed=2))
    before = store.content_path("test").read_bytes()
    with pytest.raises(BridgeError,match="retimed"):
        store.keyframe("test","main",0,1,{"scale":2})
    assert store.content_path("test").read_bytes()==before


def test_empty_transform_is_rejected(store: DraftStore) -> None:
    with pytest.raises(BridgeError,match="at least one"):
        store.transform("test","main",0,{"scale":None})
