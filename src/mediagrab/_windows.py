"""Windows handles for exclusive destination access and owned process trees.

Only imported on Windows. API layouts follow Microsoft's Win32 documentation;
no third-party process-management code or additional runtime package is bundled.
"""

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess

from .models import MediaError
from . import runtime


kernel = ctypes.WinDLL("kernel32", use_last_error=True)


def api(name, result, *args):
    function = getattr(kernel, name)
    function.restype = result
    function.argtypes = list(args)
    return function


close_handle = api("CloseHandle", wintypes.BOOL, wintypes.HANDLE)
create_file = api(
    "CreateFileW", wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
)
file_information = api(
    "GetFileInformationByHandleEx", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
    ctypes.c_void_p, wintypes.DWORD,
)
create_job = api("CreateJobObjectW", wintypes.HANDLE, ctypes.c_void_p, wintypes.LPCWSTR)
set_job_information = api(
    "SetInformationJobObject", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
    ctypes.c_void_p, wintypes.DWORD,
)
assign_job = api("AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
open_process = api("OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)


class FileAttributes(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


class FileLock:
    """A nonshared, noninheritable handle locks until closed, including on crash."""

    def __init__(self, path):
        # OPEN_ALWAYS, share=0, GENERIC_READ|WRITE, FILE_FLAG_OPEN_REPARSE_POINT.
        self.handle = create_file(str(path), 0xC0000000, 0, None, 4, 0x00200000, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            if ctypes.get_last_error() == 32:  # ERROR_SHARING_VIOLATION
                raise MediaError("busy", "Another MediaGrab download is using this destination.")
            raise ctypes.WinError()
        try:
            info = FileAttributes()
            if not file_information(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError()
            if info.attributes & 0x400:
                raise MediaError("path", "Reparse-point destination locks are refused.")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle is not None:
            close_handle(self.handle)
            self.handle = None


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
        ("scheduling", wintypes.DWORD),
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits), ("io_counters", ctypes.c_ulonglong * 6),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
    ]


class ProcessJob:
    def __init__(self):
        self.handle = create_job(None, None)
        if not self.handle:
            raise ctypes.WinError()
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not set_job_information(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError()
            self.close()
            raise error

    def assign(self, proc):
        handle = open_process(0x0100 | 0x0001, False, proc.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise ctypes.WinError()
        try:
            if not assign_job(self.handle, handle):
                raise ctypes.WinError()
        finally:
            close_handle(handle)

    def close(self):
        if self.handle is not None:
            close_handle(self.handle)
            self.handle = None


def console_python(executable):
    path = Path(executable)
    if path.name.lower() == "pythonw.exe":
        console = path.with_name("python.exe")
        if console.is_file():
            return str(console)
    return str(executable)


def start_process(args, *, env):
    job = ProcessJob()
    proc = None
    try:
        command = [console_python(args[0]), *args[1:]]
        proc = subprocess.Popen(
            [console_python(runtime.helper_python()), "-c", runtime.BOOTSTRAP, *command],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
        )
        job.assign(proc)
        proc.stdin.write(b"1")
        proc.stdin.close()
        return proc, job
    except BaseException:
        job.close()
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
        raise
