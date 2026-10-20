"""Kaomoji picker: a tray app with a global hotkey that works in any program.

Ctrl+Alt+K (config.json) opens a search box at the mouse. Type a mood or a thing (shrug,
happy cry, cat, tableflip), pick with 1-9, the arrows and Enter, or a click, and it's pasted
into the window you were in. Esc closes it. Before she types a search, it suggests kaomoji
from the words of the message she's in the middle of (see TypedLine), then the recent ones.

Files beside this script:
  kaomoji.txt   the list (format in its header), reread whenever it changes
  config.json   {"hotkey": "ctrl+alt+k", "mode": "paste", "suggest": true}; "mode": "type"
                sends keystrokes instead of pasting; "suggest": false stops it watching her typing
  usage.json    what was picked and when, for the ranking (local, not committed)
  kaomoji.log   errors, since pythonw has no console
  model/        the meaning model (see Semantic), downloaded on first run, not committed

python kaomoji.py                 run (kaomoji.cmd runs it under pythonw, no console)
python kaomoji.py --search WORDS  print the ranking for WORDS and exit
python kaomoji.py --suggest TEXT  print what the picker would suggest after typing TEXT
python kaomoji.py --selftest      open the picker for a moment, paste nothing, exit
"""

import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import queue
import random
import re
import sys
import threading
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
LIST_PATH = os.path.join(HERE, "kaomoji.txt")
CONFIG_PATH = os.path.join(HERE, "config.json")
USAGE_PATH = os.path.join(HERE, "usage.json")
LOG_PATH = os.path.join(HERE, "kaomoji.log")
MODEL_DIR = os.path.join(HERE, "model")
DEFAULTS = {"hotkey": "ctrl+alt+k", "mode": "paste", "suggest": True}

logging.basicConfig(filename=LOG_PATH, level=logging.DEBUG if os.environ.get("KAOMOJI_DEBUG") else logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kaomoji")


# ─── The list and the ranking ───────────────────────────────────────────────

GROUP = re.compile(r"^\[([a-z0-9-]+)\]\s*(.*)$")


class Entry:
    def __init__(self, text, order, group):
        self.text, self.order, self.group = text, order, group  # group: the first one it's listed under
        self.desc = ""
        self.tags = {}  # tag -> (from an extra?, line), which breaks ties in the ranking


def load_list(path=LIST_PATH):
    entries, by_text, group = [], {}, []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f):
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            m = GROUP.match(line)
            if m:
                group = [m.group(1)] + m.group(2).lower().split()
                continue
            text, extra, desc = (line.split("\t") + ["", ""])[:3]
            text = text.strip()
            if text not in by_text:  # the same kaomoji under two groups gets both groups' tags
                by_text[text] = Entry(text, len(entries), group[0] if group else "")
                entries.append(by_text[text])
            if desc.strip() and not by_text[text].desc:
                by_text[text].desc = desc.strip()
            # A group's own members beat members of other groups that carry the word as an extra.
            tags = by_text[text].tags
            for tag, rank in [(t, (0, n)) for t in group] + [(t, (1, n)) for t in extra.lower().split()]:
                tags[tag] = min(tags.get(tag, rank), rank)
    return entries


def word_score(word, tags):
    """(score, rank): 3 for a whole tag, 2 for the start of one, 1 for the middle of one."""
    best = (0, (0, 0))
    for tag, line in tags.items():
        if tag == word:
            s = 3
        elif tag.startswith(word):
            s = 2
        elif len(word) >= 3 and word in tag:
            s = 1
        else:
            continue
        if s > best[0] or (s == best[0] and line < best[1]):
            best = (s, line)
    return best


