"""Clipboard-first single-shot GUI. No clipboard history or URL persistence."""

from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
)

from .gui import Worker
from .models import MediaError
from .preferences import download_destination
from .routing import is_single_url, validate_url


def clipboard_url(text):
    """Accept just one URL, never search unrelated clipboard text for links."""
    text = text.strip()
    if not text or len(text) > 8192 or any(c.isspace() for c in text):
        return ""
    try:
        return validate_url(text)
    except MediaError:
        return ""


class QuickWindow(QDialog):
    finished_app = Signal()
    completed = Signal(object)

    def __init__(self, settings=None, *, notify=None, tray_available=None, confirm=None):
        super().__init__()
        self.settings = settings or QSettings("MediaGrab", "MediaGrab")
        self.worker = None
        self.inspection = None
        self.error = None
        self.batch = None
        self.allow_inspection = False
        self.closing = False
        self.exit_timer = QTimer(self)
        self.exit_timer.setSingleShot(True)
        self.exit_timer.timeout.connect(self.finish_app)
        self.notifier = notify
        self.confirm = confirm or self.ask
        self.setWindowTitle("MediaGrab — paste a link")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.url = QLineEdit()
        self.url.setPlaceholderText("Paste a URL and press Enter")
        self.url.setClearButtonEnabled(True)
        self.url.setAccessibleName("Media URL")
        self.url.returnPressed.connect(self.start)
        self.url.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.url.customContextMenuRequested.connect(self.url_menu)
        layout.addWidget(self.url)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.setDefault(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        icon_path = Path(__file__).with_name("assets") / "mediagrab.svg"
        icon = (
            QIcon(str(icon_path))
            if icon_path.is_file()
            else self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        )
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("MediaGrab")
        self.menu = QMenu()
        self.menu.addAction("Show progress", self.show_progress)
        self.cancel_action = self.menu.addAction("Cancel download", self.cancel)
        self.menu.addSeparator()
        self.menu.addAction("Full window…", self.open_advanced)
        self.menu.addAction("Quit", self.close)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(
            lambda reason: (
                self.show_progress() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
            )
        )
        self.background = (
            (QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages())
            if tray_available is None
            else tray_available
        )
        self.resize(560, self.sizeHint().height())

    def start_from_clipboard(self):
        # A focused surface is needed to receive clipboard contents on Wayland.
        # Give Qt one event-loop turn; leave the input visible if access is unavailable.
        self.show()
        self.url.setFocus()
        QTimer.singleShot(150, self.read_clipboard)

    def read_clipboard(self):
        if self.worker or self.url.text():
            return
        url = clipboard_url(QApplication.clipboard().text())
        if url:
            self.url.setText(url)
            self.start()

    def url_menu(self, pos):
        menu = self.url.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction("Full window…", self.open_advanced)
        menu.exec(self.url.mapToGlobal(pos))
        menu.deleteLater()

    def open_advanced(self):
        subprocess.Popen(
            [sys.executable, "-m", "mediagrab", "--advanced"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if not self.worker:
            self.finish_app()

    def show_progress(self):
        self.show()
        self.raise_()

    def notify(self, title, text, error=False):
        if self.notifier:
            self.notifier(title, text, error)
        elif self.background:
            self.tray.showMessage(
                title,
                text,
                QSystemTrayIcon.MessageIcon.Warning
                if error
                else QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
        # Without a usable tray/notification daemon the compact dialog stays visible.
        self.status.setText(text)
        self.status.show()
        if not self.background:
            self.show()

    def start(self):
        if self.worker:
            return
        self.exit_timer.stop()
        url = clipboard_url(self.url.text())
        if not url:
            self.status.setText("Paste one complete HTTP or HTTPS media link, then press Enter.")
            self.status.show()
            self.show()
            return
        self.url.setText(url)
        self.allow_inspection = False
        self.inspection = None
        self.batch = None
        self.tray.show() if self.background else None
        self.notify("MediaGrab started", "Inspecting your link and saving its media automatically.")
        self.run_worker("inspect")

    def run_worker(self, action, **kwargs):
        self.error = None
        root = download_destination(self.settings)
        cookies = str(self.settings.value("cookies_path", ""))
        self.worker = Worker(
            action,
            url=self.url.text(),
            cookies=cookies,
            root=root,
            previews=False,
            parent=self,
            **kwargs,
        )
        self.worker.inspected.connect(self.on_inspected)
        self.worker.downloaded.connect(self.on_downloaded)
        self.worker.failed.connect(self.on_error)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.url.setEnabled(False)
        self.cancel_action.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.progress.setRange(0, 0)
        self.progress.show()
        if self.background:
            self.hide()
        self.worker.start()

    def on_inspected(self, result):
        self.inspection = result

    def on_progress(self, index, count, title, percent):
        message = f"Saving {index + 1}/{count} · {title}"
        self.status.setText(message)
        self.tray.setToolTip(message[:200])
        self.progress.setRange(0, 100 if percent >= 0 else 0)
        if percent >= 0:
            self.progress.setValue(percent)

    def on_downloaded(self, result, reveal):
        self.batch = result
        warnings = self.inspection.warnings if self.inspection else []
        saved = len(result.paths) - result.skipped
        text = (
            f"{saved} saved · {result.skipped} already downloaded · {len(result.failures)} failed."
        )
        if reveal:
            text += "\n" + reveal
        if warnings:
            text += "\n" + "\n".join(warnings)
        if result.failures:
            text += "\n" + "\n".join(result.failures)
        title = "MediaGrab cancelled" if result.cancelled else "MediaGrab finished"
        self.notify(title, text[:1800], bool(result.failures or warnings))
        self.completed.emit(result)

    def on_error(self, kind, message):
        self.error = (kind, message)

    def ask(self, title, text):
        self.show()
        return (
            QMessageBox.question(
                self,
                title,
                text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def idle(self):
        self.url.setEnabled(True)
        self.cancel_action.setEnabled(False)
        self.cancel_button.hide()
        self.progress.hide()
        self.adjustSize()

    def on_finished(self):
        worker = self.worker
        self.worker = None
        cancelled = worker.cancel_event.is_set()
        worker.deleteLater()
        if self.closing:
            self.finish_app()
            return
        if cancelled and worker.action == "inspect":
            self.idle()
            self.notify("MediaGrab cancelled", "Inspection cancelled. Nothing was downloaded.")
            self.show()
            return
        if self.error:
            kind, message = self.error
            if kind == "collection" and worker.action == "inspect" and not self.allow_inspection:
                if self.confirm(
                    "Inspect possible collection?",
                    "This link may contain a profile or playlist. Inspect up to 100 entries first?",
                ):
                    self.allow_inspection = True
                    self.run_worker("inspect", allow=True)
                    return
                self.idle()
                self.status.setText(
                    "Collection skipped. Paste a single-post link to download automatically."
                )
                self.show()
                return
            self.idle()
            self.notify("MediaGrab could not download", message, True)
            self.show()
            return
        if worker.action == "inspect" and self.inspection:
            result = self.inspection
            if not result.items:
                self.idle()
                self.notify("MediaGrab could not download", "No downloadable media found.", True)
                self.show()
                return
            requires_confirmation = (
                result.collection or any(i.collection for i in result.items)
            ) and not is_single_url(self.url.text())
            if requires_confirmation and not self.confirm(
                "Download collection?",
                f"Download all {len(result.items)} listed items? Larger collections are limited to the first 100 entries.",
            ):
                self.idle()
                self.status.setText("Collection download skipped.")
                self.show()
                return
            # User requested automatic saving of all media in a single post. Unknown
            # queued child collections still hit MediaService's separate safety guard.
            self.run_worker("download", items=result.items, allow=True)
            return
        self.idle()
        if self.batch and self.batch.paths and not self.batch.failures and not self.batch.cancelled:
            # Allow the notification call to reach the desktop before dropping the tray.
            self.exit_timer.start(1200)
        else:
            self.show()

    def finish_app(self):
        if self.worker:
            return
        self.tray.hide()
        self.hide()
        self.finished_app.emit()

    def cancel(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.cancel_action.setEnabled(False)
            self.status.setText("Cancelling…")

    def reject(self):
        self.close()

    def closeEvent(self, event):
        if self.worker:
            self.closing = True
            self.cancel()
            event.ignore()
        else:
            self.tray.hide()
            self.finished_app.emit()
            event.accept()
