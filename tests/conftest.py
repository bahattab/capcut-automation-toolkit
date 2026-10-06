import json
from pathlib import Path
import pytest
from capcut_windows import drafts
from capcut_windows.environment import Settings


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> drafts.DraftStore:
    monkeypatch.setattr(drafts,"require_closed",lambda:None)
    root = tmp_path / "drafts"
    root.mkdir()
    draft = {"id":"test-draft","fps":30,"duration":4_000_000,"materials":{
        **{category:[] for category in drafts.schema.EMPTY_MATERIAL_CATS},
        "videos":[{"id":"video","material_name":"source.mp4","duration":10_000_000}]},
        "tracks":[{"id":"main","type":"video","flag":0,"segments":[{
        "id":"segment","material_id":"video","target_timerange":{"start":0,"duration":4_000_000},
        "source_timerange":{"start":2_000_000,"duration":4_000_000},
        "clip":{"scale":{"x":1,"y":1},"transform":{"x":0,"y":0},"rotation":0,"alpha":1},
        "common_keyframes":[]}]}]}
    folder = root / "test"
    folder.mkdir()
    (folder / "draft_content.json").write_text(json.dumps(draft),encoding="utf-8")
    (folder / "draft_meta_info.json").write_text(json.dumps({"draft_name":"test","tm_duration":4_000_000}),encoding="utf-8")
    (folder / "Timelines").mkdir()
    (folder / "Timelines/state.bin").write_bytes(b"native cache sentinel")
    (root / "root_meta_info.json").write_text(json.dumps({"all_draft_store":[{"draft_name":"test","draft_fold_path":str(folder),"tm_duration":4_000_000}],"draft_ids":1}),encoding="utf-8")
    return drafts.DraftStore(Settings(root,projects=tmp_path / "projects"))
