import pytest
from capcut_windows.errors import BridgeError
from capcut_windows.vision import verify_frame_count

@pytest.mark.parametrize('value',['71','72','73'])
def test_decoded_count_matches_timeline_with_one_frame_tolerance(value):
    assert verify_frame_count(value,24,3)==int(value)

@pytest.mark.parametrize('value',[None,True,72,'N/A','0','-1','70','74','72.0'])
def test_missing_zero_or_wrong_decoded_count_is_refused(value):
    with pytest.raises(BridgeError):verify_frame_count(value,24,3)
