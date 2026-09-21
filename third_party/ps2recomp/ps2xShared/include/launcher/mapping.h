#pragma once
// Sprint 9 Q3b / Sprint 10 Goal 8 (R174): the input mapping -- ONE table, resolved from configuration, whose defaults
// are the two tables socom2_host_input carried at compile time until 2026-09-21 (the pad-to-PS2 array at
// socom2_host_input.cpp:~316 and kSocom2Keys at socom2_host_input.h:50).
//
// PURE ON PURPOSE: no raylib, no environment read, no file. The launcher edits a Mapping and writes it into
// config.json's "mappings" block, one per profile (launcher_config.h: activeMapping / setActiveMapping);
// environmentFor() hands the current profile's resolved table to the game as PS2X_INPUT_MAPPING (only
// when it is not the default -- the default environment is byte for byte what it was); socom2_host_input.cpp reads
// that variable through fromEnv() and walks `pad` and `keys` as data. Every one of those steps is tested under
// ps2xTest without a window (mapping_tests.cpp), the way launcher_config is.
//
// INERT BY CONSTRUCTION (HANDOFF trap 1). The harness plays the game by posting the keyboard's gameplay mapping into
// the window, and every gate, ladder and control-round result depends on it. defaults() therefore IS today's two
// tables, byte for byte, and mapping_tests.cpp compares it against the literal old arrays -- not against anything
// this header exports. Nothing a player can see changes until they change it.
//
// THE HASH. hash() names a resolved table: FNV-1a 64 over the pad rows (host as four little-endian bytes, then the
// PS2 id) followed by the keyboard entry count and the entries (key as four little-endian bytes, then the PS2 id).
// It is ordered -- two rows swapped is a different table -- and it is the same number on every platform and every
// build. The runtime prints it once at startup on a "[socom2] input mapping hash=<16 hex> (default|custom)" line,
// so a gate can refuse to score a run whose mapping is not the pinned default (Q1b builds that refusal; this header
// only makes the number available). The default's value is kDefaultHashHex below, pinned by a test.
//
// WHAT IS NOT IN THE TABLE. The sticks: a stick is an axis, read into the PS2's four analogue fields (WASD / IJKL
// on the keyboard, the pad's two sticks), and the game reads them as movement and aim -- there is nothing to
// rebind them TO. And Triangle's pressure (R139): SOCOM II reads how HARD Triangle is pressed, which no host
// button can express; the crouch shortcut (host_crouch_shortcut.h) works on the PS2 mask AFTER this table, so
// "l3" there means "whichever host control this table binds to PS2 L3". The CONTROLLER page says both.
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace launcher::mapping
{
    // The game's sixteen digital buttons: libpad2 ids, the bit order of the DS2 report (socom2_host_input.h's
    // Socom2PadButton, which static_asserts against these).
    enum Ps2Button : uint8_t
    {
        kPs2Select = 0, kPs2L3 = 1, kPs2R3 = 2, kPs2Start = 3,
        kPs2Up = 4, kPs2Right = 5, kPs2Down = 6, kPs2Left = 7,
        kPs2L2 = 8, kPs2R2 = 9, kPs2L1 = 10, kPs2R1 = 11,
        kPs2Triangle = 12, kPs2Circle = 13, kPs2Cross = 14, kPs2Square = 15,
    };
    constexpr int kPs2ButtonCount = 16;

    // The host pad's buttons, in raylib's GamepadButton numbering (socom2_host_input.cpp static_asserts them; this
    // header stays free of raylib). By POSITION on the pad, never by a family's letter: the top face button is
    // face_up whether the pad in hand prints Y or a triangle on it. 0 is "none": an unbound row.
    enum HostButton : int
    {
        kHostNone = 0,
        kHostDpadUp = 1, kHostDpadRight = 2, kHostDpadDown = 3, kHostDpadLeft = 4,
        kHostFaceUp = 5, kHostFaceRight = 6, kHostFaceDown = 7, kHostFaceLeft = 8,
        kHostL1 = 9, kHostL2 = 10, kHostR1 = 11, kHostR2 = 12,
        kHostSelect = 13, kHostGuide = 14, kHostStart = 15,
        kHostL3 = 16, kHostR3 = 17,
    };
    constexpr int kHostButtonMax = 17;

    // One row of the pad table: `host` drives PS2 button `button`. The shape is the old table's row exactly (an
    // int and a uint8_t), so the default table is the old array's bytes and the test can say so with memcmp.
    struct PadBinding
    {
        int host;         // HostButton; kHostNone leaves the PS2 button with no pad control
        uint8_t button;   // Ps2Button
        bool operator==(const PadBinding &) const = default;
    };

    // One entry of the keyboard table: raylib's (== GLFW's) key code drives PS2 button `button`. Several entries
    // may name the same button (Enter and Escape are both Start; X and Space are both Cross).
    struct KeyBinding
    {
        int key;
        uint8_t button;   // Ps2Button
        bool operator==(const KeyBinding &) const = default;
    };

    struct Mapping
    {
        // One row per PS2 button, in the OLD TABLE'S order (d-pad, face, shoulders, triggers, select/start, stick
        // clicks) -- rowOf() finds a button's row. The `button` column never changes; a rebind edits `host`.
        std::array<PadBinding, kPs2ButtonCount> pad{};
        // The keyboard table, walked in this order. Not rebindable from the launcher's page (the keyboard is
        // menus and typing, and it is the harness's scripted path), but data all the same: config.json may
        // carry it, and the hash covers it.
        std::vector<KeyBinding> keys;
        bool operator==(const Mapping &) const = default;
    };

    // Today's two tables, exactly.
    Mapping defaults();
    bool isDefault(const Mapping &m);
    // The row index of a PS2 button in `pad` (-1 for an id out of range).
    int rowOf(uint8_t button);
    // The PS2 button a host button drives, or -1 (always -1 for kHostNone).
    int boundTo(const Mapping &m, int host);

    // The hash, as above.
    uint64_t hash(const Mapping &m);
    std::string hashHex(const Mapping &m);   // sixteen lower-case hex digits
    // Pinned by mapping_tests.cpp from the first run (2026-09-21); the runtime prints this for a default table.
    constexpr uint64_t kDefaultHash = 0xc393b87b99732a1full;
    constexpr const char *kDefaultHashHex = "c393b87b99732a1f";

    // ---- names: what config.json, the environment and the page say ------------------------------------------
    // PS2 buttons: "select" "l3" "r3" "start" "up" "right" "down" "left" "l2" "r2" "l1" "r1" "triangle" "circle"
    // "cross" "square". Host buttons: "none" "dpad_up" "dpad_right" "dpad_down" "dpad_left" "face_up" "face_right"
    // "face_down" "face_left" "l1" "l2" "r1" "r2" "select" "guide" "start" "l3" "r3". Keys: a printable ASCII key
    // as its lower-case character ("x", "1"), the named ones ("enter" "escape" "backspace" "tab" "space" "up" "down"
    // "left" "right"), anything else as "key:<code>". The FromName functions answer -1 for a name they do not know.
    const char *ps2ButtonName(uint8_t button);   // "" for an id out of range
    int ps2ButtonFromName(const std::string &name);
    const char *hostButtonName(int host);        // "none" for an id out of range
    int hostButtonFromName(const std::string &name);
    std::string keyName(int key);
    int keyFromName(const std::string &name);

    // ---- the environment: PS2X_INPUT_MAPPING ---------------------------------------------------------------
    // "pad:<ps2>=<host>,...(all sixteen rows);keys:<key>=<ps2>,..." -- the whole table, never a patch, so a
    // truncated value cannot leave rows silently at their defaults. fromEnv: unset or empty is the defaults and
    // true; anything it cannot read whole is the defaults and false (the runtime logs that and plays the defaults).
    std::string toEnv(const Mapping &m);
    bool fromEnv(const char *value, Mapping &out);

    // ---- one profile's block inside config.json's "mappings" -----------------------------------------------
    // {"pad": {"<ps2>": "<host>", ...}, "keys": {"<ps2>": ["<key>", ...], ...}}. A PATCH over the defaults: a pad
    // row the block does not name keeps its default, a keys entry replaces that button's keys (an empty list
    // unbinds it from the keyboard). fromJson takes the block's own text; a block that is not an object, or a
    // "pad"/"keys" that is not, is the defaults and false. An unknown name inside changes nothing and is not an
    // error: a config from a newer build must not lose the rows this build does know.
    // The keyboard table is written GROUPED -- a button's keys together, buttons in the order the table first
    // names them -- and read back into the same places, so a grouped table (the default is one) round-trips
    // byte for byte. A hand-written file that interleaves a button's keys is regrouped on load; the game reads
    // the same set of keys either way, only the hash tells the two apart.
    std::string toJson(const Mapping &m, const std::string &indent);
    bool fromJson(const std::string &block, Mapping &out);

    // ---- the page's edits ----------------------------------------------------------------------------------
    // rebind: from now on PS2 `button` is driven by `host`. When `host` already drives another PS2 button that is
    // a conflict, and `resolution` says what to do about it: Ask moves nothing and reports it; Swap gives the
    // other button this one's old host button; Replace leaves the other button unbound. kHostNone unbinds and
    // never conflicts. The old host button is released either way.
    enum class Resolution
    {
        Ask,
        Swap,
        Replace,
    };
    struct Conflict
    {
        enum class Kind
        {
            None,      // bound, nothing was in the way
            Taken,     // `host` drove `by`: under Ask nothing moved; under Swap/Replace it was resolved that way
            Refused,   // an id out of range: nothing moved
        };
        Kind kind = Kind::None;
        int by = -1;   // the PS2 button that had `host`, when Taken
    };
    Conflict rebind(Mapping &m, uint8_t button, int host, Resolution resolution);
    // The defaults again, in place, and returned.
    Mapping &restoreDefaults(Mapping &m);
}
