"""Per-process audio capture via Windows WASAPI *process loopback*.

In "window only" recording the system loopback grabs the whole audio mix — so a YouTube
tab playing in Chrome bleeds into a recording of a Firefox window. The only clean fix on
Windows is application/process loopback capture: `ActivateAudioInterfaceAsync` with
`AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`, which renders only the target process
(and its child processes) into a private loopback stream. Requires Windows 10 2004
(build 19041) or newer.

There is no pip package for this, so the COM plumbing is hand-rolled here on top of
pycaw's tested `IAudioClient` / `WAVEFORMATEX` definitions (which save us the worst of it).
`ProcessLoopbackRecorder` runs the whole WASAPI session on its own thread and exposes a
simple `start()/read()/stop()` interface returning mono float32 audio at 44.1 kHz, so the
AudioWorker can consume it the same way it consumes a sounddevice stream. Any failure
raises so the caller can fall back to ordinary system loopback — capture must never break.
"""

import queue
import ctypes
import threading
from ctypes import wintypes

import numpy as np

from comtypes import GUID, IUnknown, COMMETHOD, HRESULT, COMObject
from pycaw.api.audioclient import IAudioClient, WAVEFORMATEX

RECORD_SAMPLE_RATE = 44100

# --- WASAPI / AudioClient constants --------------------------------------
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


# --- activation parameter structs ----------------------------------------

class _PROCESS_LOOPBACK_PARAMS(ctypes.Structure):
    _fields_ = [
        ("TargetProcessId", wintypes.DWORD),
        ("ProcessLoopbackMode", ctypes.c_int),
    ]


class AUDIOCLIENT_ACTIVATION_PARAMS(ctypes.Structure):
    # The real struct has a union, but PROCESS_LOOPBACK is its only non-default member,
    # so a plain struct with the loopback params laid out inline is byte-compatible.
    _fields_ = [
        ("ActivationType", ctypes.c_int),
        ("ProcessLoopbackParams", _PROCESS_LOOPBACK_PARAMS),
    ]


class PROPVARIANT(ctypes.Structure):
    # Minimal PROPVARIANT carrying a VT_BLOB. ctypes inserts the 4-byte pad before the
    # 8-byte-aligned pointer automatically (matches the MSVC layout on x64).
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("cbSize", ctypes.c_ulong),
        ("pBlobData", ctypes.c_void_p),
    ]


# --- COM interfaces not provided by pycaw --------------------------------

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
    # Marker interface (no methods of its own). ActivateAudioInterfaceAsync invokes the
    # completion handler from the MTA, so the handler MUST be agile — without advertising
    # IAgileObject the activation call fails up front with E_ILLEGAL_METHOD_CALL.
    _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
    _methods_ = ()


class _CompletionHandler(COMObject):
    """Signals an event when the async activation finishes, so the worker can block on it.

    Advertises IAgileObject so the audio service can call back from the MTA without
    marshalling — required, or ActivateAudioInterfaceAsync returns E_ILLEGAL_METHOD_CALL.
    """
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
    """Capture only `pid` (and its child processes) via WASAPI process loopback.

    `start()` activates + starts the stream (raising on any failure so the caller can fall
    back). `read()` returns the mono float32 audio captured since the last call (or None).
    All COM work happens on an internal MTA thread — process-loopback activation is async
    and its completion callback must land on an MTA/pumped thread.
    """

    def __init__(self, pid: int, samplerate: int = RECORD_SAMPLE_RATE, channels: int = 2) -> None:
        self.pid = int(pid)
        self.samplerate = samplerate
        self.channels = channels
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread = None
        self._ready = threading.Event()   # set once capture is actually running
        self._error = None                # activation/init failure surfaced to start()

    # ---- public API ----------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="ProcessLoopback", daemon=True)
        self._thread.start()
        # Block until the stream is live or activation failed, so the caller knows
        # immediately whether to fall back to system loopback.
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

    # ---- capture thread ------------------------------------------------

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

    def _capture_loop(self, capture, h_event) -> None:
        block_align = self.channels * 4
        while self._running:
            # Auto-reset event fires when a packet is ready; the timeout keeps us
            # responsive to stop() even when the target process is silent.
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
