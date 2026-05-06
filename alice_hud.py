import random
import logging
import time
import re
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QLabel, QProgressBar, QVBoxLayout, QPushButton,
    QTextEdit, QHBoxLayout, QSizePolicy, QFrame, QScrollArea
)
from PyQt5.QtCore import QTimer, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QColor, QPalette, QMovie

from input_processor import InputProcessor
from intent_engine import detect_intent

from memory_manager import MemoryManager
from voice_listener import VoiceListener
from tts_engine import AssistantTTS, AssistantTTSThread
from assistant_actions import try_execute_action
from ai_connector import query_ollama_mistral
from utils import detect_emotion

from PyQt5.QtCore import QThread

def clean_tts_text(text):
    return re.sub(r'[^\x00-\x7F]+', '', text)

def extract_sentences(buffer: str):
    parts = re.split(r'([.!?])', buffer)
    sentences = [''.join(parts[i:i+2]).strip() for i in range(0, len(parts)-1, 2)]
    remainder = parts[-1] if len(parts) % 2 != 0 else ""
    return sentences, remainder
    
class AIWorker(QThread):
    response_chunk = pyqtSignal(str)
    response_finished = pyqtSignal()

    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt

    def run(self):
        try:
            response_stream = query_ollama_mistral(self.prompt, stream=True)

            for chunk in response_stream:
                self.response_chunk.emit(chunk)

        except Exception:
            self.response_chunk.emit(
                "Sorry, I'm having trouble responding right now."
            )

        self.response_finished.emit()
    
        
