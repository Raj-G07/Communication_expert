"""Standalone test: directly imports only performance_report to build and save the HTML."""
import sys
import os

# Patch webbrowser.open so it doesn't try to launch a browser (we'll verify file manually)
import webbrowser
_orig_open = webbrowser.open
webbrowser.open = lambda *a, **k: print(f"[TEST] webbrowser.open called with: {a}") or True

# Now import the report class
sys.path.insert(0, os.path.dirname(__file__))
from session.performance_report import PerformanceReport

snapshots = [
    {
        "elapsed_seconds": 30,
        "overall_score": 75,
        "language": {"clarity_score": 80, "structure_score": 70, "confidence_score": 60},
        "vision":   {"confidence_index": 85, "engagement_score": 90},
        "speech":   {"wpm": 130, "filler_count": 2, "hesitation_index": 15},
    },
    {
        "elapsed_seconds": 60,
        "overall_score": 85,
        "language": {"clarity_score": 85, "structure_score": 75, "confidence_score": 65},
        "vision":   {"confidence_index": 88, "engagement_score": 92},
        "speech":   {"wpm": 140, "filler_count": 1, "hesitation_index": 10},
    },
]

rg = PerformanceReport(session_id="test_session_123", mode="interview", snapshots=snapshots)
report = rg.build()
path = rg.save(report)

html_path = str(path).replace(".json", ".html")
md_path   = str(path).replace(".json", ".md")

print(f"JSON: {path} — exists={os.path.exists(path)}")
print(f"HTML: {html_path} — exists={os.path.exists(html_path)}")
print(f"MD:   {md_path} — exists={os.path.exists(md_path)}")

if os.path.exists(html_path):
    size = os.path.getsize(html_path)
    print(f"HTML file size: {size} bytes")
    with open(html_path, encoding="utf-8") as f:
        content = f.read(500)
    print(f"HTML snippet:\n{content}")
else:
    print("ERROR: HTML file was NOT created!")

# Restore
webbrowser.open = _orig_open
