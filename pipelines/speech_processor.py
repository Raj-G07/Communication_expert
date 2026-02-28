"""
Speech Processing Pipeline
Measures WPM, filler words, pause duration, and hesitation index from Deepgram transcripts.
"""
import re
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

logger = logging.getLogger(__name__)

# Filler words to detect
FILLER_PATTERNS = re.compile(
    r"\b(um+|uh+|er+|ah+|like|you know|you know what i mean|"
    r"basically|literally|actually|honestly|right\?|so|anyway|"
    r"i mean|kind of|sort of|i guess)\b",
    re.IGNORECASE,
)

# Ideal WPM range for most communication contexts
IDEAL_WPM_MIN = 120
IDEAL_WPM_MAX = 160


@dataclass
class TranscriptWindow:
    """Stores a rolling 30-second window of transcript data."""
    text: str = ""
    word_count: int = 0
    filler_count: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    pause_durations_ms: list[float] = field(default_factory=list)


class SpeechProcessor:
    """
    Measures real-time speech quality metrics from streaming transcripts.

    Designed to be used alongside the Deepgram STT plugin. Subscribe to
    STT transcript events and call `on_transcript` for each utterance.

    Exposes `get_state()` for the vision-agent processor state injection.
    """

    def __init__(self, window_seconds: int = 30):
        self.window_seconds = window_seconds
        self._current_window = TranscriptWindow()
        self._completed_windows: Deque[TranscriptWindow] = deque(maxlen=100)

        # Track all-session cumulative stats
        self._session_start = time.time()
        self._total_words = 0
        self._total_fillers = 0
        self._last_speech_time: Optional[float] = None
        self._pause_threshold_ms = 500  # pauses > 500ms are "notable"

    def on_transcript(self, text: str, is_final: bool = True) -> None:
        """
        Process a new transcript segment from Deepgram.

        Args:
            text: The transcript text for this utterance.
            is_final: Whether this is a final (vs partial) transcript.
        """
        if not text or not text.strip():
            return

        now = time.time()

        # Calculate pause since last speech
        if self._last_speech_time is not None:
            pause_ms = (now - self._last_speech_time) * 1000
            if pause_ms > self._pause_threshold_ms:
                self._current_window.pause_durations_ms.append(pause_ms)

        self._last_speech_time = now

        # Only count final transcripts for window metrics
        if not is_final:
            return

        words = text.strip().split()
        word_count = len(words)
        fillers = FILLER_PATTERNS.findall(text)
        filler_count = len(fillers)

        # Update current window
        self._current_window.text += " " + text
        self._current_window.word_count += word_count
        self._current_window.filler_count += filler_count

        # Update cumulative session stats
        self._total_words += word_count
        self._total_fillers += filler_count

        logger.debug(
            f"SpeechProcessor: +{word_count} words, {filler_count} fillers detected"
        )

        # Rotate window if expired
        if (now - self._current_window.start_time) >= self.window_seconds:
            self._rotate_window(now)

    def _rotate_window(self, now: float) -> None:
        """Archive the current window and start a fresh one."""
        self._current_window.end_time = now
        self._completed_windows.append(self._current_window)
        self._current_window = TranscriptWindow(start_time=now)
        logger.info("SpeechProcessor: 30s window rotated.")

    def get_current_wpm(self) -> float:
        """Calculate WPM for the active window."""
        elapsed = time.time() - self._current_window.start_time
        if elapsed < 1.0 and self._current_window.word_count == 0 and self._completed_windows:
            # Fallback to the last completed window if we just rotated
            last_window = self._completed_windows[-1]
            if last_window.end_time:
                last_elapsed = last_window.end_time - last_window.start_time
                if last_elapsed >= 1.0:
                    return (last_window.word_count / last_elapsed) * 60.0

        if elapsed < 1.0:
            return 0.0
        return (self._current_window.word_count / elapsed) * 60.0

    def get_session_wpm(self) -> float:
        """Calculate overall session WPM."""
        elapsed = time.time() - self._session_start
        if elapsed < 1.0:
            return 0.0
        return (self._total_words / elapsed) * 60.0

    def get_avg_pause_duration_ms(self) -> float:
        """Average pause duration in current window (ms)."""
        pauses = self._current_window.pause_durations_ms
        if not pauses and self._completed_windows and (time.time() - self._current_window.start_time) < 1.0:
             pauses = self._completed_windows[-1].pause_durations_ms

        if not pauses:
            return 0.0
        return sum(pauses) / len(pauses)

    def get_hesitation_index(self) -> float:
        """
        Hesitation index (0-100). Combines filler rate and pause duration.
        Higher = more hesitation.
        """
        window = self._current_window
        actual_elapsed = time.time() - window.start_time
        filler_count = window.filler_count
        
        # If the window just rotated, add the last completed window for calculations
        elapsed = actual_elapsed
        if actual_elapsed < 1.0 and self._completed_windows:
            last_window = self._completed_windows[-1]
            if last_window.end_time:
                elapsed += max(1.0, last_window.end_time - last_window.start_time)
                filler_count += last_window.filler_count

        elapsed = max(1.0, elapsed)

        # Filler rate component: normalize fillers per minute against 0-10 range
        fillers_per_min = (filler_count / elapsed) * 60.0
        filler_component = min(fillers_per_min / 10.0, 1.0) * 50.0  # 0-50 points

        # Pause component: normalize avg pause 0-3000ms range
        avg_pause = self.get_avg_pause_duration_ms()
        pause_component = min(avg_pause / 3000.0, 1.0) * 50.0  # 0-50 points

        return round(filler_component + pause_component, 1)

    def get_state(self) -> dict:
        """
        Returns the current speech metrics dict for injection into LLM context.
        Called automatically by the vision-agents framework each turn.
        """
        wpm = self.get_current_wpm()
        filler_count = self._current_window.filler_count
        avg_pause = self.get_avg_pause_duration_ms()
        hesitation = self.get_hesitation_index()
        elapsed = round(time.time() - self._current_window.start_time, 1)
        window_text = self._current_window.text.strip()

        return {
            "wpm": round(wpm, 1),
            "filler_count": filler_count,
            "avg_pause_duration_ms": round(avg_pause, 1),
            "hesitation_index": hesitation,
            "window_elapsed_seconds": elapsed,
            "window_text": window_text[:500] if window_text else "",
            "session_wpm": round(self.get_session_wpm(), 1),
            "session_total_words": self._total_words,
            "session_total_fillers": self._total_fillers,
            "wpm_status": (
                "too_slow" if wpm < IDEAL_WPM_MIN and wpm > 0
                else "too_fast" if wpm > IDEAL_WPM_MAX
                else "ideal"
            ),
        }

    def get_window_text(self) -> str:
        """Get the transcript text from the current 30s window."""
        return self._current_window.text.strip()

    def reset_window(self) -> None:
        """Manually reset the current window (e.g., after analysis triggers)."""
        now = time.time()
        self._rotate_window(now)

    def get_session_summary(self) -> dict:
        """Full session-level speech summary for the performance report."""
        return {
            "session_duration_seconds": round(time.time() - self._session_start, 1),
            "total_words": self._total_words,
            "total_fillers": self._total_fillers,
            "average_wpm": round(self.get_session_wpm(), 1),
            "filler_rate_per_minute": round(
                (self._total_fillers / max(1, time.time() - self._session_start)) * 60, 2
            ),
            "windows_completed": len(self._completed_windows),
        }
