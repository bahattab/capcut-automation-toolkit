import pytest
from capcut_windows.vision import tooltip_label, Word, Box
from capcut_windows.errors import BridgeError


def words(text,confidence=95):
    return [Word(text,confidence,Box(100,622,170,634),(1,1,1,1))]


@pytest.mark.parametrize('text,expected',[('Undo(Ctrl+Z)','Undo'),('Reset(Ctrl+Shift+Z)','Reset'),('Delete left(Q)','Delete left'),('Undo(¢','Undo')])
def test_tooltip_names_are_independent_of_unused_keycap_glyphs(text,expected):
    assert tooltip_label(words(text),expected)==Box(100,622,170,634)


@pytest.mark.parametrize('text,expected,confidence',[('Delete right(W)','Delete',95),('Redo','Undo',95),('Undo(Ctrl+Z)','Undo',61)])
def test_wrong_action_or_low_confidence_is_rejected(text,expected,confidence):
    with pytest.raises(BridgeError):
        tooltip_label(words(text,confidence),expected)


def test_uncertain_locator_cannot_truncate_another_action():
    with pytest.raises(BridgeError):
        tooltip_label(words('Delete right(W)',61),'Delete',0)
