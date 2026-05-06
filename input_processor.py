class InputProcessor:
    def __init__(self):
        self.last_input_time = 0
        self.last_text = ""
        self.cooldown = 1.0
        self.low_value_words = {"the", "yeah", "it", "oh", "hmm"}

    def process(self, text: str, session_active: bool, last_interaction_time: float, session_timeout: int):
        import time

        text = text.strip().lower()

        if not text:
            return None, session_active, last_interaction_time

        # 🚫 ignore fillers
        if text in self.low_value_words:
            print("[⚠️ Ignored filler]")
            return None, session_active, last_interaction_time

        # 🚫 too short
        if len(text) < 3:
            return None, session_active, last_interaction_time

        # ⏳ debounce ONLY duplicates
        if text == self.last_text and (time.time() - self.last_input_time < self.cooldown):
            return None, session_active, last_interaction_time

        self.last_text = text
        self.last_input_time = time.time()

        # 🔥 wake word (optional)
        if text.startswith("alice"):
            text = text.replace("alice", "", 1).strip()
            if not text:
                return "__wake__", True, time.time()

        # (session no longer blocks anything)

        return text, session_active, time.time()