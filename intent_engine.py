INTENTS = [
    "system_action",   # open app, time, etc
    "search",          # google, youtube
    "conversation",    # LLM chat
    "noise",           # ignore
]

import re

def detect_intent(text: str):
    text = text.lower().strip()

    # 🚫 noise
    if text in {"the", "yeah", "hmm", "oh"} or len(text) < 3:
        return ("noise", 1.0)

    # 🕒 system actions
    if any(k in text for k in ["time", "date", "battery", "cpu"]):
        return ("system_action", 0.9)

    # 🌐 search
    if "search" in text or "google" in text or "youtube" in text:
        return ("search", 0.9)

    # 🖥 open apps
    if text.startswith("open"):
        return ("system_action", 0.85)

    # 💬 fallback → conversation
    return ("conversation", 0.6)