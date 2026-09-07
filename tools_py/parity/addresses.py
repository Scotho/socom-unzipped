"""Guest addresses shared by the PCSX2 driver (PINE) and our runtime.

DIALOG_STATE_PTR: static word holding a pointer to the current menu-state record; the record's
first word points at the state's rdr name ("dlgMenu.rdr"). Found with find_dialog_ptr.py on a
RAM dump at the main menu (2026-09-07)."""
DIALOG_STATE_PTR = 0x00415700
DIALOG_NAME_OFFSET = 0


def current_dialog(read32, cstring):
    """Name of the current dialog ("dlgMenu") or "" when no menu state is set."""
    rec = read32(DIALOG_STATE_PTR)
    if not (0x100000 <= rec < 0x2000000):
        return ""
    s = read32(rec + DIALOG_NAME_OFFSET)
    if not (0x100000 <= s < 0x2000000):
        return ""
    name = cstring(s, 48)
    return name[:-4] if name.endswith(".rdr") else name
