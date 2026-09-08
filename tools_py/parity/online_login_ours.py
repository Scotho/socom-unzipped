"""Drive OUR exe from boot through ONLINE -> LOGIN -> universe -> persona/password (on-screen
keyboard) -> CONNECT -> EULA -> lobby against the local Horizon stack, mirroring online_login.py
(the PCSX2 reference). Screens land in --out with the same names as the PCSX2 golden set.

Usage: python -m tools_py.parity.online_login_ours [--name socomc] [--password socom]
       [--out logs/parity/ours_login] [--seconds 420] [--hold 40]
"""
import argparse
import os
import subprocess
import time

from . import drive, keys, winshot
from .online_login import osk_type

T = "ours"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="socomc")
    ap.add_argument("--password", default="socom")
    ap.add_argument("--out", default="logs/parity/ours_login")
    ap.add_argument("--seconds", type=int, default=420)
    ap.add_argument("--hold", type=int, default=40)
    ap.add_argument("--existing", action="store_true")
    ap.add_argument("--then", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running; refusing to start a second game instance")
    proc = drive.launch(T, a.seconds)
    t0 = time.time()
    hwnd = None
    while hwnd is None and time.time() - t0 < 60:
        hwnd = winshot.find_window(keys.WINDOW_TITLES[T]); time.sleep(0.5)
    if hwnd is None:
        proc.terminate(); raise SystemExit("game window not found")
    last = None
    while last is None and time.time() - t0 < 60:
        try: last = drive.frame(hwnd)
        except RuntimeError: time.sleep(0.5)
    shot = lambda n: winshot.capture(hwnd).save(os.path.join(a.out, n + ".png"))
    press = lambda b, w=0.0: (keys.press(hwnd, b, T), time.sleep(w))
    log = lambda m: print(f"{time.time() - t0:6.1f}s {m}", flush=True)

    # Boot: six presses reach the main menu (the sixth skips the attract cinematic).
    for i in range(6):
        drive.wait_stable(hwnd, 1.5, 40.0, changed_from=last); time.sleep(1.0 if i < 5 else 2.0)
        last = drive.frame(hwnd); press("cross"); log(f"boot press {i}")
    time.sleep(4.0); press("down", 1.5); press("cross", 8.0); log("ONLINE")           # menu -> ONLINE
    press("cross", 12.0); log("LOGIN"); shot("00_login")                               # LOGIN -> universes
    drive.wait_stable(hwnd, 2.0, 40.0); shot("01_universe")
    press("cross"); log("universe selected"); time.sleep(8.0); drive.wait_stable(hwnd, 2.0, 40.0); shot("02_persona")
    press("cross", 4.0); log("persona list")
    if a.existing:
        press("cross", 3.0); shot("03_name")
    else:
        press("cross", 4.0); log("<New Persona>")
        osk_type(hwnd, a.name, a.out, "name", target=T); time.sleep(3.0); shot("03_name")
    press("down", 1.0); press("cross", 4.0); shot("04_pw_kbd")
    osk_type(hwnd, a.password, target=T); time.sleep(3.0); shot("05_password")
    for _ in range(4):
        press("down", 0.8)
    shot("06_connect_focus")
    press("cross", 5.0); log("CONNECT"); shot("07_after_connect")
    if not a.existing:
        press("cross", 4.0); shot("07_save_card")
        press("cross", 4.0); shot("07_card_slot")
        press("cross", 4.0); shot("07_overwrite")
        press("left", 0.8); press("cross")
    time.sleep(15.0); drive.wait_stable(hwnd, 2.0, 30.0); shot("08_eula")
    press("cross"); log("EULA accept"); time.sleep(10.0); drive.wait_stable(hwnd, 2.0, 30.0); shot("09_lobby")
    for n, step in enumerate(a.then.split(",") if a.then else []):
        b, w = (step.split(":") + ["2"])[:2]
        if b == "type":
            osk_type(hwnd, w, target=T); time.sleep(3); shot(f"10_then_{n:02d}_typed"); continue
        press(b, float(w)); shot(f"10_then_{n:02d}_{b}")
    for i in range(a.hold // 5):
        time.sleep(5); shot(f"11_hold_{i:02d}")
    shot("final")
    proc.terminate()
    subprocess.run(["taskkill", "/F", "/IM", "socom2.exe"], capture_output=True)


if __name__ == "__main__":
    main()
