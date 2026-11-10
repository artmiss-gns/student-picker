# student-picker

A simple script to pick random students for class presentations and keep track of who presented.

It has a lightweight web UI you can put on the projector (with big names and no private info like emails or IDs shown) and a quick CLI mode if you just want to draw from the terminal.

Built with Python's standard library only. No external packages needed.

---

## Features

- **Projector safe:** Shows only student names in large text. No private emails, IDs, or grades on screen.
- **Subtask aware:** Only draws from students who actually submitted that specific exercise task.
- **Attendance & strikes:** Record if a student passed, couldn't explain (no strike), or was absent (+1 strike).
- **Already presented warning:** Warns you if you try to draw for a subtask someone already presented.
- **Manual toggles:** You can click subtask badges (`T1`–`T4`) in the list to quickly add or remove tasks if someone asks.
- **Auto saves:** Keeps state in a local `.session_data/session_state.json` file.

---

## Usage

You can run it directly with Python:

```bash
# Open the web interface (defaults to demo data if no file is given)
python3 -m student_picker.cli --demo

# Or pass your own CSV/JSON roster file
python3 -m student_picker.cli students.csv

# Or run directly in terminal (no browser)
python3 -m student_picker.cli students.csv --cli --task 1
```

If you install it:
```bash
pip install -e .
student-picker students.csv
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
