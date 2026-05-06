import os
import json
import queue
import numpy as np
import re
import time
import torch
import sounddevice as sd
from PyQt5.QtCore import QThread, pyqtSignal
from faster_whisper import WhisperModel
from vosk import Model, KaldiRecognizer
from silero_vad import load_silero_vad, get_speech_timestamps
import pvporcupine

class WakeWordListener(QThread):
    wake_detected = pyqtSignal()

    def __init__(self, keyword_path, device_index=1, parent=None):
        super().__init__(parent)
        self.running = True
        self.device_index = device_index
        self.porcupine = pvporcupine.create(keyword_paths=[keyword_path])
        self.q = queue.Queue(maxsize=100)
        

    def run(self):
        with sd.InputStream(
            channels=1, samplerate=16000, dtype='int16',
            device=self.device_index,
            blocksize=512,
            latency='low',
            callback=lambda indata, frames, time, status: self._audio_callback(indata, status)
        ):
            while self.running:
                try:
                    pcm = self.q.get(timeout=0.1)
                    result = self.porcupine.process(pcm)
                    if result >= 0:
                        print("[👂] Wake word detected!")
                        self.wake_detected.emit()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"[❌] WakeWordListener error: {e}")

    def _audio_callback(self, indata, status):
        if status:
            print(f"[❗] Audio status: {status}")
        try:
            self.q.put_nowait(bytes(indata))
        except queue.Full:
            self.q.get_nowait()
            self.q.put_nowait(bytes(indata))
            print("[⚠️] Audio queue full in wake word listener, dropped oldest chunk")

    def stop(self):
        print("[🛑] WakeWordListener stopping")
        self.running = False

class VoiceListener(QThread):
    command_received = pyqtSignal(str)
    partial_result = pyqtSignal(str)

    def __init__(self, device_index=1, parent=None):
        super().__init__(parent)
        self.running = True
        self.device_index = device_index
        self.active = False

        self.last_command_time = 0
        self.last_text = ""
        self.min_audio_length = 16000  # ~1 sec
        self.cooldown = 1.5  # seconds
       
        # 🔥 WHISPER (for final accuracy)
        self.whisper_model = WhisperModel("base", device="cuda", compute_type="float16")

        self.q = queue.Queue(maxsize=100)

        # 🧠 buffering
        self.audio_buffer = []
        
        self.vad_model = load_silero_vad()
        self.speech_active = False
        self.silence_start = None
        self.last_audio_time = time.time()
        self.stream_buffer = []
        self.last_transcribe_time = 0
        
    def clean_text(self, text):
        text = re.sub(r'\b(and|is|can|uh|um)\b', '', text)
        text = re.sub(r'\b(\w+)( \1\b)+', r'\1', text)
        return re.sub(r'\s+', ' ', text).strip()

    def audio_callback(self, indata, frames, time_info, status):
        if self.active:
            try:
                self.q.put_nowait(bytes(indata))
            except queue.Full:
                self.q.get_nowait()
                self.q.put_nowait(bytes(indata))

    def run(self):
        print(f"[🎙] Hybrid listener started on device {self.device_index}")

        self.audio_stream = sd.RawInputStream(
            samplerate=16000,
            blocksize=512,
            device=self.device_index,
            dtype='int16',
            channels=1,
            callback=self.audio_callback
        )

        self.audio_stream.start()

        while self.running:
            if not self.active:
                sd.sleep(10)
                continue

            try:
                data = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            audio_np = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

            audio_tensor = torch.from_numpy(audio_np).float()
            speech_prob = self.vad_model(audio_tensor, 16000).item()

         
            if speech_prob > 0.5:
                if not self.speech_active:
                    print("[🎤 Speech started]")
                    self.speech_active = True
                    self.audio_buffer = []
                    self.stream_buffer = []

                self.audio_buffer.append(audio_np)
                self.stream_buffer.append(audio_np)
                self.silence_start = None

                # 🔥 REAL-TIME TRANSCRIBE (every ~0.7 sec)
                if time.time() - self.last_transcribe_time > 0.7 and len(self.stream_buffer) > 5:
                    chunk = np.concatenate(self.stream_buffer)
                    self.stream_buffer = []

                    segments, _ = self.whisper_model.transcribe(
                        chunk,
                        beam_size=1,
                        vad_filter=False,
                        language="en",
                    )

                    partial = " ".join([seg.text for seg in segments]).strip()

                    if partial:
                        self.partial_result.emit(partial)

                    self.last_transcribe_time = time.time()

            else:
                if self.speech_active:
                    if self.silence_start is None:
                        self.silence_start = time.time()

                    elif time.time() - self.silence_start > 0.8:
                        print("[🛑 Speech ended]")

                        if len(self.audio_buffer) < 5:
                            print("[⚠️ Too little audio, skipping]")
                            self.speech_active = False
                            self.silence_start = None
                            continue

                        full_audio = np.concatenate(self.audio_buffer)
                        self.audio_buffer = []

                        self.process_whisper(full_audio)

                        self.speech_active = False
                        self.silence_start = None
    def process_whisper(self, audio):
        print("[🧠 Whisper processing full sentence...]")

        # ✅ 1. Ignore very short audio
        if len(audio) < self.min_audio_length:
            print("[⚠️ Skipped: audio too short]")
            return

        segments, _ = self.whisper_model.transcribe(
            audio,
            beam_size=1,
            vad_filter=False,
            language="en",
        )

        final_text = " ".join([seg.text for seg in segments]).strip()

        if not final_text:
            return

        final_text = self.clean_text(final_text)

        # ✅ 2. Ignore very short text
        if len(final_text.split()) < 2:
            print(f"[⚠️ Skipped: weak text → {final_text}]")
            return

        # ✅ 3. Remove wake word manually
        final_text = re.sub(r"\b(hey|hi)?\s*alice\b", "", final_text, flags=re.IGNORECASE).strip()

        # ✅ 4. Cooldown protection
        now = time.time()
        if now - self.last_command_time < self.cooldown:
            print("[⚠️ Skipped: cooldown active]")
            return

        # ✅ 5. Duplicate protection
        if final_text == self.last_text:
            print("[⚠️ Skipped: duplicate]")
            return

        self.last_command_time = now
        self.last_text = final_text

        print(f"[✅ FINAL]: {final_text}")
        self.command_received.emit(final_text)

    def pause_listening(self):
        print("[⏸️] VoiceListener paused")
        self.active = False
        self.audio_buffer = []

    def resume_listening(self):
        print("[▶️] VoiceListener resumed")
        self.active = True
        self.audio_buffer = []
        self.speech_active = False
        self.silence_start = None

    def stop(self):
        print("[🛑] VoiceListener stopping")
        self.running = False