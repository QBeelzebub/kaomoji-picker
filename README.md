# Kaomoji picker

A tray app: **Ctrl+Alt+K** in any program opens a search box at the mouse. Type a mood or a thing (`shrug`, `happy cry`, `angry cat`, `tableflip`), then pick with **1-9**, **↑↓ + Enter** or a click, and it's pasted where you were typing. **Esc** closes it. The ones you use most rank higher.

**Suggestions:** before you type a search, it suggests kaomoji for the message you're in the middle of. "omg im so tired lol" opens on laughs, sleepy faces and a shocked one, with the matched words in the footer (`for: omg, tired, lol`). Two signals are added together:
- **Tags:** your words against the tags in `kaomoji.txt`, with the last words counting most, and chat slang mapped to moods by `SLANG` in `kaomoji.py`.
- **Meaning:** a small local model (multilingual MiniLM, int8 ONNX, CPU only, ~15 ms) compares your message with each kaomoji's description, so "failed my exam", "jsem unavená" or "relieved" find the right faces with no tag in common. It's downloaded once into `model/` (116 MB); the app holds ~250 MB of RAM with it. Until it's loaded, a few seconds after start, tags work alone.

Close matches come in a new order each time it opens, and the first 9 mix moods (at most 4 from one group), so it doesn't open on the same faces every time. Typed searches use the model too: anything that means your words is listed after the tag matches. With no matches it shows your recent ones. To know what you typed, it keeps your letters since your last Enter, in memory only: never saved or logged, and wiped on Enter, Tab, Esc, a window switch or 5 minutes of no typing. That buffer also sees what you type into password boxes (until Enter); `"suggest": false` in `config.json` turns all of it off.

- **Run it:** double-click `kaomoji.cmd` (no console; a blue `^ω^` icon appears in the tray). Right-click the icon to edit the list or quit. Left-click picks one and only copies it, since there's no window to paste into.
- **Start with Windows:** run `install_startup.ps1` once. To undo it, delete `Kaomoji picker.lnk` from `shell:startup`.
- **Change the hotkey:** `config.json`, e.g. `"ctrl+shift+k"`, `"win+alt+k"`, `"ctrl+alt+f9"`, then quit and restart it. Ctrl+Alt is AltGr on your Czech layout, so Ctrl+Alt+K means AltGr+K (ł) can't be typed while it runs. `"mode": "type"` sends the kaomoji as keystrokes instead of pasting.
- **Add kaomoji:** `kaomoji.txt`. The format is in its header. Give each one a short description (what it shows, when you'd send it), since that's what the meaning model reads. Changes are picked up the next time the picker opens.

How it works: the hotkey is `RegisterHotKey` on its own thread. Paste saves the clipboard text, pastes with Ctrl+V and puts the text back 0.6 s later (unless something new was copied meanwhile). If the clipboard holds an image or files, it types the kaomoji instead so they aren't lost. Nothing is pasted into programs running as admin (Windows blocks it); use the tray copy there.

`python kaomoji.py --search happy cat` prints the ranking without opening anything, and `--suggest omg im so tired lol` prints the suggestions. `--selftest` opens the picker for a second. `KAOMOJI_DEBUG=1` logs every show, key and paste to `kaomoji.log`.

Known limit: irony. "failed my exam lmao" reads as funny, not as a nervous laugh; only an LLM would get that, and she chose fully local.
