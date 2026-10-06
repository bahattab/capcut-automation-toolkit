"""Read one native field while preserving memory-backed clipboard formats."""
from collections.abc import Callable
import ctypes
from ctypes import wintypes
import time
import base64
import json
import logging
from pathlib import Path
import tempfile
import uuid
from .errors import BridgeError,backend


class MemoryClipboard:
    @backend
    def __init__(self) -> None:
        import win32clipboard
        self.api=win32clipboard
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        for name,args,result in (
            ('GlobalAlloc',[wintypes.UINT,ctypes.c_size_t],ctypes.c_void_p),
            ('GlobalLock',[ctypes.c_void_p],ctypes.c_void_p),
            ('GlobalUnlock',[ctypes.c_void_p],wintypes.BOOL),
            ('GlobalSize',[ctypes.c_void_p],ctypes.c_size_t),
            ('GlobalFree',[ctypes.c_void_p],ctypes.c_void_p)):
            function=getattr(self.kernel,name);function.argtypes=args;function.restype=result
        for name in ('GetClipboardData','SetClipboardData'):
            function=getattr(self.user,name)
            function.argtypes=[wintypes.UINT]+([ctypes.c_void_p] if name.startswith('Set') else [])
            function.restype=ctypes.c_void_p
        self.buffers:dict[int,int]={}
        self.hidden:int=0
        self.original:dict[int,bytes]={}
        self.recovery_path:Path|None=None

    @backend
    def open(self,handle:int=0) -> None:
        deadline=time.monotonic()+3
        while True:
            try:
                self.api.OpenClipboard(handle)
                return
            except Exception:
                if time.monotonic()>=deadline:
                    raise
                time.sleep(.05)

    @backend
    def snapshot(self) -> tuple[dict[int,bytes],int]:
        result:dict[int,bytes]={};self.open()
        try:
            format_id=0
            while True:
                format_id=self.api.EnumClipboardFormats(format_id)
                if not format_id:
                    break
                if len(result)>=64:
                    raise BridgeError('The clipboard cannot be preserved safely. No field was copied.')
                if format_id>=0xc000 and self.api.GetClipboardFormatName(format_id).lower() in {'ole private data','dataobject'}:
                    raise BridgeError('Object clipboard data cannot be preserved safely. No field was copied.')
                handle=self.user.GetClipboardData(format_id)
                size=self.kernel.GlobalSize(handle)
                if not handle or not 0<size<=16*1024*1024:
                    raise BridgeError('This clipboard format cannot be preserved safely. No field was copied.')
                pointer=self.kernel.GlobalLock(handle)
                if not pointer:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    result[format_id]=ctypes.string_at(pointer,size)
                finally:
                    self.kernel.GlobalUnlock(handle)
                if sum(map(len,result.values()))>32*1024*1024:
                    raise BridgeError('The clipboard is too large to preserve safely. No field was copied.')
            return result,self.api.GetClipboardSequenceNumber()
        finally:
            self.api.CloseClipboard()

    @backend
    def prepare(self,original:dict[int,bytes]) -> None:
        import win32api,win32gui
        self.original=original.copy()
        self.hidden=win32gui.CreateWindowEx(0,'STATIC','',0,0,0,0,0,0,0,win32api.GetModuleHandle(None),None)
        for format_id,data in original.items():
            handle=self.kernel.GlobalAlloc(2,len(data))
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self.buffers[format_id]=handle
            pointer=self.kernel.GlobalLock(handle)
            if not pointer:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                ctypes.memmove(pointer,data,len(data))
            finally:
                self.kernel.GlobalUnlock(handle)

    @backend
    def restore(self,sequence:int) -> bool:
        self.open(self.hidden)
        try:
            if self.api.GetClipboardSequenceNumber()!=sequence:
                return False
            self.api.EmptyClipboard()
            failed=False
            for format_id,handle in list(self.buffers.items()):
                for attempt in range(3):
                    if self.user.SetClipboardData(format_id,handle):
                        del self.buffers[format_id]  # Windows owns this allocation.
                        break
                    time.sleep(.05)
                else:
                    failed=True
            if failed:
                self.recover()
                raise BridgeError('Windows could not restore every clipboard format. Stop further desktop input.')
            return True
        finally:
            self.api.CloseClipboard()

    @backend
    def recover(self) -> None:
        """Persist only encrypted recovery data, scoped to this Windows user."""
        import win32crypt
        payload=json.dumps({str(k):base64.b64encode(v).decode('ascii') for k,v in self.original.items()}).encode('utf-8')
        if self.recovery_path is not None:
            _,readback=win32crypt.CryptUnprotectData(self.recovery_path.read_bytes(),None,None,None,1)
            if readback!=payload:
                raise BridgeError('The encrypted clipboard recovery could not be verified. No field was copied.')
            return
        protected=win32crypt.CryptProtectData(payload,'CapCut kit clipboard recovery',None,None,None,1)
        path=Path(tempfile.gettempdir())/('capcut-kit-clipboard-recovery-'+uuid.uuid4().hex+'.dpapi')
        with path.open('xb') as stream:
            stream.write(protected)
        self.recovery_path=path
        _,readback=win32crypt.CryptUnprotectData(path.read_bytes(),None,None,None,1)
        if readback!=payload:
            raise BridgeError('The encrypted clipboard recovery could not be verified. No field was copied.')

    @backend
    def discard_recovery(self) -> None:
        if self.recovery_path is not None:
            self.recovery_path.unlink(missing_ok=True)
            self.recovery_path=None

    @backend
    def close(self) -> None:
        import win32gui
        try:
            for handle in self.buffers.values():
                self.kernel.GlobalFree(handle)
            self.buffers.clear()
            self.original.clear()
        finally:
            if self.hidden:
                win32gui.DestroyWindow(self.hidden)
                self.hidden=0
            if self.recovery_path is not None:
                logging.getLogger('capcut-kit').error('Encrypted clipboard recovery retained at %s',self.recovery_path)


