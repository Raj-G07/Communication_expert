"""
Vision Processing Pipeline
Extends YOLOPoseProcessor to compute higher-level body language metrics:
- Face orientation, eye contact, posture, hand movement
- Generates confidence index, engagement score, body language rating
"""
import logging
import math
import time
from typing import Any, Optional

from vision_agents.plugins.ultralytics import YOLOPoseProcessor

logger = logging.getLogger(__name__)

# COCO keypoint indices
KP_NOSE = 0
KP_LEFT_EYE = 1
KP_RIGHT_EYE = 2
KP_LEFT_EAR = 3
KP_RIGHT_EAR = 4
KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8


class CommunicationVisionProcessor(YOLOPoseProcessor):
    """
    Extended YOLO Pose Processor for communication coaching.

    Adds body language interpretation on top of raw pose detection:
    - Eye contact estimation (camera-facing heuristic from nose/ear alignment)
    - Posture scoring (shoulder height symmetry and vertical alignment)
    - Hand movement tracking (wrist velocity)
    - Confidence and engagement composite scores

    get_state() returns a structured dict injected into the LLM each turn.
    """

    name = "communication_vision"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Wrist velocity tracking
        self._prev_wrist_positions: dict[str, tuple[float, float]] = {}
        self._prev_wrist_time: float = time.time()
        self._wrist_velocity_history: list[float] = []  # last N frames

        # Rolling score history (for smoothing)
        self._eye_contact_history: list[float] = []
        self._posture_history: list[float] = []
        self._confidence_history: list[float] = []
        self._engagement_history: list[float] = []

        self._history_len = 30  # ~1 second at 30fps

        # Latest state for get_state()
        self._latest_state: dict = {
            "confidence_index": 70.0,
            "engagement_score": 70.0,
            "body_language_rating": "good",
            "posture": "upright",
            "eye_contact": "strong",
            "hand_activity": "natural",
            "persons_detected": 0,
        }

    def _safe_keypoint(
        self, kpts: list, index: int, conf_threshold: float = 0.3
    ) -> Optional[tuple[float, float]]:
        """Return (x, y) if keypoint confidence exceeds threshold, else None."""
        if index >= len(kpts):
            return None
        x, y, c = kpts[index]
        return (float(x), float(y)) if float(c) > conf_threshold else None

    def _score_eye_contact(self, kpts: list) -> float:
        """
        Estimate eye contact (0-100) using nose/ear symmetry.
        When looking at camera: nose is centered, ears are equidistant.
        When looking away: nose shifts toward one side, ear asymmetry increases.
        """
        nose = self._safe_keypoint(kpts, KP_NOSE)
        left_ear = self._safe_keypoint(kpts, KP_LEFT_EAR)
        right_ear = self._safe_keypoint(kpts, KP_RIGHT_EAR)

        if not nose or not left_ear or not right_ear:
            return 60.0  # neutral when keypoints unavailable

        nose_x = nose[0]
        left_ear_x = left_ear[0]
        right_ear_x = right_ear[0]

        ear_width = abs(right_ear_x - left_ear_x)
        if ear_width < 1e-3:
            return 60.0

        # Ratio of nose position within ear span (0.5 = perfectly centered)
        nose_ratio = (nose_x - left_ear_x) / ear_width
        center_deviation = abs(nose_ratio - 0.5)  # 0 = perfect center

        # Convert to 0-100 score (0 deviation = 100, 0.5 deviation = 0)
        score = max(0.0, 100.0 - (center_deviation / 0.5) * 100.0)
        return round(score, 1)

    def _score_posture(self, kpts: list) -> tuple[float, str]:
        """
        Score posture (0-100) and classify it.
        Uses shoulder height symmetry and shoulder-to-hip vertical alignment.
        Returns (score, label).
        """
        left_shoulder = self._safe_keypoint(kpts, KP_LEFT_SHOULDER)
        right_shoulder = self._safe_keypoint(kpts, KP_RIGHT_SHOULDER)
        left_hip = self._safe_keypoint(kpts, KP_LEFT_HIP)
        right_hip = self._safe_keypoint(kpts, KP_RIGHT_HIP)

        if not left_shoulder or not right_shoulder:
            return 65.0, "upright"

        # Shoulder symmetry (y coordinates should be similar)
        shoulder_height_diff = abs(left_shoulder[1] - right_shoulder[1])
        shoulder_width = abs(left_shoulder[0] - right_shoulder[0])
        if shoulder_width < 1e-3:
            return 65.0, "upright"

        symmetry_score = max(0.0, 100.0 - (shoulder_height_diff / shoulder_width) * 200)

        # Shoulder vertical position (higher on screen = better posture for seated person)
        # We use shoulder midpoint y as proxy for upright-ness
        shoulder_mid_y = (left_shoulder[1] + right_shoulder[1]) / 2.0
        posture_score = symmetry_score  # Simplified; extend with hip alignment if available

        if left_hip and right_hip:
            hip_mid_y = (left_hip[1] + right_hip[1]) / 2.0
            # Torso height ratio: larger = more upright
            torso_height = abs(hip_mid_y - shoulder_mid_y)
            shoulder_to_hip_ratio = torso_height / max(1, shoulder_width)
            # Ideal ratio ~1.3-1.8 for upright seated posture
            ratio_score = min(100.0, (shoulder_to_hip_ratio / 1.5) * 100.0)
            posture_score = (symmetry_score * 0.5) + (ratio_score * 0.5)

        posture_score = round(max(0.0, min(100.0, posture_score)), 1)

        if posture_score >= 75:
            label = "upright"
        elif posture_score >= 50:
            label = "leaning"
        else:
            label = "slouched"

        return posture_score, label

    def _score_hand_activity(self, kpts: list) -> tuple[float, str]:
        """
        Score hand movement and classify as natural/excessive/minimal.
        Uses wrist velocity relative to body width.
        """
        now = time.time()
        dt = now - self._prev_wrist_time
        self._prev_wrist_time = now

        if dt < 1e-6:
            return 50.0, "natural"

        velocities: list[float] = []
        shoulder_width = 1.0

        left_shoulder = self._safe_keypoint(kpts, KP_LEFT_SHOULDER)
        right_shoulder = self._safe_keypoint(kpts, KP_RIGHT_SHOULDER)
        if left_shoulder and right_shoulder:
            shoulder_width = max(
                1.0, abs(right_shoulder[0] - left_shoulder[0])
            )

        for side, kp_idx in [("left", KP_LEFT_WRIST), ("right", KP_RIGHT_WRIST)]:
            wrist = self._safe_keypoint(kpts, kp_idx)
            if wrist:
                prev = self._prev_wrist_positions.get(side)
                if prev:
                    dx = wrist[0] - prev[0]
                    dy = wrist[1] - prev[1]
                    velocity = math.sqrt(dx**2 + dy**2) / (shoulder_width * dt)
                    velocities.append(velocity)
                self._prev_wrist_positions[side] = wrist

        if not velocities:
            return 50.0, "natural"

        avg_velocity = sum(velocities) / len(velocities)
        self._wrist_velocity_history.append(avg_velocity)
        if len(self._wrist_velocity_history) > self._history_len:
            self._wrist_velocity_history.pop(0)

        smoothed = sum(self._wrist_velocity_history) / len(self._wrist_velocity_history)

        # Classify velocity ranges (normalized to shoulder width per second)
        if smoothed < 0.3:
            return smoothed * 100, "minimal"
        elif smoothed > 2.5:
            return min(100.0, smoothed * 20), "excessive"
        else:
            # Map 0.3-2.5 to "natural" range, score 60-90
            score = 60.0 + ((smoothed - 0.3) / 2.2) * 30.0
            return round(score, 1), "natural"

    def _smooth_score(self, history: list[float], new_val: float) -> float:
        """Exponential smoothing for score stability."""
        history.append(new_val)
        if len(history) > self._history_len:
            history.pop(0)
        if not history:
            return new_val
        # Weighted average (recent values weighted more)
        n = len(history)
        weights = [i + 1 for i in range(n)]
        return sum(v * w for v, w in zip(history, weights)) / sum(weights)

    def _process_person_keypoints(self, kpts: list) -> dict[str, Any]:
        """Compute all body language metrics for one detected person."""
        eye_contact_raw = self._score_eye_contact(kpts)
        posture_raw, posture_label = self._score_posture(kpts)
        hand_score, hand_label = self._score_hand_activity(kpts)

        eye_contact = self._smooth_score(self._eye_contact_history, eye_contact_raw)
        posture_score = self._smooth_score(self._posture_history, posture_raw)

        # Composite confidence index
        confidence_raw = (eye_contact * 0.4) + (posture_score * 0.4) + (hand_score * 0.2)
        confidence = self._smooth_score(self._confidence_history, confidence_raw)

        # Engagement score (eye contact + energy signals)
        activity_bonus = 10.0 if hand_label == "natural" else 0.0
        engagement_raw = (eye_contact * 0.6) + (posture_score * 0.3) + activity_bonus
        engagement = self._smooth_score(self._engagement_history, engagement_raw)

        # Body language rating
        avg_score = (confidence + engagement) / 2.0
        if avg_score >= 80:
            rating = "excellent"
        elif avg_score >= 60:
            rating = "good"
        elif avg_score >= 40:
            rating = "fair"
        else:
            rating = "poor"

        # Eye contact label
        if eye_contact >= 70:
            eye_label = "strong"
        elif eye_contact >= 45:
            eye_label = "intermittent"
        else:
            eye_label = "weak"

        return {
            "confidence_index": round(confidence, 1),
            "engagement_score": round(engagement, 1),
            "body_language_rating": rating,
            "posture": posture_label,
            "eye_contact": eye_label,
            "hand_activity": hand_label,
            "eye_contact_score": round(eye_contact, 1),
            "posture_score": round(posture_score, 1),
            "hand_activity_score": round(hand_score, 1),
        }

    def get_state(self) -> dict:
        """
        Returns body language state dict injected into LLM context each turn.
        Falls back to cached state if no new pose data available.
        """
        return self._latest_state.copy()

    def _process_pose_sync(self, frame_array) -> tuple:
        """
        Override parent to intercept pose_data and compute body language metrics.
        """
        annotated_frame, pose_data = super()._process_pose_sync(frame_array)

        persons = pose_data.get("persons", [])
        if persons:
            # Analyze first detected person (primary speaker)
            kpts = persons[0].get("keypoints", [])
            if kpts:
                body_language = self._process_person_keypoints(kpts)
                body_language["persons_detected"] = len(persons)
                self._latest_state = body_language
                logger.debug(f"Body language: {body_language}")
        else:
            self._latest_state["persons_detected"] = 0

        return annotated_frame, pose_data
