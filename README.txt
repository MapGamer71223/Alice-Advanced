<div align="center">

# Alice

```text
Real-time AI Voice Assistant
```

Low-latency desktop AI assistant built around:
- streaming LLM interaction
- semantic memory retrieval
- local inference
- voice-first interaction
- desktop automation

</div>

---

# System Architecture

```text
microphone input
        ↓
speech recognition
        ↓
input filtering + intent routing
        ↓
semantic memory retrieval
        ↓
LLM streaming inference
        ↓
emotion detection
        ↓
Piper TTS synthesis
        ↓
animated HUD response
```

---

# Core Systems

## Streaming LLM Engine

Alice uses local LLM inference through Ollama with:
- token streaming
- asynchronous worker threads
- conversational memory injection
- real-time HUD updates

```text
user input
   ↓
memory context injection
   ↓
Ollama streaming
   ↓
partial token emission
   ↓
real-time interface update
```

**Core files**
- `ai_connector.py`
- `alice_hud.py`

---

## Semantic Memory System

Custom long-term memory engine using:
- SentenceTransformers embeddings
- vector similarity retrieval
- contextual memory injection
- persistent storage

```text
conversation
      ↓
embedding generation
      ↓
vector indexing
      ↓
semantic retrieval
      ↓
memory-enhanced prompting
```

**Core files**
- `memory_manager.py`

---

## Voice + TTS Pipeline

Real-time voice interaction pipeline using:
- Piper TTS
- threaded playback
- interruption handling
- emotion-aware synthesis

```text
LLM response
    ↓
emotion analysis
    ↓
speech synthesis
    ↓
audio playback
    ↓
HUD sync
```

**Core files**
- `tts_engine.py`
- `utils.py`

---

## Intent + Action Engine

Desktop automation layer supporting:
- application launching
- browser control
- search automation
- system monitoring
- action routing

```text
voice command
      ↓
intent classification
      ↓
action routing
      ↓
desktop execution
```

**Core files**
- `intent_engine.py`
- `assistant_actions.py`

---

## HUD Interface

Custom PyQt5 HUD interface with:
- animated avatar rendering
- live transcript display
- speaking-state visualization
- streaming response rendering

```text
AI state
   ↓
HUD renderer
   ↓
animated avatar
   ↓
real-time feedback
```

**Core files**
- `alice_hud.py`
- `main.py`

---

# Stack

<div align="center">

![Python](https://img.shields.io/badge/Python-0d1117?style=for-the-badge&logo=python)
![PyQt5](https://img.shields.io/badge/PyQt5-0d1117?style=for-the-badge&logo=qt)
![Ollama](https://img.shields.io/badge/Ollama-0d1117?style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-0d1117?style=for-the-badge)
![SQLite](https://img.shields.io/badge/SQLite-0d1117?style=for-the-badge&logo=sqlite)
![PyTorch](https://img.shields.io/badge/PyTorch-0d1117?style=for-the-badge&logo=pytorch)

</div>

---

# Features

- Real-time AI interaction
- Local-first inference
- Semantic memory retrieval
- Streaming responses
- Emotion-aware TTS
- Desktop automation
- Voice-first interaction design

---

# Running

```bash
pip install -r requirements.txt
python main.py
```
