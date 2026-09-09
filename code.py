# Jornada 720 keyboard matrix scanner (CircuitPython, RP2040 / Ground Studio Marble Pico)
#
# WHAT THIS DOES:
# You don't know yet which of the 24 ribbon cable pins are "rows" and which
# are "columns" (or even which pins carry power/ground vs. real signals).
# This script sidesteps that problem: it treats every pin you list below as
# a candidate signal line, and cycles through driving each one LOW in turn
# while watching all the others (pulled HIGH) for a change. When you press a
# key on the Jornada keyboard, it briefly connects two of those lines
# together, and the script prints which pair just got connected.
#
# HOW TO USE:
# 1. SAFETY FIRST: with the ribbon unplugged from the Jornada motherboard
#    (or the unit powered off), use a multimeter in continuity/resistance
#    mode to check each of the 24 ribbon pins against a known ground pin
#    and a known power-rail pin. A real matrix signal line should read
#    open/high-resistance to both. Do NOT wire a pin that shows a dead
#    short to power or ground into a GPIO - driving a power rail low with
#    a GPIO output can damage the Pico or the Jornada board. Only wire the
#    pins that look like genuine switch-matrix lines.
# 2. Wire those ribbon pins to the Marble Pico GPIOs listed in PIN_NAMES
#    below, in order (ribbon pin 1 -> PIN_NAMES[0], pin 2 -> PIN_NAMES[1],
#    etc.). GP15 is skipped on purpose - it's reserved for board reset.
#    If you wire things in a different order, just reorder PIN_NAMES to
#    match.
# 3. Save this file as "code.py" on the CIRCUITPY drive (CircuitPython runs
#    it automatically on boot / on save).
# 4. Open a serial terminal (e.g. `screen`, `mu`, or the Mu/Thonny serial
#    monitor) to watch the REPL output.
# 5. Press keys one at a time on the Jornada keyboard and note the pin pairs
#    that get printed - that's your row/column map.

import board
import digitalio
import time

# ---- EDIT THIS LIST if you wired the ribbon in a different order ----
# These are all 25 general-purpose GPIOs on the GroundStudio Marble Pico
# (GP15 is excluded - it's reserved for board reset, do not use it).
# A 24-pin ribbon uses the first 24 of these; GP28 is left spare.
PIN_NAMES = [
    "GP0", "GP1", "GP2", "GP3", "GP4", "GP5", "GP6", "GP7",
    "GP8", "GP9", "GP10", "GP11", "GP12", "GP13", "GP14",
    "GP16", "GP17", "GP18", "GP19", "GP20", "GP21", "GP22",
    "GP26", "GP27", "GP28",
]
# GP28 stands in for a ribbon wire moved off of RUN - RUN is the chip's
# reset line, not a GPIO, and wiring it into the matrix causes random
# resets whenever that line gets pulled low.
# ------------------------------------------------------------------

SETTLE_TIME = 0.001   # seconds to let the driven pin settle before reading
SCAN_DELAY = 0.02     # seconds between full scan passes

pins = [getattr(board, name) for name in PIN_NAMES]


def as_input(pin):
    """Configure a pin as a pulled-up input (its idle state)."""
    io = digitalio.DigitalInOut(pin)
    io.direction = digitalio.Direction.INPUT
    io.pull = digitalio.Pull.UP
    return io


# Start every pin as a pulled-up input.
ios = [as_input(p) for p in pins]

# Tracks which pin-pairs are currently connected, so we only print on
# press/release instead of spamming the console every scan pass.
active_pairs = set()

print("Jornada matrix scanner starting...")
print("Watching {} pins: {}".format(len(PIN_NAMES), PIN_NAMES))
print("Press keys on the Jornada keyboard now.\n")

while True:
    seen_this_pass = set()

    for drive_index in range(len(PIN_NAMES)):
        # Switch the "driver" pin to an output held LOW.
        ios[drive_index].deinit()
        drive_io = digitalio.DigitalInOut(pins[drive_index])
        drive_io.direction = digitalio.Direction.OUTPUT
        drive_io.value = False
        ios[drive_index] = drive_io

        time.sleep(SETTLE_TIME)

        # Check every other (still pulled-up) pin for a LOW reading.
        for read_index in range(len(PIN_NAMES)):
            if read_index == drive_index:
                continue
            if not ios[read_index].value:
                pair = (drive_index, read_index)
                seen_this_pass.add(pair)
                if pair not in active_pairs:
                    print(
                        "PRESSED  coord=({}, {})  pins={} -> {}".format(
                            drive_index, read_index,
                            PIN_NAMES[drive_index], PIN_NAMES[read_index],
                        )
                    )

        # Restore the driver pin to a pulled-up input before moving on.
        ios[drive_index].deinit()
        ios[drive_index] = as_input(pins[drive_index])

    # Anything that was active last pass but not this pass just released.
    for pair in active_pairs - seen_this_pass:
        drive_index, read_index = pair
        print(
            "released coord=({}, {})  pins={} -> {}".format(
                drive_index, read_index,
                PIN_NAMES[drive_index], PIN_NAMES[read_index],
            )
        )

    active_pairs = seen_this_pass
    time.sleep(SCAN_DELAY)
