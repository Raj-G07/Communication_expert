"""
Performance Report Generator
Aggregates session snapshots into a full coaching report with trends and recommendations.
"""
import json
import logging
import time
import os
import webbrowser
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("reports")


class PerformanceReport:
    """
    Generates the end-of-session performance report from all 30s snapshots.

    Saves a JSON file to reports/<session_id>.json and returns
    a spoken summary string for ElevenLabs TTS delivery.
    """

    def __init__(self, session_id: str, mode: str, snapshots: list[dict]):
        self.session_id = session_id
        self.mode = mode
        self.snapshots = snapshots

    def _average(self, key_path: list[str]) -> float:
        """Average a nested metric across all snapshots."""
        values = []
        for s in self.snapshots:
            obj = s
            for key in key_path:
                obj = obj.get(key, {}) if isinstance(obj, dict) else None
                if obj is None:
                    break
            if isinstance(obj, (int, float)):
                values.append(float(obj))
        if not values:
            return 0.0
        return round(sum(values) / len(values), 1)

    def _trend_direction(self, key_path: list[str]) -> str:
        """Determine if a metric trended up, down, or was stable over the session."""
        values = []
        for s in self.snapshots:
            obj = s
            for key in key_path:
                obj = obj.get(key, {}) if isinstance(obj, dict) else None
                if obj is None:
                    break
            if isinstance(obj, (int, float)):
                values.append(float(obj))

        if len(values) < 2:
            return "stable"

        first_half = sum(values[: len(values) // 2]) / max(1, len(values) // 2)
        second_half = sum(values[len(values) // 2 :]) / max(1, len(values) - len(values) // 2)
        delta = second_half - first_half
        if delta > 5:
            return "improving"
        elif delta < -5:
            return "declining"
        return "stable"

    def build(self) -> dict:
        """Assemble the full report dict."""
        overall_scores = [s.get("overall_score", 70) for s in self.snapshots]
        avg_overall = round(sum(overall_scores) / max(1, len(overall_scores)), 1)
        peak_overall = round(max(overall_scores, default=0), 1)
        final_overall = overall_scores[-1] if overall_scores else 0

        report = {
            "session_id": self.session_id,
            "mode": self.mode,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_seconds": self.snapshots[-1].get("elapsed_seconds", 0) if self.snapshots else 0,
            "snapshot_count": len(self.snapshots),

            "summary_scores": {
                "overall_average": avg_overall,
                "overall_peak": peak_overall,
                "overall_final": final_overall,
                "clarity": self._average(["language", "clarity_score"]),
                "structure": self._average(["language", "structure_score"]),
                "confidence_language": self._average(["language", "confidence_score"]),
                "confidence_body": self._average(["vision", "confidence_index"]),
                "engagement": self._average(["vision", "engagement_score"]),
                "average_wpm": self._average(["speech", "wpm"]),
                "average_filler_count": self._average(["speech", "filler_count"]),
                "average_hesitation_index": self._average(["speech", "hesitation_index"]),
            },

            "trends": {
                "overall_score": self._trend_direction(["overall_score"]),
                "clarity": self._trend_direction(["language", "clarity_score"]),
                "confidence": self._trend_direction(["language", "confidence_score"]),
                "body_language": self._trend_direction(["vision", "confidence_index"]),
                "hesitation": self._trend_direction(["speech", "hesitation_index"]),
            },

            "strengths": self._identify_strengths(),
            "improvement_areas": self._identify_improvement_areas(),
            "next_session_focus": self._suggest_next_focus(),

            "score_timeline": [
                {"elapsed": s.get("elapsed_seconds", 0), "score": s.get("overall_score", 0)}
                for s in self.snapshots
            ],

            "raw_snapshots": self.snapshots,
        }
        return report

    def _identify_strengths(self) -> list[str]:
        """Identify top 3 strengths from session averages."""
        strengths = []
        avg_clarity = self._average(["language", "clarity_score"])
        avg_conf_body = self._average(["vision", "confidence_index"])
        avg_engagement = self._average(["vision", "engagement_score"])
        avg_structure = self._average(["language", "structure_score"])
        avg_hesitation = self._average(["speech", "hesitation_index"])
        avg_wpm = self._average(["speech", "wpm"])

        if avg_clarity >= 75:
            strengths.append(f"Excellent message clarity ({avg_clarity:.0f}/100)")
        if avg_conf_body >= 70:
            strengths.append(f"Strong physical presence and confident body language ({avg_conf_body:.0f}/100)")
        if avg_engagement >= 70:
            strengths.append(f"High engagement and camera presence ({avg_engagement:.0f}/100)")
        if avg_structure >= 75:
            strengths.append(f"Well-structured responses ({avg_structure:.0f}/100)")
        if avg_hesitation < 20:
            strengths.append("Very low filler word usage — speaks fluently and directly")
        if 120 <= avg_wpm <= 160:
            strengths.append(f"Good speaking pace ({avg_wpm:.0f} WPM — within ideal range)")

        return strengths[:3]

    def _identify_improvement_areas(self) -> list[str]:
        """Identify top 3 areas needing improvement."""
        areas = []
        avg_hesitation = self._average(["speech", "hesitation_index"])
        avg_clarity = self._average(["language", "clarity_score"])
        avg_structure = self._average(["language", "structure_score"])
        avg_eye = self._average(["vision", "eye_contact_score"])
        avg_wpm = self._average(["speech", "wpm"])
        avg_conf_lang = self._average(["language", "confidence_score"])

        if avg_hesitation > 40:
            areas.append(f"Reduce filler words and hesitation (index: {avg_hesitation:.0f}/100 — aim for <20)")
        if avg_clarity < 65:
            areas.append(f"Improve message clarity ({avg_clarity:.0f}/100 — lead with your main point)")
        if avg_structure < 65:
            areas.append(f"Use clearer structure ({avg_structure:.0f}/100 — try STAR or topic→evidence→conclusion)")
        if avg_eye < 50:
            areas.append("Maintain stronger eye contact with the camera")
        if avg_wpm > 180:
            areas.append(f"Slow your pace ({avg_wpm:.0f} WPM — aim for 120-160)")
        elif avg_wpm < 100 and avg_wpm > 0:
            areas.append(f"Increase your pace ({avg_wpm:.0f} WPM — you're speaking too slowly)")
        if avg_conf_lang < 60:
            areas.append("Replace hedging phrases ('I think', 'maybe', 'kind of') with direct statements")

        return areas[:3]

    def _suggest_next_focus(self) -> str:
        """Single most important thing to practice next session."""
        areas = self._identify_improvement_areas()
        if areas:
            return areas[0]
        return "Keep practicing — you're performing at a high level. Try increasing session length."

    def build_tts_summary(self, report: Optional[dict] = None) -> str:
        """
        Generate a natural, spoken session summary for TTS delivery.
        Friendly, coach-like, and brief.
        """
        if report is None:
            report = self.build()

        scores = report.get("summary_scores", {})
        overall = scores.get("overall_average", 70)
        trends = report.get("trends", {})
        strengths = report.get("strengths", [])
        areas = report.get("improvement_areas", [])

        # Determine performance tier
        if overall >= 85:
            opener = "That was an excellent session."
        elif overall >= 70:
            opener = "That was a solid session with some great moments."
        elif overall >= 55:
            opener = "Good effort today — you made real progress."
        else:
            opener = "Thanks for sticking through the session — every rep counts."

        # Overall trend comment
        overall_trend = trends.get("overall_score", "stable")
        trend_comment = {
            "improving": "Your performance improved significantly as the session went on — great momentum.",
            "declining": "You started strong but fatigued toward the end — work on stamina.",
            "stable": f"You held a consistent score around {overall:.0f} out of 100 throughout.",
        }.get(overall_trend, "")

        # Strength mention
        strength_line = ""
        if strengths:
            strength_line = f"Your biggest strength today was: {strengths[0]}."

        # Improvement mention
        focus_line = ""
        if areas:
            focus_line = f"Your number one focus for next time: {areas[0]}."

        # Closer
        closer = "Keep practicing — small improvements every day compound into remarkable results."

        parts = [opener, trend_comment, strength_line, focus_line, closer]
        return " ".join(p for p in parts if p)

    def build_markdown(self, report: dict) -> str:
        """
        Generate a human-readable Markdown report.
        """
        scores = report.get("summary_scores", {})
        overall = scores.get("overall_average", 70)
        trends = report.get("trends", {})
        strengths = report.get("strengths", [])
        areas = report.get("improvement_areas", [])

        md = f"# Coaching Session Report\n\n"
        md += f"**Session ID:** `{report.get('session_id')}`\n"
        md += f"**Mode:** {report.get('mode', 'Unknown').title()}\n"
        md += f"**Date:** {report.get('generated_at')}\n"
        md += f"**Duration:** {report.get('duration_seconds', 0)} seconds\n\n"
        
        md += f"## Overall Performance: {overall}/100\n\n"
        
        md += f"### Top Strengths\n"
        if strengths:
            for s in strengths:
                md += f"- ✅ {s}\n"
        else:
            md += "- No prominent strengths identified in this session.\n"
        md += "\n"

        md += f"### Areas for Improvement\n"
        if areas:
            for a in areas:
                md += f"- 🎯 {a}\n"
        else:
            md += "- You did great! No major areas for improvement identified.\n"
        md += "\n"
        
        md += f"### Next Session Focus\n"
        md += f"**{report.get('next_session_focus', 'Keep practicing!')}**\n\n"

        md += f"### Detailed Scores\n"
        md += f"- **Clarity:** {scores.get('clarity', 0)}/100 ({trends.get('clarity', 'stable')})\n"
        md += f"- **Structure:** {scores.get('structure', 0)}/100\n"
        md += f"- **Language Confidence:** {scores.get('confidence_language', 0)}/100 ({trends.get('confidence', 'stable')})\n"
        md += f"- **Body Language & Presence:** {scores.get('confidence_body', 0)}/100 ({trends.get('body_language', 'stable')})\n"
        md += f"- **Engagement:** {scores.get('engagement', 0)}/100\n"
        md += f"- **Speaking Pace:** {scores.get('average_wpm', 0)} WPM\n"
        md += f"- **Filler Words Count (Avg/30s):** {scores.get('average_filler_count', 0)}\n"
        md += f"- **Hesitation Index:** {scores.get('average_hesitation_index', 0)}/100 ({trends.get('hesitation', 'stable')})\n"

        return md

    def build_html(self, report: Optional[dict] = None) -> str:
        """
        Generate a self-contained HTML performance report with score visualisation.
        """
        if report is None:
            report = self.build()

        scores = report.get("summary_scores", {})
        trends = report.get("trends", {})
        strengths = report.get("strengths", [])
        areas = report.get("improvement_areas", [])
        overall = scores.get("overall_average", 0)
        mode = report.get("mode", "interview").title()
        duration = int(report.get("duration_seconds", 0))
        generated_at = report.get("generated_at", "")
        timeline = report.get("score_timeline", [])

        # Colour based on score tier
        if overall >= 85:
            gauge_color = "#22c55e"  # green
            tier_label = "Excellent"
        elif overall >= 70:
            gauge_color = "#3b82f6"  # blue
            tier_label = "Solid"
        elif overall >= 55:
            gauge_color = "#f59e0b"  # amber
            tier_label = "Developing"
        else:
            gauge_color = "#ef4444"  # red
            tier_label = "Needs Work"

        def trend_badge(t: str) -> str:
            icons = {"improving": ("▲", "#22c55e"), "declining": ("▼", "#ef4444"), "stable": ("●", "#94a3b8")}
            icon, color = icons.get(t, ("●", "#94a3b8"))
            return f'<span style="color:{color};font-size:0.75rem;font-weight:600">{icon} {t.capitalize()}</span>'

        def score_card(label: str, value, trend_key: str = "") -> str:
            v = round(float(value), 0) if value else 0
            pct = min(100, max(0, v))
            bar_color = gauge_color if pct >= 70 else ("#f59e0b" if pct >= 50 else "#ef4444")
            td = f"<br>{trend_badge(trends.get(trend_key, 'stable'))}" if trend_key else ""
            return f"""
            <div class="card">
              <div class="card-label">{label}</div>
              <div class="card-score">{v:.0f}<span style="font-size:1rem;color:#94a3b8">/100</span></div>
              <div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{bar_color}"></div></div>
              {td}
            </div>"""

        # Timeline chart data
        chart_points = ""
        if timeline:
            max_elapsed = max(p.get("elapsed", 1) for p in timeline) or 1
            max_score = 100
            pts = []
            for p in timeline:
                x = round(p.get("elapsed", 0) / max_elapsed * 560, 1)
                y = round((1 - p.get("score", 0) / max_score) * 140, 1)
                pts.append(f"{x},{y}")
            chart_points = " ".join(pts)

        strengths_html = "".join(
            f'<li>✅ {s}</li>' for s in strengths
        ) or "<li>Keep practising — strengths will emerge over longer sessions.</li>"

        areas_html = "".join(
            f'<li>🎯 {a}</li>' for a in areas
        ) or "<li>Great work — no major areas for improvement identified.</li>"

        minutes, seconds = divmod(duration, 60)
        duration_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

        # Gauge: SVG circle
        circumference = 2 * 3.14159 * 54
        dash_offset = circumference * (1 - overall / 100)

        wpm = scores.get("average_wpm", 0)
        fillers = scores.get("average_filler_count", 0)
        hesitation = scores.get("average_hesitation_index", 0)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Session Report — {mode} Coach</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:2rem 1rem}}
  .container{{max-width:860px;margin:0 auto}}
  header{{text-align:center;margin-bottom:2.5rem}}
  header h1{{font-size:1.6rem;font-weight:800;letter-spacing:-0.5px;color:#f8fafc}}
  header p{{color:#94a3b8;font-size:0.9rem;margin-top:0.4rem}}
  .hero{{display:flex;align-items:center;justify-content:center;gap:3rem;background:#1e293b;border-radius:1.25rem;padding:2rem 2.5rem;margin-bottom:2rem;flex-wrap:wrap}}
  .gauge-wrap{{text-align:center}}
  .gauge-wrap svg{{display:block;margin:0 auto}}
  .gauge-label{{margin-top:0.5rem;font-size:0.85rem;color:#94a3b8}}
  .gauge-tier{{font-size:1.1rem;font-weight:700;color:{gauge_color}}}
  .hero-meta{{text-align:left}}
  .hero-meta h2{{font-size:1.05rem;font-weight:700;color:#f1f5f9;margin-bottom:0.75rem}}
  .meta-row{{display:flex;gap:0.5rem;align-items:center;color:#94a3b8;font-size:0.85rem;margin-bottom:0.3rem}}
  .meta-row strong{{color:#e2e8f0}}
  .section-title{{font-size:1rem;font-weight:700;margin-bottom:1rem;color:#f1f5f9}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:1rem;margin-bottom:2rem}}
  .card{{background:#1e293b;border-radius:1rem;padding:1rem 1.1rem}}
  .card-label{{font-size:0.75rem;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem}}
  .card-score{{font-size:1.6rem;font-weight:800;color:#f8fafc;line-height:1;margin-bottom:0.5rem}}
  .bar-bg{{background:#334155;border-radius:99px;height:5px;overflow:hidden}}
  .bar-fill{{height:100%;border-radius:99px;transition:width 0.8s ease}}
  .speech-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:2rem}}
  .stat-box{{background:#1e293b;border-radius:1rem;padding:1rem;text-align:center}}
  .stat-value{{font-size:1.5rem;font-weight:800;color:#f8fafc}}
  .stat-unit{{font-size:0.75rem;color:#94a3b8;margin-top:0.2rem}}
  .lists{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:2rem}}
  .list-box{{background:#1e293b;border-radius:1rem;padding:1.25rem}}
  .list-box h3{{font-size:0.85rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;color:#94a3b8}}
  .list-box ul{{list-style:none;display:flex;flex-direction:column;gap:0.5rem}}
  .list-box li{{font-size:0.87rem;color:#cbd5e1;line-height:1.4}}
  .focus-box{{background:linear-gradient(135deg,#1e3a5f,#1e293b);border:1px solid #3b82f6;border-radius:1rem;padding:1.25rem 1.5rem;margin-bottom:2rem}}
  .focus-box h3{{font-size:0.8rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#60a5fa;margin-bottom:0.5rem}}
  .focus-box p{{font-size:0.92rem;color:#e2e8f0}}
  .chart-section{{background:#1e293b;border-radius:1rem;padding:1.25rem;margin-bottom:2rem}}
  .chart-section svg{{width:100%;height:160px}}
  footer{{text-align:center;color:#475569;font-size:0.78rem;margin-top:1rem}}
  @media(max-width:540px){{.lists{{grid-template-columns:1fr}}.hero{{gap:1.5rem}}.speech-stats{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🎯 {mode} Session Report</h1>
    <p>{generated_at.replace('T',' ').replace('Z',' UTC')} &nbsp;·&nbsp; Duration: {duration_str}</p>
  </header>

  <!-- Hero: gauge + meta -->
  <div class="hero">
    <div class="gauge-wrap">
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle cx="65" cy="65" r="54" fill="none" stroke="#334155" stroke-width="12"/>
        <circle cx="65" cy="65" r="54" fill="none" stroke="{gauge_color}" stroke-width="12"
          stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{dash_offset:.1f}"
          stroke-linecap="round" transform="rotate(-90 65 65)"/>
        <text x="65" y="60" text-anchor="middle" font-size="22" font-weight="800" fill="#f8fafc" font-family="Inter,sans-serif">{overall:.0f}</text>
        <text x="65" y="76" text-anchor="middle" font-size="11" fill="#94a3b8" font-family="Inter,sans-serif">/100</text>
      </svg>
      <div class="gauge-tier">{tier_label}</div>
      <div class="gauge-label">Overall Score</div>
    </div>
    <div class="hero-meta">
      <h2>Session Summary</h2>
      <div class="meta-row"><strong>Mode:</strong>&nbsp;{mode}</div>
      <div class="meta-row"><strong>Duration:</strong>&nbsp;{duration_str}</div>
      <div class="meta-row"><strong>Snapshots:</strong>&nbsp;{report.get('snapshot_count', 0)}</div>
      <div class="meta-row"><strong>Overall Trend:</strong>&nbsp;{trend_badge(trends.get('overall_score','stable'))}</div>
    </div>
  </div>

  <!-- Score cards -->
  <div class="section-title">Score Breakdown</div>
  <div class="cards">
    {score_card("Clarity", scores.get("clarity", 0), "clarity")}
    {score_card("Structure", scores.get("structure", 0))}
    {score_card("Confidence", scores.get("confidence_language", 0), "confidence")}
    {score_card("Body Language", scores.get("confidence_body", 0), "body_language")}
    {score_card("Engagement", scores.get("engagement", 0))}
  </div>

  <!-- Speech stats -->
  <div class="section-title">Speech Metrics</div>
  <div class="speech-stats">
    <div class="stat-box">
      <div class="stat-value">{wpm:.0f}</div>
      <div class="stat-unit">WPM (avg)</div>
    </div>
    <div class="stat-box">
      <div class="stat-value">{fillers:.1f}</div>
      <div class="stat-unit">Filler words / 30s</div>
    </div>
    <div class="stat-box">
      <div class="stat-value">{hesitation:.0f}</div>
      <div class="stat-unit">Hesitation index {trend_badge(trends.get('hesitation','stable'))}</div>
    </div>
  </div>"""

        # Score timeline chart (only if we have data)
        if timeline and chart_points:
            html += f"""
  <div class="chart-section">
    <div class="section-title" style="margin-bottom:0.75rem">Score Timeline</div>
    <svg viewBox="0 0 580 150" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{gauge_color}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="{gauge_color}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <!-- Grid lines -->
      <line x1="0" y1="35" x2="560" y2="35" stroke="#334155" stroke-width="1" stroke-dasharray="4"/>
      <line x1="0" y1="70" x2="560" y2="70" stroke="#334155" stroke-width="1" stroke-dasharray="4"/>
      <line x1="0" y1="105" x2="560" y2="105" stroke="#334155" stroke-width="1" stroke-dasharray="4"/>
      <text x="565" y="38" fill="#475569" font-size="9" font-family="Inter,sans-serif">75</text>
      <text x="565" y="73" fill="#475569" font-size="9" font-family="Inter,sans-serif">50</text>
      <text x="565" y="108" fill="#475569" font-size="9" font-family="Inter,sans-serif">25</text>
      <!-- Fill area -->
      <polygon points="{chart_points} 560,140 0,140" fill="url(#lg)"/>
      <!-- Line -->
      <polyline points="{chart_points}" fill="none" stroke="{gauge_color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
    </svg>
  </div>"""

        html += f"""
  <!-- Strengths and improvements -->
  <div class="lists">
    <div class="list-box">
      <h3>Strengths</h3>
      <ul>{strengths_html}</ul>
    </div>
    <div class="list-box">
      <h3>Areas for Improvement</h3>
      <ul>{areas_html}</ul>
    </div>
  </div>

  <!-- Next session focus -->
  <div class="focus-box">
    <h3>🎯 Next Session Focus</h3>
    <p>{report.get('next_session_focus', 'Keep practising — you are performing at a high level.')}</p>
  </div>

  <footer>Visions AI Coach &nbsp;·&nbsp; Session {report.get('session_id','')} &nbsp;·&nbsp; {generated_at}</footer>
</div>
</body>
</html>"""
        return html

    def save(self, report: Optional[dict] = None) -> Path:
        """
        Save the report JSON and HTML to reports/<session_id>.{json,html,md}.
        Opens the HTML report in the default browser automatically.
        Returns the path to the JSON file.
        """
        if report is None:
            report = self.build()

        REPORTS_DIR.mkdir(exist_ok=True)
        json_path = REPORTS_DIR / f"{self.session_id}.json"
        md_path   = REPORTS_DIR / f"{self.session_id}.md"
        html_path = REPORTS_DIR / f"{self.session_id}.html"

        # ── JSON ───────────────────────────────────────────
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Session JSON report saved to {json_path}")

        # ── Markdown (saved for reference, not auto-opened) ─
        markdown_content = self.build_markdown(report)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info(f"Session Markdown report saved to {md_path}")

        # ── HTML (auto-opened in browser) ──────────────────
        html_content = self.build_html(report)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"Session HTML report saved to {html_path}")

        try:
            webbrowser.open(html_path.absolute().as_uri())
            logger.info(f"Opened HTML report in browser: {html_path}")
        except Exception as e:
            logger.error(f"Failed to auto-open HTML report: {e}")

        return json_path
