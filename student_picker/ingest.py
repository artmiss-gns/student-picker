"""
student-picker: Automated Submissions Ingestion & Notebook Diffing
Analyzes student .ipynb submissions against a base exercise sheet to determine
attempted subtasks, and exports a clean roster for the picker.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_lms_xlsx(xlsx_path: Path) -> Tuple[List[str], List[List[str]]]:
    """Reads an LMS Excel export without external dependencies using zipfile and XML."""
    with zipfile.ZipFile(xlsx_path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in tree.findall("ns:si", ns):
                shared.append("".join(t.text for t in si.findall(".//ns:t", ns) if t.text))

        tree = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row in tree.findall(".//ns:row", ns):
            row_vals = []
            for c in row.findall("ns:c", ns):
                t = c.get("t")
                v = c.find("ns:v", ns)
                val = v.text if v is not None else ""
                if t == "s" and val != "":
                    try:
                        val = shared[int(val)]
                    except Exception:
                        pass
                row_vals.append(val)
            rows.append(row_vals)

    return (rows[0] if rows else []), (rows[1:] if len(rows) > 1 else [])


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_cell_modified(base_src: str, student_src: str, cell_type: str) -> bool:
    """Determines whether a student modified or answered a cell."""
    b_norm = norm_text(base_src)
    s_norm = norm_text(student_src)

    if b_norm == s_norm or not s_norm:
        return False

    # Standard blank template placeholders
    placeholders = (
        "**Answer:** *Your answer here.*",
        "*Your answer here.*",
        "**Answer:**",
        "# TODO",
        "# Put your answer here",
        "pass",
    )
    if s_norm in placeholders:
        return False

    if cell_type == "code":
        if "raise NotImplementedError" in student_src:
            # Check if actual logic was added besides NotImplementedError
            lines = [
                l for l in student_src.splitlines()
                if l.strip() and not l.strip().startswith("#")
                and "raise NotImplementedError" not in l
                and not l.strip().startswith("def ")
            ]
            if not lines:
                return False

    # Check for empty markdown tables
    if "| # |" in b_norm and "| # |" in s_norm:
        empty_rows = sum(1 for line in student_src.splitlines() if re.match(r"\|\s*\d+\s*\|\s*\|\s*\|\s*\|", line))
        if empty_rows >= 6:
            return False

    return True


def parse_subtask_sections(nb_cells: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """Groups notebook cell indices by subtask headers found in markdown."""
    subtask_cells: Dict[str, List[int]] = {}
    current_task = None

    for idx, cell in enumerate(nb_cells):
        src = "".join(cell.get("source", []))
        # Look for headers like: ## Subtask 1, ### 2(a), ## Task 3, ### Aufgabe 4
        m = re.search(r"(?:Subtask|Task|Aufgabe)\s+(\d+)", src, re.IGNORECASE)
        if not m:
            m = re.search(r"###\s+(\d+)\s*[\(\[]?[a-z]?[\)\]]?", src, re.IGNORECASE)

        if m:
            task_num = m.group(1)
            current_task = f"Subtask {task_num}"
            if current_task not in subtask_cells:
                subtask_cells[current_task] = []

        if current_task is not None:
            subtask_cells[current_task].append(idx)

    # Fallback default if no explicit headers found
    if not subtask_cells:
        subtask_cells["Subtask 1"] = list(range(len(nb_cells)))

    return subtask_cells


def analyze_student_notebook(
    student_nb_path: Path,
    base_nb_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Analyzes a student notebook against the base sheet to detect attempted subtasks."""
    if not student_nb_path.exists():
        return {"attempt_count": 0, "tasks": [], "valid": False}

    try:
        with open(student_nb_path, "r", encoding="utf-8") as f:
            student_nb = json.load(f)
        student_cells = student_nb.get("cells", [])

        if not base_nb_path or not base_nb_path.exists():
            # Heuristic fallback if no base sheet provided
            full_text = "".join("".join(c.get("source", [])) for c in student_cells)
            found = re.findall(r"(?:Subtask|Task|Aufgabe)\s+(\d+)", full_text, re.IGNORECASE)
            tasks = [f"Subtask {t}" for t in sorted(set(int(x) for x in found if x.isdigit()))]
            return {"attempt_count": len(tasks), "tasks": tasks, "valid": len(tasks) >= 2}

        with open(base_nb_path, "r", encoding="utf-8") as f:
            base_nb = json.load(f)
        base_cells = base_nb.get("cells", [])

        # Group cells by subtasks
        task_map = parse_subtask_sections(base_cells)
        attempted_tasks = []

        for task_name, cell_indices in task_map.items():
            task_done = False
            for c_idx in cell_indices:
                if c_idx >= len(base_cells) or c_idx >= len(student_cells):
                    continue

                b_cell = base_cells[c_idx]
                s_cell = student_cells[c_idx]

                b_src = "".join(b_cell.get("source", []))
                s_src = "".join(s_cell.get("source", []))
                ctype = b_cell.get("cell_type", "")

                if is_cell_modified(b_src, s_src, ctype):
                    task_done = True
                    break

            if task_done:
                attempted_tasks.append(task_name)

        # Sort tasks naturally
        def natural_key(t):
            m = re.search(r"\d+", t)
            return int(m.group(0)) if m else t

        attempted_tasks.sort(key=natural_key)
        attempt_count = len(attempted_tasks)
        return {
            "attempt_count": attempt_count,
            "tasks": attempted_tasks,
            "valid": attempt_count >= 2,
        }

    except Exception as e:
        return {"attempt_count": 0, "tasks": [], "valid": False, "error": str(e)}


