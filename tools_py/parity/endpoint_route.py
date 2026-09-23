"""Move our game's audio to a chosen endpoint for one run, and put everything back -- the endpoint A/B's tool.

Fix wave A (2026-09-22): a ten-minute briefing capture on the Bluetooth JBL Flip 6 showed DEVICE dips (in the
loopback, not in the mixer's dump). The experiment that settles whether they are the Bluetooth path's or ours is
the same capture on a WIRED endpoint. Two things stand in the way, both in docs/KNOWN.md section 4:

  * Windows routes our executables per exe PATH (HKCU\\...\\Audio\\PolicyConfig\\PropertyStore, "App volume and
    device preferences"): dist\\socom2.exe is pinned to the JBL, so changing the default device moves nothing.
  * The loopback recorder (tools_py/parity/loopback_record.py) records the DEFAULT endpoint, so the game and the
    recorder must move together.

So `set` (1) exports the PropertyStore key to a .reg backup, (2) deletes the entries for our exe paths so they
follow the default, (3) remembers the current default endpoints and (4) makes the chosen device the default for
the console and multimedia roles (communications is left alone: a call in progress keeps its device). `restore`
puts the defaults back and re-imports the key. `check` reads a run log's mix-stream-open line and exits 5 unless
it names the expected device -- the refusal the handoff asks for: a run whose endpoint is not the one intended
is not scored as an A/B. `status` prints both tables and changes nothing.

    python -m tools_py.parity.endpoint_route status
    python -m tools_py.parity.endpoint_route set "HyperX" --backup logs/parity/<stamp>/routing_backup
    python -m tools_py.parity.endpoint_route restore --backup logs/parity/<stamp>/routing_backup
    python -m tools_py.parity.endpoint_route check logs/run_<stamp>.log --expect "HyperX"

Windows only for status/set/restore (pycaw + comtypes for the defaults, winreg + reg.exe for the routing);
`check` is pure text and runs anywhere. The pieces that touch the machine are behind the small functions below
so the tests exercise the selection and the parsing without a registry.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

POLICY_KEY = r"Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore"
# The exe paths whose routing entries are removed for the run: the two our harness launches (docs/KNOWN.md
# section 4's table). Matched case-insensitively as substrings of the entry's value.
OUR_EXES = (r"\projects\socom_pc\dist\socom2.exe", r"\projects\socom_pc\third_party\ps2recomp\build-clang\ps2xruntime\ps2entryrunner.exe")
ROLES = {"console": 0, "multimedia": 1, "communications": 2}
SET_ROLES = ("console", "multimedia")
MIX_OPEN = re.compile(r"\[audio\] 989snd mix stream open \(.*?device (?P<device>.+?), period ")


# ---- pure ------------------------------------------------------------------------------------------------

def mix_open_device(log_text: str) -> Optional[str]:
    """The device named by the run's first mix-stream-open line, or None when the run printed none."""
    m = MIX_OPEN.search(log_text)
    return m.group("device") if m else None


def check_device(log_text: str, expect: str) -> Tuple[bool, str]:
    """(ok, message): does the run's own line name a device containing `expect` (case-insensitive)?"""
    dev = mix_open_device(log_text)
    if dev is None:
        return False, "the run printed no '[audio] 989snd mix stream open' line: its endpoint is unknown -- not scored"
    if expect.lower() not in dev.lower():
        return False, f"the run rendered to '{dev}', not to a device matching '{expect}' -- not scored as this leg of the A/B"
    return True, f"the run rendered to '{dev}'"


def entries_for_our_exes(entries: Dict[str, str], exes=OUR_EXES) -> List[str]:
    """The PropertyStore subkeys (of {subkey: value}) whose value routes one of our exe paths."""
    hits = []
    for sub, value in entries.items():
        v = value.lower()
        if any(exe in v for exe in exes):
            hits.append(sub)
    return sorted(hits)


def pick_device(devices: List[Tuple[str, str, str]], want: str) -> Tuple[str, str]:
    """(id, name) of the one ACTIVE render device whose name contains `want` (case-insensitive) from
    [(id, name, state)]. Zero or several matches is an error: the run must not guess its endpoint."""
    hits = [(i, n) for i, n, s in devices if s == "Active" and want.lower() in n.lower()]
    if len(hits) != 1:
        raise SystemExit(f"endpoint_route: {len(hits)} active render devices match '{want}': "
                         f"{[n for _i, n in hits] or [n for _i, n, s in devices if s == 'Active']}")
    return hits[0]


# ---- the machine -----------------------------------------------------------------------------------------

def render_devices() -> List[Tuple[str, str, str]]:
    from pycaw.utils import AudioUtilities
    out = []
    for d in AudioUtilities.GetAllDevices():
        if str(d.id).startswith("{0.0.0."):                      # render endpoints; capture ones are {0.0.1.
            out.append((str(d.id), str(d.FriendlyName), d.state.name))
    return out


def _enumerator():
    import comtypes
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator
    return comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)


def default_endpoints() -> Dict[str, str]:
    e = _enumerator()
    return {role: e.GetDefaultAudioEndpoint(0, n).GetId() for role, n in ROLES.items()}


