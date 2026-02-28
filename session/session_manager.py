"""
Session Manager
Maintains per-call state, tracks 30-second coaching snapshots, and aggregates scores.
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")


@dataclass
class CoachingSnapshot:
    """A single 30-second analysis snapshot."""
    timestamp: float
    elapsed_seconds: float
    speech_state: dict
    language_scores: dict
    vision_state: dict
    coaching_message: str = ""

    def overall_score(self) -> float:
        """Compute weighted overall communication score."""
        clarity = self.language_scores.get("clarity_score", 70)
        structure = self.language_scores.get("structure_score", 70)
        confidence_lang = self.language_scores.get("confidence_score", 70)
        confidence_body = self.vision_state.get("confidence_index", 70)
        engagement = self.vision_state.get("engagement_score", 70)

        speech_penalty = min(30.0, self.speech_state.get("hesitation_index", 0) * 0.3)

        raw = (
            clarity * 0.20
            + structure * 0.20
            + confidence_lang * 0.15
            + confidence_body * 0.20
            + engagement * 0.25
        ) - speech_penalty

        return round(max(0.0, min(100.0, raw)), 1)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "elapsed_seconds": self.elapsed_seconds,
            "overall_score": self.overall_score(),
            "speech": self.speech_state,
            "language": self.language_scores,
            "vision": self.vision_state,
            "coaching_message": self.coaching_message,
        }


class SessionManager:
    """
    Manages the coaching session lifecycle:
    - Stores timestamped snapshots every 30 seconds
    - Exposes aggregated score trends for the dashboard
    - Triggers session report generation on call end
    """

    def __init__(self, session_id: Optional[str] = None, mode: str = "interview"):
        self.session_id = session_id or str(uuid4())
        self.mode = mode
        self.start_time = time.time()
        self._snapshots: list[CoachingSnapshot] = []
        self._analysis_interval = 30.0  # seconds
        self._analysis_task: Optional[asyncio.Task] = None
        self._on_analysis_callbacks: list = []

        logger.info(f"SessionManager created: session_id={self.session_id}, mode={mode}")

    def register_analysis_callback(self, callback) -> None:
        """
        Register a coroutine to call every 30 seconds.
        Callback signature: async def callback() -> None
        """
        self._on_analysis_callbacks.append(callback)

    def start_analysis_loop(self) -> None:
        """Start the periodic 30-second analysis cycle."""
        self._analysis_task = asyncio.create_task(self._analysis_loop())
        logger.info("Analysis loop started (30s intervals)")

    async def _analysis_loop(self) -> None:
        """Fires registered callbacks every 30 seconds."""
        try:
            while True:
                await asyncio.sleep(self._analysis_interval)
                logger.info(
                    f"[{self.session_id}] 30s analysis cycle firing "
                    f"(elapsed: {self.elapsed_seconds():.0f}s)"
                )
                for callback in self._on_analysis_callbacks:
                    try:
                        await callback()
                    except Exception as e:
                        logger.error(f"Analysis callback error: {e}")
        except asyncio.CancelledError:
            logger.info("Analysis loop cancelled")

    def record_snapshot(
        self,
        speech_state: dict,
        language_scores: dict,
        vision_state: dict,
        coaching_message: str = "",
    ) -> CoachingSnapshot:
        """
        Store a coaching snapshot for the current window.
        Returns the snapshot.
        """
        snapshot = CoachingSnapshot(
            timestamp=time.time(),
            elapsed_seconds=self.elapsed_seconds(),
            speech_state=speech_state.copy(),
            language_scores=language_scores.copy(),
            vision_state=vision_state.copy(),
            coaching_message=coaching_message,
        )
        self._snapshots.append(snapshot)
        logger.info(
            f"Snapshot #{len(self._snapshots)} recorded: "
            f"overall={snapshot.overall_score()}"
        )
        return snapshot

    def elapsed_seconds(self) -> float:
        return round(time.time() - self.start_time, 1)

    def get_score_trend(self) -> list[dict]:
        """Return list of {elapsed, overall_score} for trend charts."""
        return [
            {"elapsed": s.elapsed_seconds, "score": s.overall_score()}
            for s in self._snapshots
        ]

    def get_latest_scores(self) -> dict:
        """Return the most recent snapshot's scores, or defaults."""
        if not self._snapshots:
            return {
                "overall_score": 70.0,
                "speech_score": 70.0,
                "body_language_score": 70.0,
                "structure_score": 70.0,
                "confidence_score": 70.0,
            }
        s = self._snapshots[-1]
        return {
            "overall_score": s.overall_score(),
            "speech_score": max(0, 100 - s.speech_state.get("hesitation_index", 0)),
            "body_language_score": s.vision_state.get("confidence_index", 70),
            "structure_score": s.language_scores.get("structure_score", 70),
            "confidence_score": s.language_scores.get("confidence_score", 70),
            "clarity_score": s.language_scores.get("clarity_score", 70),
            "engagement_score": s.vision_state.get("engagement_score", 70),
        }

    def get_leaderboard_entry(self) -> dict:
        """Compact entry for the GetStream leaderboard."""
        scores = self.get_latest_scores()
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "elapsed_seconds": self.elapsed_seconds(),
            "overall_score": scores["overall_score"],
            "snapshot_count": len(self._snapshots),
        }

    async def stop(self) -> None:
        """Stop the analysis loop and return session data."""
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass

    def get_all_snapshots(self) -> list[dict]:
        return [s.to_dict() for s in self._snapshots]
