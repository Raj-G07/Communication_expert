"""
Language Intelligence Pipeline
Uses Gemini to evaluate transcript quality: clarity, grammar, STAR structure,
vocabulary richness, and emotional tone. Returns structured JSON scores.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# The coach mode changes which evaluation criteria are emphasized
COACH_MODE = os.environ.get("COACH_MODE", "interview").lower()


EVALUATION_PROMPTS = {
    "interview": """
You are evaluating a job interview answer. The speaker just said:

"{transcript}"

Speech metrics from this window:
- WPM: {wpm} (ideal: 120-160)
- Filler words: {filler_count}
- Hesitation index: {hesitation_index}/100

Evaluate the following and respond ONLY with valid JSON. No markdown, no explanation:
{{
  "clarity_score": <0-100, how clear and direct is the message>,
  "structure_score": <0-100, does it follow STAR: Situation/Task/Action/Result>,
  "confidence_score": <0-100, does language sound confident, not hedging>,
  "vocabulary_score": <0-100, vocabulary richness and precision>,
  "emotional_tone": <"confident"|"nervous"|"monotone"|"engaging"|"aggressive">,
  "star_components_present": <list of STAR elements detected, e.g. ["situation","action"]>,
  "grammar_issues": <list of up to 3 specific grammar problems, empty if none>,
  "suggestions": <list of up to 3 specific, actionable improvements>,
  "top_strength": <one sentence about what the speaker did best>,
  "priority_fix": <one sentence about the single most important thing to improve>
}}
""",

    "speaking": """
You are evaluating a public speech or presentation segment. The speaker just said:

"{transcript}"

Speech metrics from this window:
- WPM: {wpm} (ideal: 120-160)
- Filler words: {filler_count}
- Hesitation index: {hesitation_index}/100

Evaluate and respond ONLY with valid JSON. No markdown, no explanation:
{{
  "clarity_score": <0-100>,
  "structure_score": <0-100, narrative arc quality: hook + body + call-to-action>,
  "confidence_score": <0-100>,
  "vocabulary_score": <0-100>,
  "emotional_tone": <"confident"|"nervous"|"monotone"|"engaging"|"aggressive">,
  "star_components_present": [],
  "grammar_issues": <list of up to 3 issues>,
  "suggestions": <list of up to 3 improvements>,
  "top_strength": <one sentence>,
  "priority_fix": <one sentence>
}}
""",

    "debate": """
You are evaluating a debate contribution. The speaker just said:

"{transcript}"

Speech metrics:
- WPM: {wpm}
- Filler words: {filler_count}
- Hesitation index: {hesitation_index}/100

Respond ONLY with valid JSON:
{{
  "clarity_score": <0-100>,
  "structure_score": <0-100, argument logic and evidence use>,
  "confidence_score": <0-100, assertiveness and stance clarity>,
  "vocabulary_score": <0-100>,
  "emotional_tone": <"confident"|"nervous"|"monotone"|"engaging"|"aggressive">,
  "star_components_present": [],
  "grammar_issues": <list of up to 3>,
  "suggestions": <list of up to 3>,
  "top_strength": <one sentence>,
  "priority_fix": <one sentence>
}}
""",

    "fluency": """
You are evaluating casual conversational fluency. The speaker just said:

"{transcript}"

Speech metrics:
- WPM: {wpm}
- Filler words: {filler_count}
- Hesitation index: {hesitation_index}/100

