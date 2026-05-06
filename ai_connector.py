import time
import logging
import requests
import json
import re

from typing import Generator, Optional, Dict, Any

# --- Logging setup ---
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO
)

def warm_ollama(model="phi3:mini", ollama_url="http://localhost:11434/api/chat"):
    try:
        logging.info("Warming Ollama model...")
        requests.post(
            ollama_url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "System warm-up"}],
                "stream": False
            },
            timeout=30
        )
        logging.info("Ollama warm load complete.")
    except Exception as e:
        logging.warning(f"Ollama warm load failed: {e}")

# --- Main entrypoint ---
def query_ollama_mistral(
    prompt: str,
    model: str = "phi3:mini",
    stream: bool = False,
    ollama_url: str = "http://localhost:11434/api/chat",
    timeout: int = 60
):

    logging.info("query_alice called | Model: %s | Stream: %s", model, stream)

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": stream
    }

    def stream_gen():
        try:
            with requests.post(ollama_url, json=payload, stream=True, timeout=timeout) as r:
                r.raise_for_status()

                buffer = ""

                for chunk in r.iter_content(chunk_size=1024):
                    if not chunk:
                        continue

                    decoded = chunk.decode("utf-8", errors="ignore")
                    buffer += decoded

                    while True:
                        try:
                            data, index = json.JSONDecoder().raw_decode(buffer)
                            buffer = buffer[index:].lstrip()

                            if "message" in data:
                                piece = data["message"].get("content", "")
                                if piece:
                                    yield piece

                            if data.get("done"):
                                return

                        except json.JSONDecodeError:
                            break

        except Exception as e:
            logging.error("Ollama streaming error: %s", e)
            yield "Sorry, something went wrong."

    if stream:
        return stream_gen()

    # non-stream fallback
    try:
        response = requests.post(ollama_url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        return (data.get("message", {}) or {}).get("content", "")

    except Exception as e:
        logging.error("Ollama error: %s", e)
        return "Sorry, I had a problem responding."