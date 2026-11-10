# student-picker

A simple script to pick random students for class presentations and keep track of who presented.

It has a lightweight web UI you can put on the projector (with big names and no private info like emails or IDs shown) and a quick CLI mode if you just want to draw from the terminal.

Built with Python's standard library only. No external packages needed.

---

## Features

- **Projector safe:** Shows only student names in large text. No private emails, IDs, or grades on screen.
- **Session management:** Auto-discovers existing session folders or files. Switch between tutorial sessions with one click in the header dropdown.
- **Web file loading / ingestion:** Ingest notebooks or load session files directly from the browser modal or via CLI.
- **Subtask aware:** Only draws from students who actually submitted that specific exercise task.
- **Attendance & strikes:** Record if a student passed, couldn't explain (no strike), or was absent (+1 strike).
- **Already presented warning:** Warns you if you try to draw for a subtask someone already presented.
- **Manual toggles:** You can click subtask badges (`T1`–`T4`) in the list to quickly add or remove tasks if someone asks.
- **Auto saves:** Keeps state in a file-based `session_state.json` file inside the session folder.

---

## Usage

### 1. Ingest Homework Submissions (Automatic Notebook Diffing)
If your LMS (ILIAS, Moodle, etc.) exports a spreadsheet and a folder of student Jupyter notebooks, you can automatically detect which subtasks each student answered:

```bash
student-picker ingest "Exercise_1.xlsx" --base "blank_exercise1.ipynb" --group 6
```
This compares each student's `.ipynb` against the blank sheet, checks for completed code/answers, and creates `submissions.csv` and `submissions.json`.

### 2. Run the Web Interface
```bash
# Launch the picker (automatically loads generated submissions.csv or submissions.json)
student-picker

# Or test with the built-in demo dataset
student-picker --demo
```

### 3. Terminal CLI Mode
```bash
# Draw directly in the terminal without opening a browser
student-picker submissions.csv --cli --task 1
```

---

## Keyboard shortcuts (in browser)

- `Space`: Draw random student
- `P`: Mark as passed
- `F`: Mark as failed attempt (stays in pool)
- `S`: Record strike (absent)
- `Esc`: Clear / cancel

---

## Input format

A basic CSV like this:
```csv
Full Name,Email,Subtasks Attempted
Alice Smith,alice@example.edu,"Subtask 1; Subtask 2; Subtask 3"
Bob Jones,bob@example.edu,"Subtask 1; Subtask 2"
```

Or JSON:
```json
{
  "submissions": [
    {
      "id": "1",
      "full_name": "Alice Smith",
      "subtasks_attempted": ["Subtask 1", "Subtask 2"]
    }
  ]
}
```

---

## License

MIT