Respond ONLY with valid JSON:
{{
  "clarity_score": <0-100>,
  "structure_score": <0-100, thought completion and flow>,
  "confidence_score": <0-100>,
  "vocabulary_score": <0-100>,
  "emotional_tone": <"confident"|"nervous"|"monotone"|"engaging"|"natural">,
  "star_components_present": [],
  "grammar_issues": <list of up to 3>,
  "suggestions": <list of up to 3>,
  "top_strength": <one sentence>,
  "priority_fix": <one sentence>
}}
""",
}

DEFAULT_SCORES = {
    "clarity_score": 70,
    "structure_score": 70,
    "confidence_score": 70,
    "vocabulary_score": 70,
    "emotional_tone": "neutral",
    "star_components_present": [],
    "grammar_issues": [],
    "suggestions": [],
    "top_strength": "Keep going — you're making progress.",
    "priority_fix": "Focus on speaking clearly and directly.",
}


class LanguageIntelligence:
    """
    Handles language quality evaluation via Gemini.

    Instead of making direct API calls, this class builds the evaluation
    prompt and parses the structured JSON response. The agent registers
    `evaluate_communication` as a function tool that Gemini calls itself.

    Usage:
        lang = LanguageIntelligence()
        prompt = lang.build_evaluation_prompt(transcript, speech_state)
        # Send prompt to Gemini; parse response with parse_scores()
    """

    def __init__(self, mode: str = COACH_MODE):
        self.mode = mode
        self._last_scores: dict = DEFAULT_SCORES.copy()
        logger.info(f"LanguageIntelligence initialized in '{mode}' mode")

    def build_evaluation_prompt(
        self,
        transcript: str,
        speech_state: dict,
    ) -> str:
        """
        Build the Gemini evaluation prompt for the current window.

        Args:
            transcript: The 30-second transcript text.
            speech_state: Dict from SpeechProcessor.get_state()

        Returns:
            Formatted prompt string for sending to Gemini.
        """
        template = EVALUATION_PROMPTS.get(self.mode, EVALUATION_PROMPTS["interview"])
        return template.format(
            transcript=transcript[:1500],
            wpm=speech_state.get("wpm", 0),
            filler_count=speech_state.get("filler_count", 0),
            hesitation_index=speech_state.get("hesitation_index", 0),
        )

    def parse_scores(self, response_text: str) -> dict:
        """
        Parse the JSON response from Gemini into structured scores.

        Args:
            response_text: Raw text response from Gemini.

        Returns:
            Score dict, falling back to defaults on parse error.
        """
        # Strip any markdown code fences around JSON
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            scores = json.loads(text)
            # Validate required keys exist, else merge with defaults
            for key in DEFAULT_SCORES:
                if key not in scores:
                    scores[key] = DEFAULT_SCORES[key]
            self._last_scores = scores
            logger.info(f"Language scores parsed: clarity={scores.get('clarity_score')}, "
                        f"structure={scores.get('structure_score')}, "
                        f"confidence={scores.get('confidence_score')}")
            return scores
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse language scores JSON: {e}\nResponse: {text[:200]}")
            return self._last_scores.copy()

    def get_last_scores(self) -> dict:
        """Return the most recently parsed scores."""
        return self._last_scores.copy()

    def build_coaching_context(self, scores: dict, speech_state: dict) -> str:
        """
        Build a compact coaching context string to inject into the LLM.
        This is appended to the 30-second coaching trigger prompt.
        """
        lines = [
            f"=== 30-Second Analysis Window ===",
            f"Mode: {self.mode}",
            "",
            "SPEECH METRICS:",
            f"  WPM: {speech_state.get('wpm', 0)} ({speech_state.get('wpm_status', 'unknown')})",
            f"  Filler words: {speech_state.get('filler_count', 0)}",
            f"  Avg pause: {speech_state.get('avg_pause_duration_ms', 0):.0f}ms",
            f"  Hesitation index: {speech_state.get('hesitation_index', 0)}/100",
            "",
            "LANGUAGE QUALITY:",
            f"  Clarity: {scores.get('clarity_score', 0)}/100",
            f"  Structure: {scores.get('structure_score', 0)}/100",
            f"  Confidence: {scores.get('confidence_score', 0)}/100",
            f"  Vocabulary: {scores.get('vocabulary_score', 0)}/100",
            f"  Tone: {scores.get('emotional_tone', 'unknown')}",
        ]

        if scores.get("grammar_issues"):
            lines.append(f"  Grammar issues: {', '.join(scores['grammar_issues'][:2])}")

        if scores.get("star_components_present") and self.mode == "interview":
            lines.append(
                f"  STAR components: {', '.join(scores['star_components_present'])}"
            )

        lines += [
            "",
            f"Top strength: {scores.get('top_strength', '')}",
            f"Priority fix: {scores.get('priority_fix', '')}",
            "",
            "Now deliver a brief 2-3 sentence coaching message following your coaching rules.",
        ]

        return "\n".join(lines)
