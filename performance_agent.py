"""
Main Orchestration — AI Communication Coach
Wires together: Gemini Realtime LLM, Deepgram STT, ElevenLabs TTS,
YOLO Vision Processor, Speech Processor, Session Manager, and Performance Report.

Usage:
    COACH_MODE=interview python performance_agent.py
"""
import asyncio
import logging
import os
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from vision_agents.core.edge.types import User
from vision_agents.core.agents import agents
from vision_agents.core.stt.events import STTTranscriptEvent, STTPartialTranscriptEvent
from vision_agents.plugins import gemini, getstream, deepgram, elevenlabs

from pipelines.speech_processor import SpeechProcessor
from pipelines.language_intelligence import LanguageIntelligence
from pipelines.vision_processor import CommunicationVisionProcessor
from session.session_manager import SessionManager
from session.performance_report import PerformanceReport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────
COACH_MODE = os.environ.get("COACH_MODE", "interview").lower()
VALID_MODES = {"interview", "speaking", "debate", "fluency"}
if COACH_MODE not in VALID_MODES:
    logger.warning(f"Unknown COACH_MODE '{COACH_MODE}', defaulting to 'interview'")
    COACH_MODE = "interview"

MODE_LABELS = {
    "interview": "🎯 Interview Coach",
    "speaking": "🎤 Public Speaking Coach",
    "debate": "🗣️ Debate Coach",
    "fluency": "🌟 Daily Fluency Coach",
}


# ──────────────────────────────────────────────────
# Analysis cycle: runs every 30s inside the session
# ──────────────────────────────────────────────────
async def run_coaching_cycle(
    agent: agents.Agent,
    speech_proc: SpeechProcessor,
    lang_intel: LanguageIntelligence,
    vision_proc: CommunicationVisionProcessor,
    session: SessionManager,
) -> None:
    """
    Fired every 30 seconds by the SessionManager's analysis loop.
    1. Collect state from all processors
    2. Build structured coaching context
    3. Ask Gemini to deliver spoken coaching
    4. Store snapshot
    """
    speech_state = speech_proc.get_state()
    vision_state = vision_proc.get_state()
    window_text = speech_proc.get_window_text()

    # Build language evaluation prompt & use last known scores
    # (For production, integrate a Gemini text-call here; for realtime we inject context)
    lang_scores = lang_intel.get_last_scores()

    # If we have transcript text, build a richer prompt for Gemini to evaluate
    if window_text and len(window_text.split()) > 5:
        coaching_context = lang_intel.build_coaching_context(lang_scores, speech_state)
    else:
        coaching_context = (
            "The user hasn't spoken much yet. Encourage them to continue and remind them "
            "you're listening. Keep it warm and brief."
        )

    # Send coaching trigger to Gemini Realtime (it will speak via ElevenLabs TTS)
    await agent.simple_response(coaching_context)

    # Store snapshot after coaching
    session.record_snapshot(
        speech_state=speech_state,
        language_scores=lang_scores,
        vision_state=vision_state,
        coaching_message=coaching_context[:200],
    )

    # Rotate speech processor window after analysis
    speech_proc.reset_window()
    logger.info(f"[Cycle] Scores → overall={session.get_latest_scores().get('overall_score')}")


