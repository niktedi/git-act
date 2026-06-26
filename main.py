import calendar
import os
from contextlib import asynccontextmanager
from datetime import date

import holidays
import psycopg
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

load_dotenv()

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def get_conn() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME", "calendar"),
    )


def init_db() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS day_notes (
                id SERIAL PRIMARY KEY,
                day DATE NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_day_notes_day ON day_notes (day)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Polish Holidays Calendar", lifespan=lifespan)


class NoteIn(BaseModel):
    day: date
    content: str


def days_with_notes(year: int, month: int) -> set[int]:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT day FROM day_notes WHERE day BETWEEN %s AND %s",
            (first, last),
        )
        return {row[0].day for row in cur.fetchall()}


def render_calendar() -> str:
    today = date.today()
    year, month = today.year, today.month

    pl_holidays = holidays.Poland(years=year)
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    month_name = calendar.month_name[month]
    noted = days_with_notes(year, month)

    header = "".join(f"<th>{day}</th>" for day in WEEKDAYS)

    rows = []
    for week in weeks:
        cells = []
        for index, day in enumerate(week):
            if day == 0:
                cells.append('<td class="empty"></td>')
                continue

            current = date(year, month, day)
            classes = ["day"]
            if index >= 5:
                classes.append("weekend")
            if current == today:
                classes.append("today")

            holiday_name = pl_holidays.get(current)
            label = ""
            if holiday_name:
                classes.append("holiday")
                label = f'<div class="holiday-name">{holiday_name}</div>'

            dot = '<span class="dot"></span>' if day in noted else ""
            class_attr = f' class="{" ".join(classes)}"'
            cells.append(
                f'<td{class_attr} data-day="{current.isoformat()}">'
                f'<div class="day-num">{day}</div>{label}{dot}</td>'
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")

    body = "".join(rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{month_name} {year} — Polish Holidays</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    margin: 0; padding: 2rem; background: #0d1117; color: #e6edf3;
    display: flex; flex-direction: column; align-items: center;
  }}
  h1 {{ font-weight: 600; margin: 0 0 1.5rem; }}
  table {{
    border-collapse: collapse; background: #161b22; width: min(900px, 100%);
    box-shadow: 0 4px 24px rgba(0,0,0,.5); border-radius: 12px; overflow: hidden;
  }}
  th {{ background: #21262d; color: #e6edf3; padding: .75rem; font-weight: 500; }}
  td {{
    border: 1px solid #30363d; height: 90px; width: 14.28%;
    vertical-align: top; padding: .4rem .5rem; position: relative;
  }}
  td.empty {{ background: #0d1117; }}
  td.day {{ cursor: pointer; transition: background .15s; }}
  td.day:hover {{ background: #1f2630; }}
  .day-num {{ font-weight: 600; }}
  td.weekend .day-num {{ color: #ff7b72; }}
  td.today {{ outline: 3px solid #58a6ff; outline-offset: -3px; }}
  td.holiday .day-num {{ color: #ff7b72; }}
  td.holiday {{ box-shadow: inset 0 0 0 2px #ff7b72; }}
  .holiday-name {{ font-size: .72rem; margin-top: .25rem; color: #ffa198; }}
  .dot {{
    position: absolute; right: 8px; bottom: 8px;
    width: 10px; height: 10px; border-radius: 50%; background: #2ea043;
    box-shadow: 0 0 6px #2ea043;
  }}
  .overlay {{
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6);
    align-items: center; justify-content: center; z-index: 10;
  }}
  .overlay.open {{ display: flex; }}
  .popup {{
    background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    width: min(440px, 92vw); max-height: 80vh; display: flex; flex-direction: column;
    box-shadow: 0 8px 40px rgba(0,0,0,.6);
  }}
  .popup-head {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 1rem 1.25rem; border-bottom: 1px solid #30363d;
  }}
  .popup-head h2 {{ margin: 0; font-size: 1.05rem; font-weight: 600; }}
  .close {{
    background: none; border: none; color: #8b949e; font-size: 1.4rem;
    cursor: pointer; line-height: 1;
  }}
  .tiles {{ padding: 1rem 1.25rem; overflow-y: auto; flex: 1; }}
  .tile {{
    background: #21262d; border: 1px solid #30363d; border-radius: 8px;
    padding: .6rem .75rem; margin-bottom: .6rem;
    display: flex; align-items: flex-start; gap: .5rem;
  }}
  .tile .tile-text {{ flex: 1; white-space: pre-wrap; word-break: break-word; }}
  .tile .del {{
    background: none; border: none; color: #8b949e; cursor: pointer;
    font-size: 1.1rem; line-height: 1; padding: 0 .15rem; flex-shrink: 0;
  }}
  .tile .del:hover {{ color: #ff7b72; }}
  .empty-msg {{ color: #8b949e; font-style: italic; }}
  .composer {{
    padding: 1rem 1.25rem; border-top: 1px solid #30363d;
    display: flex; flex-direction: column; gap: .6rem;
  }}
  .composer textarea {{
    width: 100%; box-sizing: border-box; resize: vertical; min-height: 64px;
    background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 8px; padding: .6rem .75rem; font: inherit;
  }}
  .composer button {{
    align-self: flex-end; background: #2ea043; color: #fff; border: none;
    border-radius: 8px; padding: .5rem 1.25rem; font: inherit; font-weight: 600;
    cursor: pointer;
  }}
  .composer button:hover {{ background: #2c974b; }}
  .composer button:disabled {{ opacity: .5; cursor: default; }}
</style>
</head>
<body>
  <h1>{month_name} {year} — Polish Holidays</h1>
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{body}</tbody>
  </table>

  <div class="overlay" id="overlay">
    <div class="popup">
      <div class="popup-head">
        <h2 id="popup-title"></h2>
        <button class="close" id="close-btn" aria-label="Close">&times;</button>
      </div>
      <div class="tiles" id="tiles"></div>
      <div class="composer">
        <textarea id="note-input" placeholder="Write a text block…"></textarea>
        <button id="add-btn">Add</button>
      </div>
    </div>
  </div>

<script>
const overlay = document.getElementById('overlay');
const tilesEl = document.getElementById('tiles');
const titleEl = document.getElementById('popup-title');
const inputEl = document.getElementById('note-input');
const addBtn = document.getElementById('add-btn');
let currentDay = null;
let currentCell = null;

function renderTiles(notes) {{
  tilesEl.innerHTML = '';
  if (!notes.length) {{
    const p = document.createElement('div');
    p.className = 'empty-msg';
    p.textContent = 'No text blocks yet.';
    tilesEl.appendChild(p);
    return;
  }}
  for (const note of notes) {{
    const tile = document.createElement('div');
    tile.className = 'tile';
    const text = document.createElement('span');
    text.className = 'tile-text';
    text.textContent = note.content;
    const del = document.createElement('button');
    del.className = 'del';
    del.title = 'Delete';
    del.textContent = '\u00d7';
    del.addEventListener('click', () => deleteNote(note.id));
    tile.appendChild(text);
    tile.appendChild(del);
    tilesEl.appendChild(tile);
  }}
}}

async function deleteNote(id) {{
  const res = await fetch('/api/notes/' + id, {{ method: 'DELETE' }});
  if (!res.ok) return;
  const list = await (await fetch('/api/notes?day=' + currentDay)).json();
  renderTiles(list);
  if (!list.length && currentCell) {{
    const dot = currentCell.querySelector('.dot');
    if (dot) dot.remove();
  }}
}}

async function openPopup(cell) {{
  currentDay = cell.dataset.day;
  currentCell = cell;
  titleEl.textContent = currentDay;
  inputEl.value = '';
  tilesEl.innerHTML = '';
  overlay.classList.add('open');
  inputEl.focus();
  const res = await fetch('/api/notes?day=' + currentDay);
  renderTiles(await res.json());
}}

function closePopup() {{
  overlay.classList.remove('open');
  currentDay = null;
  currentCell = null;
}}

async function addNote() {{
  const content = inputEl.value.trim();
  if (!content) return;
  addBtn.disabled = true;
  const res = await fetch('/api/notes', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ day: currentDay, content }}),
  }});
  addBtn.disabled = false;
  if (!res.ok) return;
  inputEl.value = '';
  const list = await (await fetch('/api/notes?day=' + currentDay)).json();
  renderTiles(list);
  if (currentCell && !currentCell.querySelector('.dot')) {{
    const dot = document.createElement('span');
    dot.className = 'dot';
    currentCell.appendChild(dot);
  }}
  inputEl.focus();
}}

document.querySelectorAll('td.day').forEach(cell => {{
  cell.addEventListener('click', () => openPopup(cell));
}});
document.getElementById('close-btn').addEventListener('click', closePopup);
overlay.addEventListener('click', e => {{ if (e.target === overlay) closePopup(); }});
addBtn.addEventListener('click', addNote);
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closePopup(); }});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(render_calendar())


@app.get("/api/notes")
def list_notes(day: date) -> JSONResponse:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, content, created_at FROM day_notes "
            "WHERE day = %s ORDER BY created_at, id",
            (day,),
        )
        notes = [
            {"id": r[0], "content": r[1], "created_at": r[2].isoformat()}
            for r in cur.fetchall()
        ]
    return JSONResponse(notes)


@app.post("/api/notes")
def add_note(note: NoteIn) -> JSONResponse:
    content = note.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content must not be empty")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO day_notes (day, content) VALUES (%s, %s) "
            "RETURNING id, created_at",
            (note.day, content),
        )
        row = cur.fetchone()
    return JSONResponse(
        {
            "id": row[0],
            "day": note.day.isoformat(),
            "content": content,
            "created_at": row[1].isoformat(),
        },
        status_code=201,
    )


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: int) -> JSONResponse:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM day_notes WHERE id = %s", (note_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="note not found")
    return JSONResponse({"deleted": note_id})


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
