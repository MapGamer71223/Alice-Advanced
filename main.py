import sys
import time
from PyQt5.QtWidgets import QDesktopWidget, QGraphicsOpacityEffect
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
import logging

from alice_loader import LoaderThread  # Import the loader thread


from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from alice_hud import AliceHUD

import traceback
import pygame
pygame.mixer.init(frequency=22050, size=-16, channels=1)

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s: %(message)s')

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception


class LoadingScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.resize(600, 300)
        self.center_on_screen()
        self.setStyleSheet("background-color: #12121F; border: 2px solid #00FFD0; border-radius: 15px;")

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.title = QLabel("🔮 Alice Ultra Initializing...")
        self.title.setFont(QFont("Consolas", 20, QFont.Bold))
        self.title.setStyleSheet("color: #FFD700; padding-bottom: 20px;")
        self.title.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel("Starting up...")
        self.status_label.setFont(QFont("Segoe UI", 12))
        self.status_label.setStyleSheet("color: #00FFD0;")
        self.status_label.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(20)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #222;
                border-radius: 10px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FFD700, stop:1 #00FFD0
                );
                border-radius: 10px;
            }
        """)

        layout.addWidget(self.title)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)

        self.setLayout(layout)

        # Opacity effect for fade animation
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(800)
        self.opacity_anim.setStartValue(1)
        self.opacity_anim.setEndValue(0)
        self.opacity_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.opacity_anim.finished.connect(self._on_fade_finished)

        # Start loader thread
        self.loader_thread = LoaderThread()
        self.loader_thread.progress_update.connect(self.update_progress)
        self.loader_thread.finished.connect(self.start_main_ui)
        self.loader_thread.start()

    def center_on_screen(self):
        frame_gm = self.frameGeometry()
        screen = QDesktopWidget().availableGeometry().center()
        frame_gm.moveCenter(screen)
        self.move(frame_gm.topLeft())

    def update_progress(self, value: int, message: str):
        self.progress.setValue(value)
        self.status_label.setText(message)

    def start_main_ui(self):
        # Start fade animation before launching main UI
        self.opacity_anim.start()

    def _on_fade_finished(self):
        try:
            # Pass initialized components if needed
            self.main = AliceHUD(memory_manager=self.loader_thread.memory_manager,
                                 tts_engine=self.loader_thread.tts_engine,
                                 voice_listener=self.loader_thread.voice_listener)
            self.main.show()
        except Exception as e:
            logging.error(f"Failed to launch AliceHUD: {e}")
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = LoadingScreen()
    splash.show()
    sys.exit(app.exec_())
