import pytest
from capcut_windows.environment import Settings
from capcut_windows.errors import BridgeError
from capcut_windows.vision import WindowsVision


def test_export_dialog_requires_editor_profile_before_ocr_or_input(tmp_path):
    driver=WindowsVision(Settings(tmp_path))
    def unsupported(*args):
        raise BridgeError('Editor profile is unverified')
    driver.require_profile=unsupported
    driver.active_draft=lambda:pytest.fail('Version gate must precede title/OCR inspection')
    driver.click_box=lambda *args:pytest.fail('Unverified export profile must prevent input')
    with pytest.raises(BridgeError,match='unverified'):
        driver.action('export')
