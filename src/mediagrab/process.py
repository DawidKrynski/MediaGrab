"""Bounded subprocess IO; a new process group owns downloader and FFmpeg children."""

import os
import queue
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from threading import Event, Thread

from .models import Cancelled, MediaError

MAX_OUTPUT_BYTES = 32 * 1024 * 1024


@dataclass
class Output:
    stdout: str
    stderr: str
    returncode: int


def pipe_events(proc, *, threaded=False):
    """Yield bounded chunks or a heartbeat so cancellation never waits for output."""
    if not threaded:
        with selectors.DefaultSelector() as selector:
            for name, stream in (("out", proc.stdout), ("err", proc.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map() or proc.poll() is None:
                ready = selector.select(0.1)
                if not ready:
                    yield None
                for key, _ in ready:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        yield key.data, chunk
        return

    # Windows selectors cannot monitor anonymous subprocess pipes. A bounded
    # queue prevents a verbose downloader from outrunning the metadata limit.
    output = queue.Queue(maxsize=16)
    stopped = Event()

    def send(event):
        while not stopped.is_set():
            try:
                output.put(event, timeout=0.1)
                return
            except queue.Full:
                pass

    def read(name, stream):
        try:
            while not stopped.is_set():
                chunk = stream.read1(65536)
                if not chunk:
                    break
                send((name, chunk))
        except OSError:
            send((name, OSError()))
        finally:
            send((name, None))

    threads = [
        Thread(target=read, args=(name, stream), daemon=True)
        for name, stream in (("out", proc.stdout), ("err", proc.stderr))
    ]
    for thread in threads:
        thread.start()
    remaining = len(threads)
    try:
        while remaining or proc.poll() is None:
            try:
                name, chunk = output.get(timeout=0.1)
            except queue.Empty:
                yield None
                continue
            if chunk is None:
                remaining -= 1
            elif isinstance(chunk, OSError):
                raise MediaError("process", "Could not read the downloader output.")
            else:
                yield name, chunk
    finally:
        stopped.set()
        for thread in threads:
            thread.join(timeout=2)


def classify_error(text: str) -> MediaError:
    # Warnings and generic cookie-help links are not an authentication verdict.
    # Prefer terminal error lines when the CLI includes earlier warnings.
    lines = text.lower().splitlines()
    fatal = [line for line in lines if line.lstrip().startswith("error:") or "[error]" in line]
    s = "\n".join(fatal) if fatal else text.lower()
    if any(x in s for x in ("429", "rate limit", "rate-limit", "too many requests")):
        return MediaError("rate_limit", "The website is limiting requests. Please try again later.")
    if any(
        x in s
        for x in (
            "no module named",
            "ffmpeg not found",
            "ffmpeg is not installed",
            "ffprobe not found",
            "javascript runtime",
            "no impersonate target",
        )
    ):
        return MediaError(
            "dependency",
            "A required download component is missing. The application installation needs repair.",
        )
    if "empty media response" in s:
        return MediaError(
            "access",
            "Instagram returned no downloadable media. The link may be unavailable or restricted for anonymous downloads.",
        )
    if any(x in s for x in ("unsupported url", "no suitable extractor", "unsupportedurl")):
        return MediaError(
            "unsupported", "This type of media link is not supported by the downloader."
        )
    if any(
        x in s
        for x in (
            "authrequired",
            "authenticationerror",
            "authentication required",
            "authenticated cookies",
            "login required",
            "log in",
            "sign in",
            "redirect to login page",
            "redirected to the login page",
            "only available for registered users",
            "cookies are no longer valid",
            "401",
        )
    ):
        return MediaError(
            "login",
            "The website requires authentication for this request. If you already have a cookies file, select it with Choose…, then click Inspect again.",
        )
    if any(
        x in s
        for x in ("unavailable", "not found", "404", "private", "deleted", "403", "geo-restrict")
    ):
        return MediaError(
            "unavailable", "Content is unavailable, private, region blocked, or access was denied."
        )
    return MediaError(
        "network", "Extraction/download failed. Check connectivity or try again later."
    )


class Runner:
    def __init__(self, cancel: Event | None = None):
        self.cancel = cancel if cancel is not None else Event()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    @staticmethod
    def kill_group(proc):
        # Kill the group even when its leader exited; FFmpeg may still hold the pipes.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        time.sleep(0.15)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def run(self, args: list[str], *, timeout=180, on_line=None) -> Output:
        self.check()
        job = None
        # Metadata/path protocols are UTF-8 even when a Windows desktop session
        # defaults redirected Python output to a legacy code page.
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            if os.name == "nt":
                from ._windows import start_process

                proc, job = start_process(args, env=environment)
            else:
                proc = subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    env=environment,
                )
        except FileNotFoundError:
            raise MediaError(
                "dependency", "A required program is missing. Reinstall application dependencies."
            ) from None
        parts = {"out": bytearray(), "err": bytearray()}
        pending = {"out": b"", "err": b""}
        start = time.monotonic()
        events = pipe_events(proc, threaded=os.name == "nt")
        try:
            for event in events:
                self.check()
                if time.monotonic() - start > timeout:
                    raise MediaError(
                        "timeout",
                        "The operation timed out. Try again or inspect a smaller collection.",
                    )
                if event is None:
                    continue
                name, chunk = event
                parts[name].extend(chunk)
                if len(parts[name]) > MAX_OUTPUT_BYTES:
                    raise MediaError(
                        "limit",
                        "Engine metadata exceeded the safety limit; use a single-post URL.",
                    )
                if on_line:
                    pending[name] += chunk
                    while b"\n" in pending[name]:
                        line, pending[name] = pending[name].split(b"\n", 1)
                        on_line(line.removesuffix(b"\r").decode("utf-8", "replace"))
            self.check()
            return Output(
                parts["out"].decode("utf-8", "replace"),
                parts["err"].decode("utf-8", "replace"),
                proc.wait(),
            )
        finally:
            if job is not None:
                # Kills the engine and every child even if the bootstrap exited.
                job.close()
            else:
                self.kill_group(proc)
            proc.wait()
            events.close()
            proc.stdout.close()
            proc.stderr.close()
