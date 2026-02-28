"""
Unit tests for SpeechProcessor — no live API dependencies required.
Run: python -m pytest tests/ -v
"""
import time
import pytest
from pipelines.speech_processor import SpeechProcessor, FILLER_PATTERNS


class TestFillerDetection:
    """Test filler word regex coverage."""

    def test_detects_um(self):
        matches = FILLER_PATTERNS.findall("Um, I think we should um go")
        assert len(matches) >= 2

    def test_detects_uh(self):
        matches = FILLER_PATTERNS.findall("So uh basically we uh need to")
        assert len(matches) >= 2

    def test_detects_like(self):
        matches = FILLER_PATTERNS.findall("It was like really like good you know")
        assert len(matches) >= 3

    def test_detects_you_know(self):
        matches = FILLER_PATTERNS.findall("You know what I mean, you know?")
        assert len(matches) >= 1

    def test_clean_text_has_no_fillers(self):
        matches = FILLER_PATTERNS.findall("The project delivered fantastic results on time.")
        assert len(matches) == 0


class TestWPMCalculation:
    """Test WPM computation accuracy."""

    def test_wpm_zero_at_start(self):
        proc = SpeechProcessor()
        assert proc.get_current_wpm() == 0.0

    def test_wpm_after_transcript(self):
        proc = SpeechProcessor()
        # Manually adjust start time to simulate 60 seconds elapsed
        proc._current_window.start_time = time.time() - 60.0
        proc.on_transcript("one two three four five six seven eight nine ten", is_final=True)
        wpm = proc.get_current_wpm()
        # 10 words / ~60s = ~10 WPM (exact timing varies slightly)
        assert 5.0 < wpm < 20.0

    def test_wpm_ideal_range(self):
        proc = SpeechProcessor()
        # Simulate 120 words in 60 seconds → 120 WPM
        proc._current_window.start_time = time.time() - 60.0
        words = " ".join(["word"] * 120)
        proc.on_transcript(words, is_final=True)
        wpm = proc.get_current_wpm()
        assert 100 < wpm < 140  # some timing variance expected

    def test_wpm_status_too_slow(self):
        proc = SpeechProcessor()
        proc._current_window.start_time = time.time() - 60.0
        proc.on_transcript("hello", is_final=True)  # 1 word / 60s ≈ 1 WPM
        state = proc.get_state()
        assert state["wpm_status"] == "too_slow"

    def test_wpm_status_ideal(self):
        proc = SpeechProcessor()
        proc._current_window.start_time = time.time() - 60.0
        words = " ".join(["word"] * 140)
        proc.on_transcript(words, is_final=True)
        state = proc.get_state()
        assert state["wpm_status"] == "ideal"


class TestHesitationIndex:
    """Test hesitation index normalization."""

    def test_hesitation_zero_no_fillers_no_pause(self):
        proc = SpeechProcessor()
        proc._current_window.start_time = time.time() - 30.0
        proc.on_transcript("clear confident speech without any fillers at all", is_final=True)
        # No pauses added manually, filler_count = 0
        hi = proc.get_hesitation_index()
        assert 0.0 <= hi <= 30.0  # low hesitation expected

    def test_hesitation_increases_with_fillers(self):
        proc = SpeechProcessor()
        proc._current_window.start_time = time.time() - 30.0
        proc.on_transcript("um uh like um basically um you know um uh", is_final=True)
        hi = proc.get_hesitation_index()
        print(f"HI IS {hi}")
        assert hi > 10.0

    def test_hesitation_bounded_0_100(self):
        proc = SpeechProcessor()
        proc._current_window.start_time = time.time() - 30.0
        # Extreme case
        proc.on_transcript(" ".join(["um"] * 50), is_final=True)
        proc._current_window.pause_durations_ms = [5000.0] * 20
        hi = proc.get_hesitation_index()
        assert 0.0 <= hi <= 100.0


class TestGetState:
    """Test state dict structure for LLM injection."""

    def test_state_has_required_keys(self):
        proc = SpeechProcessor()
        state = proc.get_state()
        required = [
            "wpm", "filler_count", "avg_pause_duration_ms",
            "hesitation_index", "window_elapsed_seconds",
            "window_text", "session_wpm", "wpm_status",
        ]
        for key in required:
            assert key in state, f"Missing key: {key}"

    def test_state_wpm_is_float(self):
        proc = SpeechProcessor()
        state = proc.get_state()
        assert isinstance(state["wpm"], float)

    def test_window_text_truncated_at_500(self):
        proc = SpeechProcessor()
        long_text = "word " * 200  # 1000 chars
        proc.on_transcript(long_text, is_final=True)
        state = proc.get_state()
        assert len(state["window_text"]) <= 500


class TestSessionSummary:
    """Test session summary generation."""

    def test_session_summary_keys(self):
        proc = SpeechProcessor()
        proc.on_transcript("hello world", is_final=True)
        summary = proc.get_session_summary()
        assert "total_words" in summary
        assert "total_fillers" in summary
        assert "average_wpm" in summary

    def test_session_total_words_count(self):
        proc = SpeechProcessor()
        proc.on_transcript("one two three", is_final=True)
        proc.on_transcript("four five six seven", is_final=True)
        assert proc.get_session_summary()["total_words"] == 7
