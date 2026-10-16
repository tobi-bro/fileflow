"""
Generate realistic sample clutter files for testing FileFlow.
Creates a variety of documents, screenshots, audio, archives, spreadsheets, and code files.
"""

import sys
from pathlib import Path


def generate_sample_files(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        # Documents
        ("Annual_Financial_Report_2026.pdf", "PDF header sample content"),
        ("Project_Proposal.docx", "Word document content"),
        ("Meeting_Notes.txt", "Action items: 1. Deploy 2. Test"),
        ("User_Manual.rtf", "Rich text format documentation"),
        # Images & Screenshots
        ("Screenshot_2026-10-15_Dashboard.png", "PNG image bytes"),
        ("Screen Shot 2026-10-16 at 09.30.jpg", "JPEG image bytes"),
        ("company_logo.svg", "<svg><circle cx='10' cy='10' r='5'/></svg>"),
        ("banner_graphic.webp", "WEBP image data"),
        # Spreadsheets & Presentations
        ("Q3_Revenue_Breakdown.xlsx", "Excel spreadsheet data"),
        ("customer_leads_export.csv", "id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com"),
        ("Tech_Conference_Keynote.pptx", "PowerPoint presentation slides"),
        # Code & Scripts
        ("data_pipeline.py", "import os\nprint('Data pipeline running')\n"),
        ("web_component.tsx", "export const Widget = () => <div>Widget</div>;"),
        ("styles.css", "body { background: #121212; color: #fff; }"),
        # Archives
        ("project_assets_v2.zip", "ZIP compressed archive"),
        ("server_logs_backup.tar.gz", "GZ compressed tarball"),
        # Audio & Video
        ("podcast_interview_ep42.mp3", "Audio stream data"),
        ("product_demo_screencast.mp4", "Video stream data"),
        # Executables (Treated as risky)
        ("setup_updater.exe", "Executable binary (simulated)"),
        ("backup_routine.bat", "REM Batch script\n"),
        # Other / Unknown
        ("LICENSE", "MIT License text"),
        ("custom_telemetry.xyz123", "Unknown custom data payload"),
    ]

    for filename, content in samples:
        filepath = target_dir / filename
        filepath.write_text(content, encoding="utf-8")

    print(f"Generated {len(samples)} sample files in: {target_dir.resolve()}")


if __name__ == "__main__":
    out_dir = Path("sample_files") if len(sys.argv) < 2 else Path(sys.argv[1])
    generate_sample_files(out_dir)
