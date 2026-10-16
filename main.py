"""
FileFlow — Smart File Organization System
CLI Entrypoint demonstrating Phase 1 Core Engine:
- Scanning
- Extension-based categorization
- Configurable rules evaluation
- Dry-run preview planning
- Safe file organization
- Safe undo & SQLite history
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from fileflow.core.classifier import FileClassifier
from fileflow.core.logger import get_logger, setup_logger
from fileflow.core.models import CollisionPolicy
from fileflow.core.organizer import SafeFileOrganizer
from fileflow.core.planner import OrganizationPlanner
from fileflow.core.rules import RuleEngine
from fileflow.core.scanner import FileScanner
from fileflow.core.undo import JobHistoryManager, UndoManager
from scripts.generate_samples import generate_sample_files

setup_logger()
logger = get_logger("fileflow.cli")

BANNER = r"""
  ______ _ _      ______ _               
 |  ____(_) |    |  ____| |              
 | |__   _| | ___| |__  | | _____      __
 |  __| | | |/ _ \  __| | |/ _ \ \ /\ / /
 | |    | | |  __/ |    | | (_) \ V  V / 
 |_|    |_|_|\___|_|    |_|\___/ \_/\_/  
       Smart File Organization System
"""


def format_bytes(size: int) -> str:
    """Format byte size into human readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def run_cli():
    print(BANNER)
    parser = argparse.ArgumentParser(description="FileFlow — Smart File Organization System")
    parser.add_argument(
        "folder",
        nargs="?",
        default="sample_files",
        help="Folder to scan and organize (default: sample_files)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview operations without moving files (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute organization after preview",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subfolders recursively",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Generate realistic test files in the specified directory before scanning",
    )
    parser.add_argument(
        "--undo-last",
        action="store_true",
        help="Undo the most recent organization job",
    )

    args = parser.parse_args()

    history = JobHistoryManager()
    undo_mgr = UndoManager(history_manager=history)

    # Handle Undo request
    if args.undo_last:
        jobs = history.list_jobs(limit=1)
        if not jobs:
            print("No previous jobs found in history.")
            return
        last_job = jobs[0]
        print(f"\n[UNDO] Found most recent job: {last_job.job_id} ({last_job.source_folder})")
        preview = undo_mgr.create_undo_preview(last_job.job_id)
        print(f"Eligible to restore: {preview.safe_count} files | Ineligible: {preview.unsafe_count} files")
        for op in preview.operations:
            status_text = "[OK]" if op.can_restore else f"[BLOCKED: {op.reason}]"
            print(f"  {status_text} {op.current_path.name} -> {op.restore_path}")

        confirm = input("\nProceed with undo reversal? (y/N): ").strip().lower()
        if confirm == "y":
            success, messages, restored, failed = undo_mgr.execute_undo(last_job.job_id)
            print(f"\nUndo Complete! Restored: {restored}, Failed: {failed}")
            for msg in messages:
                print(f"  {msg}")
        return

    target_dir = Path(args.folder).resolve()

    # Generate samples if requested or if sample_files is empty
    if args.generate_samples or (target_dir.name == "sample_files" and (not target_dir.exists() or not any(target_dir.iterdir()))):
        print(f"\nCreating sample test files in '{target_dir}'...")
        generate_sample_files(target_dir)

    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Target path '{target_dir}' does not exist or is not a directory.")
        sys.exit(1)

    print(f"\n[1/4] Scanning folder: {target_dir}")
    classifier = FileClassifier()
    scanner = FileScanner(classifier=classifier)
    scanned_files, errors = scanner.scan(target_dir, recursive=args.recursive)

    if errors:
        print("\nWarnings during scan:")
        for err in errors:
            print(f"  ! {err}")

    print(f"Discovered {len(scanned_files)} files.")
    if not scanned_files:
        print("Folder is empty. Nothing to organize.")
        return

    # Category Breakdown
    cat_counts = Counter(f.category for f in scanned_files)
    print("\n[2/4] Category Breakdown:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat:<15}: {count} file(s)")

    # Rule Planning
    print("\n[3/4] Evaluating rules and generating dry-run preview plan...")
    rule_engine = RuleEngine(classifier=classifier)
    planner = OrganizationPlanner(rule_engine=rule_engine, classifier=classifier)
    plan = planner.create_plan(source_folder=target_dir, scanned_files=scanned_files)

    print(f"\n{'File Name':<35} | {'Category':<13} | {'Rule':<25} | {'Destination':<28} | {'Status'}")
    print("-" * 120)

    for op in plan.operations:
        name = op.source_path.name
        if len(name) > 32:
            name = name[:29] + "..."
        cat = op.category
        rule_name = op.matched_rule_name or "Default"
        if len(rule_name) > 23:
            rule_name = rule_name[:20] + "..."
        dest = op.proposed_destination.relative_to(target_dir) if op.proposed_destination.is_relative_to(target_dir) else op.proposed_destination.name
        dest_str = str(dest)
        if len(dest_str) > 26:
            dest_str = dest_str[:23] + "..."
        status_str = op.status.value.upper()
        if op.warnings:
            status_str += " *"

        print(f"{name:<35} | {cat:<13} | {rule_name:<25} | {dest_str:<28} | {status_str}")

    print("-" * 120)
    print(f"Summary: {len(plan.operations)} operations planned | {plan.warnings_count} warning(s) | {plan.conflicts_count} conflict(s)")
    print("(*) Indicates an auto-rename or security warning (see logs for full audit).")

    if not args.execute:
        print("\n[Dry-run mode complete. No files were modified.]")
        print("To execute this plan, run with '--execute' flag or confirm below.")
        confirm = input("\nExecute organization now? (y/N): ").strip().lower()
        if confirm != "y":
            print("Operation cancelled. No files were touched.")
            return

    # Execution
    print("\n[4/4] Executing safe organization...")
    organizer = SafeFileOrganizer()

    def on_progress(cur, total, op, res):
        print(f"  [{cur}/{total}] {res.status.value.upper()}: {op.source_path.name} -> {res.destination_path.name if res.destination_path else 'N/A'}")

    job_record = organizer.execute_plan(plan, progress_callback=on_progress)
    history.save_job(job_record)

    print(f"\nOrganization Complete!")
    print(f"  Job ID    : {job_record.job_id}")
    print(f"  Status    : {job_record.status}")
    print(f"  Executed  : {job_record.total_executed}")
    print(f"  Skipped   : {job_record.total_skipped}")
    print(f"  Failed    : {job_record.total_failed}")
    print(f"\nTip: To safely revert these operations at any time, run:")
    print(f"  python main.py --undo-last")


if __name__ == "__main__":
    run_cli()
