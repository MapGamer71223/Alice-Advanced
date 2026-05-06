import os
import re
import uuid
import threading
import random
from piper import PiperVoice
import wave
from collections import OrderedDict
from PyQt5.QtCore import QThread, pyqtSignal
import pygame
PUNCTUATION_PAUSE_MS = 220  # pause after period/comma/question/exclamation

def punctuated_segments(text):
    # Split on sentence-ending punctuation with retention
    segments = re.split(r'([.,!?;:])', text)
    pairs = [''.join(segments[i:i+2]) for i in range(0, len(segments), 2)]
    return pairs

class AssistantTTSThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, text, tts_engine, emotion="neutral"):
        super().__init__()
        self.text = text
        self.tts_engine = tts_engine
        self.emotion = emotion
        self._stop_event = threading.Event()

    def run(self):
        path = None
        try:
            path = self.tts_engine.generate(self.text, self.emotion)
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            sound = pygame.mixer.Sound(path)
            channel = sound.play(fade_ms=100)

            if channel is None:
                print("[⚠️] Playback failed (channel None)")
            else:
                while channel.get_busy():
                    if self._stop_event.is_set():
                        channel.fadeout(200)
                        break
                    pygame.time.delay(50)
        except Exception as e:
            print(f"[❌] Error in TTS playback: {e}")
        finally:
            try:
                if 'sound' in locals():
                    del sound
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as cleanup_err:
                print(f"[!] Cleanup error in TTS thread: {cleanup_err}")
            self.finished_signal.emit()

    def stop(self):
        self._stop_event.set()
        self.wait()


class AssistantTTS:
    _cache = OrderedDict()
    _max_cache_size = 30

    def __init__(self):
        print("🔊 Loading Piper TTS...")
        self.voice = PiperVoice.load("model.onnx", "model.onnx.json")

    def sanitize_text(self, text):
        text = re.sub(r"[^\x00-\x7F]+", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def generate(self, text, emotion="neutral"):
        text = self.sanitize_text(text)
        cache_key = text

        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        output_path = f"assistant_{uuid.uuid4().hex}.wav"

        audio_stream = self.voice.synthesize(text)

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)        # mono
            wav_file.setsampwidth(2)        # 16-bit
            wav_file.setframerate(22050)    # match model
            for chunk in audio_stream:
                wav_file.writeframes(chunk.audio_int16_bytes)
        self._cache[cache_key] = output_path

        # cleanup old cache
        if len(self._cache) > self._max_cache_size:
            _, old_path = self._cache.popitem(last=False)
            try:
                os.remove(old_path)
            except:
                pass

        return output_path