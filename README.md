# Visions — AI Communication Coach

A **multimodal, real-time AI communication coach** that joins a live video call and gives you personalised, spoken feedback on your speech, body language, and communication style — every 30 seconds.

Built on **Gemini Realtime**, **Deepgram STT**, **ElevenLabs TTS**, **GetStream** video, and **Ultralytics YOLO** pose detection.

---

## Features

| Area | What it measures |
|---|---|
| 🎙 **Speech** | WPM (words-per-minute), filler words, pause duration, hesitation index |
| 🧠 **Language** | Clarity, STAR structure (interview mode), confidence, vocabulary, grammar, emotional tone |
| 👁 **Body language** | Eye contact, posture, hand activity — via YOLO pose estimation at 5 fps |
| 📊 **Session report** | Overall score trend, per-dimension breakdown, strengths & improvements |

---

## Architecture

```
performance_agent.py          ← Main orchestrator
│
├── pipelines/
│   ├── speech_processor.py   ← WPM, filler words, pauses, hesitation index
│   ├── language_intelligence.py ← Gemini-powered clarity / STAR / confidence scoring
│   └── vision_processor.py   ← YOLO pose → eye contact, posture, hand movement
│
├── session/
│   ├── session_manager.py    ← 30-second snapshot loop, score aggregation
│   └── performance_report.py ← Builds + saves JSON / Markdown / HTML report
│
├── reports/                  ← Auto-generated session reports land here
├── performance_agent.md      ← LLM system instructions / coaching persona
└── yolo11n-pose.pt           ← YOLO pose model (nano, pre-bundled)
```

Every 30 seconds the **analysis loop** fires:
1. `SpeechProcessor` — computes WPM and hesitation from Deepgram transcripts.
2. `LanguageIntelligence` — builds an evaluation prompt and injects context into Gemini.
3. `CommunicationVisionProcessor` — reads YOLO pose data for body language scores.
4. `SessionManager` — records a `CoachingSnapshot` and Gemini delivers spoken feedback.
5. On call end — `PerformanceReport` builds a full HTML / Markdown / JSON session report.

---

## Coaching Modes

| Mode | `COACH_MODE` value | Focus |
|---|---|---|
| 🎯 Interview Coach | `interview` | STAR structure, confidence, clarity |
| 🎤 Public Speaking | `speaking` | Narrative arc, hook → body → call-to-action |
| 🗣 Debate | `debate` | Argument logic, assertiveness, evidence use |
| 🌟 Daily Fluency | `fluency` | Conversational flow, vocabulary, naturalness |

---

## Prerequisites

- **Python ≥ 3.12**
- **[uv](https://github.com/astral-sh/uv)** package manager

### API Keys Required

Create a `.env` file in `c:\Visions\` (copy `.env.example` as a starting point):

```ini
GEMINI_API_KEY=          # Google Gemini Realtime
STREAM_API_KEY=          # GetStream video
STREAM_API_SECRET=
DEEPGRAM_API_KEY=        # Speech-to-text
ELEVENLABS_API_KEY=      # Text-to-speech
ELEVENLABS_VOICE_ID=     # Optional — defaults to a built-in voice
ULTRALYTICS_API_KEY=     # YOLO pose model

EXAMPLE_BASE_URL=https://pronto-staging.getstream.io

# Coach mode: interview | speaking | debate | fluency
COACH_MODE=interview
```

---

## How to Run Locally

### 1. Install dependencies

```shell
uv sync
```

This creates a `.venv` folder automatically.

### 2. Start the coach

```shell
.venv\Scripts\python.exe performance_agent.py
```

Or set a coaching mode first:

```shell
set COACH_MODE=speaking
.venv\Scripts\python.exe performance_agent.py
```

### 3. Join the call

Once the script logs `Agent joining the call...`, a browser tab opens automatically with a GetStream staging URL.  
→ Allow camera & microphone, click **Join**, and start speaking.

---

## Session Reports

When the call ends (or the tab is closed), the agent automatically generates a **Session Performance Report** inside `c:\Visions\reports\`:

| File | Contents |
|---|---|
| `<session_id>.json` | Raw snapshot data — scores, trends, per-window speech/vision/language metrics |
| `<session_id>.md` | Human-readable Markdown summary |
| `<session_id>.html` | Visual HTML report — **automatically opens in your browser** |

The HTML report includes:
- **Overall score** and trend chart across the session
- **Top strengths** and areas for improvement
- **Next session focus** recommendation
- **Dimension breakdown** — Clarity · Structure · Confidence · Body Language · Engagement · WPM · Hesitation

> Reports are generated even if the session ends abruptly (e.g. browser tab closed mid-call).

---

## Running Tests

The test suite covers specific pipeline components (WPM calculations, snapshot scoring, etc.):

```shell
.venv\Scripts\python.exe -m pytest tests/
```

---

## Project Dependencies

Managed by [`uv`](https://github.com/astral-sh/uv) via `pyproject.toml`:

- [`vision-agents`](https://pypi.org/project/vision-agents/) ≥ 0.3.7 — core agent framework with Gemini Realtime, Deepgram STT, ElevenLabs TTS, and GetStream plugins
- [`vision-agents-plugins-ultralytics`](https://pypi.org/project/vision-agents-plugins-ultralytics/) ≥ 0.3.7 — YOLO pose processor integration