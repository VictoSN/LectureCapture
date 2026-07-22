import queue
import ctypes
import threading
from ctypes import wintypes

import numpy as np

import comtypes
from comtypes import GUID, IUnknown, COMMETHOD, HRESULT, COMObject
from pycaw.api.audioclient import IAudioClient, WAVEFORMATEX
from pycaw.api.mmdeviceapi import IMMDeviceEnumerator, IMMDevice

RECORD_SAMPLE_RATE = 44100

# WASAPI / AudioClient constants
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_IEEE_FLOAT = 0x0003
VT_BLOB = 65
S_OK = 0

# Process-loopback activation enums.
AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0

# The magic device path the process-loopback interface is activated against.
VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"

# Win32 wait results.
WAIT_OBJECT_0 = 0
COINIT_MULTITHREADED = 0x0

_kernel32 = ctypes.windll.kernel32
_ole32 = ctypes.windll.ole32


# Activation parameter structs

class _PROCESS_LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [
        ("TargetProcessId", wintypes.DWORD),
        ("ProcessLoopbackMode", ctypes.c_int),
    ]


class AUDIOCLIENT_ACTIVATION_PARAMS(ctypes.Structure):
    # PROCESS_LOOPBACK is the only non-default union member, so a plain struct works.
    _fields_ = [
        ("ActivationType", ctypes.c_int),
        ("ProcessLoopbackParams", _PROCESS_LOOPBACK_PARAMS),
    ]


class PROPVARIANT(ctypes.Structure):
    # Minimal PROPVARIANT with VT_BLOB. ctypes auto-pads to match x64 MSVC layout.
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("cbSize", ctypes.c_ulong),
        ("pBlobData", ctypes.c_void_p),
    ]


# COM interfaces not provided by pycaw

class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")
    _methods_ = (
        COMMETHOD(
            [], HRESULT, "GetBuffer",
            (["out"], ctypes.POINTER(ctypes.POINTER(ctypes.c_byte)), "ppData"),
            (["out"], ctypes.POINTER(wintypes.UINT), "pNumFramesToRead"),
            (["out"], ctypes.POINTER(wintypes.DWORD), "pdwFlags"),
            (["out"], ctypes.POINTER(ctypes.c_ulonglong), "pu64DevicePosition"),
            (["out"], ctypes.POINTER(ctypes.c_ulonglong), "pu64QPCPosition"),
        ),
        COMMETHOD(
            [], HRESULT, "ReleaseBuffer",
            (["in"], wintypes.UINT, "NumFramesRead"),
        ),
        COMMETHOD(
            [], HRESULT, "GetNextPacketSize",
            (["out"], ctypes.POINTER(wintypes.UINT), "pNumFramesInNextPacket"),
        ),
    )


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = (
        COMMETHOD(
            [], HRESULT, "GetActivateResult",
            (["out"], ctypes.POINTER(HRESULT), "activateResult"),
            (["out"], ctypes.POINTER(ctypes.POINTER(IUnknown)), "activatedInterface"),
        ),
    )


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = (
        COMMETHOD(
            [], HRESULT, "ActivateCompleted",
            (["in"], ctypes.POINTER(IActivateAudioInterfaceAsyncOperation), "activateOperation"),
        ),
    )


class IAgileObject(IUnknown):
    # Marker interface (no methods). Required for the MTA completion handler to work.
    _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    _methods_ = ()


class _CompletionHandler(COMObject):
    """Signals an event on async activation completion. Advertises IAgileObject so the
    MTA callback works without marshalling (required to avoid E_ILLEGAL_METHOD_CALL)."""
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self) -> None:
        super().__init__()
        self.event = _kernel32.CreateEventW(None, True, False, None)  # manual-reset

    def ActivateCompleted(self, this, activateOperation):  # noqa: N802 (COM method name)
        _kernel32.SetEvent(self.event)
        return S_OK


_ActivateAudioInterfaceAsync = ctypes.windll.Mmdevapi.ActivateAudioInterfaceAsync
_ActivateAudioInterfaceAsync.restype = HRESULT
_ActivateAudioInterfaceAsync.argtypes = [
    wintypes.LPCWSTR,
    ctypes.POINTER(GUID),
    ctypes.POINTER(PROPVARIANT),
    ctypes.POINTER(IActivateAudioInterfaceCompletionHandler),
    ctypes.POINTER(ctypes.POINTER(IActivateAudioInterfaceAsyncOperation)),
]


def _make_float_format(samplerate: int, channels: int) -> WAVEFORMATEX:
    wf = WAVEFORMATEX()
    wf.wFormatTag = WAVE_FORMAT_IEEE_FLOAT
    wf.nChannels = channels
    wf.nSamplesPerSec = samplerate
    wf.wBitsPerSample = 32
    wf.nBlockAlign = channels * 4
    wf.nAvgBytesPerSec = samplerate * wf.nBlockAlign
    wf.cbSize = 0
    return wf