def search(entries, query, usage, jitter=None, semantic=None):
    """Tag matches first; then, if a semantic model is ready, whatever means the same thing."""
    jitter = jitter or {}
    words = query.lower().split()
    if not words:
        recent = sorted((e for e in entries if e.text in usage),
                        key=lambda e: -usage[e.text][1])
        seen = {e.text for e in recent}
        return recent + [e for e in entries if e.text not in seen]
    scored = []
    for e in entries:
        parts = [word_score(w, e.tags) for w in words]
        if not any(s for s, _ in parts):
            continue
        score = sum(s for s, _ in parts)
        score += 10 if all(s for s, _ in parts) else 0  # matching every word beats any partial match
        score += min(usage.get(e.text, (0, 0))[0], 20) * 0.1  # her favourites float up a little
        score += 0.5 * jitter.get(e.text, 0)  # equal matches come in a new order each time
        scored.append((-score, min(line for s, line in parts if s), e))
    scored.sort(key=lambda s: s[:2])
    results = [s[2] for s in scored]
    sims = semantic.similarities(query, entries) if semantic else None
    if sims is not None:
        seen = {e.text for e in results}
        results += [entries[i] for i in sims.argsort()[::-1][:40]
                    if sims[i] > 0.3 and entries[i].text not in seen]
    return results


# Chat words -> the tags they mean. A word not listed here is matched against the tags as it is.
# fuck and shit aren't here: she uses them as intensifiers ("fucking peak"), not as anger.
SLANG = {
    "lol": "laugh", "lmao": "laugh", "lmfao": "laugh", "rofl": "laugh", "haha": "laugh",
    "hahaha": "laugh", "hah": "laugh", "xd": "laugh", "kek": "laugh", "lul": "laugh",
    "funny": "laugh", "hilarious": "laugh",
    "ty": "thanks", "thx": "thanks", "tysm": "thanks", "thank": "thanks",
    "gn": "tired", "goodnight": "tired", "night": "tired", "eepy": "tired", "bed": "tired",
    "nap": "tired", "exhausted": "tired",
    "hi": "wave", "hii": "wave", "hey": "wave", "hello": "wave", "yo": "wave", "sup": "wave",
    "bye": "wave", "cya": "wave", "gtg": "wave", "gm": "wave", "morning": "wave",
    "omg": "surprised", "wtf": "surprised", "holy": "surprised", "whoa": "surprised", "woah": "surprised",
    "ugh": "angry", "hate": "angry", "annoying": "annoyed", "pissed": "angry", "mad": "angry",
    "furious": "angry", "bruh": "facepalm", "cringe": "facepalm", "why": "facepalm",
    "sry": "sorry", "mb": "sorry", "oops": "sorry", "apologies": "sorry",
    "ily": "love", "ilysm": "love", "luv": "love", "loved": "love", "miss": "love",
    "aww": "cute", "adorable": "cute", "cutie": "cute",
    "crying": "cry", "sob": "cry", "sobbing": "cry", "tears": "cry", "rip": "sad", "depressed": "sad",
    "idk": "shrug", "dunno": "shrug", "whatever": "shrug", "maybe": "shrug",
    "hmm": "think", "hm": "think", "wonder": "think", "thinking": "think",
    "yay": "excited", "hype": "excited", "finally": "excited", "pog": "excited", "poggers": "excited",
    "epic": "excited", "peak": "excited", "lets": "excited", "letsgo": "excited", "woo": "excited",
    "ok": "goodjob", "okay": "goodjob", "nice": "goodjob", "gg": "goodjob", "great": "goodjob",
    "yes": "yes", "yep": "yes", "yeah": "yes", "ye": "yes",
    "no": "no", "nope": "no", "nah": "no",
    "hugs": "hug", "pls": "please", "plz": "please",
    "hungry": "food", "pizza": "food", "eating": "food", "dinner": "food", "lunch": "food",
    "kitty": "cat", "meow": "cat", "doggo": "dog", "puppy": "dog",
    "ded": "dead", "dying": "dead", "kms": "dead", "died": "dead",
    "scary": "scared", "afraid": "scared", "yikes": "nervous", "awkward": "nervous",
    "gaming": "game", "playing": "game", "won": "game", "song": "music",
    "hehe": "smug", "heh": "smug", "sus": "stare", "ew": "disgust", "eww": "disgust", "gross": "disgust",
    "homework": "write", "study": "write", "studying": "write", "coffee": "drink", "tea": "drink",
}
STOP = set("a an the i im me my you your u it its is are was be to of in on at and or but so "
           "that this just like with for have has had do did not dont can will what "
           "good fuck fucking fucked shit shitty damn".split())


