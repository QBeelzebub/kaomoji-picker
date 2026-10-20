# Kaomoji picker

A tray app: **Ctrl+Alt+K** in any program opens a search box at the mouse. Type a mood or a thing (`shrug`, `happy cry`, `angry cat`, `tableflip`), then pick with **1-9**, **↑↓ + Enter** or a click, and it's pasted where you were typing. **Esc** closes it. An empty search shows your recent ones first, and the ones you use most rank higher.

- **Run it:** double-click `kaomoji.cmd` (no console; a blue `^ω^` icon appears in the tray). Right-click the icon to edit the list or quit. Left-click picks one and only copies it, since there's no window to paste into.
- **Start with Windows:** run `install_startup.ps1` once. To undo it, delete `Kaomoji picker.lnk` from `shell:startup`.
- **Change the hotkey:** `config.json`, e.g. `"ctrl+shift+k"`, `"win+alt+k"`, `"ctrl+alt+f9"`, then quit and restart it. Ctrl+Alt is AltGr on your Czech layout, so Ctrl+Alt+K means AltGr+K (ł) can't be typed while it runs. `"mode": "type"` sends the kaomoji as keystrokes instead of pasting.
- **Add kaomoji:** `kaomoji.txt`. The format is in its header. Changes are picked up the next time the picker opens.

How it works: the hotkey is `RegisterHotKey` on its own thread. Paste saves the clipboard text, pastes with Ctrl+V and puts the text back 0.6 s later (unless something new was copied meanwhile). If the clipboard holds an image or files, it types the kaomoji instead so they aren't lost. Nothing is pasted into programs running as admin (Windows blocks it); use the tray copy there.

`python kaomoji.py --search happy cat` prints the ranking without opening anything. `--selftest` opens the picker for a second. `KAOMOJI_DEBUG=1` logs every show, key and paste to `kaomoji.log`.

Possible next step: a second hotkey that sends the sentence you just typed to Haiku and pastes the kaomoji it picks.
