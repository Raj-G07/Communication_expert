import os
from session.performance_report import PerformanceReport

def test_report_generation():
    print("Testing PerformanceReport markdown generation...")
    # Mock some basic snapshots
    snapshots = [
        {
            "elapsed_seconds": 30,
            "overall_score": 75,
            "language": {
                "clarity_score": 80,
                "structure_score": 70,
                "confidence_score": 60,
            },
            "vision": {
                "confidence_index": 85,
                "engagement_score": 90,
            },
            "speech": {
                "wpm": 130,
                "filler_count": 2,
                "hesitation_index": 15,
            }
        },
        {
            "elapsed_seconds": 60,
            "overall_score": 85,
            "language": {
                "clarity_score": 85,
                "structure_score": 75,
                "confidence_score": 65,
            },
            "vision": {
                "confidence_index": 88,
                "engagement_score": 92,
            },
            "speech": {
                "wpm": 140,
                "filler_count": 1,
                "hesitation_index": 10,
            }
        }
    ]

    report_gen = PerformanceReport(
        session_id="test_session_123",
        mode="interview",
        snapshots=snapshots
    )
    
    # This will build the report, save the JSON, save the MD, and attempt to open it
    json_path = report_gen.save()
    
    print(f"Test completed. JSON path: {json_path}")
    md_path = str(json_path).replace(".json", ".md")
    if os.path.exists(md_path):
        print(f"Markdown file successfully created at: {md_path}")
        with open(md_path, "r", encoding="utf-8") as f:
            print("\n--- MARKDOWN CONTENT ---")
            print(f.read())
            print("------------------------\n")
    else:
        print(f"ERROR: Markdown file not found at: {md_path}")

if __name__ == "__main__":
    test_report_generation()
