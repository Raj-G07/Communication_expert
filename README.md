# Visions - AI Communication Coach

The AI Communication Coach runs using a combination of Gemini Realtime, getstream, deepgram, elevenlabs, and Ultralytics YOLO. 

## How to Run Locally

### Prerequisites
You need the `uv` Python package manager installed. Currently, we use Python `>=3.12`.
Ensure you have created a `.env` file containing all the necessary API keys in your `c:\Visions` directory. The main required key is `GEMINI_API_KEY`.

### 1. Installation 
To install the dependencies, you can simply run `uv sync` from the `c:\Visions` directory. This creates a `.venv` for you in the folder automatically.

### 2. Run the Communication Coach
Execute the script natively with your local virtual environment:

```shell
.venv\Scripts\python.exe performance_agent.py
```

Optional: You can customize the behavior by passing environment variables:
```shell
# Available modes: "interview", "speaking", "debate", "fluency"
set COACH_MODE=interview
.venv\Scripts\python.exe performance_agent.py
```

### 3. Join the Call
Once the script says `Agent joining the call...`, a browser tab will automatically open on your Windows machine, linking to a GetStream staging URL. Allow your camera and microphone, click "Join", and you can start conversing! 

When you hang up the call or close the tab, the agent will gracefully shut down and generate a Session Performance Report in `c:\Visions\reports\`:

- `<session_id>.json` — raw data including summary scores, trends, and per-snapshot data
- `<session_id>.md` — a human-readable **Markdown summary** that automatically opens on your screen, including:
  - Overall performance score
  - Top strengths and areas for improvement
  - Next session focus
  - Detailed breakdown (clarity, structure, body language, confidence, WPM, hesitation, engagement)

## Running the Tests
To run the automated test suite testing the specific components of the pipeline (like Speech WPM Calculations):
```shell
.venv\Scripts\python.exe -m pytest tests/
```