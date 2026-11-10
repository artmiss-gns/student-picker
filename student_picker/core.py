"""
Core data models, session management, and drawing logic for student-picker.
Fully file-based storage with zero external dependencies.
"""

import csv
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def task_sort_key(task_str: Any) -> Tuple[int, Any]:
    """Sort key that orders subtasks numerically by first found digit, then alphabetically."""
    m = re.search(r"\d+", str(task_str))
    return (0, int(m.group(0))) if m else (1, str(task_str))


def load_submissions_data(source_path: Path) -> List[Dict[str, Any]]:
    """Loads student records from either a JSON file or a CSV spreadsheet."""
    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    if source_path.suffix.lower() == ".json":
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("submissions", data.get("students", []))

    # CSV Loading
    students = []
    with open(source_path, "r", encoding="utf-8-sig") as f:
        # Detect delimiter (; or ,)
        sample = f.read(2048)
        f.seek(0)
        delim = ";" if ";" in sample and "," not in sample else ","
        reader = csv.DictReader(f, delimiter=delim)

        for idx, row in enumerate(reader):
            name = (
                row.get("Full Name")
                or row.get("full_name")
                or row.get("Name")
                or f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
            )
            if not name:
                continue

            raw_tasks = (
                row.get("Subtasks Attempted")
                or row.get("Subtasks")
                or row.get("tasks")
                or ""
            )
            if isinstance(raw_tasks, str):
                tasks = [t.strip() for t in re.split(r"[;,]", raw_tasks) if t.strip()]
            elif isinstance(raw_tasks, list):
                tasks = raw_tasks
            else:
                tasks = []

            # Clean tasks to standard "Subtask X"
            clean_tasks = []
            for t in tasks:
                m = re.search(r"\d+", str(t))
                clean_tasks.append(f"Subtask {m.group(0)}" if m else str(t))

            clean_tasks = sorted(list(set(clean_tasks)), key=task_sort_key)

            students.append({
                "id": f"std_{idx + 1}",
                "full_name": name,
                "filename": row.get("File Name") or row.get("filename") or f"{name.replace(' ', '_').lower()}.ipynb",
                "subtasks_attempted": clean_tasks,
                "attempt_count": len(clean_tasks),
                "valid_submission": len(clean_tasks) >= 2,
                "strikes": int(row.get("Strikes", 0)),
                "has_presented": row.get("Presented", "").lower() in ("yes", "true", "1"),
                "subtask_presented": row.get("Subtask Presented") or None,
                "status": "eligible",
            })
    return students


def load_session_state(session_dir: Path) -> Dict[str, Any]:
    """Reads session_state.json from the session directory if it exists."""
    state_file = session_dir / "session_state.json"
    if not state_file.exists():
        return {"students": {}, "history": [], "custom_students": []}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"students": {}, "history": [], "custom_students": []}


