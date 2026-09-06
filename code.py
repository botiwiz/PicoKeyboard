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
# 1. Wire the ribbon cable's candidate signal pins to some Pico GPIOs.
#    Avoid pins used for onboard LED/USB/etc. Leave out anything you know
#    for certain is power or ground.
# 2. Edit PIN_NAMES below to match the GPIOs you actually wired up.
# 3. Save this file as "code.py" on the CIRCUITPY drive (CircuitPython runs
#    it automatically on boot / on save).
# 4. Open a serial terminal (e.g. `screen`, `mu`, or the Mu/Thonny serial
#    monitor) to watch the REPL output.
# 5. Press keys one at a time on the Jornada keyboard and note the pin pairs
#    that get printed - that's your row/column map.

import board
import digitalio
import time

# ---- EDIT THIS LIST to match how you wired the ribbon cable ----
PIN_NAMES = [
    "GP0", "GP1", "GP2", "GP3", "GP4", "GP5", "GP6", "GP7",
    "GP8", "GP9", "GP10", "GP11", "GP12", "GP13",
]
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
