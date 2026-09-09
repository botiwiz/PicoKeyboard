"""Jornada 720 keymap helper - interactive, runs on your PC (not the Pico).

Watches the Pico's serial output for PRESSED lines from the matrix
scanner (code.py). The first time it sees a new key, a window pops up -
press the matching key on THIS computer's keyboard and it captures
that automatically (no keycode names to remember or type). Figures out
which wired pins are "rows" (driven outputs) vs "columns" (pulled-up
inputs) on its own from what it observes, and rewrites a ready-to-flash
code.py after every key you assign.

Setup (one-time):
    pip install pyserial

Run:
    python keymap_helper.py
    (it lists available COM ports and asks you to pick one)

Your progress is saved to keymap_state.json next to this script, so
you can stop and resume anytime without losing what you've mapped.
"""

import json
import os
import re
import sys
import tempfile
import tkinter as tk

import serial
from serial.tools import list_ports

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keymap_state.json")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "code.py")
BAUD_RATE = 115200

PRESSED_RE = re.compile(r"PRESSED\s+coord=\(\s*-?\d+\s*,\s*-?\d+\s*\)\s+pins=(\S+)\s*->\s*(\S+)")

KEYCODES = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "ZERO",
    "ENTER", "ESCAPE", "BACKSPACE", "TAB", "SPACE", "DELETE", "INSERT",
    "MINUS", "EQUALS", "LEFT_BRACKET", "RIGHT_BRACKET", "BACKSLASH", "POUND",
    "SEMICOLON", "QUOTE", "GRAVE_ACCENT", "COMMA", "PERIOD", "FORWARD_SLASH",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "HOME", "END", "PAGE_UP", "PAGE_DOWN", "UP_ARROW", "DOWN_ARROW",
    "LEFT_ARROW", "RIGHT_ARROW", "PRINT_SCREEN", "SCROLL_LOCK", "PAUSE",
    "CAPS_LOCK", "APPLICATION",
    "LEFT_CONTROL", "LEFT_SHIFT", "LEFT_ALT", "LEFT_GUI",
    "RIGHT_CONTROL", "RIGHT_SHIFT", "RIGHT_ALT", "RIGHT_GUI",
]
KEYCODE_SET = set(KEYCODES)

# Tkinter reports the key you press as an X11-style "keysym". This maps
# those onto adafruit_hid Keycode names so pressing a key on your PC
# keyboard is enough - no keycode names to type or remember. Press keys
# WITHOUT holding Shift so the base key comes through (Shift itself can
# still be captured directly, as its own modifier key).
DIGIT_KEYSYMS = {
    "0": "ZERO", "1": "ONE", "2": "TWO", "3": "THREE", "4": "FOUR",
    "5": "FIVE", "6": "SIX", "7": "SEVEN", "8": "EIGHT", "9": "NINE",
}
NAMED_KEYSYMS = {
    "return": "ENTER",
    "escape": "ESCAPE",
    "backspace": "BACKSPACE",
    "tab": "TAB",
    "space": "SPACE",
    "delete": "DELETE",
    "insert": "INSERT",
    "minus": "MINUS",
    "equal": "EQUALS",
    "bracketleft": "LEFT_BRACKET",
    "bracketright": "RIGHT_BRACKET",
    "backslash": "BACKSLASH",
    "semicolon": "SEMICOLON",
    "apostrophe": "QUOTE",
    "grave": "GRAVE_ACCENT",
    "comma": "COMMA",
    "period": "PERIOD",
    "slash": "FORWARD_SLASH",
    "home": "HOME",
    "end": "END",
    "prior": "PAGE_UP",
    "next": "PAGE_DOWN",
    "up": "UP_ARROW",
    "down": "DOWN_ARROW",
    "left": "LEFT_ARROW",
    "right": "RIGHT_ARROW",
    "print": "PRINT_SCREEN",
    "scroll_lock": "SCROLL_LOCK",
    "pause": "PAUSE",
    "caps_lock": "CAPS_LOCK",
    "control_l": "LEFT_CONTROL",
    "control_r": "RIGHT_CONTROL",
    "shift_l": "LEFT_SHIFT",
    "shift_r": "RIGHT_SHIFT",
    "alt_l": "LEFT_ALT",
    "alt_r": "RIGHT_ALT",
    "super_l": "LEFT_GUI",
    "super_r": "RIGHT_GUI",
    "win_l": "LEFT_GUI",
    "win_r": "RIGHT_GUI",
    "app": "APPLICATION",
    "menu": "APPLICATION",
}
FUNCTION_KEY_RE = re.compile(r"^f([1-9]|1[0-2])$")


