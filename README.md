# Kaomoji picker

A tray app: **Ctrl+Alt+K** in any program opens a search box at the mouse. Type a mood or a thing (`shrug`, `happy cry`, `angry cat`, `tableflip`), then pick with **1-9**, **↑↓ + Enter** or a click, and it's pasted where you were typing. **Esc** closes it. The ones you use most rank higher.

**Suggestions:** before you type a search, it suggests kaomoji for the message you're in the middle of. "omg im so tired lol" opens on laughs, sleepy faces and a shocked one, with the matched words in the footer (`for: omg, tired, lol`). The last words count most, and the first 9 mix moods. Chat slang is mapped to moods in `SLANG` in `kaomoji.py`; any other word is matched against the tags in `kaomoji.txt`. With no matches it shows your recent ones. To know what you typed, it keeps your letters since your last Enter, in memory only: never saved or logged, and wiped on Enter, Tab, Esc, a window switch or 5 minutes of no typing. That buffer also sees what you type into password boxes (until Enter); `"suggest": false` in `config.json` turns all of it off.

- **Run it:** double-click `kaomoji.cmd` (no console; a blue `^ω^` icon appears in the tray). Right-click the icon to edit the list or quit. Left-click picks one and only copies it, since there's no window to paste into.
- **Start with Windows:** run `install_startup.ps1` once. To undo it, delete `Kaomoji picker.lnk` from `shell:startup`.
- **Change the hotkey:** `config.json`, e.g. `"ctrl+shift+k"`, `"win+alt+k"`, `"ctrl+alt+f9"`, then quit and restart it. Ctrl+Alt is AltGr on your Czech layout, so Ctrl+Alt+K means AltGr+K (ł) can't be typed while it runs. `"mode": "type"` sends the kaomoji as keystrokes instead of pasting.
- **Add kaomoji:** `kaomoji.txt`. The format is in its header. Changes are picked up the next time the picker opens.

How it works: the hotkey is `RegisterHotKey` on its own thread. Paste saves the clipboard text, pastes with Ctrl+V and puts the text back 0.6 s later (unless something new was copied meanwhile). If the clipboard holds an image or files, it types the kaomoji instead so they aren't lost. Nothing is pasted into programs running as admin (Windows blocks it); use the tray copy there.

`python kaomoji.py --search happy cat` prints the ranking without opening anything, and `--suggest omg im so tired lol` prints the suggestions. `--selftest` opens the picker for a second. `KAOMOJI_DEBUG=1` logs every show, key and paste to `kaomoji.log`.

Possible next step: sending the typed line to a free OpenRouter model so it reads the tone ("failed my exam lmao" wants a nervous laugh, which keywords can't see).
