import sys
import os
import subprocess
import threading
import time
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QTextEdit, QPushButton, QComboBox,
    QLineEdit, QGroupBox, QMessageBox, QStatusBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

LOG_FILE = Path("logs.txt")
ALERT_FILE = Path("alert_history.txt")
BACKEND_SCRIPT = Path("smart_logger_shell.sh")
REFRESH_INTERVAL_MS = 5000

if BACKEND_SCRIPT.exists():
    BACKEND_SCRIPT.chmod(0o755)

class SystemMonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("System Monitor (Shell Backend)")
        self.resize(1000, 680)
        self.setMinimumSize(900, 580)

        self.monitor_process = None
        self.monitor_thread = None

        self.init_ui()
        self.start_backend()
        self.start_refresh_timer()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        status_group = QGroupBox("Live Status")
        status_layout = QHBoxLayout(status_group)

        self.cpu_label = QLabel("CPU: --%")
        self.cpu_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        self.cpu_bar = QProgressBar(maximum=100)
        self.cpu_bar.setTextVisible(True)

        self.mem_label = QLabel("Memory: --%")
        self.mem_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        self.mem_bar = QProgressBar(maximum=100)
        self.mem_bar.setTextVisible(True)

        status_layout.addWidget(self.cpu_label)
        status_layout.addWidget(self.cpu_bar)
        status_layout.addStretch(1)
        status_layout.addWidget(self.mem_label)
        status_layout.addWidget(self.mem_bar)

        layout.addWidget(status_group)

        log_group = QGroupBox("Recent Logs")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group, stretch=1)

        ctrl_layout = QHBoxLayout()
        self.level_combo = QComboBox()
        self.level_combo.addItems(["INFO", "WARNING", "ERROR"])
        self.msg_edit = QLineEdit()
        self.msg_edit.setPlaceholderText("Enter message to log manually...")

        add_btn = QPushButton("Add Log")
        add_btn.clicked.connect(self.add_manual_log)

        refresh_btn = QPushButton("Refresh Now")
        refresh_btn.clicked.connect(self.refresh_display)

        alerts_btn = QPushButton("Show Alert History")
        alerts_btn.clicked.connect(self.show_alert_history)

        ctrl_layout.addWidget(QLabel("Level:"))
        ctrl_layout.addWidget(self.level_combo)
        ctrl_layout.addWidget(self.msg_edit, stretch=1)
        ctrl_layout.addWidget(add_btn)
        ctrl_layout.addWidget(refresh_btn)
        ctrl_layout.addWidget(alerts_btn)

        layout.addLayout(ctrl_layout)

        self.statusBar().showMessage("Initializing...")

    def start_backend(self):
        """Start the shell monitoring script in background"""
        def run_monitor():
            try:
                self.monitor_process = subprocess.Popen(
                    [str(BACKEND_SCRIPT)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                for line in self.monitor_process.stdout:
                    print("Backend:", line.strip())
            except Exception as e:
                self.statusBar().showMessage(f"Failed to start monitor: {e}", 15000)

        self.monitor_thread = threading.Thread(target=run_monitor, daemon=True)
        self.monitor_thread.start()
        self.statusBar().showMessage("Monitoring backend started", 8000)

    def start_refresh_timer(self):
        """Start periodic GUI refresh"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_display)
        self.timer.start(REFRESH_INTERVAL_MS)

    def refresh_display(self):
        """Update GUI with latest CPU/MEM (simple parsing from log) + full log view"""
        try:
            lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
            if not lines:
                self.log_text.setPlainText("(log empty)")
                return

            self.log_text.setPlainText("\n".join(lines[-40:]))
            from PyQt6.QtGui import QTextCursor
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
            for line in reversed(lines):
                if "INFO" in line and "CPU:" in line and "MEM:" in line:
                    parts = line.split()
                    cpu_str = parts[-2].split(":")[1].rstrip("%")
                    mem_str = parts[-1].split(":")[1].rstrip("%")
                    try:
                        cpu = int(cpu_str)
                        mem = int(mem_str)
                        self.cpu_label.setText(f"CPU: {cpu}%")
                        self.cpu_bar.setValue(cpu)
                        self.mem_label.setText(f"Memory: {mem}%")
                        self.mem_bar.setValue(mem)

                        red = "#e74c3c"
                        green = "#2ecc71"
                        self.cpu_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {red if cpu > 80 else green}; }}")
                        self.mem_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {red if mem > 80 else green}; }}")
                    except ValueError:
                        pass
                    break

        except Exception as e:
            self.log_text.setPlainText(f"Error reading log: {e}")

    def add_manual_log(self):
        level = self.level_combo.currentText()
        msg = self.msg_edit.text().strip()
        if not msg:
            QMessageBox.warning(self, "Input required", "Please enter a message")
            return

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} {level} {msg}\n"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)

        self.msg_edit.clear()
        self.refresh_display()
        self.statusBar().showMessage("Manual log entry added", 4000)

    def show_alert_history(self):
        try:
            content = ALERT_FILE.read_text(encoding="utf-8").strip()
            if not content:
                content = "No alerts recorded yet."
            QMessageBox.information(self, "Alert History", content)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot read alert history:\n{e}")

    def closeEvent(self, event):
        if self.monitor_process and self.monitor_process.poll() is None:
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Monitoring is still running. Terminate it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.monitor_process.terminate()
                try:
                    self.monitor_process.wait(3)
                except:
                    self.monitor_process.kill()
        event.accept()


if __name__ == "__main__":
    if not BACKEND_SCRIPT.exists():
        print(f"Error: Backend script not found: {BACKEND_SCRIPT}")
        sys.exit(1)
    app = QApplication(sys.argv)
    window = SystemMonitorWindow()
    window.show()
    window.refresh_display()
    sys.exit(app.exec())