def process_submissions_folder(
    submissions_file: Path,
    base_notebook: Optional[Path] = None,
    group_filter: Optional[int] = None,
    output_dir: Optional[Path] = None,
    roster_csv: Optional[Path] = None,
) -> Path:
    """Processes LMS submissions spreadsheet and student notebooks."""
    if not output_dir:
        output_dir = Path.cwd() / "submissions_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Reading submissions from: {submissions_file}")
    
    # Locate student notebook files (in nearby Abgaben/ or submissions/ folder)
    search_dirs = [
        submissions_file.parent / "Abgaben",
        submissions_file.parent / "submissions",
        submissions_file.parent.parent / "Abgaben",
        submissions_file.parent,
    ]
    notebook_map = {}
    for d in search_dirs:
        if d.exists() and d.is_dir():
            for p in glob.glob(f"{d}/**/*.ipynb", recursive=True):
                notebook_map[Path(p).name] = Path(p)

    print(f"📄 Found {len(notebook_map)} student notebook files.")

    # Read roster if provided
    roster_lookup = {}
    if roster_csv and roster_csv.exists():
        with open(roster_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";" if ";" in f.readline() else ",")
            f.seek(0)
            for row in reader:
                name = row.get("Full Name") or f"{row.get('First name', '')} {row.get('Last name', '')}".strip()
                if name:
                    roster_lookup[name.lower()] = row

    # Parse LMS spreadsheet
    _, rows = parse_lms_xlsx(submissions_file) if submissions_file.suffix.lower() == ".xlsx" else ([], [])
    if not rows and submissions_file.suffix.lower() == ".csv":
        with open(submissions_file, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)[1:]

    records = []
    for r in rows:
        if len(r) < 3:
            continue
        last = r[0].strip()
        first = r[1].strip() if len(r) > 1 else ""
        fname = r[4].strip() if len(r) > 4 else r[-1].strip()
        full_name = f"{first} {last}".strip()

        # Group filtering (if requested, e.g. group 6)
        if group_filter is not None:
            prefix = str(group_filter)
            matches_group = fname.startswith(f"{prefix}_") or fname.startswith(f"Group{prefix}") or fname.startswith(f"Gruppe{prefix}")
            is_in_roster = full_name.lower() in roster_lookup
            if not matches_group and not is_in_roster:
                continue

        nb_path = notebook_map.get(fname)
        analysis = analyze_student_notebook(nb_path, base_notebook) if nb_path else {"attempt_count": 0, "tasks": [], "valid": False}

        records.append({
            "id": f"std_{len(records)+1}",
            "full_name": full_name,
            "filename": fname,
            "subtasks_attempted": analysis["tasks"],
            "attempt_count": analysis["attempt_count"],
            "valid_submission": analysis["valid"],
            "strikes": 0,
            "has_presented": False,
            "subtask_presented": None,
            "status": "eligible",
        })

    # Save JSON
    json_path = output_dir / "submissions.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"submissions": records}, f, indent=2, ensure_ascii=False)

    # Save CSV
    csv_path = output_dir / "submissions.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Full Name", "File Name", "Subtasks Attempted", "Attempt Count", "Valid Submission"])
        for s in records:
            writer.writerow([
                s["full_name"],
                s["filename"],
                "; ".join(s["subtasks_attempted"]),
                s["attempt_count"],
                "Yes" if s["valid_submission"] else "No",
            ])

    print(f"✅ Ingest complete: {len(records)} matching students processed.")
    print(f"📄 Output saved to: {output_dir}\n")
    return output_dir
