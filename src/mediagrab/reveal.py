"""Reveal completed files using the desktop's native file-selection interface."""

import asyncio
import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RevealResult:
    selected: bool
    message: str


def reveal_message(paths):
    # Linux-only dependency: Windows installations do not need a D-Bus stack.
    from dbus_next import Message

    uris = list(dict.fromkeys(Path(p).expanduser().resolve().as_uri() for p in paths))
    return Message(
        destination="org.freedesktop.FileManager1",
        path="/org/freedesktop/FileManager1",
        interface="org.freedesktop.FileManager1",
        member="ShowItems",
        signature="ass",
        body=[uris, ""],
    )


async def send_message(message):
    from dbus_next import MessageType
    from dbus_next.aio import MessageBus

    bus = await MessageBus().connect()
    try:
        reply = await asyncio.wait_for(bus.call(message), timeout=5)
        return reply.message_type != MessageType.ERROR
    finally:
        bus.disconnect()


def select_in_explorer(paths):
    """Ask Windows Explorer to select each folder's completed files together.

    Called from the download worker, with COM initialized for that thread. PIDLs
    remain alive until Shell32 finishes reading them and are always released.
    """
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    pointer = ctypes.c_void_p
    hresult = ctypes.c_long
    ole.CoInitializeEx.argtypes = [pointer, ctypes.c_ulong]
    ole.CoInitializeEx.restype = hresult
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [pointer]
    ole.CoTaskMemFree.restype = None
    shell.SHParseDisplayName.argtypes = [
        ctypes.c_wchar_p,
        pointer,
        ctypes.POINTER(pointer),
        ctypes.c_ulong,
        pointer,
    ]
    shell.SHParseDisplayName.restype = hresult
    shell.ILFindLastID.argtypes = [pointer]
    shell.ILFindLastID.restype = pointer
    shell.SHOpenFolderAndSelectItems.argtypes = [
        pointer,
        ctypes.c_uint,
        ctypes.POINTER(pointer),
        ctypes.c_ulong,
    ]
    shell.SHOpenFolderAndSelectItems.restype = hresult

    initialized = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    if initialized < 0:
        return False
    try:
        folders = dict.fromkeys(path.parent for path in paths)
        for folder in folders:
            allocated = []
            try:

                def parse(path, allocated):
                    pidl = pointer()
                    result = shell.SHParseDisplayName(str(path), None, ctypes.byref(pidl), 0, None)
                    if pidl.value:
                        allocated.append(pidl)
                    if result < 0 or not pidl.value:
                        raise OSError("Windows could not resolve a completed file.")
                    return pidl

                parent = parse(folder, allocated)
                children = [
                    shell.ILFindLastID(parse(path, allocated))
                    for path in paths
                    if path.parent == folder
                ]
                if not all(children):
                    return False
                selection = (pointer * len(children))(*children)
                if shell.SHOpenFolderAndSelectItems(parent, len(children), selection, 0) < 0:
                    return False
            finally:
                for pidl in reversed(allocated):
                    ole.CoTaskMemFree(pidl)
        return True
    finally:
        ole.CoUninitialize()


def open_directory(path):
    path = str(Path(path).expanduser().resolve())
    if sys.platform == "win32":
        os.startfile(path)
    else:
        # xdg-open accepts absolute paths without shell quoting/interpolation.
        subprocess.Popen(
            ["xdg-open", path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def reveal_files(paths, sender=None, opener=open_directory):
    paths = list(dict.fromkeys(Path(p).expanduser().resolve() for p in paths if Path(p).is_file()))
    if not paths:
        return RevealResult(False, "No completed files to reveal.")
    try:
        if sys.platform == "win32":
            ok = select_in_explorer(paths)
        else:
            message = reveal_message(paths)
            ok = sender(message) if sender else asyncio.run(send_message(message))
        if ok:
            return RevealResult(True, "File manager accepted the file selection request.")
    except Exception:
        pass
    try:
        for folder in dict.fromkeys(p.parent for p in paths):
            opener(folder)
        return RevealResult(
            False, "File selection was unavailable; opened the containing folder(s) instead."
        )
    except OSError:
        return RevealResult(
            False, "File selection was unavailable and the file manager could not be opened."
        )