class ProcessLoopbackRecorder:
    """Capture audio via WASAPI loopback. pid=None captures all system output;
    a pid captures just that process. COM runs on an internal MTA thread."""

    def __init__(self, pid: int | None = None, samplerate: int = RECORD_SAMPLE_RATE, channels: int = 2) -> None:
        self.pid = int(pid) if pid is not None else None
        self.samplerate = samplerate
        self.channels = channels
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread = None
        self._ready = threading.Event()   # set once capture is actually running
        self._error = None                # activation/init failure surfaced to start()

    # Public API

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="ProcessLoopback", daemon=True)
        self._thread.start()
        # Block until stream live or activation failed, so caller knows to fall back.
        if not self._ready.wait(timeout=5.0):
            self._running = False
            raise RuntimeError("process loopback did not start in time")
        if self._error is not None:
            raise RuntimeError(f"process loopback failed: {self._error}")

    def read(self, timeout: float = 0.1) -> "np.ndarray | None":
        """Pop all audio captured so far as one mono float32 array (None if nothing yet)."""
        chunks = []
        try:
            chunks.append(self._queue.get(timeout=timeout))
        except queue.Empty:
            return None
        while True:
            try:
                chunks.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return np.concatenate(chunks) if chunks else None

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3)

    # Capture thread

    def _run(self) -> None:
        _ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        audio_client = None
        h_event = None
        try:
            audio_client = self._activate()
            wf = _make_float_format(self.samplerate, self.channels)
            audio_client.Initialize(
                AUDCLNT_SHAREMODE_SHARED,
                AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
                2_000_000,  # 0.2s buffer (REFERENCE_TIME, 100ns units)
                0,
                ctypes.pointer(wf),
                None,
            )
            h_event = _kernel32.CreateEventW(None, False, False, None)  # auto-reset
            audio_client.SetEventHandle(h_event)

            capture_unk = audio_client.GetService(IAudioCaptureClient._iid_)
            capture = capture_unk.QueryInterface(IAudioCaptureClient)

            audio_client.Start()
            self._ready.set()
            self._capture_loop(capture, h_event)
            audio_client.Stop()
        except Exception as e:
            self._error = e
            self._ready.set()  # unblock start() so it can raise/fall back
        finally:
            if h_event:
                _kernel32.CloseHandle(h_event)
            _ole32.CoUninitialize()

    def _activate(self) -> IAudioClient:
        if self.pid is not None:
            return self._activate_process_loopback()
        return self._activate_system_loopback()

    def _activate_process_loopback(self) -> IAudioClient:
        params = AUDIOCLIENT_ACTIVATION_PARAMS()
        params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
        params.ProcessLoopbackParams.TargetProcessId = self.pid
        params.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE

        prop = PROPVARIANT()
        prop.vt = VT_BLOB
        prop.cbSize = ctypes.sizeof(params)
        prop.pBlobData = ctypes.cast(ctypes.pointer(params), ctypes.c_void_p)

        handler = _CompletionHandler()
        handler_ptr = handler.QueryInterface(IActivateAudioInterfaceCompletionHandler)
        op = ctypes.POINTER(IActivateAudioInterfaceAsyncOperation)()

        hr = _ActivateAudioInterfaceAsync(
            VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
            ctypes.byref(IAudioClient._iid_),
            ctypes.byref(prop),
            handler_ptr,
            ctypes.byref(op),
        )
        if hr != S_OK:
            raise RuntimeError(f"ActivateAudioInterfaceAsync failed (hr=0x{hr & 0xFFFFFFFF:08X})")

        # Wait for the async completion callback, then read the real activation result.
        if _kernel32.WaitForSingleObject(handler.event, 5000) != WAIT_OBJECT_0:
            raise RuntimeError("activation completion timed out")
        activate_hr, activated = op.GetActivateResult()
        if activate_hr != S_OK:
            raise RuntimeError(f"GetActivateResult failed (hr=0x{activate_hr & 0xFFFFFFFF:08X})")
        return activated.QueryInterface(IAudioClient)

    def _activate_system_loopback(self) -> IAudioClient:
        enumerator = comtypes.CoCreateInstance(
            GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
            interface=IMMDeviceEnumerator,
            clsctx=comtypes.CLSCTX_INPROC_SERVER,
        )
        device = enumerator.GetDefaultAudioEndpoint(0, 0)  # eRender=0, eConsole=0
        unk = device.Activate(IAudioClient._iid_, comtypes.CLSCTX_ALL, None)
        return unk.QueryInterface(IAudioClient)

    def _capture_loop(self, capture, h_event) -> None:
        block_align = self.channels * 4
        while self._running:
            # Auto-reset event fires per packet; timeout keeps us responsive to stop().
            _kernel32.WaitForSingleObject(h_event, 200)
            while self._running:
                num = capture.GetNextPacketSize()
                if num == 0:
                    break
                data_ptr, frames, flags, _devpos, _qpc = capture.GetBuffer()
                if flags & AUDCLNT_BUFFERFLAGS_SILENT or not data_ptr:
                    mono = np.zeros(frames, dtype=np.float32)
                else:
                    raw = ctypes.string_at(data_ptr, frames * block_align)
                    stereo = np.frombuffer(raw, dtype=np.float32).reshape(-1, self.channels)
                    mono = stereo.mean(axis=1).astype(np.float32)
                capture.ReleaseBuffer(frames)
                self._queue.put(mono)


def pid_from_hwnd(hwnd) -> "int | None":
    """Resolve the owning process id of a top-level window (for window-only capture)."""
    try:
        import win32process
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid) or None
    except Exception as e:
        print(f"[ProcessLoopback] could not resolve PID for hwnd={hwnd}: {e}")
        return None