def keysym_to_keycode(keysym):
    """Translate a Tkinter keysym into an adafruit_hid Keycode name, or
    None if that key isn't one we recognize."""
    k = keysym.lower()
    if len(k) == 1 and k.isalpha():
        return k.upper()
    if k in DIGIT_KEYSYMS:
        return DIGIT_KEYSYMS[k]
    if FUNCTION_KEY_RE.match(k):
        return k.upper()
    return NAMED_KEYSYMS.get(k)


def edge_key(pin_a, pin_b):
    """Undirected key for a pin pair, order-independent."""
    return "|".join(sorted([pin_a, pin_b]))


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"assignments": {}}  # edge_key -> {"pins": [a, b], "key": "A" or None}


def save_state(state):
    # write to a temp file then swap in, so a crash mid-write can't corrupt
    # progress you've already mapped
    dir_ = os.path.dirname(STATE_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".keymap_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, STATE_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def compute_roles(assignments):
    """2-color the pin graph so every pin lands consistently on the
    'row' (driven) or 'column' (read) side, regardless of which
    direction the scanner happened to detect first. Returns
    (roles, conflicts) where roles maps pin -> 0/1 and conflicts lists
    edges that couldn't be colored consistently (a sign that pin
    isn't a clean matrix line)."""
    roles = {}
    conflicts = []
    edges = [tuple(v["pins"]) for v in assignments.values()]

    def neighbors(pin):
        for a, b in edges:
            if a == pin:
                yield b
            elif b == pin:
                yield a

    all_pins = set()
    for a, b in edges:
        all_pins.add(a)
        all_pins.add(b)

    for start in sorted(all_pins):
        if start in roles:
            continue
        roles[start] = 0
        stack = [start]
        while stack:
            pin = stack.pop()
            for nb in neighbors(pin):
                want = 1 - roles[pin]
                if nb not in roles:
                    roles[nb] = want
                    stack.append(nb)
                elif roles[nb] != want:
                    conflicts.append((pin, nb))
    return roles, conflicts


def generate_code(assignments, roles):
    row_pins = sorted([p for p, r in roles.items() if r == 0])
    col_pins = sorted([p for p, r in roles.items() if r == 1])

    lines = []
    lines.append("# Jornada 720 HID keyboard - generated by keymap_helper.py")
    lines.append("# Needs the adafruit_hid library folder copied into CIRCUITPY/lib")
    lines.append("# (from the Adafruit CircuitPython Library Bundle - one-time setup).")
    lines.append("")
    lines.append("import board")
    lines.append("import digitalio")
    lines.append("import time")
    lines.append("import usb_hid")
    lines.append("from adafruit_hid.keyboard import Keyboard")
    lines.append("from adafruit_hid.keycode import Keycode")
    lines.append("")
    lines.append("ROW_PINS = [" + ", ".join("board." + p for p in row_pins) + "]")
    lines.append("COL_PINS = [" + ", ".join("board." + p for p in col_pins) + "]")
    lines.append("")
    lines.append("# (row_index, col_index) -> Keycode")
    lines.append("KEYMAP = {")
    for v in assignments.values():
        key = v.get("key")
        if not key:
            continue
        a, b = v["pins"]
        row_pin, col_pin = (a, b) if roles.get(a) == 0 else (b, a)
        if row_pin not in row_pins or col_pin not in col_pins:
            continue
        ri = row_pins.index(row_pin)
        ci = col_pins.index(col_pin)
        lines.append(
            "    ({}, {}): Keycode.{},  # {} x {}".format(ri, ci, key, row_pin, col_pin)
        )
    lines.append("}")
    lines.append("")
    lines.append("kbd = Keyboard(usb_hid.devices)")
    lines.append("")
    lines.append("rows = []")
    lines.append("for pin in ROW_PINS:")
    lines.append("    io = digitalio.DigitalInOut(pin)")
    lines.append("    io.direction = digitalio.Direction.OUTPUT")
    lines.append("    io.value = True")
    lines.append("    rows.append(io)")
    lines.append("")
    lines.append("cols = []")
    lines.append("for pin in COL_PINS:")
    lines.append("    io = digitalio.DigitalInOut(pin)")
    lines.append("    io.direction = digitalio.Direction.INPUT")
    lines.append("    io.pull = digitalio.Pull.UP")
    lines.append("    cols.append(io)")
    lines.append("")
    lines.append("pressed = set()")
    lines.append("")
    lines.append("while True:")
    lines.append("    for ri, row in enumerate(rows):")
    lines.append("        row.value = False")
    lines.append("        for ci, col in enumerate(cols):")
    lines.append("            coord = (ri, ci)")
    lines.append("            if not col.value:")
    lines.append("                if coord not in pressed:")
    lines.append("                    pressed.add(coord)")
    lines.append("                    if coord in KEYMAP:")
    lines.append("                        kbd.press(KEYMAP[coord])")
    lines.append("            elif coord in pressed:")
    lines.append("                pressed.discard(coord)")
    lines.append("                if coord in KEYMAP:")
    lines.append("                    kbd.release(KEYMAP[coord])")
    lines.append("        row.value = True")
    lines.append("    time.sleep(0.01)")
    lines.append("")
    return "\n".join(lines)


def pick_port():
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found. Is the Pico plugged in?")
        sys.exit(1)
    print("Available serial ports:")
    for i, p in enumerate(ports):
        print("  [{}] {} - {}".format(i, p.device, p.description))
    if len(ports) == 1:
        print("Using the only one available: {}".format(ports[0].device))
        return ports[0].device
    choice = input("Pick a port number: ").strip()
    return ports[int(choice)].device


def ask_key(pin_a, pin_b, mapped_count):
    """Pop up a window and capture the next key the user presses on
    THIS computer's keyboard, translated straight to a Keycode name.
    Returns None if they click Skip."""
    result = {"value": "__PENDING__"}

    root = tk.Tk()
    root.title("Jornada Keymap")
    root.attributes("-topmost", True)
    root.geometry("440x180")

    base_text = (
        "New key detected!\n\n"
        "Pins: {} <-> {}\n"
        "Mapped so far: {}\n\n"
        "Press the matching key on THIS keyboard now (without holding\n"
        "Shift, so the base key comes through)."
    ).format(pin_a, pin_b, mapped_count)

    msg = tk.StringVar(value=base_text)
    tk.Label(root, textvariable=msg, justify="left", padx=14, pady=14).pack(
        fill="both", expand=True
    )

    def on_key(event):
        code = keysym_to_keycode(event.keysym)
        if code is None:
            msg.set(
                "Key \"{}\" isn't supported yet.\n\n"
                "Try a letter, digit, F-key, arrow, or common\n"
                "punctuation/modifier key instead.\n\n"
                "Pins: {} <-> {}".format(event.keysym, pin_a, pin_b)
            )
            return
        result["value"] = code
        root.destroy()

    def on_skip():
        result["value"] = None
        root.destroy()

    tk.Button(root, text="Skip this key", command=on_skip).pack(pady=(0, 12))

    root.bind("<KeyPress>", on_key)
    root.focus_force()
    root.mainloop()

    return result["value"]


def main():
    port = pick_port()
    state = load_state()
    assignments = state["assignments"]
    mapped_count = sum(1 for v in assignments.values() if v.get("key"))

    print("Connecting to {} at {} baud...".format(port, BAUD_RATE))
    ser = serial.Serial(port, BAUD_RATE, timeout=1)
    print("Connected. Press keys on the Jornada now. Ctrl-C to stop.\n")

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue

            m = PRESSED_RE.search(line)
            if not m:
                continue
            pin_a, pin_b = m.group(1), m.group(2)
            key = edge_key(pin_a, pin_b)

            if key in assignments:
                continue  # already asked about this pin pair (mapped or skipped)

            print("New pin pair: {} <-> {}".format(pin_a, pin_b))
            keycode = ask_key(pin_a, pin_b, mapped_count)
            assignments[key] = {"pins": [pin_a, pin_b], "key": keycode}
            if keycode:
                mapped_count += 1
                print("  -> mapped to {}".format(keycode))
            else:
                print("  -> skipped")

            save_state(state)
            roles, conflicts = compute_roles(assignments)
            if conflicts:
                print("  WARNING: these pins didn't sort cleanly into rows/columns:")
                for a, b in conflicts:
                    print("    {} <-> {}".format(a, b))
            code_text = generate_code(assignments, roles)
            with open(OUTPUT_PATH, "w") as f:
                f.write(code_text)
            print("  code.py updated ({} keys mapped so far)\n".format(mapped_count))

    except KeyboardInterrupt:
        print("\nStopping. {} keys mapped. code.py is up to date at:\n  {}".format(
            mapped_count, OUTPUT_PATH
        ))
    finally:
        ser.close()


if __name__ == "__main__":
    main()