def suggest(entries, text, usage, jitter=None, semantic=None):
    """Rank kaomoji for what she has typed so far. Two signals: tag matches on her words
    (the last words count most, slang mapped through SLANG), and, once the model is loaded,
    how close in meaning each kaomoji's description is to the message.
    Returns (entries, the words that matched)."""
    jitter = jitter or {}
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP][-12:]
    scores, both, hits = {}, {}, []  # both: how many more words beyond the first an entry matched
    for distance, word in enumerate(reversed(words)):
        weight = 1 / (1 + 0.3 * distance)
        want = SLANG.get(word, word)
        matched = False
        for e in entries:
            best = 0
            for tag, (extra, _) in e.tags.items():
                # whole tag, or the tag is the word's stem (sleeping -> sleep, laughing -> laugh)
                if tag == want or (len(tag) >= 4 and want.startswith(tag)):
                    best = max(best, 0.6 if extra else 1.0)
            if best:
                scores[e.text] = scores.get(e.text, 0) + best * weight
                both[e.text] = both.get(e.text, -1) + 1
                matched = True
        if matched and word not in hits:
            hits.append(word)
    by_text = {e.text: e for e in entries}
    total = {t: KEYWORD_WEIGHT * (scores[t] + 0.5 * both[t]) for t in scores}  # 0.5: a sleepy cat for "cat sleeping"
    if words and semantic:
        # The model doesn't know chat slang, so it gets the meanings spelled out too.
        meant = [SLANG[w] for w in words if w in SLANG]
        sims = semantic.similarities(" ".join(text.split()[-30:] + meant), entries)
        if sims is not None:
            for e, sim in zip(entries, sims):
                if sim > SIM_FLOOR or e.text in total:
                    total[e.text] = total.get(e.text, 0) + SIM_WEIGHT * max(sim - SIM_FLOOR, 0)
            if not hits and sims.max() > SIM_FLOOR + 0.1:
                hits = ["your message"]
    for t in total:
        total[t] += min(usage.get(t, (0, 0))[0], 20) * 0.05 + 0.6 * jitter.get(t, 0)
    ranked = sorted(total, key=lambda t: (-total[t], by_text[t].order))
    # The first screen mixes moods: at most 4 from one group, so "hungry lol" isn't nine laughs.
    first, rest, per_group = [], [], {}
    for t in ranked:
        e = by_text[t]
        per_group[e.group] = per_group.get(e.group, 0) + 1
        (first if per_group[e.group] <= 4 and len(first) < 9 else rest).append(e)
    return first + rest, list(reversed(hits))


KEYWORD_WEIGHT, SIM_WEIGHT, SIM_FLOOR = 1.0, 6.0, 0.25  # tuned by hand on --suggest examples