def set_default(device_id: str, role: str) -> None:
    import comtypes
    from pycaw.api.policyconfig import IPolicyConfig
    from pycaw.constants import CLSID_CPolicyConfigClient
    pc = comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL)
    hr = pc.SetDefaultEndpoint(device_id, ROLES[role])
    if hr:
        raise SystemExit(f"endpoint_route: SetDefaultEndpoint({device_id}, {role}) -> HRESULT {hr:#x}")


def routing_entries() -> Dict[str, str]:
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, POLICY_KEY) as k:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(k, sub) as sk:
                    out[sub] = str(winreg.QueryValue(sk, None))
            except OSError:
                out[sub] = ""
    return out


def delete_routing_entry(sub: str) -> None:
    """Remove one PropertyStore entry, whatever it holds underneath.

    2026-09-22: the plain winreg.DeleteKey died with WinError 5 on the first entry `set` tried. Not an ACL --
    RegDeleteKey refuses a key that still has subkeys, and an entry whose app volume or mute has been touched
    has one ({219ED5A0-9CBF-4F3A-B927-37C9E5C5F14F}, the per-app property store). So delete depth-first. A
    WinError 5 that survives this one IS the ACL, and it reaches the operator unchanged.
    """
    import winreg
    _delete_tree(winreg, POLICY_KEY + "\\" + sub)


def _delete_tree(winreg, path: str) -> None:
    """The key at `path` under HKCU and everything below it, children before parents. `winreg` is passed in so
    the tests can hand it a registry that is not the machine's."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
        while True:
            try:
                child = winreg.EnumKey(k, 0)     # index 0 each time: the list shrinks as children go
            except OSError:
                break
            _delete_tree(winreg, path + "\\" + child)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def export_key(path_reg: str) -> None:
    subprocess.run(["reg", "export", "HKCU\\" + POLICY_KEY, path_reg, "/y"], check=True, capture_output=True)


def import_key(path_reg: str) -> None:
    subprocess.run(["reg", "import", path_reg], check=True, capture_output=True)


# ---- commands --------------------------------------------------------------------------------------------

def cmd_status() -> int:
    names = {i: n for i, n, _s in render_devices()}
    for role, dev in default_endpoints().items():
        print(f"default {role:<15} {names.get(dev, '?')}  {dev}")
    entries = routing_entries()
    ours = entries_for_our_exes(entries)
    print(f"routing entries: {len(entries)} in all, {len(ours)} for our exes:")
    for sub in ours:
        print(f"  {sub}  {entries[sub]}")
    return 0


def cmd_set(want: str, backup: str) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(backup)) or ".", exist_ok=True)
    reg_path = os.path.abspath(backup + ".reg")
    json_path = os.path.abspath(backup + ".json")
    if os.path.exists(json_path):
        raise SystemExit(f"endpoint_route: {json_path} exists -- a previous `set` was not restored; restore it first")
    devices = render_devices()
    dev_id, dev_name = pick_device(devices, want)
    before = default_endpoints()
    export_key(reg_path)
    entries = routing_entries()
    ours = entries_for_our_exes(entries)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"defaults": before, "removed": {sub: entries[sub] for sub in ours}, "reg": reg_path,
                   "set_to": {"id": dev_id, "name": dev_name}}, f, indent=1)
    for sub in ours:
        delete_routing_entry(sub)
        print(f"removed routing {sub}: {entries[sub]}")
    names = {i: n for i, n, _s in devices}
    for role in SET_ROLES:
        set_default(dev_id, role)
        print(f"default {role}: {names.get(before[role], '?')} -> {dev_name}")
    print(f"backup: {json_path} (+ .reg)")
    return 0


def cmd_restore(backup: str) -> int:
    json_path = os.path.abspath(backup + ".json")
    if not os.path.exists(json_path):
        raise SystemExit(f"endpoint_route: no backup at {json_path}")
    with open(json_path, encoding="utf-8") as f:
        saved = json.load(f)
    names = {i: n for i, n, _s in render_devices()}
    for role in SET_ROLES:
        set_default(saved["defaults"][role], role)
        print(f"default {role}: back to {names.get(saved['defaults'][role], saved['defaults'][role])}")
    import_key(saved["reg"])
    print(f"routing: re-imported {saved['reg']} ({len(saved['removed'])} entries were removed)")
    os.replace(json_path, json_path + ".restored")
    return 0


def cmd_check(log_path: str, expect: str) -> int:
    with open(log_path, encoding="utf-8", errors="replace") as f:
        ok, msg = check_device(f.read(), expect)
    print(("OK: " if ok else "REFUSED: ") + msg)
    return 0 if ok else 5


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("set")
    p.add_argument("device", help="substring of the ACTIVE render device's name (exactly one must match)")
    p.add_argument("--backup", required=True, help="path stem for the backup (.reg and .json are written)")
    p = sub.add_parser("restore")
    p.add_argument("--backup", required=True)
    p = sub.add_parser("check")
    p.add_argument("log")
    p.add_argument("--expect", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return cmd_status()
    if a.cmd == "set":
        return cmd_set(a.device, a.backup)
    if a.cmd == "restore":
        return cmd_restore(a.backup)
    return cmd_check(a.log, a.expect)


if __name__ == "__main__":
    sys.exit(main())
