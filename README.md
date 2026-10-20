# Kaomoji picker

A small Windows tray app. Press **Ctrl+Alt+K** in any text box and a picker opens at your mouse, already showing kaomoji that fit the message you're typing: a question gets `(・・?)`, "im so tired" gets `(｡-ω-)zzz`, "bruh" gets `(－‸ლ)`. Type to search instead (`shrug`, `happy cry`, `angry cat`, `tableflip`), pick with **1-9**, **↑↓ + Enter** or a click, and it's pasted where you were typing. **Esc** closes it.

Everything runs on your PC. The suggestions come from a small local model; nothing you type leaves the machine.

## Install

Windows 10 or 11, and Python 3.10 or newer. If you don't have Python, `winget install Python.Python.3.12` gets it.

1. Get the folder: `git clone` this repo, or download it as a ZIP and unzip it somewhere it can stay (it runs from there).
2. Double-click **`install.cmd`**. It makes a Python environment in `.venv`, installs the packages (~150 MB), downloads the model (116 MB), checks it works, asks whether to start with Windows, and starts the picker. A `^ω^` icon appears in the tray.

Run `install.cmd` again any time to repair or update. After a `git pull`, quit from the tray icon and start `kaomoji.cmd`.

## Using it

- **Ctrl+Alt+K** opens it. The bottom line says which moods it read from your message (`for: confused, think`). With nothing typed, it shows your recent ones.
- **Tray icon:** left-click picks one and copies it to the clipboard. Right-click to edit the list or quit.
- **`kaomoji.cmd`** starts it again if you quit it.

## Making it yours

- **`kaomoji.txt`**: the ~850 kaomoji, in groups, with tags and a short description each. The format is in its header. Changes apply the next time the picker opens.
- **`moods.txt`**: example messages for each mood. The model works out the mood of your message by comparing it with these. If a message gets the wrong mood, add a line like it under the right one, in your own words and in any language.
- **`config.json`**:
  - `"hotkey"`: e.g. `"ctrl+shift+k"`, `"win+alt+k"`, `"ctrl+alt+f9"`. Quit and restart after changing it. On layouts with AltGr (Czech, German, Polish...), Ctrl+Alt is AltGr, so Ctrl+Alt+K blocks whatever AltGr+K types.
  - `"mode": "type"` types the kaomoji as keystrokes instead of pasting it.
  - `"suggest": false` turns the suggestions off (see Privacy).

## How the suggestions work

1. **The mood.** Votes come from three places: your words that are tags in `kaomoji.txt` (chat slang like lol, ty, gn is mapped to moods by `SLANG` in `kaomoji.py`, and the last words count most); a `?`, a question word at the start, or a `!`; and the model, which compares your message by meaning with the examples in `moods.txt`.
2. **The kaomoji.** The top one to three moods share the first 9 slots (4/3/2). Within a mood the order is shuffled each time it opens, nudged toward the ones whose description fits your message and the ones you pick most.

The model is [paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) as int8 ONNX, on the CPU: about 15 ms per message, 50+ languages, and the app uses ~250 MB of RAM with it. Until it has loaded, a few seconds after start, the words and punctuation vote alone. It can't read irony: "failed my exam lmao" reads as funny.

## Privacy

To know what you're typing, the app watches your keystrokes and keeps the letters, `?` and `!` you've typed since your last Enter. It holds them in memory only: never saved, logged or sent anywhere, and wiped on Enter, Tab, Esc, a window switch or 5 minutes without typing. That also means it sees what you type into password boxes until you press Enter. Set `"suggest": false` in `config.json` if you'd rather it didn't watch at all.

Because it watches keys rather than reading the text box, it misses pasted text, edits made with the mouse or arrow keys mid-message, and autocorrect.

## Details

- **Paste:** it saves your clipboard text, pastes with Ctrl+V, and puts the text back 0.6 s later (unless you copied something new meanwhile). If the clipboard holds an image or files, it types the kaomoji instead so they aren't lost.
- **Programs running as administrator** don't accept pastes from it (Windows blocks that). Use the tray icon to copy one there.
- **Files it makes:** `usage.json` (what you picked, for the ranking), `kaomoji.log` (errors), `model/` and `.venv/`. None of them are committed.
- **Command line:** `python kaomoji.py --search happy cat` prints the search ranking, `--suggest omg im so tired lol` prints the suggestions, `--selftest` opens the picker for a second. Set `KAOMOJI_DEBUG=1` to log every show, key and paste to `kaomoji.log`.