# ──────────────────────────────────────────────────
# Agent setup and session lifecycle
# ──────────────────────────────────────────────────
async def start_communication_coach() -> None:
    logger.info(f"🚀 Starting {MODE_LABELS.get(COACH_MODE, 'AI Coach')} (mode={COACH_MODE})")

    # ── Pipelines ──────────────────────────────────
    speech_proc = SpeechProcessor(window_seconds=30)
    lang_intel = LanguageIntelligence(mode=COACH_MODE)
    vision_proc = CommunicationVisionProcessor(
        model_path="yolo11n-pose.pt",
        conf_threshold=0.4,
        enable_hand_tracking=True,
        enable_wrist_highlights=True,
        fps=5,  # 5fps for YOLO to conserve CPU during live call
    )

    # ── Session manager ────────────────────────────
    session_id = str(uuid4())
    session = SessionManager(session_id=session_id, mode=COACH_MODE)

    # ── LLM: Gemini Realtime ───────────────────────
    llm = gemini.Realtime(fps=3)

    # ── Speech: Deepgram STT + ElevenLabs TTS ─────
    stt = deepgram.STT(eager_turn_detection=True)
    tts = elevenlabs.TTS(
        voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "VR6AewLTigWG4xSOukaG"),
        model_id="eleven_multilingual_v2",
    )

    with open("performance_agent.md", "r", encoding="utf-8") as f:
        instructions_text = f.read()

    # ── Agent ──────────────────────────────────────
    agent = agents.Agent(
        edge=getstream.Edge(),
        agent_user=User(
            name=f"Visions — {MODE_LABELS.get(COACH_MODE, 'AI Coach')}",
            id="visions_communication_coach",
        ),
        instructions=instructions_text,
        llm=llm,
        stt=stt,
        tts=tts,
        processors=[vision_proc],
        broadcast_metrics=True,
        broadcast_metrics_interval=10.0,
    )

    # ── Wire Deepgram transcripts → SpeechProcessor ─
    @agent.events.subscribe
    async def on_transcript(event: STTTranscriptEvent):
        speech_proc.on_transcript(event.text or "", is_final=True)

    @agent.events.subscribe
    async def on_partial_transcript(event: STTPartialTranscriptEvent):
        speech_proc.on_transcript(event.text or "", is_final=False)

    logger.info("Agent created and pipelines wired")

    await agent.create_user()
    logger.info("Agent user registered")

    # ── Create the call ────────────────────────────
    call_id = str(uuid4())
    call = agent.edge.client.video.call("default", call_id)
    logger.info(f"📞 Call ID: {call_id}")

    await agent.edge.open_demo(call)
    logger.info("🌐 Demo UI opened in browser — join the call to begin coaching")

    # ── Join call and run session ──────────────────
    logger.info("Agent joining the call...")

    async def _generate_and_deliver_report() -> None:
        """Generate and save the session report. Opens HTML in browser automatically."""
        await session.stop()
        logger.info("📊 Generating session performance report...")
        snapshots = session.get_all_snapshots()
        report_gen = PerformanceReport(
            session_id=session_id,
            mode=COACH_MODE,
            snapshots=snapshots,
        )
        report = report_gen.build()
        report_path = report_gen.save(report)  # saves JSON + HTML + MD; opens HTML in browser
        scores = report["summary_scores"]
        logger.info(f"✅ Report saved: {report_path}")
        logger.info(
            f"🏆 Final score: {scores.get('overall_average')}/100  |  "
            f"Clarity: {scores.get('clarity')}  |  "
            f"Structure: {scores.get('structure')}  |  "
            f"Engagement: {scores.get('engagement')}  |  "
            f"WPM: {scores.get('average_wpm')}"
        )
        logger.info("🌐 Session report opened in your browser.")

    async with agent.join(call):
        # Greeting is handled by the system instructions (Gemini says it automatically)
        logger.info(f"✅ Session started — mode: {COACH_MODE}")

        # Register and start the 30-second analysis loop
        async def analysis_callback():
            await run_coaching_cycle(agent, speech_proc, lang_intel, vision_proc, session)

        session.register_analysis_callback(analysis_callback)
        session.start_analysis_loop()

        try:
            # Wait for the call to end (user hangs up or closes tab)
            await agent.finish()

            # ── Session ended cleanly: generate report ──────────────────
            await _generate_and_deliver_report()

        except BaseException as e:
            # ── Session ended abruptly: still save the report ──────────
            logger.warning(f"Session ended unexpectedly ({type(e).__name__}: {e}). Saving report anyway...")
            try:
                await _generate_and_deliver_report()
            except Exception as report_err:
                logger.error(f"Failed to generate report after unexpected session end: {report_err}")
            raise


# ──────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(start_communication_coach())