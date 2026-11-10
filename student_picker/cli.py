import argparse
import sys
from pathlib import Path

from .core import draw_student, get_eligible_pool, get_merged_students, load_session_state, load_submissions_data
from .server import AppServer


def run_cli_draw(data_path: Path, session_dir: Path, subtask: str = None):
    base_students = load_submissions_data(data_path)
    students = get_merged_students(base_students, session_dir)
    state = load_session_state(session_dir)

    task_name = f"Subtask {subtask}" if subtask and str(subtask).isdigit() else subtask
    
    # Check if someone already presented
    if task_name:
        for sid, s in state.get("students", {}).items():
            if s.get("has_presented") and s.get("subtask_presented") == task_name:
                pres_name = s.get("full_name") or sid
                print(f"\n⚠️  {task_name} has already been presented by {pres_name}!")
                confirm = input(f"Select another student for {task_name} anyway? (y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Selection cancelled.")
                    return

    drawn = draw_student(students, subtask=task_name)
    if not drawn:
        target = task_name if task_name else "any subtask"
        print(f"\n❌ No eligible students remaining for {target}!")
        return

    print("\n" + "━" * 54)
    print(f"🎯 DRAWN STUDENT FOR {task_name.upper() if task_name else 'PRESENTATION'}:")
    print(f"\n      ⭐️  {drawn['full_name'].upper()}  ⭐️\n")
    print(f"   Subtasks Done: {', '.join(drawn.get('subtasks_attempted', []))}")
    print("━" * 54 + "\n")


def main():
    # Check for 'ingest' subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "ingest":
        ingest_parser = argparse.ArgumentParser(
            prog="student-picker ingest",
            description="Inspect student notebooks against a base exercise sheet to detect subtasks."
        )
        ingest_parser.add_argument("file", help="Path to LMS Excel (.xlsx) or CSV export file")
        ingest_parser.add_argument("--base", default=None, help="Path to blank teacher template notebook (.ipynb)")
        ingest_parser.add_argument("--group", type=int, default=None, help="Filter by specific tutorial group number (e.g. 6)")
        ingest_parser.add_argument("--roster", default=None, help="Official group roster CSV for cross-referencing")
        ingest_parser.add_argument("--out", default=None, help="Output directory for generated submissions files")
        
        iargs = ingest_parser.parse_args(sys.argv[2:])
        from .ingest import process_submissions_folder
        process_submissions_folder(
            submissions_file=Path(iargs.file).resolve(),
            base_notebook=Path(iargs.base).resolve() if iargs.base else None,
            group_filter=iargs.group,
            output_dir=Path(iargs.out).resolve() if iargs.out else None,
            roster_csv=Path(iargs.roster).resolve() if iargs.roster else None,
        )
        return

    parser = argparse.ArgumentParser(
        description="student-picker: Pick random students for presentations and track participation."
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to student submissions CSV or JSON file (defaults to demo data if omitted)"
    )
    parser.add_argument("--cli", action="store_true", help="Run in terminal CLI mode instead of starting Web UI")
    parser.add_argument("--task", type=str, default=None, help="Subtask number or name to draw for (e.g. 1, 2)")
    parser.add_argument("--port", type=int, default=8006, help="Web UI port (default: 8006)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch browser")
    parser.add_argument("--session-dir", type=str, default=None, help="Directory for storing session state (default: ~/.ta_selector/default)")
    parser.add_argument("--demo", action="store_true", help="Run with built-in demo roster")

    args = parser.parse_args()

    # Determine data file
    package_root = Path(__file__).resolve().parent.parent
    demo_file = package_root / "demo" / "demo_roster.csv"

    if args.demo or (not args.file and not Path("submissions.json").exists() and not Path("submissions.csv").exists()):
        data_path = demo_file
        print("💡 Using built-in demo dataset (zero real student data).")
    elif args.file:
        data_path = Path(args.file).resolve()
    elif Path("submissions.json").exists():
        data_path = Path("submissions.json").resolve()
    else:
        data_path = Path("submissions.csv").resolve()

    if not data_path.exists():
        print(f"Error: Data file not found at {data_path}")
        sys.exit(1)

    # Determine session directory
    if args.session_dir:
        session_dir = Path(args.session_dir).resolve()
    else:
        session_dir = data_path.parent / ".session_data"

    if args.cli:
        run_cli_draw(data_path, session_dir, subtask=args.task)
    else:
        server = AppServer(data_path, session_dir, port=args.port)
        server.run(auto_open=not args.no_browser)


if __name__ == "__main__":
    main()