@backend
def copy_native_text(copy:Callable[[],None],owner_pid:int) -> str:
    import win32process
    clipboard=MemoryClipboard()
    original,initial=clipboard.snapshot()
    copied_sequence:int|None=None
    copy_attempted=False
    try:
        clipboard.prepare(original)
        clipboard.recover()
        if clipboard.api.GetClipboardSequenceNumber()!=initial:
            raise BridgeError('The clipboard changed before copying. No input was sent.')
        copy_attempted=True
        copy()
        deadline=time.monotonic()+10
        while clipboard.api.GetClipboardSequenceNumber()==initial and time.monotonic()<deadline:
            time.sleep(.05)
        clipboard.open()
        try:
            sequence=clipboard.api.GetClipboardSequenceNumber()
            owner=clipboard.api.GetClipboardOwner()
            if sequence==initial:
                raise BridgeError('CapCut did not copy the requested field.')
            if not owner or win32process.GetWindowThreadProcessId(owner)[1]!=owner_pid:
                raise BridgeError('The clipboard changed outside CapCut. Its new contents were left untouched.')
            copied_sequence=sequence
            text=clipboard.api.GetClipboardData(clipboard.api.CF_UNICODETEXT)
            if clipboard.api.GetClipboardSequenceNumber()!=copied_sequence:
                raise BridgeError('The clipboard changed during the field read.')
        finally:
            clipboard.api.CloseClipboard()
        if not isinstance(text,str):
            raise BridgeError('The native field did not supply readable text.')
        return text
    finally:
        try:
            # Ctrl+C may have succeeded before a later input cleanup raised.
            # Identify this owned change under the clipboard lock before restoring.
            if copy_attempted and copied_sequence is None:
                clipboard.open()
                try:
                    sequence=clipboard.api.GetClipboardSequenceNumber()
                    owner=clipboard.api.GetClipboardOwner()
                    if sequence!=initial and owner and win32process.GetWindowThreadProcessId(owner)[1]==owner_pid:
                        copied_sequence=sequence
                finally:
                    clipboard.api.CloseClipboard()
            if copied_sequence is not None:
                if not clipboard.restore(copied_sequence):
                    raise BridgeError('The clipboard changed externally. Its new contents were left untouched.')
                restored,_=clipboard.snapshot()
                if any(restored.get(format_id)!=data for format_id,data in original.items()):
                    raise BridgeError('The original clipboard could not be verified. Stop further desktop input.')
                clipboard.discard_recovery()
            elif not copy_attempted:
                clipboard.discard_recovery()
        finally:
            clipboard.close()
