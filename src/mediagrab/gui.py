import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from threading import Event

import requests
from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import BatchResult, MediaError, default_selection, selected_items
from .preferences import download_destination
from .privacy import protect_private_directory
from .process import Runner
from .reveal import open_directory, reveal_files
from .service import MediaService


class Worker(QThread):
    inspected = Signal(object)
    downloaded = Signal(object, str)
    failed = Signal(str, str)
    progress = Signal(int, int, str, int)
    thumbnail = Signal(str, bytes)

    def __init__(
        self,
        action,
        *,
        url="",
        cookies="",
        items=None,
        root="",
        allow=False,
        previews=True,
        parent=None,
    ):
        super().__init__(parent)
        self.action, self.url, self.cookies = action, url, cookies
        self.items, self.root, self.allow = items or [], root, allow
        self.previews = previews
        self.cancel_event = Event()

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="mediagrab-private-") as private:
                cookies = ""
                if self.cookies:
                    original = Path(self.cookies).expanduser()
                    if not original.is_file():
                        raise MediaError("cookies", "The selected cookies file does not exist.")
                    protect_private_directory(private)
                    cookies = str(Path(private) / "cookies.txt")
                    shutil.copyfile(original, cookies)
                    os.chmod(cookies, 0o600)
                service = MediaService(Runner(self.cancel_event), cookies)
                if self.action == "inspect":
                    result = service.inspect(self.url, self.allow)
                    self.inspected.emit(result)
                    if not self.previews:
                        return
                    # Only explicit thumbnail URLs; never fetch original images for previews.
                    deadline = time.monotonic() + 8
                    with requests.Session() as session:
                        for item in result.items:
                            if self.cancel_event.is_set() or time.monotonic() > deadline:
                                break
                            if not item.thumbnail.startswith(("http://", "https://")):
                                continue
                            try:
                                with session.get(
                                    item.thumbnail, timeout=(2, 2), stream=True
                                ) as response:
                                    response.raise_for_status()
                                    if not response.headers.get("Content-Type", "").startswith(
                                        "image/"
                                    ):
                                        continue
                                    data = bytearray()
                                    for chunk in response.iter_content(65536):
                                        if (
                                            self.cancel_event.is_set()
                                            or len(data) + len(chunk) > 2_000_000
                                            or time.monotonic() > deadline
                                        ):
                                            break
                                        data.extend(chunk)
                                    else:
                                        self.thumbnail.emit(item.key, bytes(data))
                            except requests.RequestException:
                                continue
                elif self.action == "download":
                    result = service.download(self.items, self.root, self.progress.emit, self.allow)
                    # One reveal request for all successes, including a cancelled/partial batch.
                    reveal = reveal_files(result.paths) if result.paths else None
                    self.downloaded.emit(result, reveal.message if reveal else "")
                elif self.action == "open":
                    root = Path(self.root).expanduser()
                    root.mkdir(parents=True, exist_ok=True)
                    open_directory(root)
        except MediaError as error:
            self.failed.emit(error.kind, str(error))
        except Exception:
            # Never relay raw downloader/requests exceptions, which can contain secrets.
            self.failed.emit(
                "application",
                "Operation failed. Check dependencies, destination permissions and free space.",
            )


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("MediaGrab", "MediaGrab")
        self.items = []
        self.worker = None
        self.pending = None
        self.closing = False
        self.last_root = ""
        self.setWindowTitle("MediaGrab")
        self.resize(940, 650)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title = QLabel("MediaGrab")
        title.setStyleSheet("font-size: 24px; font-weight: 600")
        layout.addWidget(title)
        hint = QLabel("Paste a media link, inspect, then choose what to save.")
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://…")
        self.url.setClearButtonEnabled(True)
        self.inspect_button = QPushButton("Inspect")
        row.addWidget(self.url, 1)
        row.addWidget(self.inspect_button)
        layout.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Select", "Type", "Title", "Quality"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 75)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(3, 190)
        self.table.setIconSize(QSize(80, 52))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        selection = QHBoxLayout()
        self.select_all = QPushButton("Select all")
        self.select_none = QPushButton("Select none")
        self.auto = QCheckBox("Automatically download single items")
        self.auto.setChecked(self.settings.value("auto_single", False, type=bool))
        selection.addWidget(self.select_all)
        selection.addWidget(self.select_none)
        selection.addStretch()
        selection.addWidget(self.auto)
        layout.addLayout(selection)
        destination_row = QHBoxLayout()
        destination_row.addWidget(QLabel("Destination"))
        self.destination = QLineEdit(download_destination(self.settings))
        self.browse_destination = QPushButton("Browse…")
        destination_row.addWidget(self.destination, 1)
        destination_row.addWidget(self.browse_destination)
        layout.addLayout(destination_row)
        cookie_row = QHBoxLayout()
        cookie_row.addWidget(QLabel("Cookies file (optional)"))
        self.cookies = QLineEdit(str(self.settings.value("cookies_path", "")))
        self.cookies.setPlaceholderText("Explicit Netscape cookies.txt file; no browser access")
        self.cookies.setClearButtonEnabled(True)
        self.browse_cookies = QPushButton("Choose…")
        cookie_row.addWidget(self.cookies, 1)
        cookie_row.addWidget(self.browse_cookies)
        layout.addLayout(cookie_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status = QLabel("Ready · Files will be grouped by source website.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.hide()
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open folder")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.download_button = QPushButton("Download selected")
        self.download_button.setEnabled(False)
        actions.addWidget(self.open_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.download_button)
        layout.addLayout(actions)
        self.inspect_button.clicked.connect(self.inspect)
        self.url.returnPressed.connect(self.inspect)
        self.download_button.clicked.connect(self.download)
        self.cancel_button.clicked.connect(self.cancel)
        self.open_button.clicked.connect(self.open_folder)
        self.select_all.clicked.connect(lambda: self.check_all(True))
        self.select_none.clicked.connect(lambda: self.check_all(False))
        self.table.itemChanged.connect(self.update_selection)
        self.browse_destination.clicked.connect(self.choose_destination)
        self.browse_cookies.clicked.connect(self.choose_cookies)
        self.auto.toggled.connect(self.save_preferences)

    def save_preferences(self):
        self.settings.setValue("auto_single", self.auto.isChecked())
        self.settings.setValue("destination", self.destination.text())
        self.settings.setValue("cookies_path", self.cookies.text())
        self.settings.sync()

    def choose_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Download root", self.destination.text())
        if path:
            self.destination.setText(path)
            self.save_preferences()

    def choose_cookies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Netscape cookies file", str(Path.home()))
        if path:
            self.cookies.setText(path)
            self.save_preferences()

    def check_all(self, enabled):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked
            )

    def selected(self):
        keys = {
            self.items[row].key
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        }
        return selected_items(self.items, keys)

    def update_selection(self):
        self.download_button.setEnabled(self.worker is None and bool(self.selected()))

    def start_worker(self, action, **kwargs):
        if self.worker is not None:
            return
        self.save_preferences()
        self.details.hide()
        self.worker = Worker(action, cookies=self.cookies.text().strip(), parent=self, **kwargs)
        self.worker.inspected.connect(self.on_inspected)
        self.worker.downloaded.connect(self.on_downloaded)
        self.worker.failed.connect(self.on_error)
        self.worker.progress.connect(self.on_progress)
        self.worker.thumbnail.connect(self.on_thumbnail)
        self.worker.finished.connect(self.on_finished)
        self.busy(True)
        self.worker.start()

    def busy(self, active):
        for widget in (
            self.url,
            self.inspect_button,
            self.destination,
            self.browse_destination,
            self.cookies,
            self.browse_cookies,
            self.open_button,
            self.select_all,
            self.select_none,
            self.auto,
            self.table,
        ):
            widget.setEnabled(not active)
        self.download_button.setEnabled(not active and bool(self.selected()))
        self.cancel_button.setEnabled(active)
        if active:
            self.progress_bar.setRange(0, 0)

    def inspect(self, allow=False):
        if self.worker is not None:
            return
        self.items = []
        self.table.setRowCount(0)
        self.status.setText("Inspecting media metadata…")
        self.start_worker("inspect", url=self.url.text(), allow=allow)

    def on_inspected(self, result):
        self.items = result.items
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.items))
        defaults = default_selection(self.items)
        for row, item in enumerate(self.items):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if item.key in defaults else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, check)
            for col, value in ((1, item.kind), (2, item.title), (3, item.quality)):
                cell = QTableWidgetItem(value)
                cell.setToolTip(item.page_url if item.backend == "queued" else value)
                self.table.setItem(row, col, cell)
            self.table.setRowHeight(row, 62)
        self.table.blockSignals(False)
        self.status.setText(f"Found {len(self.items)} item(s). Select media to download.")
        if result.warnings:
            self.details.setPlainText("\n".join(result.warnings))
            self.details.show()
        if (
            len(self.items) == 1
            and self.auto.isChecked()
            and not result.collection
            and not result.warnings
            and not self.items[0].collection
        ):
            self.pending = "auto"

    def on_thumbnail(self, key, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            for row, item in enumerate(self.items):
                if item.key == key:
                    self.table.item(row, 2).setIcon(
                        QIcon(
                            pixmap.scaled(
                                80,
                                52,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                    )

    def download(self):
        if self.worker is not None:
            return
        items = self.selected()
        if not items:
            return
        if not self.destination.text().strip():
            self.status.setText("Choose a destination first.")
            return
        allow = False
        if any(item.collection for item in items):
            allow = (
                QMessageBox.question(
                    self,
                    "Download collection selection?",
                    f"Download only these {len(items)} selected entries from the collection?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            )
            if not allow:
                return
        self.last_root = self.destination.text()
        self.start_worker("download", items=items, root=self.last_root, allow=allow)

    def on_progress(self, index, count, title, percent):
        self.status.setText(f"{index + 1}/{count} · {title}")
        self.progress_bar.setRange(0, 100 if percent >= 0 else 0)
        if percent >= 0:
            self.progress_bar.setValue(percent)

    def on_downloaded(self, result: BatchResult, reveal):
        prefix = "Cancelled" if result.cancelled else "Finished"
        self.status.setText(
            f"{prefix} · {len(result.paths)} file(s) available · {result.skipped} already downloaded · {len(result.failures)} failed."
        )
        self.details.setPlainText("\n".join([reveal, *result.failures, *map(str, result.paths)]))
        self.details.show()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0 if result.cancelled else 100)

    def on_error(self, kind, message):
        self.status.setText(f"{kind.replace('_', ' ').title()}: {message}")
        if kind == "collection":
            self.pending = "collection"

    def on_finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.busy(False)
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        if self.closing:
            self.close()
            return
        pending, self.pending = self.pending, None
        if worker.cancel_event.is_set():
            pending = None
            if worker.action == "inspect":
                self.status.setText(
                    "Inspection cancelled. Any listed items remain available for manual selection."
                )
        if pending == "collection":
            answer = QMessageBox.question(
                self,
                "Inspect possible collection?",
                "This URL may be a channel, profile, playlist, short link or unrecognized site. "
                "Inspect up to 100 entries? No full media will be downloaded yet.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                QTimer.singleShot(0, lambda: self.inspect(True))
        elif pending == "auto":
            QTimer.singleShot(0, self.download)

    def cancel(self):
        self.pending = None
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelling and cleaning up unfinished files…")

    def open_folder(self):
        if not self.destination.text().strip():
            self.status.setText("Choose a destination first.")
            return
        self.start_worker("open", root=self.destination.text())

    def closeEvent(self, event):
        self.save_preferences()
        if self.worker is not None:
            self.closing = True
            self.cancel()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MediaGrab")
    app.setOrganizationName("MediaGrab")
    if "--advanced" in sys.argv:
        window = MainWindow()
        window.show()
    else:
        from .quick import QuickWindow

        app.setQuitOnLastWindowClosed(False)
        window = QuickWindow()
        window.finished_app.connect(app.quit)
        window.start_from_clipboard()
    sys.exit(app.exec())
