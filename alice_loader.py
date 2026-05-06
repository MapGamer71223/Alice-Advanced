import time
import importlib
import traceback
from typing import Callable, Optional
from PyQt5.QtCore import QThread, pyqtSignal
from ai_connector import warm_ollama

class LoaderThread(QThread):
    """
    Worker thread to initialize modules asynchronously.
    Emits progress_update(int percentage, str message).

    NOTE: public API preserved:
      - progress_update signal
      - load_memory(), init_tts(), init_voice(), init_ai(), finalize() methods
      - run() method that drives the sequence
    """

    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal()          # emitted when all steps completed successfully
    error = pyqtSignal(str, str)     # (step_name, error_message) emitted on fatal step error

    def __init__(
        self,
        parent=None,
        model_size: str = "small",
        device_index: int = 1,
        memory_class: str = "memory_manager.MemoryManager",
        tts_class: str = "tts_engine.AssistantTTS",
        voice_class: str = "voice_listener.VoiceListener",
        max_retries: int = 2,
        step_delay_ms: int = 150
    ):
        super().__init__(parent)
        # preserved attributes expected by other code
        self.memory_manager = None
        self.tts_engine = None
        self.voice_listener = None
        self.ai_ready = False

        # config / helpers
        self._stopped = False
        self.model_size = model_size
        self.device_index = device_index
        self.memory_class = memory_class
        self.tts_class = tts_class
        self.voice_class = voice_class
        self.max_retries = max_retries
        self.step_delay_ms = step_delay_ms

        # internal bookkeeping
        self._last_error: Optional[str] = None

    # --- run orchestration (preserves original behavior but is more robust) ---
    def run(self):
        steps = [
            ("Loading memory module...", self.load_memory),
            ("Initializing TTS engine...", self.init_tts),
            ("Preparing voice recognition...", self.init_voice),
            ("Loading AI brain...", self.init_ai),
            ("Almost ready...", self.finalize),
        ]

        total = len(steps)
        for idx, (msg, func) in enumerate(steps, start=1):
            if self._stopped:
                self.progress_update.emit(int(((idx-1)/total)*100), "Initialization cancelled.")
                return

            # emit start progress (slightly before running)
            self.progress_update.emit(int(((idx-1)/total)*100), msg)

            success = self._run_with_retries(func, msg)

            # short pause for UI smoothness (keeps previous behavior)
            self.msleep(self.step_delay_ms)

            if not success:
                # emit error and stop
                err_text = self._last_error or f"Step failed: {msg}"
                self.progress_update.emit(0, f"Error during: {msg}")
                self.error.emit(msg, err_text)
                return

            # update progress after successful step
            self.progress_update.emit(int((idx/total)*100), msg)

        # done
        self.ai_ready = True
        self.progress_update.emit(100, "Ready")
        self.finished.emit()

    # --- retry helper ---
    def _run_with_retries(self, func: Callable[[], bool], step_name: str) -> bool:
        attempts = 0
        while attempts <= self.max_retries and not self._stopped:
            attempts += 1
            start = time.time()
            try:
                ok = func()
                duration = time.time() - start
                if ok:
                    return True
                # if function returns False, try again (up to retries)
                self._last_error = f"{step_name} returned False on attempt {attempts} (took {duration:.2f}s)."
            except Exception as e:
                duration = time.time() - start
                tb = traceback.format_exc()
                self._last_error = f"{step_name} exception on attempt {attempts}: {e}\n{tb}"
            # small backoff between retries
            if attempts <= self.max_retries:
                backoff = 0.2 * attempts
                time.sleep(backoff)
        return False

    # --- public cancellation API ---
    def stop(self):
        """
        Signal the loader to abort ASAP. This will not force-kill initialization
        but it prevents starting further steps and attempts to cleanly stop.
        """
        self._stopped = True

    # --- preserved step methods (kept names & signatures) ---
    def load_memory(self) -> bool:
        """
        Loads MemoryManager. Keeps same method name and returns True on success.
        Attempts dynamic import by default, and allows class path override via self.memory_class.
        """
        try:
            module_name, class_name = self.memory_class.rsplit(".", 1)
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            # allow custom constructor signatures (no args expected by default)
            self.memory_manager = cls()
            return True
        except Exception as e:
            # fallback: try direct import of memory_manager module
            try:
                mod = importlib.import_module("memory_manager")
                cls = getattr(mod, "MemoryManager")
                self.memory_manager = cls()
                return True
            except Exception as e2:
                self._last_error = f"MemoryManager init error: {e} | fallback error: {e2}"
                return False

    def init_tts(self) -> bool:
        """
        Initializes TTS engine and stores it on self.tts_engine.
        """
        try:
            module_name, class_name = self.tts_class.rsplit(".", 1)
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            # prefer constructor with no args; if it requires args, let it raise up
            self.tts_engine = cls()
            # If engine exposes a warmup method, call it (non-blocking/light)
            if hasattr(self.tts_engine, "warmup") and callable(self.tts_engine.warmup):
                try:
                    self.tts_engine.warmup()
                except Exception:
                    # ignore warmup failures; engine itself was constructed fine
                    pass
            return True
        except Exception as e:
            self._last_error = f"TTS Engine init error: {e}"
            return False

    def init_voice(self) -> bool:
        """
        Initializes voice listener. Keeps the same method name/signature.
        Attempts to pass preferred model_size and device_index if the class accepts them.
        """
        try:
            module_name, class_name = self.voice_class.rsplit(".", 1)
            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name)
            # try to initialize with common args, fallback to zero-arg constructor
            try:
                self.voice_listener = cls(model_size=self.model_size, device_index=self.device_index)
            except TypeError:
                # signature did not accept those args
                try:
                    self.voice_listener = cls()
                except Exception as e2:
                    raise e2
            # if the voice listener provides a quick test method, call it lightly (do not block)
            if hasattr(self.voice_listener, "list_input_devices"):
                try:
                    # call but ignore results — useful for warming ASIO drivers
                    _ = getattr(self.voice_listener, "list_input_devices")()
                except Exception:
                    pass
            return True
        except Exception as e:
            self._last_error = f"VoiceListener init error: {e}"
            return False

    def init_ai(self) -> bool:
        """
        Warm up the Ollama model so first response is fast.
        """
        try:
            from ai_connector import query_ollama_mistral

            # warm load the model
            _ = query_ollama_mistral(
                "Hello",
                stream=False
            )

            self.ai_ready = True
            return True

        except Exception as e:
            self._last_error = f"AI initialization error: {e}"
            return False

    def finalize(self) -> bool:
        """
        Final step for any last-minute preparations. Kept identical in signature.
        """
        try:
            # small post-init sanity checks
            issues = []
            if self.memory_manager is None:
                issues.append("memory_manager not initialized")
            if self.tts_engine is None:
                issues.append("tts_engine not initialized")
            if self.voice_listener is None:
                issues.append("voice_listener not initialized")
            if issues:
                self._last_error = "Finalize checks failed: " + "; ".join(issues)
                # permit finalize to succeed even if voice is optional — return True if at least memory + tts exist
                if self.memory_manager is None or self.tts_engine is None:
                    return False
            return True
        except Exception as e:
            self._last_error = f"Finalize error: {e}"
            return False
