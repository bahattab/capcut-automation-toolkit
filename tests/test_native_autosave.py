from datetime import datetime
import os
import time
from PIL import Image
import pytest
import capcut_windows.drafts as drafts
import capcut_windows.vision as module
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision, View, Box, Word


@pytest.mark.parametrize('case',['valid','wrong-timestamp','invalid-clock','disagree','changed-project','changed-file'])
def test_autosave_requires_native_consensus_stable_project_and_matching_file(tmp_path,monkeypatch,case):
    path=tmp_path/'draft_content.json'
    path.write_text('{}')
    stamp=time.time()
    os.utime(path,(stamp,stamp-300 if case=='wrong-timestamp' else stamp))
    clock=datetime.fromtimestamp(stamp).strftime('%H:%M:%S')
    driver=WindowsVision(Settings(tmp_path))
    names=iter(['Trial','Other' if case=='changed-project' else 'Trial'])
    driver.active_draft=lambda:next(names)
    driver.require_profile=lambda controls='editor':None
    driver.paused=lambda:True
    view=View(1,Box(0,0,1680,1050),Image.new('RGB',(1680,1050)))
    driver.capture=lambda:view
    def words(captured,region,scale,**kwargs):
        value='25:00:00' if case=='invalid-clock' else '23:59:59' if case=='disagree' and scale==3 else clock
        return [Word('Auto',95,Box(182,13,206,22),(1,1,1,1)),
                Word('saved:',95,Box(209,13,242,22),(1,1,1,1)),
                Word(value,95,Box(245,13,291,22),(1,1,1,1))]
    driver.words=words
    checks=[]
    driver.point=lambda *args:checks.append(True)
    driver.key=lambda *args:pytest.fail('Save must not assume a keyboard binding')
    def clips():
        if case=='changed-file':path.write_text('{"changed":true}')
    driver._clip_views=clips
    monkeypatch.setattr(drafts,'DraftStore',lambda settings:type('Store',(),{'content_path':lambda self,name:path})())
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    if case=='valid':
        assert driver.save()=={'active_draft':'Trial','status':'native_autosave_confirmed','effect_verified':False,
                              'verification_scope':'autosave_record_and_primary_geometry','latest_full_state_verified':False}
        assert checks==[True]
    else:
        with pytest.raises(BridgeError):driver.save()
        assert checks==[]