class Semantic:
    """A small multilingual sentence-embedding model (paraphrase-multilingual-MiniLM-L12-v2,
    int8 ONNX), run locally on the CPU: 116 MB in model/, ~15 ms per message, reads Czech too.
    The whole app holds ~250 MB with it. Two things keep it there: sentencepiece instead of
    tokenizer.json (whose 250k-word vocabulary costs 250 MB in the tokenizers library), and
    onnxruntime with the graph optimiser and memory arena off. The descriptions are embedded
    once in the background; until then similarities() returns None."""

    REPO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    FILES = ("sentencepiece.bpe.model", "onnx/model_quint8_avx2.onnx")

    def __init__(self):
        self.session, self.pieces, self.entries, self.matrix = None, None, None, None
        self.lock = threading.Lock()

    def load(self):
        import glob
        import onnxruntime as ort
        import sentencepiece
        paths = []
        for name in self.FILES:
            found = glob.glob(os.path.join(MODEL_DIR, "models--*", "snapshots", "*", *name.split("/")))
            if not found:  # first run: fetch it once
                from huggingface_hub import hf_hub_download
                found = [hf_hub_download(self.REPO, name, cache_dir=MODEL_DIR)]
            paths.append(found[0])
        self.pieces = sentencepiece.SentencePieceProcessor(model_file=paths[0])
        opts = ort.SessionOptions()
        opts.enable_cpu_mem_arena = False
        opts.enable_mem_pattern = False
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        opts.intra_op_num_threads = 2
        self.session = ort.InferenceSession(paths[1], opts, providers=["CPUExecutionProvider"])

    def token_ids(self, text):
        # XLM-R ids: <s>=0, </s>=2, <unk>=3, and every sentencepiece id shifted up by one
        return [0] + [i + 1 if i else 3 for i in self.pieces.encode(text)][:126] + [2]

    def embed(self, texts):
        import numpy as np
        rows = [self.token_ids(t) for t in texts]
        width = max(len(r) for r in rows)
        ids = np.array([r + [1] * (width - len(r)) for r in rows], dtype=np.int64)  # 1 = <pad>
        mask = np.array([[1] * len(r) + [0] * (width - len(r)) for r in rows], dtype=np.int64)
        out = self.session.run(None, {"input_ids": ids, "attention_mask": mask,
                                      "token_type_ids": np.zeros_like(ids)})[0]
        v = (out * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)  # mean pooling
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def prepare(self, entries):
        try:
            import numpy as np
            with self.lock:
                if self.session is None:
                    self.load()
                texts = [e.desc or " ".join(t for t, (extra, _) in e.tags.items() if not extra)
                         for e in entries]
                matrix = np.vstack([self.embed(texts[i:i + 32]) for i in range(0, len(texts), 32)])
            self.matrix = matrix
            self.entries = entries  # set last: similarities() checks it
            log.info("meaning model ready")
        except Exception:
            log.exception("couldn't load the meaning model; suggestions use tags only")

    def similarities(self, text, entries):
        """Cosine similarity of text to each entry, or None if not ready for this list."""
        if self.entries is not entries or not text.strip():
            return None
        with self.lock:
            v = self.embed([text])[0]
        return self.matrix @ v


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        log.exception("couldn't read %s", path)
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ─── Win32: hotkey, focus, clipboard, keystrokes ────────────────────────────

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.GetForegroundWindow.restype = wt.HWND
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.VkKeyScanW.argtypes = [wt.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.OpenClipboard.argtypes = [wt.HWND]
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]
user32.GetClipboardSequenceNumber.restype = wt.DWORD
user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = wt.HMONITOR
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, CF_UNICODETEXT, GMEM_MOVEABLE, GA_ROOT = 0x312, 13, 0x2, 2
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
VK_CONTROL, VK_V = 0x11, 0x56
MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
             "shift": MOD_SHIFT, "win": MOD_WIN}


def parse_hotkey(spec):
    """'ctrl+alt+k' -> (modifier flags, virtual key)."""
    mods, vk = 0, None
    for part in spec.lower().replace(" ", "").split("+"):
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif re.fullmatch(r"f([1-9]|1\d|2[0-4])", part):
            vk = 0x6F + int(part[1:])
        elif part == "space":
            vk = 0x20
        elif len(part) == 1 and part.isascii() and part.isalnum():
            vk = ord(part.upper())
        elif len(part) == 1 and user32.VkKeyScanW(part) != -1:
            vk = user32.VkKeyScanW(part) & 0xFF
        else:
            raise ValueError(f"don't know the key {part!r} in hotkey {spec!r}")
    if vk is None or not mods:
        raise ValueError(f"hotkey {spec!r} needs a modifier and a key, like ctrl+alt+k")
    return mods | MOD_NOREPEAT, vk


VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE, VK_SPACE = 0x08, 0x09, 0x0D, 0x1B, 0x20
WH_KEYBOARD_LL, WM_KEYDOWN, WM_SYSKEYDOWN, LLKHF_INJECTED, LLKHF_ALTDOWN = 13, 0x100, 0x104, 0x10, 0x20


