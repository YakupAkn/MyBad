# MyBad

Like every programmer, my filesystem had devolved into pure chaos: infinite folders inside folders, with files cryptically named `1` or `a`. To escape the madness, I wrote a cleanup utility... and naturally threw it right into `C:\` so I wouldn't misplace it.

**MyBad** is an AI-assisted lost-file finder. You describe the file in plain language — language, folder, what it roughly did, when you last touched it — and it turns that story into filters, scores candidates on disk, and shows you the most likely matches.

Built for the moments when you know the file *exists*, you just no longer know *where*.

## What it does

- Scans your code-ish files (Python, HTML/JS, C/C++, Arduino, and friends)
- Asks an LLM to turn your description into structured filters (`ext`, path/folder, content hints, recency, …)
- Ranks hits, shows previews, sibling files, and optional AI “what does this file do?”
- Learns from simple correct / wrong feedback over time

## Editions

| Build | Role |
|-------|------|
| **Console** | Terminal workflow, scripts, power users |
| **GUI** | Windowed UI for everyday digging |
| **Downloader** | Small helper to pick Console / GUI and fetch the release EXE |

Sources:

- `mybad.py` — core engine + console entry
- `mybad_gui.py` — Tkinter UI
- `indirme_yardimcisi.py` — download helper UI
- `build_exe.bat` — builds all three EXEs

## Quick start (from source)

```text
py mybad.py
py mybad_gui.py
```

On first run it asks for a **Groq API key** and stores it in `.env` (not committed).

Optional env:

- `MYBAD_ROOT` — scan root (default: drive root / home)
- `MYBAD_EXTS` — comma-separated extensions
- `ES_PATH` — path to Everything’s `es.exe` on Windows (much faster scans)
- `GROQ_API_KEY` — API key if you prefer env over `.env`

## Build EXEs (Windows)

```text
build_exe.bat
```

Output under `dist\`:

- `MyBad-Console.exe`
- `MyBad-GUI.exe`
- `MyBad-Indir.exe`

## Example query

> html dilinde stemdefterim klasörü içinde bir dosya

Folder hints map to `path_any`, language/extension to `ext_any`, and the rest to content / name filters as needed.

## Privacy / safety

- Your API key stays local in `.env`
- The database (`mybad2.db`) is local and gitignored
- File contents are only sent to the model when you search or ask for an explanation

---

*Named MyBad because the filesystem was, in fact, my bad.*
