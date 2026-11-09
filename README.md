# ta-selector

A lightweight, projection-safe presentation selector and strike tracker for university tutorials, seminars, and lab courses.

Built with pure Python standard library (`http.server`, `json`, `csv`). No external web frameworks, node dependencies, or complex setup required.

---

## Why this exists

During university tutorial sessions where students are selected randomly to present homework solutions:
1. **Projection Safety**: Projecting an Excel spreadsheet or raw roster exposes student IDs, emails, and internal notes to the entire room. `ta-selector` renders large 44px names on a clean stage without displaying private contact info.
2. **Subtask-Specific Drawing**: Students should only be drawn for subtasks they actually submitted or attempted.
3. **Course Policy Rules**: Supports typical tutorial rules:
   - **Passed**: Student explained their solution satisfactorily (Rule 4).
   - **Failed Attempt**: Student attempted in good faith but couldn't explain (stays in the pool, no strike).
   - **Strike / Absent**: Student was called but absent without an excuse (+1 strike).
   - **Excused**: Documented medical/official absence.
4. **Already-Presented Protection**: Warns and requires confirmation before drawing a student for a subtask that has already been presented.
5. **Interactive Subtask Overrides**: Clickable subtask badges (`T1`–`T4`) in the table and on stage allow the TA to toggle submission status in real-time if a student corrects their status in class.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/artmiss-gns/ta-selector.git
cd ta-selector

# Install in editable mode
pip install -e .
```

---

## Quick Start

### 1. Run with Demo Data
Test the interface immediately without any data files:
```bash
ta-selector --demo
```
This automatically launches your browser at `http://localhost:8006` loaded with a synthetic demo roster.

### 2. Run with Your Own Roster
Pass your CSV or JSON spreadsheet:
```bash
ta-selector students.csv
```

### 3. Terminal CLI Mode
If you prefer running directly in your terminal without a browser:
```bash
# Draw for any task
ta-selector students.csv --cli

# Draw specifically for Subtask 2
ta-selector students.csv --cli --task 2
```

---

## Input Formats

### CSV Format
`ta-selector` accepts simple CSV files with the following headers:
```csv
Full Name,Email,Subtasks Attempted
Alice Smith,alice@example.edu,"Subtask 1; Subtask 2; Subtask 3"
Bob Jones,bob@example.edu,"Subtask 1; Subtask 2"
```

### JSON Format
```json
{
  "submissions": [
    {
      "id": "std_1",
      "full_name": "Alice Smith",
      "subtasks_attempted": ["Subtask 1", "Subtask 2", "Subtask 3"]
    }
  ]
}
```

---

## Keyboard Shortcuts (In-Class Presentation View)

| Key | Action |
| :--- | :--- |
| `Space` | Draw a random eligible student |
| `P` | Mark current student as **Passed** |
| `F` | Mark as **Failed Attempt** (stays in pool, no strike) |
| `S` | Record **Strike** (absent / refused) |
| `Esc` | Clear stage / dismiss warning modal |

---

## License

MIT License. Feel free to adapt for your own courses and tutorial groups.