class TypedLine:
    """The letters she has typed since her last Enter, so the picker can guess from them.
    Memory only: never saved or logged. Cleared on Enter, Tab, Esc, a window switch, and
    after 5 minutes without typing. Ctrl+A/V/X/Z clear it too, since the text changed unseen."""

    def __init__(self):
        self.chars, self.window, self.last = [], None, 0.0

    def key(self, vk, char, ctrl, alt, window, now):
        if window != self.window or now - self.last > 300:
            self.chars.clear()
        self.window, self.last = window, now
        if vk in (VK_RETURN, VK_TAB, VK_ESCAPE):
            self.chars.clear()
        elif ctrl or alt:  # shortcuts, and AltGr (Ctrl+Alt) characters
            if ctrl and not alt and vk == VK_BACK:
                text = "".join(self.chars).rstrip()
                self.chars = list(text[:len(text) - len(text.split(" ")[-1])])
            elif ctrl and not alt and vk in (0x41, 0x56, 0x58, 0x5A):
                self.chars.clear()
        elif vk == VK_BACK:
            if self.chars:
                self.chars.pop()
        elif vk == VK_SPACE or (char and not char.isalpha()):
            self.chars.append(" ")
        elif char:
            self.chars.append(char)
        del self.chars[:-200]

    def text(self):
        return "".join(self.chars)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = wt.HKL
user32.MapVirtualKeyExW.argtypes = [wt.UINT, wt.UINT, wt.HKL]
user32.MapVirtualKeyExW.restype = wt.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE


def key_char(vk, window):
    """The plain letter a key types in that window's layout, without accents (č -> c).
    MapVirtualKeyEx, unlike ToUnicode, leaves the dead-key state alone, so her typing is untouched."""
    import unicodedata
    layout = user32.GetKeyboardLayout(user32.GetWindowThreadProcessId(window, None) if window else 0)
    mapped = user32.MapVirtualKeyExW(vk, 2, layout)  # MAPVK_VK_TO_CHAR
    if not mapped or mapped & 0x80000000:  # nothing, or a dead key
        return None
    return unicodedata.normalize("NFD", chr(mapped & 0xFFFF).lower())[0]


def hotkey_loop(mods, vk, events, registered, watch_typing):
    """Own thread: the hotkey and the keyboard hook both belong to the thread that pumps
    their messages, and sharing it means the typed line needs no lock."""
    registered["ok"] = bool(user32.RegisterHotKey(None, 1, mods, vk))
    registered["done"].set()
    if not registered["ok"]:
        return
    typed = TypedLine()

    def on_key(code, wparam, lparam):
        if code == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not kb.flags & LLKHF_INJECTED:  # skip what this app types itself
                try:
                    window = user32.GetForegroundWindow()
                    ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                    typed.key(kb.vkCode, key_char(kb.vkCode, window), ctrl,
                              bool(kb.flags & LLKHF_ALTDOWN), window, time.monotonic())
                except Exception:
                    log.exception("keyboard hook")
        return user32.CallNextHookEx(None, code, wparam, lparam)

    hook_proc = HOOKPROC(on_key)  # kept referenced for as long as the loop runs
    if watch_typing and not user32.SetWindowsHookExW(WH_KEYBOARD_LL, hook_proc,
                                                     kernel32.GetModuleHandleW(None), 0):
        log.error("couldn't watch typing (error %d); suggestions are off", ctypes.get_last_error())
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if msg.message == WM_HOTKEY:
            window = user32.GetForegroundWindow()
            events.put(("show", (window, typed.text() if typed.window == window else "")))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):  # only here so the union has its real size
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send_keys(keys):
    """keys: list of (vk, scan, flags)."""
    arr = (INPUT * len(keys))()
    for i, (vk, scan, flags) in enumerate(keys):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    user32.SendInput(len(keys), arr, ctypes.sizeof(INPUT))


def type_text(text):
    units = text.encode("utf-16-le")
    keys = []
    for i in range(0, len(units), 2):
        unit = int.from_bytes(units[i:i + 2], "little")
        keys += [(0, unit, KEYEVENTF_UNICODE), (0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    send_keys(keys)


def press_ctrl_v():
    send_keys([(VK_CONTROL, 0, 0), (VK_V, 0, 0), (VK_V, 0, KEYEVENTF_KEYUP),
               (VK_CONTROL, 0, KEYEVENTF_KEYUP)])


def open_clipboard():
    for _ in range(10):  # another program can be holding it for a moment
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def clipboard_read():
    """('text', str), ('empty', None), ('other', None) for images and files, or None."""
    if not open_clipboard():
        return None
    try:
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            ptr = kernel32.GlobalLock(handle) if handle else None
            if not ptr:
                return None
            try:
                return ("text", ctypes.wstring_at(ptr))
            finally:
                kernel32.GlobalUnlock(handle)
        return ("empty", None) if user32.CountClipboardFormats() == 0 else ("other", None)
    finally:
        user32.CloseClipboard()


def clipboard_write(text):
    data = text.encode("utf-16-le") + b"\0\0"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not open_clipboard():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # the clipboard owns the memory now
    finally:
        user32.CloseClipboard()


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD)]


