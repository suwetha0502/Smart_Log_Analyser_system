import sys
import time
import subprocess
from pathlib import Path
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QProgressBar, QMessageBox, QLineEdit,
    QComboBox, QDialog
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


BASE_DIR = Path(__file__).resolve().parent

LOG_FILE = BASE_DIR / "logs.txt"
APP_HISTORY_FILE = BASE_DIR / "app_history.txt"
CPU_SERIES_FILE = BASE_DIR / "cpu_series.txt"
STATUS_FILE = BASE_DIR / "status.txt"

BACKEND_NAME = "smart_logger_shell.sh"
BASH_PATH = r"C:\Program Files\Git\bin\bash.exe"


class CpuGraphWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=60)
        self.setMinimumHeight(280)
        self.setStyleSheet("background-color: #101317; border: 1px solid #444; border-radius: 8px;")

    def set_values(self, vals):
        self.values = deque(vals, maxlen=60)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(self.rect(), QColor("#101317"))

        grid_pen = QPen(QColor("#2f3540"))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        for i in range(5):
            y = rect.top() + i * rect.height() / 4
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))

        for i in range(6):
            x = rect.left() + i * rect.width() / 5
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))

        painter.setPen(QColor("#9aa4b2"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(rect.left(), rect.top() - 2, "100%")
        painter.drawText(rect.left(), rect.bottom(), "0%")

        vals = list(self.values)
        if len(vals) < 2:
            painter.setPen(QColor("#9aa4b2"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for CPU data...")
            painter.end()
            return

        pen = QPen(QColor("#00d4ff"))
        pen.setWidth(3)
        painter.setPen(pen)

        step_x = rect.width() / max(1, len(vals) - 1)

        for i in range(len(vals) - 1):
            x1 = rect.left() + i * step_x
            y1 = rect.bottom() - (vals[i] / 100.0) * rect.height()
            x2 = rect.left() + (i + 1) * step_x
            y2 = rect.bottom() - (vals[i + 1] / 100.0) * rect.height()
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        last_val = vals[-1]
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(
            rect.adjusted(0, 0, -10, -10),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            f"{last_val}%"
        )
        painter.end()


class AlertPopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ALERT")
        self.setModal(False)
        self.setFixedSize(360, 170)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.icon = QLabel("❗")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet("font-size: 36px; color: red; font-weight: bold;")

        self.text_label = QLabel("")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("font-size: 18px; color: #ff4d4d; font-weight: bold;")

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        layout.addWidget(self.icon)
        layout.addWidget(self.text_label)
        layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setStyleSheet("""
            QDialog {
                background-color: #1c1f26;
                border: 2px solid #ff3b30;
                border-radius: 10px;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: 1px solid #666;
                border-radius: 8px;
                padding: 8px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)

    def set_message(self, msg):
        self.text_label.setText(msg)


class SmartLogger(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Monitor (Shell Backend)")
        self.resize(1500, 900)

        self.backend_process = None
        self.last_alert_key = ""
        self.alert_popup = None

        self.init_ui()
        self.apply_dark_theme()
        self.start_backend()
        self.start_timer()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main = QVBoxLayout(central)
        main.setContentsMargins(14, 12, 14, 12)
        main.setSpacing(14)

        title_status = QLabel("Live Status")
        title_status.setStyleSheet("font-size: 20px; font-weight: bold;")
        main.addWidget(title_status)

        top_card = QWidget()
        top_card.setObjectName("card")
        top_layout = QHBoxLayout(top_card)
        top_layout.setContentsMargins(20, 20, 20, 20)
        top_layout.setSpacing(40)

        left_block = QVBoxLayout()
        right_block = QVBoxLayout()

        self.cpu_label = QLabel("CPU: --%")
        self.cpu_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setTextVisible(False)
        self.cpu_bar.setFixedHeight(18)

        self.mem_label = QLabel("Memory: --%")
        self.mem_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.mem_bar = QProgressBar()
        self.mem_bar.setRange(0, 100)
        self.mem_bar.setTextVisible(False)
        self.mem_bar.setFixedHeight(18)

        left_block.addWidget(self.cpu_label)
        left_block.addSpacing(10)
        left_block.addWidget(self.cpu_bar)

        right_block.addWidget(self.mem_label)
        right_block.addSpacing(10)
        right_block.addWidget(self.mem_bar)

        top_layout.addLayout(left_block, 1)
        top_layout.addLayout(right_block, 1)

        main.addWidget(top_card)

        title_logs = QLabel("Recent Logs")
        title_logs.setStyleSheet("font-size: 20px; font-weight: bold;")
        main.addWidget(title_logs)

        logs_card = QWidget()
        logs_card.setObjectName("card")
        logs_layout = QVBoxLayout(logs_card)
        logs_layout.setContentsMargins(18, 18, 18, 18)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(360)
        self.logs.setStyleSheet("""
            QTextEdit {
                background-color: #05080c;
                color: white;
                border: 1px solid #333;
                border-radius: 6px;
                font-family: Consolas;
                font-size: 14px;
            }
        """)
        logs_layout.addWidget(self.logs)
        main.addWidget(logs_card, 1)

        controls = QHBoxLayout()
        controls.setSpacing(12)

        level_lbl = QLabel("Level:")
        level_lbl.setStyleSheet("font-size: 16px;")
        controls.addWidget(level_lbl)

        self.level_box = QComboBox()
        self.level_box.addItems(["INFO", "WARNING", "ERROR"])
        self.level_box.setFixedHeight(40)
        self.level_box.setFixedWidth(130)
        controls.addWidget(self.level_box)

        self.msg_box = QLineEdit()
        self.msg_box.setPlaceholderText("Enter message to log manually...")
        self.msg_box.setFixedHeight(40)
        controls.addWidget(self.msg_box, 1)

        self.add_btn = QPushButton("Add Log")
        self.add_btn.clicked.connect(self.add_log)
        controls.addWidget(self.add_btn)

        self.refresh_btn = QPushButton("Refresh Now")
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn)

        self.graph_btn = QPushButton("CPU Graph")
        self.graph_btn.clicked.connect(self.show_cpu_graph_window)
        controls.addWidget(self.graph_btn)

        self.app_btn = QPushButton("App History")
        self.app_btn.clicked.connect(self.show_app_history)
        controls.addWidget(self.app_btn)

        self.archive_btn = QPushButton("Archive")
        self.archive_btn.clicked.connect(self.archive_logs)
        controls.addWidget(self.archive_btn)

        self.restore_btn = QPushButton("Restore")
        self.restore_btn.clicked.connect(self.restore_logs)
        controls.addWidget(self.restore_btn)

        main.addLayout(controls)

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: white;
                font-size: 14px;
            }

            QWidget#card {
                background-color: #333333;
                border: 1px solid #4a4a4a;
                border-radius: 10px;
            }

            QPushButton {
                background-color: #505050;
                border: 1px solid #666;
                color: white;
                border-radius: 8px;
                padding: 8px 14px;
                min-height: 26px;
            }

            QPushButton:hover {
                background-color: #5e5e5e;
            }

            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #666;
                border-radius: 8px;
                padding: 6px;
            }

            QProgressBar {
                background-color: #4a4a4a;
                border: 1px solid #555;
                border-radius: 8px;
            }

            QProgressBar::chunk {
                border-radius: 8px;
                background-color: #00b894;
            }
        """)

    def start_backend(self):
        try:
            shell_path = BASE_DIR / BACKEND_NAME
            if not shell_path.exists():
                QMessageBox.critical(self, "Error", f"Shell file not found:\n{shell_path}")
                return

            self.backend_process = subprocess.Popen(
                [BASH_PATH, "-lc", f"bash {BACKEND_NAME}"],
                cwd=str(BASE_DIR)
            )
        except Exception as e:
            QMessageBox.critical(self, "Backend Error", f"Could not start backend.\n\n{e}")

    def start_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)

    def read_status(self):
        if not STATUS_FILE.exists():
            return None

        data = {}
        try:
            for line in STATUS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
            return data
        except Exception:
            return None

    def update_bar_color(self, bar, value):
        color = "#00b894"
        if value >= 70:
            color = "#f39c12"
        if value >= 80:
            color = "#ff3b30"

        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #4a4a4a;
                border: 1px solid #555;
                border-radius: 8px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 8px;
            }}
        """)

    def read_cpu_series(self):
        vals = []
        if not CPU_SERIES_FILE.exists():
            return vals

        try:
            lines = CPU_SERIES_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines[-60:]:
                if "|" in line:
                    _, value = line.split("|", 1)
                    try:
                        vals.append(int(value.strip()))
                    except ValueError:
                        pass
        except Exception:
            pass
        return vals

    def refresh(self):
        if LOG_FILE.exists():
            lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            self.logs.setPlainText("\n".join(lines[-40:]))

        status = self.read_status()
        if status:
            try:
                cpu = int(status.get("CPU", "0"))
                mem = int(status.get("MEM", "0"))

                self.cpu_label.setText(f"CPU: {cpu}%")
                self.mem_label.setText(f"Memory: {mem}%")

                self.cpu_bar.setValue(cpu)
                self.mem_bar.setValue(mem)

                self.update_bar_color(self.cpu_bar, cpu)
                self.update_bar_color(self.mem_bar, mem)

                self.handle_alert(cpu, mem)
            except Exception:
                pass

    def handle_alert(self, cpu, mem):
        alert_msg = ""
        alert_key = ""

        if cpu >= 80:
            alert_msg = f"High CPU Usage Detected\nCPU reached {cpu}%"
            alert_key = f"CPU-{cpu}"
        elif mem >= 80:
            alert_msg = f"High Memory Usage Detected\nMemory reached {mem}%"
            alert_key = f"MEM-{mem}"

        if not alert_msg:
            if self.alert_popup and self.alert_popup.isVisible():
                self.alert_popup.close()
            self.last_alert_key = ""
            return

        if alert_key == self.last_alert_key:
            return

        self.last_alert_key = alert_key

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [ALERT] {alert_msg.replace(chr(10), ' | ')}\n")

        if self.alert_popup and self.alert_popup.isVisible():
            self.alert_popup.close()

        self.alert_popup = AlertPopup(self)
        self.alert_popup.set_message(alert_msg)
        self.alert_popup.show()

    def add_log(self):
        msg = self.msg_box.text().strip()
        level = self.level_box.currentText()

        if not msg:
            QMessageBox.information(self, "Input Required", "Please enter a message.")
            return

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n")

        self.msg_box.clear()
        self.refresh()

    def show_app_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("App History")
        dialog.resize(900, 600)

        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("""
            QTextEdit {
                background-color: #05080c;
                color: white;
                border: 1px solid #333;
                border-radius: 6px;
                font-family: Consolas;
                font-size: 14px;
            }
        """)

        if APP_HISTORY_FILE.exists():
            text.setPlainText(APP_HISTORY_FILE.read_text(encoding="utf-8", errors="ignore"))
        else:
            text.setPlainText("No app history available.")

        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.setStyleSheet("""
            QDialog { background-color: #1f2229; color: white; }
            QPushButton {
                background-color: #505050;
                border: 1px solid #666;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
            }
        """)
        dialog.exec()

    def show_cpu_graph_window(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("CPU Usage Live Graph")
        dialog.resize(1000, 500)

        layout = QVBoxLayout(dialog)

        graph = CpuGraphWidget()
        graph.set_values(self.read_cpu_series())
        layout.addWidget(graph)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.setStyleSheet("""
            QDialog { background-color: #1f2229; color: white; }
            QPushButton {
                background-color: #505050;
                border: 1px solid #666;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
            }
        """)

        timer = QTimer(dialog)
        timer.timeout.connect(lambda: graph.set_values(self.read_cpu_series()))
        timer.start(3000)

        dialog.exec()

    def archive_logs(self):
        archive_dir = BASE_DIR / "archives"
        archive_dir.mkdir(exist_ok=True)
        backup = archive_dir / "log_backup.txt"

        if LOG_FILE.exists():
            backup.write_text(LOG_FILE.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            LOG_FILE.write_text("", encoding="utf-8")
            QMessageBox.information(self, "Archive", "Logs archived successfully.")
            self.refresh()
        else:
            QMessageBox.information(self, "Archive", "No log file found.")

    def restore_logs(self):
        backup = BASE_DIR / "archives" / "log_backup.txt"

        if backup.exists():
            LOG_FILE.write_text(backup.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            QMessageBox.information(self, "Restore", "Logs restored successfully.")
            self.refresh()
        else:
            QMessageBox.information(self, "Restore", "No archive found.")

    def closeEvent(self, event):
        try:
            if self.backend_process:
                self.backend_process.terminate()
        except Exception:
            pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SmartLogger()
    win.show()
    sys.exit(app.exec())