class AliceHUD(QWidget):
    tts_finished_signal = pyqtSignal()

    def __init__(self, memory_manager=None, tts_engine=None, voice_listener=None):
        super().__init__()

        self.memory_manager = memory_manager or MemoryManager()
        self.tts_engine = tts_engine or AssistantTTS()
        self.voice_thread = voice_listener or VoiceListener(model_size="small", device_index=1)
        self.is_streaming_speaking = False
        
        self._init_ui()
        self._connect_signals_slots()
        self._init_voice_components()
        self._init_timers()

        self.input_processor = InputProcessor()
        self.session_active = False
        self.last_interaction_time = 0
        self.session_timeout = 30  # seconds (you can tune this)
        # Removed memory cleanup timer initialization to match your memory_manager
        self.tts_queue = []
        self.tts_busy = False
        # Other initialization
        QTimer.singleShot(1200, lambda: self.speak("System online. Welcome back."))

    def _init_ui(self):
        # Window basics
        self.setWindowTitle("Alice Ultra HUD")
        self.setGeometry(100, 100, 1100, 740)
        self.setMinimumSize(800, 600)

        # Base palette
        self.setStyleSheet("background-color: #0E0F14;")
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor("#0E0F14"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # Main layouts
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 18, 18, 18)
        self.main_layout.setSpacing(12)
        self.setLayout(self.main_layout)

        # Top status row
        self.top_frame = QFrame(self)
        self.top_frame.setObjectName("top_frame")
        self.top_frame.setStyleSheet("QFrame#top_frame { background: transparent; }")
        self.top_layout = QHBoxLayout(self.top_frame)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(12)

        self.status_label = QLabel("🧠 Booting up Alice...", self)
        self.status_label.setFont(QFont("Consolas", 16, QFont.Bold))
        self.status_label.setStyleSheet("color: #FFD966;")
        self.top_layout.addWidget(self.status_label, stretch=1)

        self.user_last = QLabel("", self)
        self.user_last.setFont(QFont("Segoe UI", 10, QFont.StyleItalic))
        self.user_last.setStyleSheet("color:#B8C2CC;")
        self.user_last.setFixedHeight(28)
        self.top_layout.addWidget(self.user_last, alignment=Qt.AlignRight)

        self.main_layout.addWidget(self.top_frame)

        # Center HUD area: avatar + transcript box
        self.center_frame = QFrame(self)
        self.center_frame.setStyleSheet("QFrame { background: rgba(255,255,255,0.02); border-radius: 12px; }")
        self.center_layout = QHBoxLayout(self.center_frame)
        self.center_layout.setContentsMargins(14, 14, 14, 14)
        self.center_layout.setSpacing(16)

        # Avatar column
        self.avatar_col = QVBoxLayout()
        self.avatar_col.setSpacing(10)

        self.avatar_gif = QMovie("assets/alice_avatar.gif")
        self.avatar_label = QLabel(self)
        self.avatar_label.setMovie(self.avatar_gif)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setFixedSize(180, 180)
        self.avatar_gif.start()
        self.avatar_col.addWidget(self.avatar_label, alignment=Qt.AlignTop | Qt.AlignHCenter)

        # Voice bar and status under avatar
        self.voice_bar = QProgressBar(self)
        self.voice_bar.setRange(0, 100)
        self.voice_bar.setTextVisible(False)
        self.voice_bar.setFixedHeight(14)
        self.voice_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice_bar.setStyleSheet("QProgressBar { background-color: #111; border: 1px solid rgba(255,255,255,0.06); border-radius: 7px;} QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #FFD700, stop:1 #00FFFF); }")
        self.avatar_col.addWidget(self.voice_bar)

        self.center_layout.addLayout(self.avatar_col, stretch=0)

        # Transcript / output box column
        self.output_col = QVBoxLayout()
        self.output_col.setSpacing(8)

        # Rich, scrollable read-only text area for full assistant output
        self.output_box = QTextEdit(self)
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(200)
        self.output_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.output_box.setFont(QFont("Segoe UI", 12))
        self.output_box.setStyleSheet(
            "QTextEdit { background: transparent; color: #E6F1FF; border: none; padding: 8px; }")
        self.output_box.setPlaceholderText("Assistant output will appear here in full. Scroll to read longer replies.")

        # Put output_box inside a framed scroll area for clearer separation
        self.output_frame = QFrame(self)
        self.output_frame.setStyleSheet("QFrame { background: rgba(255,255,255,0.02); border-radius: 10px; border: 1px solid rgba(255,255,255,0.03); }")
        self.output_frame_layout = QVBoxLayout(self.output_frame)
        self.output_frame_layout.setContentsMargins(6, 6, 6, 6)
        self.output_frame_layout.addWidget(self.output_box)

        self.output_col.addWidget(self.output_frame)

        # Subtitle label (single-line condensed view) to emulate previous behaviour
        self.subtitle_label = QLabel(self)
        self.subtitle_label.setFont(QFont("Segoe UI", 13))
        self.subtitle_label.setStyleSheet("color: #7FFFD4; padding:4px;")
        self.subtitle_label.setFixedHeight(36)
        self.output_col.addWidget(self.subtitle_label)

        self.center_layout.addLayout(self.output_col, stretch=1)

        self.main_layout.addWidget(self.center_frame, stretch=1)

        # Bottom area: memory, suggestions, controls
        self.bottom_frame = QFrame(self)
        self.bottom_layout = QHBoxLayout(self.bottom_frame)
        self.bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.bottom_layout.setSpacing(12)

        self.memory_label = QLabel("Context: ", self)
        self.memory_label.setFont(QFont("Consolas", 9))
        self.memory_label.setStyleSheet("color:#9EA7B3;")
        self.memory_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bottom_layout.addWidget(self.memory_label, stretch=2)

        self.suggest_label = QLabel("", self)
        self.suggest_label.setFont(QFont("Consolas", 9, QFont.StyleItalic))
        self.suggest_label.setStyleSheet("color:#AFA5FF;")
        self.suggest_label.setFixedWidth(300)
        self.bottom_layout.addWidget(self.suggest_label, alignment=Qt.AlignRight)

        self.stop_speaking_btn = QPushButton("Stop Speaking", self)
        self.stop_speaking_btn.setFixedWidth(140)
        self.stop_speaking_btn.setStyleSheet(
            "background-color: #e63946; color: white; font-weight: bold; padding: 6px; border-radius: 6px;"
        )
        self.stop_speaking_btn.setEnabled(False)
        self.stop_speaking_btn.hide()
        self.stop_speaking_btn.setToolTip("Click to stop Alice speaking and listen immediately")
        self.bottom_layout.addWidget(self.stop_speaking_btn, alignment=Qt.AlignRight)

        self.main_layout.addWidget(self.bottom_frame)

        # store emotion colors
        self.bg_colors = {
            "neutral": "#0E0F14",
            "happy": "#102018",
            "sad": "#1A0F2A",
            "calm": "#081014"
        }
        self.current_emotion = "neutral"
    
    def is_session_active(self):
   
        return (time.time() - self.last_interaction_time) < self.session_timeout

    def _connect_signals_slots(self):
        self.tts_finished_signal.connect(self.listen)
        self.stop_speaking_btn.clicked.connect(self._stop_speaking)

    def show_partial(self, text):
        if not self.is_speaking:
            self.subtitle_label.setText(text)
    def _init_voice_components(self):
        self.tts_thread: Optional[AssistantTTSThread] = None
        self.last_command_text: Optional[str] = None
        self.is_speaking = False
        try:
            if not self.voice_thread:
                self.voice_thread = VoiceListener(model_size="small", device_index=1)
                
            self.voice_thread.partial_result.connect(self.show_partial)

            try:
                self.voice_thread.command_received.disconnect()
            except Exception:
                pass
            print("[📤 EMITTING COMMAND]")
            self.voice_thread.command_received.connect(self.handle_command)

        except Exception as e:
            logging.error(f"VoiceListener initialization error: {e}")

    def _init_timers(self):
        self.voice_timer = QTimer()
        self.voice_timer.timeout.connect(self.animate_voice)

        self.suggestion_timer = QTimer()
        self.suggestion_timer.timeout.connect(self.show_suggest)
        self.suggestion_timer.start(7000)

    def _set_speaking_state(self, speaking: bool):
        self.is_speaking = speaking
        self.stop_speaking_btn.setEnabled(speaking)
        if speaking:
            self.stop_speaking_btn.show()
        else:
            self.stop_speaking_btn.hide()

    def _process_tts_queue(self):
        if self.tts_busy or not self.tts_queue:
            return

        text = self.tts_queue.pop(0)
        self.tts_busy = True

        self.status_label.setText("💬 Speaking...")
        self._speak_internal(text)
    
    def speak(self, text: str, interrupt=False):
        if interrupt:
            self.tts_queue.clear()
            if self.tts_thread and self.tts_thread.isRunning():
                self.tts_thread.stop()
                self.tts_thread.wait()
            self.tts_busy = False

        self.tts_queue.append(text)
        self._process_tts_queue()
        
  

    def _speak_internal(self, text: str):
       
        self._set_speaking_state(True)

        text = clean_tts_text(text)
        emotion_label, _ = detect_emotion(text) if text else ("neutral", 0.6)
        self.current_emotion = emotion_label
        self.set_bg_color(emotion_label)
        self.avatar_gif.start()
        self.status_label.setText(f"💬 Speaking... [{emotion_label}]")

        # Put the full response into the output_box so it's always visible and scrollable
        self.output_box.clear()
        if text:
            # preserve existing quick subtitle for instant glance
            self.subtitle_label.setText(text if len(text) < 140 else text[:137] + "...")
            self.output_box.setPlainText(text)
            self.output_box.moveCursor(self.output_box.textCursor().Start)
        else:
            self.subtitle_label.clear()

        self.voice_timer.start(90)

        if self.voice_thread and hasattr(self.voice_thread, "pause_listening"):
            try:
                self.voice_thread.pause_listening()
            except Exception as e:
                logging.error(f"Error pausing voice listener: {e}")

        if self.tts_thread and self.tts_thread.isRunning():
            try:
                self.tts_thread.stop()
                self.tts_thread.wait()
            except Exception as e:
                logging.error(f"Error stopping previous TTS thread: {e}")
            self.tts_thread = None

        self.tts_thread = AssistantTTSThread(text, self.tts_engine, emotion=emotion_label)
        try:
            self.tts_thread.finished_signal.connect(self._after_tts)
        except Exception:
            self.tts_thread.finished.connect(self._after_tts)
        self.tts_thread.start()
        logging.info("TTS thread started.")

    def _stop_speaking(self):
        if not self.is_speaking:
            return

        self._set_speaking_state(False)

        if self.tts_thread and self.tts_thread.isRunning():
            try:
                self.tts_thread.stop()
                self.tts_thread.wait()
            except Exception as e:
                logging.error(f"Error stopping TTS thread: {e}")
            self.tts_thread = None

        self.voice_timer.stop()
        self.voice_bar.setValue(0)
        self.subtitle_label.clear()
        self.status_label.setText("🛑 Speaking stopped by user.")

        # Keep the output_box content so user can read the full response after stopping
        self.listen()

    def _after_tts(self):
        logging.info("TTS thread finished.")
        self._set_speaking_state(False)
        self.last_interaction_time = time.time()
        self.voice_timer.stop()
        self.voice_bar.setValue(0)
        self.tts_finished_signal.emit()

        if self.voice_thread and hasattr(self.voice_thread, "resume_listening"):
            try:
                self.voice_thread.resume_listening()
            except Exception as e:
                logging.error(f"Error resuming voice listener: {e}")
        self.tts_busy = False
        self._process_tts_queue()

    def listen(self):
        if self.is_speaking:
            return

        try:
            self.avatar_gif.stop()
        except Exception:
            pass
        self.status_label.setText("🎧 Listening...")
        if self.voice_thread:
            try:
                if not self.voice_thread.isRunning():
                    self.voice_thread.start()
                if hasattr(self.voice_thread, "resume_listening"):
                    self.voice_thread.resume_listening()
            except Exception as e:
                logging.error(f"Error resuming voice listener in listen(): {e}")

    def animate_voice(self):
        base = 55 if self.current_emotion == "sad" else 35
        boost = 100 if self.current_emotion == "happy" else random.randint(50, 85)
        self.voice_bar.setValue(random.randint(base, boost))

    def handle_command(self, text: str):
        print(f"[🔥 HANDLE COMMAND RECEIVED]: {text}")
        # 🔥 CLEAN INPUT
        text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)  # remove punctuation
        text = re.sub(r'\s+', ' ', text).strip()
        # 🔹 STEP 1: Process input (wake word, session, cleanup)
        processed, self.session_active, self.last_interaction_time = \
            self.input_processor.process(
                text,
                self.session_active,
                self.last_interaction_time,
                self.session_timeout
            )
        print(f"[🧪 PROCESSED]: {processed}")

        if processed is None:
            return

        if processed == "__wake__":
            self.speak("Yeah?")
            return

        text = processed.strip().lower()

        # 🔹 STEP 2: Detect intent
        intent, confidence = detect_intent(text)
        print(f"[🧠] Intent: {intent} ({confidence})")

        # 🔹 STEP 3: Ignore noise early
        if intent == "noise":
            return

        # UI update
        self.last_command_text = text
        self.user_last.setText(f"User: {text}")
        self.suggest_label.clear()

        # 🔹 STEP 4: ROUTING (single source of truth)

        # ⚡ SYSTEM / ACTION
        if intent in ["system_action", "search"]:
            action_response = try_execute_action(text)

            if action_response:
                # ❌ DO NOT STORE IN MEMORY
                self.update_memory_display()
                self.speak(action_response)
                return

            # fallback if intent wrong
            print("[⚠️] Intent said action, but no action matched → fallback to LLM")

        # 💬 CONVERSATION
        if intent == "conversation":
            self.memory_manager.add_memory(text, "user_chat")
            self.update_memory_display()
            print("[🚀 ROUTING TO LLM]")
            QTimer.singleShot(200, lambda t=text: self.get_ai_response(t))
            return
        print(f"[🧠 INTENT DEBUG]: {intent}, confidence={confidence}")
        
    def show_suggest(self):
        if (not self.user_last.text()) or (self.user_last.text() == "User: [Silent]"):
            self.suggest_label.setText(random.choice([
                "What can I do for you?",
                "Try 'Tell me a joke.'",
                "Ask 'What's your mood Alice?'",
                "Say 'Play my favorite music.'"
            ]))

    def update_memory_display(self):
        try:
            context = self.memory_manager.format_memories_for_context(limit=12) or ""
            logging.debug(f"Memory context:\n{context}")
            tail = context[-330:] if len(context) > 330 else context
            self.memory_label.setText("Context: " + tail)
        except Exception:
            self.memory_label.setText("Context: ")

    def set_bg_color(self, emotion_label: str):
        color = self.bg_colors.get(emotion_label, "#0E0F14")
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(color))
        self.setPalette(pal)
        self.setAutoFillBackground(True)


    def _handle_ai_response(self, ai_response):
        self.memory_manager.add_memory(ai_response, "assistant_chat")
        self.update_memory_display()
        self.speak(ai_response)
    
    def update_response(self, chunk):
        if not hasattr(self, "stream_buffer"):
            self.stream_buffer = ""

        self.stream_buffer += chunk

        # UI update
        self.output_box.setPlainText(self.stream_buffer)
        self.subtitle_label.setText(
            self.stream_buffer[:140] + "..." if len(self.stream_buffer) > 140 else self.stream_buffer
        )

        # 🔥 sentence extraction
        sentences, remainder = extract_sentences(self.stream_buffer)

        buffer = ""

        for sentence in sentences:
            clean = sentence.strip()

            buffer += " " + clean

            # speak only when sentence is meaningful
            # ❌ disable streaming speech for now
            pass

        self.stream_buffer = remainder
        
    def finish_response(self):
        remaining = getattr(self, "stream_buffer", "").strip()

        if not remaining:
            remaining = self.output_box.toPlainText().strip()

        if remaining and not self.is_speaking:
            self.speak(remaining)

            self.memory_manager.add_memory(self.last_prompt, "user_chat")
            self.memory_manager.add_memory(remaining, "assistant_chat")
            self.update_memory_display()

        self.stream_buffer = ""
        self.output_box.setPlainText(remaining)
        logging.info(f"[LLM FINAL]: {remaining}")
        
    def get_ai_response(self, prompt: str) -> None:
        self.last_prompt = prompt
        logging.info(f"[LLM INPUT]: {prompt}")

        raw_memory = self.memory_manager.format_memories_for_context()

        # 🔥 CLEAN MEMORY
        def clean_memory(text):
            text = re.sub(r'\b(user_chat|assistant_chat|conversation|last conversation topic)\b:?', '', text)
            text = re.sub(r'⚠️.*', '', text)
            text = re.sub(r'You are Alice.*?assistant\.', '', text)

            text = re.sub(r'Extra data:.*', '', text)
            text = re.sub(r'[-"]', '', text)
            return re.sub(r'\s+', ' ', text).strip()

        memory_context = clean_memory(raw_memory)

        full_prompt = f"""
You are Alice.

You are:
- concise
- natural
- slightly playful
- not overly poetic
- not robotic

Speak like a real human assistant, not like an AI.

Conversation:
{memory_context}

User: {prompt}
Alice:
"""
        logging.info(f"[FULL PROMPT]: {full_prompt}")
        if hasattr(self, "ai_thread") and self.ai_thread.isRunning():
            print("[⚠️ Skipping: AI busy]")
            return
        self.ai_thread = AIWorker(full_prompt)

        self.ai_thread.response_chunk.connect(self.update_response)
        self.ai_thread.response_finished.connect(self.finish_response)

        self.ai_thread.start()