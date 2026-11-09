import csv
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            name = (
                row.get("Full Name")
                or row.get("full_name")
                or row.get("Name")
                or f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
            )
            if not name:
                continue

            # Parse subtasks (semicolon or comma separated)
            raw_tasks = row.get("Subtasks Attempted") or row.get("Subtasks") or row.get("tasks") or ""
            if isinstance(raw_tasks, str):
                tasks = [t.strip() for t in re.split(r"[;,]", raw_tasks) if t.strip()]
            elif isinstance(raw_tasks, list):
                tasks = raw_tasks
            else:
                tasks = []

            students.append({
                "id": f"std_{idx + 1}",
                "full_name": name,
                "filename": row.get("File Name") or row.get("filename") or f"{name.replace(' ', '_').lower()}.ipynb",
                "subtasks_attempted": tasks,
                "attempt_count": len(tasks),
                "valid_submission": len(tasks) >= 2,
                "strikes": int(row.get("Strikes", 0)),
                "has_presented": row.get("Presented", "").lower() in ("yes", "true", "1"),
                "subtask_presented": row.get("Subtask Presented") or None,
                "status": "eligible",
            })
    return students


def load_session_state(session_dir: Path) -> Dict[str, Any]:
    state_file = session_dir / "session_state.json"
    if not state_file.exists():
        return {"students": {}, "history": [], "custom_students": []}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"students": {}, "history": [], "custom_students": []}


def save_session_state(session_dir: Path, students: List[Dict[str, Any]], history: List[Dict[str, Any]], custom_students: Optional[List[Dict[str, Any]]] = None) -> None:
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
        json.dump({
            "students": overrides,
            "custom_students": custom_students,
            "history": history
        }, f, indent=2, ensure_ascii=False)


def get_merged_students(base_students: List[Dict[str, Any]], session_dir: Path) -> List[Dict[str, Any]]:
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
    eligible = []
    for s in students:
        if s.get("has_presented"):
            continue
        if s.get("status") in ("disqualified", "excused") or s.get("strikes", 0) >= 2:
            continue
        tasks = s.get("subtasks_attempted", [])
        if len(tasks) < 2:
            continue
        if subtask and subtask != "All":
            target = f"Subtask {subtask}" if str(subtask).isdigit() else subtask
            if target not in tasks:
                continue
        eligible.append(s)
    return eligible


def draw_student(students: List[Dict[str, Any]], subtask: Optional[str] = None) -> Optional[Dict[str, Any]]:
    pool = get_eligible_pool(students, subtask)
    if not pool:
        return None
    return random.choice(pool)
