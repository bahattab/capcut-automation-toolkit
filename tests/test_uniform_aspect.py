import json
import pytest
from capcut_windows.drafts import DraftStore

@pytest.mark.parametrize('operation',['transform','keyframe'])
@pytest.mark.parametrize('scale',[.8,1.2,1.5])
def test_uniform_scale_retains_square_axis_ratio_for_native_renderer(store: DraftStore,operation,scale):
    original=store.load('test')
    original['tracks'][0]['segments'][0]['uniform_scale']={'on':False,'value':2.0}
    store.content_path('test').write_text(json.dumps(original))
    if operation=='transform':store.transform('test','main',0,{'scale':scale})
    else:store.keyframe('test','main',0,1,{'scale':scale})
    segment=store.load('test')['tracks'][0]['segments'][0]
    assert segment['uniform_scale']=={'on':True,'value':1.0}
    assert segment['source_timerange']==original['tracks'][0]['segments'][0]['source_timerange']
    if operation=='transform':assert segment['clip']['scale']=={'x':scale,'y':scale}
    else:
        assert {f['property_type'] for f in segment['common_keyframes']}=={'KFTypeScaleX','KFTypeScaleY'}
        assert all(f['keyframe_list'][0]['values']==[scale] for f in segment['common_keyframes'])

def test_opacity_keyframe_preserves_existing_nonuniform_aspect(store: DraftStore):
    original=store.load('test')
    original['tracks'][0]['segments'][0]['uniform_scale']={'on':False,'value':2.0}
    store.content_path('test').write_text(json.dumps(original))
    store.keyframe('test','main',0,1,{'opacity':.5})
    assert store.load('test')['tracks'][0]['segments'][0]['uniform_scale']=={'on':False,'value':2.0}