def work_area_at(x, y):
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromPoint(wt.POINT(x, y), 2), ctypes.byref(info))
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


def force_foreground(hwnd):
    """Windows only lets the foreground process hand focus over; borrow its input queue."""
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    mine = kernel32.GetCurrentThreadId()
    theirs = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True))
    try:
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(mine, theirs, False)


# ─── The picker window ──────────────────────────────────────────────────────

BG, FIELD, TEXT, DIM, SELECT, EDGE = "#1e1f22", "#2b2d31", "#dbdee1", "#8e9297", "#404249", "#5865f2"
ROWS, SHOWN = 9, 300


class Picker:
    def __init__(self, root, config, events):
        self.root, self.config, self.events = root, config, events
        self.entries, self.list_mtime = [], None
        self.usage = load_json(USAGE_PATH, {})
        self.results, self.target = [], None
        self.suggested, self.hits, self.jitter = [], [], {}
        self.semantic = Semantic()

        top = self.top = tk.Toplevel(root, bg=EDGE, padx=1, pady=1)
        top.withdraw()
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        body = tk.Frame(top, bg=BG, padx=8, pady=8)
        body.pack(fill="both", expand=True)

        self.query = tk.StringVar()
        self.field = tk.Entry(body, textvariable=self.query, font=("Segoe UI", 12), bg=FIELD,
                              fg=TEXT, insertbackground=TEXT, relief="flat", width=34)
        self.field.pack(fill="x", ipady=5)
        self.list = tk.Listbox(body, height=ROWS, font=("Segoe UI", 14), bg=BG, fg=TEXT,
                               selectbackground=SELECT, selectforeground="#ffffff",
                               activestyle="none", highlightthickness=0, borderwidth=0,
                               exportselection=False, takefocus=0)
        self.list.pack(fill="both", expand=True, pady=(6, 4))
        self.footer = tk.Label(body, font=("Segoe UI", 9), bg=BG, fg=DIM, anchor="w")
        self.footer.pack(fill="x")

        self.query.trace_add("write", lambda *_: self.refresh())
        for seq, fn in [("<Escape>", lambda e: self.hide()),
                        ("<Return>", lambda e: self.pick_index(self.selected())),
                        ("<KP_Enter>", lambda e: self.pick_index(self.selected())),
                        ("<Down>", lambda e: self.move(1)), ("<Up>", lambda e: self.move(-1)),
                        ("<Next>", lambda e: self.move(ROWS)), ("<Prior>", lambda e: self.move(-ROWS)),
                        ("<Control-BackSpace>", self.delete_word), ("<Key>", self.number_key)]:
            self.field.bind(seq, fn)
        self.list.bind("<ButtonRelease-1>", lambda e: self.pick_index(self.list.nearest(e.y)))
        top.bind("<FocusOut>", lambda e: root.after(150, self.hide_if_unfocused))
        self.reload_if_changed()  # loads the meaning model now, not on the first hotkey

    # --- data ---

    def reload_if_changed(self):
        try:
            mtime = os.path.getmtime(LIST_PATH)
            if mtime != self.list_mtime:
                self.entries, self.list_mtime = load_list(), mtime
                threading.Thread(target=self.semantic.prepare, args=(self.entries,), daemon=True).start()
        except (OSError, UnicodeDecodeError):
            log.exception("couldn't read the kaomoji list")

    def refresh(self):
        results = search(self.entries, self.query.get(), self.usage, self.jitter, self.semantic)
        if self.suggested and not self.query.get().strip():
            seen = {e.text for e in self.suggested}
            results = self.suggested + [e for e in results if e.text not in seen]
        self.results = results[:SHOWN]
        self.list.delete(0, "end")
        for i, e in enumerate(self.results):
            self.list.insert("end", f" {i + 1}    {e.text}" if i < ROWS else f"       {e.text}")
        if self.results:
            self.list.selection_set(0)
            self.list.see(0)
        if not self.results:
            self.footer.config(text="Nothing matches. Try another word, or add it to kaomoji.txt")
        else:
            if self.query.get().strip():
                what = f"{len(self.results)} found"
            elif self.suggested:  # the matched words only, never the typed text itself
                what = "for: " + ", ".join(self.hits[-4:])
            else:
                what = "recent first"
            self.footer.config(text=f"{what}    1-9 or Enter to pick, Esc to close")

    # --- keys ---

    def selected(self):
        sel = self.list.curselection()
        return sel[0] if sel else 0

    def move(self, step):
        if self.results:
            i = max(0, min(len(self.results) - 1, self.selected() + step))
            self.list.selection_clear(0, "end")
            self.list.selection_set(i)
            self.list.see(i)
        return "break"

    def number_key(self, event):
        # By key code, not character: on her Czech layout the top row types ěščř, not digits.
        log.debug("key %r code %#x state %#x", event.char, event.keycode, event.state)
        if event.state & 0x4:  # Ctrl held
            return None
        for base in (0x30, 0x60):  # top row, numpad
            if base + 1 <= event.keycode <= base + 9:
                self.pick_index(event.keycode - base - 1)
                return "break"
        return None

    def delete_word(self, event):
        text, cur = self.query.get(), self.field.index("insert")
        start = len(text[:cur].rstrip()) - len(text[:cur].rstrip().split(" ")[-1])
        self.field.delete(start, cur)
        return "break"

    # --- showing and picking ---

    def show(self, target, typed=""):
        self.target = target
        self.reload_if_changed()
        rnd = random.Random()
        self.jitter = {e.text: rnd.random() for e in self.entries}
        self.suggested, self.hits = suggest(self.entries, typed, self.usage, self.jitter, self.semantic)
        self.query.set("")
        self.refresh()
        top = self.top
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        left, up, right, down = work_area_at(pt.x, pt.y)
        x = max(left, min(pt.x - 24, right - w))
        y = pt.y + 18 if pt.y + 18 + h <= down else max(up, pt.y - 18 - h)
        top.geometry(f"+{x}+{y}")
        top.deiconify()
        top.lift()
        top.update()
        me = user32.GetAncestor(top.winfo_id(), GA_ROOT)
        force_foreground(me)
        top.focus_force()
        self.field.focus_set()
        log.debug("show: target %s, picker %s, foreground %s", target, me, user32.GetForegroundWindow())

    def hide(self):
        self.top.withdraw()

    def hide_if_unfocused(self):
        if self.top.winfo_viewable() and self.root.focus_get() is None:
            log.debug("hide: lost focus to %s", user32.GetForegroundWindow())
            self.hide()

    def pick_index(self, i):
        if not 0 <= i < len(self.results):
            return "break"
        text = self.results[i].text
        log.debug("pick %d: %s", i, text)
        self.hide()
        count = self.usage.get(text, (0, 0))[0]
        self.usage[text] = [count + 1, time.time()]
        try:
            save_json(USAGE_PATH, self.usage)
        except OSError:
            log.exception("couldn't save usage")
        self.root.after(10, lambda: self.deliver(text, self.target, 0))
        return "break"

    def deliver(self, text, target, tries):
        if not target or not user32.IsWindow(target):
            clipboard_write(text)  # opened from the tray: nowhere to paste, so just copy it
            return
        if user32.GetForegroundWindow() != target:
            force_foreground(target)
            if tries < 10:
                self.root.after(30, lambda: self.deliver(text, target, tries + 1))
                return
            log.warning("couldn't give focus back to the window; pasting anyway")
        log.debug("deliver: foreground %s after %d tries", user32.GetForegroundWindow(), tries)
        self.root.after(30, lambda: self.send(text))

    def send(self, text):
        if self.config.get("mode") == "type":
            type_text(text)
            return
        saved = clipboard_read()
        if saved is None or saved[0] == "other" or not clipboard_write(text):
            type_text(text)  # an image or files on the clipboard: type it rather than lose them
            return
        mark = user32.GetClipboardSequenceNumber()
        press_ctrl_v()
        if saved[0] == "text":
            def restore():
                if user32.GetClipboardSequenceNumber() == mark:  # she hasn't copied anything since
                    clipboard_write(saved[1])
            self.root.after(600, restore)