def save_session_state(
    session_dir: Path,
    students: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
    custom_students: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persists presentation records, strikes, and subtasks to session_state.json."""
    session_dir.mkdir(parents=True, exist_ok=True)
    overrides = {}
    for s in students:
        overrides[s["id"]] = {
            "full_name": s.get("full_name", ""),
            "strikes": s.get("strikes", 0),
            "has_presented": s.get("has_presented", False),
            "subtask_presented": s.get("subtask_presented", None),
            "status": s.get("status", "eligible"),
            "notes": s.get("notes", ""),
            "subtasks_attempted": s.get("subtasks_attempted", []),
            "attempt_count": len(s.get("subtasks_attempted", [])),
            "valid_submission": len(s.get("subtasks_attempted", [])) >= 2,
        }

    if custom_students is None:
        existing = load_session_state(session_dir)
        custom_students = existing.get("custom_students", [])

    state_path = session_dir / "session_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "students": overrides,
                "custom_students": custom_students,
                "history": history,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def get_merged_students(base_students: List[Dict[str, Any]], session_dir: Optional[Path]) -> List[Dict[str, Any]]:
    """Merges base student submissions with local session overrides."""
    if not session_dir:
        return [dict(s) for s in base_students]
    state = load_session_state(session_dir)
    overrides = state.get("students", {})
    custom = state.get("custom_students", [])

    all_students = [dict(s) for s in base_students] + [dict(c) for c in custom]
    for s in all_students:
        sid = s["id"]
        if sid in overrides:
            s.update(overrides[sid])
        tasks = s.get("subtasks_attempted", [])
        s["attempt_count"] = len(tasks)
        s["valid_submission"] = len(tasks) >= 2

    return all_students


def get_eligible_pool(students: List[Dict[str, Any]], subtask: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filters students who are eligible to present for a given subtask."""
    eligible = []
    for s in students:
        if s.get("has_presented"):
            continue
        if s.get("status") in ("disqualified", "excused") or s.get("strikes", 0) >= 2:
            continue
        tasks = s.get("subtasks_attempted", [])
        # Rule 3: Valid submission requires attempting >= 2 subtasks
        if len(tasks) < 2:
            continue
        if subtask and subtask != "All":
            target = f"Subtask {subtask}" if str(subtask).isdigit() else subtask
            if target not in tasks:
                continue
        eligible.append(s)
    return eligible


def draw_student(students: List[Dict[str, Any]], subtask: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Selects a random eligible student from the pool."""
    pool = get_eligible_pool(students, subtask)
    if not pool:
        return None
    return random.choice(pool)


class SessionManager:
    """Manages file-based sessions on disk, auto-discovering existing session folders."""

    def __init__(self, base_dir: Path, default_session_path: Optional[Path] = None):
        self.base_dir = base_dir.resolve()
        self.sessions_dir = self.base_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.active_session_name = "default"
        self.active_data_file: Optional[Path] = None
        self.active_session_dir: Optional[Path] = None

        if default_session_path and default_session_path.exists():
            self.set_active_file(default_session_path)
        else:
            self.auto_discover_initial()

    def list_sessions(self) -> List[Dict[str, str]]:
        """Returns list of available sessions discovered on disk."""
        sessions = []
        # Check sessions_dir subfolders
        if self.sessions_dir.exists():
            for p in sorted(self.sessions_dir.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    if (p / "submissions.json").exists() or (p / "submissions.csv").exists():
                        sessions.append({"name": p.name, "path": str(p)})

        # Check root base_dir for session folders (e.g. exercise_1, exercise_2)
        for p in sorted(self.base_dir.iterdir()):
            if p.is_dir() and p != self.sessions_dir and not p.name.startswith(".") and p.name != "__pycache__":
                if (p / "submissions.json").exists() or (p / "submissions.csv").exists():
                    if not any(s["name"] == p.name for s in sessions):
                        sessions.append({"name": p.name, "path": str(p)})

        # If empty, add default / demo
        if not sessions and self.active_data_file:
            sessions.append({"name": self.active_session_name, "path": str(self.active_session_dir)})

        return sessions

    def auto_discover_initial(self):
        """Auto-discovers and sets the initial active session if available."""
        available = self.list_sessions()
        if available:
            self.set_active_session(available[0]["name"])
        else:
            # Check for submissions.json or submissions.csv in root
            root_json = self.base_dir / "submissions.json"
            root_csv = self.base_dir / "submissions.csv"
            if root_json.exists():
                self.set_active_file(root_json)
            elif root_csv.exists():
                self.set_active_file(root_csv)
            else:
                demo_file = Path(__file__).resolve().parent.parent / "demo" / "demo_roster.csv"
                if demo_file.exists():
                    self.set_active_file(demo_file, session_name="demo")

    def set_active_session(self, session_name: str) -> bool:
        """Switches active session by folder name."""
        candidates = [
            self.sessions_dir / session_name,
            self.base_dir / session_name,
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                target_file = c / "submissions.json"
                if not target_file.exists():
                    target_file = c / "submissions.csv"
                if target_file.exists():
                    self.active_session_name = session_name
                    self.active_data_file = target_file
                    self.active_session_dir = c
                    return True
        return False

    def set_active_file(self, file_path: Path, session_name: Optional[str] = None):
        """Sets active session directly from a CSV or JSON file."""
        self.active_data_file = file_path.resolve()
        name = session_name or file_path.stem
        self.active_session_name = name

        # Session dir sits in sessions/ or parent
        if file_path.parent.name in ("sessions", name):
            self.active_session_dir = file_path.parent
        else:
            self.active_session_dir = self.sessions_dir / name
        self.active_session_dir.mkdir(parents=True, exist_ok=True)

    def get_current_students(self) -> List[Dict[str, Any]]:
        """Loads and returns merged students for current active session."""
        if not self.active_data_file or not self.active_data_file.exists():
            return []
        base = load_submissions_data(self.active_data_file)
        return get_merged_students(base, self.active_session_dir)

    def save_state(self, students: List[Dict[str, Any]], history: List[Dict[str, Any]]):
        """Saves current state for active session."""
        if self.active_session_dir:
            save_session_state(self.active_session_dir, students, history)