# ─── Tray icon and startup ──────────────────────────────────────────────────

def make_tray(events):
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(88, 101, 242, 255))
    try:
        font = ImageFont.truetype("segoeuib.ttf", 30)
        draw.text((32, 34), "^ω^", font=font, fill="white", anchor="mm")
    except OSError:
        draw.ellipse((18, 22, 26, 30), fill="white")
        draw.ellipse((38, 22, 46, 30), fill="white")
        draw.arc((20, 28, 44, 48), 20, 160, fill="white", width=4)
    menu = pystray.Menu(
        pystray.MenuItem("Pick one (copies it)", lambda: events.put(("show", (None, ""))), default=True),
        pystray.MenuItem("Edit the list", lambda: os.startfile(LIST_PATH)),
        pystray.MenuItem("Quit", lambda: events.put(("quit", None))))
    return pystray.Icon("kaomoji", img, "Kaomoji picker", menu)


def show_error(text):
    log.error(text)
    ctypes.windll.user32.MessageBoxW(None, text, "Kaomoji picker", 0x10)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--suggest"]:
        sys.stdout.reconfigure(encoding="utf-8")
        entries, semantic = load_list(), Semantic()
        semantic.prepare(entries)
        found, hits = suggest(entries, " ".join(args[1:]), load_json(USAGE_PATH, {}), semantic=semantic)
        print("matched:", ", ".join(hits) or "nothing")
        for e in found[:9]:
            print(e.text)
        return
    if args[:1] == ["--search"]:
        sys.stdout.reconfigure(encoding="utf-8")
        usage = load_json(USAGE_PATH, {})
        for e in search(load_list(), " ".join(args[1:]), usage)[:15]:
            print(e.text, "   ", " ".join(sorted(e.tags)[:12]))
        return
    selftest = args[:1] == ["--selftest"]

    if not selftest:
        kernel32.CreateMutexW(None, False, "Local\\hona-kaomoji-picker")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            show_error("The kaomoji picker is already running (look for it in the tray).")
            return

    config = {**DEFAULTS, **load_json(CONFIG_PATH, {})}
    try:
        mods, vk = parse_hotkey(config["hotkey"])
    except ValueError as err:
        show_error(f"{err}\n\nFix the hotkey in {CONFIG_PATH}")
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text, and pixels that match the cursor
    except (AttributeError, OSError):
        pass
    events = queue.Queue()
    registered = {"done": threading.Event()}
    threading.Thread(target=hotkey_loop, args=(mods, vk, events, registered, config["suggest"] and not selftest),
                     daemon=True).start()
    registered["done"].wait(5)
    if not registered.get("ok"):
        msg = f"{config['hotkey']} is already taken by another program. Pick another in {CONFIG_PATH}"
        if not selftest:
            show_error(msg)
            return
        print("warning:", msg)

    root = tk.Tk()
    root.withdraw()
    root.report_callback_exception = lambda *exc: log.error("error", exc_info=exc)
    picker = Picker(root, config, events)
    tray = None
    if not selftest:
        tray = make_tray(events)
        threading.Thread(target=tray.run, daemon=True).start()
        log.info("running, hotkey %s", config["hotkey"])

    def poll():
        try:
            while True:
                kind, arg = events.get_nowait()
                if kind == "show":
                    picker.show(*arg)
                elif kind == "quit":
                    if tray:
                        tray.stop()
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(40, poll)

    if selftest:
        def check():
            focused = root.focus_get() is picker.field
            picker.query.set("happy cat")
            print(f"hotkey registered: {registered.get('ok')}, search box focused: {focused}")
            print(f"{len(picker.entries)} kaomoji loaded; 'happy cat' ->",
                  " | ".join(e.text for e in picker.results[:5]))
            root.after(1200, root.destroy)
        sys.stdout.reconfigure(encoding="utf-8")
        root.after(100, lambda: picker.show(None))
        root.after(600, check)
    root.after(40, poll)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("crashed")
        raise
