// Sprint 9 Q3b / Sprint 10 Goal 8 (R174): the input mapping as data -- launcher/mapping.h, tested without a window
// the way launcher_config is.
//
// The first case is the one the whole item rests on (HANDOFF trap 1): the harness plays the game by posting the
// keyboard's gameplay mapping into the window, and every gate, ladder and control round depends on it. So the
// resolved mapping, with nothing configured, must be BYTE FOR BYTE the two tables socom2_host_input carried at
// compile time -- and the arrays below are those tables, copied literally, not derived from anything mapping.h
// exports. If a default ever moves, this case says so before a gate has to.
#include "MiniTest.h"
#include "launcher/launcher_config.h"
#include "launcher/mapping.h"

#include <algorithm>
#include <cstring>
#include <string>
#include <vector>

namespace
{
    // socom2_host_input.cpp:315-324 as it was on 2026-09-21 (kPadButtons), with raylib's GamepadButton values
    // written as numbers: LEFT_FACE_UP=1 RIGHT=2 DOWN=3 LEFT=4, RIGHT_FACE_UP=5 RIGHT=6 DOWN=7 LEFT=8,
    // LEFT_TRIGGER_1=9 LEFT_TRIGGER_2=10 RIGHT_TRIGGER_1=11 RIGHT_TRIGGER_2=12, MIDDLE_LEFT=13 MIDDLE=14
    // MIDDLE_RIGHT=15, LEFT_THUMB=16 RIGHT_THUMB=17.
    struct OldPadEntry { int button; uint8_t pad; };
    constexpr OldPadEntry kOldPadButtons[] = {
        {1, 4}, {2, 5},      // LEFT_FACE_UP -> kPadUp, LEFT_FACE_RIGHT -> kPadRight
        {3, 6}, {4, 7},      // LEFT_FACE_DOWN -> kPadDown, LEFT_FACE_LEFT -> kPadLeft
        {5, 12}, {6, 13},    // RIGHT_FACE_UP -> kPadTriangle, RIGHT_FACE_RIGHT -> kPadCircle
        {7, 14}, {8, 15},    // RIGHT_FACE_DOWN -> kPadCross, RIGHT_FACE_LEFT -> kPadSquare
        {9, 10}, {11, 11},   // LEFT_TRIGGER_1 -> kPadL1, RIGHT_TRIGGER_1 -> kPadR1
        {10, 8}, {12, 9},    // LEFT_TRIGGER_2 -> kPadL2, RIGHT_TRIGGER_2 -> kPadR2
        {13, 0}, {15, 3},    // MIDDLE_LEFT -> kPadSelect, MIDDLE_RIGHT -> kPadStart
        {16, 1}, {17, 2},    // LEFT_THUMB -> kPadL3, RIGHT_THUMB -> kPadR3
    };

    // socom2_host_input.h:50-54 as it was on 2026-09-21 (kSocom2Keys), raylib's key codes as numbers.
    struct OldKeyEntry { int key; uint8_t button; };
    constexpr OldKeyEntry kOldKeys[] = {
        {257, 3}, {256, 3}, {259, 0},                    // Enter, Escape (owner 2026-09-20), Backspace
        {265, 4}, {262, 5}, {264, 6}, {263, 7},          // arrows
        {'Z', 15}, {'X', 14}, {32, 14}, {'C', 13}, {'V', 12},
        {'Q', 10}, {'E', 11}, {'1', 8}, {'3', 9}, {'2', 1}, {'4', 2},
    };

    bool hasKey(const std::vector<std::string> &env, const std::string &key)
    {
        return std::any_of(env.begin(), env.end(), [&](const std::string &s) { return s.rfind(key + "=", 0) == 0; });
    }

    std::string valueOf(const std::vector<std::string> &env, const std::string &key)
    {
        for (const std::string &s : env)
            if (s.rfind(key + "=", 0) == 0)
                return s.substr(key.size() + 1);
        return std::string();
    }
}

void register_mapping_tests()
{
    MiniTest::Case("InputMapping", [](TestCase &tc)
    {
        tc.Run("inert by construction: with nothing configured the resolved mapping is today's two tables, byte for byte", [](TestCase &t)
        {
            using namespace launcher::mapping;
            const Mapping m = defaults();

            // The pad table: the same rows, in the same order, with the same host button and the same PS2 id.
            t.Equals(static_cast<int>(kPs2ButtonCount), 16, "sixteen digital buttons");
            t.Equals(sizeof(kOldPadButtons) / sizeof(kOldPadButtons[0]), static_cast<size_t>(kPs2ButtonCount), "the old table had one row per button");
            for (int i = 0; i < kPs2ButtonCount; ++i)
            {
                t.Equals(m.pad[i].host, kOldPadButtons[i].button, "pad row " + std::to_string(i) + ": the host button is the old table's");
                t.Equals(static_cast<int>(m.pad[i].button), static_cast<int>(kOldPadButtons[i].pad), "pad row " + std::to_string(i) + ": the PS2 button is the old table's");
            }
            // Byte for byte, not field by field: the runtime walks these rows as memory.
            static_assert(sizeof(PadBinding) == sizeof(OldPadEntry), "the pad row is the old row's shape");
            t.Equals(std::memcmp(m.pad.data(), kOldPadButtons, sizeof(kOldPadButtons)), 0, "the pad table is the old array's bytes");

            // The keyboard table: the same entries, in the same order.
            t.Equals(m.keys.size(), sizeof(kOldKeys) / sizeof(kOldKeys[0]), "eighteen keyboard entries, as before");
            for (size_t i = 0; i < m.keys.size() && i < sizeof(kOldKeys) / sizeof(kOldKeys[0]); ++i)
            {
                t.Equals(m.keys[i].key, kOldKeys[i].key, "key entry " + std::to_string(i) + ": the key is the old table's");
                t.Equals(static_cast<int>(m.keys[i].button), static_cast<int>(kOldKeys[i].button), "key entry " + std::to_string(i) + ": the button is the old table's");
            }
            static_assert(sizeof(KeyBinding) == sizeof(OldKeyEntry), "the key row is the old row's shape");
            t.IsTrue(m.keys.size() == sizeof(kOldKeys) / sizeof(kOldKeys[0]) &&
                         std::memcmp(m.keys.data(), kOldKeys, sizeof(kOldKeys)) == 0,
                     "the keyboard table is the old array's bytes");

            t.IsTrue(isDefault(m), "and the library agrees it is the default");
            t.IsTrue(m == defaults(), "defaults() is deterministic");
        });

        tc.Run("the hash names the resolved table: pinned for the default, and any moved row changes it", [](TestCase &t)
        {
            using namespace launcher::mapping;
            const Mapping m = defaults();
            const std::string hex = hashHex(m);
            t.Equals(hex.size(), static_cast<size_t>(16), "sixteen hex digits");
            t.Equals(hex, std::string(kDefaultHashHex), "the default's hash is the literal the header documents and a gate can pin (computed: " + hex + ")");
            t.Equals(hash(m), kDefaultHash, "as a number too");

            Mapping moved = defaults();
            moved.pad[4].host = kHostL3;   // Triangle on the stick click
            t.IsTrue(hash(moved) != hash(m), "one moved pad row changes the hash");
            t.IsFalse(isDefault(moved), "and it is no longer the default");
            Mapping keyMoved = defaults();
            keyMoved.keys[0].key = 'P';
            t.IsTrue(hash(keyMoved) != hash(m) && hash(keyMoved) != hash(moved), "one moved key changes it too, differently");
            Mapping fewer = defaults();
            fewer.keys.pop_back();
            t.IsTrue(hash(fewer) != hash(m), "a shorter keyboard table is a different table");
            Mapping swapped = defaults();
            std::swap(swapped.pad[0].host, swapped.pad[1].host);
            t.IsTrue(hash(swapped) != hash(m), "two rows swapped is a different table (the hash is ordered)");
        });

        tc.Run("names: every PS2 button, every host button and every default key has a name that reads back", [](TestCase &t)
        {
            using namespace launcher::mapping;
            for (int b = 0; b < kPs2ButtonCount; ++b)
            {
                const std::string name = ps2ButtonName(static_cast<uint8_t>(b));
                t.IsTrue(!name.empty(), "PS2 button " + std::to_string(b) + " has a name");
                t.Equals(ps2ButtonFromName(name), b, "and it reads back: " + name);
            }
            t.Equals(std::string(ps2ButtonName(12)), std::string("triangle"), "12 is triangle (libpad2's order)");
            t.Equals(std::string(ps2ButtonName(0)), std::string("select"), "0 is select");
            t.Equals(ps2ButtonFromName("banana"), -1, "an unknown PS2 name is -1");
            t.Equals(ps2ButtonFromName(""), -1, "and so is an empty one");

            for (int h = 0; h <= kHostButtonMax; ++h)
            {
                const std::string name = hostButtonName(h);
                t.IsTrue(!name.empty(), "host button " + std::to_string(h) + " has a name");
                t.Equals(hostButtonFromName(name), h, "and it reads back: " + name);
            }
            t.Equals(std::string(hostButtonName(kHostNone)), std::string("none"), "0 is none: an unbound row");
            t.Equals(std::string(hostButtonName(kHostFaceUp)), std::string("face_up"), "5 is the top face button (Y / Triangle)");
            t.Equals(std::string(hostButtonName(kHostL3)), std::string("l3"), "16 is the left stick click");
            t.Equals(hostButtonFromName("Y"), -1, "a family's letter is not a host button name: the names are the pad's positions");
            t.Equals(hostButtonFromName("dpad_up"), kHostDpadUp, "1 is the d-pad's up");
            t.Equals(std::string(hostButtonName(99)), std::string("none"), "an id past the last button names nothing");

            for (const KeyBinding &k : defaults().keys)
            {
                const std::string name = keyName(k.key);
                t.IsTrue(!name.empty(), "key " + std::to_string(k.key) + " has a name");
                t.Equals(keyFromName(name), k.key, "and it reads back: " + name);
            }
            t.Equals(keyName(257), std::string("enter"), "257 is enter");
            t.Equals(keyName(256), std::string("escape"), "256 is escape");
            t.Equals(keyName(32), std::string("space"), "32 is space");
            t.Equals(keyName('X'), std::string("x"), "a letter is itself, lower case");
            t.Equals(keyFromName("X"), static_cast<int>('X'), "and reads back in either case");
            t.Equals(keyFromName("x"), static_cast<int>('X'), "(raylib's codes are the capitals)");
            t.Equals(keyName(300), std::string("key:300"), "a key with no word is its number");
            t.Equals(keyFromName("key:300"), 300, "which reads back");
            t.Equals(keyFromName("banana"), -1, "an unknown key name is -1");
            t.Equals(keyFromName("key:x"), -1, "and so is a number that is not one");
        });

        tc.Run("the environment string round-trips, and unset, empty or junk resolves to the defaults", [](TestCase &t)
        {
            using namespace launcher::mapping;
            Mapping m;
            t.IsTrue(fromEnv(nullptr, m) && m == defaults(), "unset: the defaults, and that is not an error");
            t.IsTrue(fromEnv("", m) && m == defaults(), "empty: the defaults");
            t.IsFalse(fromEnv("pad:banana", m), "junk is refused...");
            t.IsTrue(m == defaults(), "...and the mapping is then the defaults, never half of something");
            t.IsFalse(fromEnv("pad:triangle=banana", m), "an unknown host button is refused");
            t.IsFalse(fromEnv("pad:banana=face_up", m), "and so is an unknown PS2 button");
            t.IsFalse(fromEnv("keys:banana=start", m), "and an unknown key");

            const std::string env = toEnv(defaults());
            t.IsTrue(env.rfind("pad:", 0) == 0, "the string starts with the pad table");
            t.IsTrue(env.find(";keys:") != std::string::npos, "and carries the keyboard table after it");
            t.IsTrue(env.find(' ') == std::string::npos && env.find('\n') == std::string::npos, "one token, no whitespace: it travels as an environment value");
            t.IsTrue(env.find("triangle=face_up") != std::string::npos, "a pad row reads PS2=host: triangle=face_up");
            t.IsTrue(env.find("enter=start") != std::string::npos, "a key entry reads key=PS2: enter=start");
            t.IsTrue(fromEnv(env.c_str(), m) && m == defaults(), "the defaults survive the round trip");

            Mapping custom = defaults();
            custom.pad[4].host = kHostL3;        // triangle on the stick click
            custom.pad[14].host = kHostNone;     // L3's row: unbound
            custom.keys.push_back(KeyBinding{'P', 12});
            const std::string customEnv = toEnv(custom);
            t.IsTrue(customEnv.find("l3=none") != std::string::npos, "an unbound row says none");
            t.IsTrue(fromEnv(customEnv.c_str(), m) && m == custom, "a custom mapping survives the round trip");
            t.IsTrue(hash(m) == hash(custom), "with its hash");

            // The string is a whole table, not a patch: every pad row must be there, so a truncated value cannot
            // silently leave the missing rows at their defaults and look like a deliberate mapping.
            t.IsFalse(fromEnv("pad:triangle=l3", m), "a pad table with fewer than sixteen rows is refused");
            t.IsFalse(fromEnv("pad:up=dpad_up,up=dpad_down,right=dpad_right,down=dpad_down,left=dpad_left,triangle=face_up,circle=face_right,cross=face_down,square=face_left,l1=l1,r1=r1,l2=l2,r2=r2,select=select,start=start,l3=l3,r3=r3", m),
                      "a row named twice is refused");
        });

        tc.Run("config.json: a profile with no block plays the defaults, a malformed block is the defaults, a partial one patches them, and it round-trips", [](TestCase &t)
        {
            using namespace launcher::mapping;
            launcher::Config c;
            t.IsTrue(c.mappings.empty(), "a fresh Config saves no mapping for anyone");
            t.IsTrue(launcher::activeMapping(c) == defaults(), "and its profile plays the defaults");
            launcher::Config old;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 1, \"profile\": \"craig\"}", old), "an older config.json with no mappings block parses");
            t.IsTrue(launcher::activeMapping(old) == defaults(), "and its profile plays the defaults");

            launcher::Config bad;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 2, \"mappings\": 5}", bad), "a mappings that is not an object does not sink the file");
            t.IsTrue(bad.mappings.empty() && bad.gsScale == 2, "nobody has a mapping and the rest of the file is kept");
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": 5}}", bad), "a profile's block that is not an object parses");
            t.IsTrue(launcher::activeMapping(bad) == defaults(), "as the defaults");
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": {\"pad\": \"x\"}}}", bad), "a pad table that is not an object parses");
            t.IsTrue(launcher::activeMapping(bad) == defaults(), "as the defaults");
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": {\"pad\": {\"triangle\": \"banana\"}}}}", bad), "an unknown host name parses");
            t.IsTrue(launcher::activeMapping(bad) == defaults(), "and the row it names keeps its default");
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": {\"pad\": {\"banana\": \"l3\"}}}}", bad), "an unknown PS2 name parses");
            t.IsTrue(launcher::activeMapping(bad) == defaults(), "and changes nothing");
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"../x\": {\"pad\": {\"triangle\": \"l3\"}}}}", bad), "a profile name that is not a name parses");
            t.IsTrue(bad.mappings.empty(), "and is dropped, not healed into somebody else's profile");
            t.IsFalse(launcher::fromJson("{\"mappings\": {\"player\": {\"pad\": {\"triangle\": ", bad), "a block that is not JSON at all is still a malformed file");
            t.IsTrue(bad.mappings.empty(), "which is the defaults, like every other field");

            launcher::Config patched;
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": {\"pad\": {\"triangle\": \"l3\", \"l3\": \"none\"}}}}", patched), "a partial pad block parses");
            const Mapping pm = launcher::activeMapping(patched);
            t.Equals(pm.pad[4].host, kHostL3, "the named row moved");
            t.Equals(pm.pad[14].host, kHostNone, "and the unbound one is unbound");
            t.Equals(pm.pad[0].host, kHostDpadUp, "a row the block does not name keeps its default");
            t.IsTrue(pm.keys == defaults().keys, "and the keyboard table is untouched");
            patched.profile = "craig";
            t.IsTrue(launcher::activeMapping(patched) == defaults(), "another profile on the same machine plays the defaults");

            launcher::Config keyed;
            t.IsTrue(launcher::fromJson("{\"mappings\": {\"player\": {\"keys\": {\"triangle\": [\"v\", \"p\"], \"select\": []}}}}", keyed), "a keys block parses");
            const Mapping km = launcher::activeMapping(keyed);
            std::vector<int> triangleKeys, selectKeys;
            for (const KeyBinding &k : km.keys)
            {
                if (k.button == 12) triangleKeys.push_back(k.key);
                if (k.button == 0) selectKeys.push_back(k.key);
            }
            t.IsTrue(triangleKeys == std::vector<int>{'V', 'P'}, "triangle's keys are the block's, in its order");
            t.IsTrue(selectKeys.empty(), "an empty list unbinds a button from the keyboard");
            t.Equals(km.keys.size(), defaults().keys.size(), "eighteen entries still: one added, one removed");
            t.IsTrue(km.pad == defaults().pad, "and the pad table is untouched");

            // The setter keeps the list honest: a profile back at the defaults has no entry.
            launcher::Config custom;
            Mapping m = defaults();
            m.pad[4].host = kHostL3;
            m.pad[14].host = kHostNone;
            // A second key for Triangle, beside its first: the block groups a button's keys, so a grouped table
            // is what round-trips exactly (an interleaved one is regrouped, same keys, different hash).
            m.keys.insert(m.keys.begin() + 12, KeyBinding{'P', 12});
            launcher::setActiveMapping(custom, m);
            t.Equals(custom.mappings.size(), static_cast<size_t>(1), "one profile has a mapping");
            t.IsTrue(launcher::activeMapping(custom) == m, "and it is the one set");
            custom.profile = "craig";
            launcher::setActiveMapping(custom, defaults());
            t.Equals(custom.mappings.size(), static_cast<size_t>(1), "setting the defaults for a profile without an entry adds none");
            custom.profile = "player";
            launcher::setActiveMapping(custom, defaults());
            t.IsTrue(custom.mappings.empty(), "and setting them for the profile that had one removes it");

            // The round trip, through the launcher's own writer.
            launcher::setActiveMapping(custom, m);
            const std::string json = launcher::toJson(custom);
            t.IsTrue(json.find("\"mappings\"") != std::string::npos, "the block is written");
            t.IsTrue(json.find("\"player\": {") != std::string::npos, "keyed by the profile");
            t.IsTrue(json.find("\"triangle\": \"l3\"") != std::string::npos, "with the moved row");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(json, back), "parses its own output");
            t.IsTrue(launcher::activeMapping(back) == m, "and the mapping survives the round trip");
            t.IsTrue(back.mappings == custom.mappings, "whole");
            t.Equals(hashHex(launcher::activeMapping(back)), hashHex(m), "with its hash");
            Mapping interleaved = defaults();
            interleaved.keys.push_back(KeyBinding{'P', 12});   // Triangle's second key at the END of the table
            launcher::setActiveMapping(custom, interleaved);
            t.IsTrue(launcher::fromJson(launcher::toJson(custom), back), "an interleaved table's file parses");
            const Mapping regrouped = launcher::activeMapping(back);
            t.IsTrue(regrouped != interleaved, "it comes back regrouped: Triangle's keys together");
            std::vector<int> tri;
            for (const KeyBinding &k : regrouped.keys)
                if (k.button == 12) tri.push_back(k.key);
            t.IsTrue(tri == std::vector<int>{'V', 'P'}, "the same keys, in the same order, beside each other");
            t.Equals(regrouped.keys.size(), interleaved.keys.size(), "and nothing lost");
            const std::string fresh = launcher::toJson(launcher::Config{});
            t.IsTrue(fresh.find("\"mappings\": {}") != std::string::npos, "a fresh config writes an empty block: nothing was changed, so nothing is said");
            t.IsTrue(launcher::fromJson(fresh, back), "and it parses");
            t.IsTrue(back.mappings.empty(), "as nobody's mapping");
        });

        tc.Run("the environment: a default mapping sends nothing, a custom one sends PS2X_INPUT_MAPPING", [](TestCase &t)
        {
            using namespace launcher::mapping;
            launcher::Config c;
            const std::vector<std::string> before = launcher::environmentFor(c);
            t.IsFalse(hasKey(before, "PS2X_INPUT_MAPPING"), "the default mapping adds nothing: the game's environment is byte for byte what it was");
            Mapping custom = defaults();
            custom.pad[4].host = kHostL3;
            launcher::setActiveMapping(c, custom);
            const std::vector<std::string> env = launcher::environmentFor(c);
            t.IsTrue(hasKey(env, "PS2X_INPUT_MAPPING"), "a moved row reaches the game");
            t.Equals(env.size(), before.size() + 1, "and is the only thing it adds");
            Mapping m;
            t.IsTrue(fromEnv(valueOf(env, "PS2X_INPUT_MAPPING").c_str(), m) && m == custom, "as the whole resolved table");
            c.profile = "craig";
            t.IsFalse(hasKey(launcher::environmentFor(c), "PS2X_INPUT_MAPPING"), "another profile, no mapping: nothing is sent");
        });

        // Sprint 10 Goal 8: the edits the CONTROLLER page makes, pure. A rebind is "this PS2 button, from now on, is
        // that host button"; the host button it takes may already drive another PS2 button, which is the conflict.
        tc.Run("rebinding: a free host button binds, a taken one is a conflict that swaps, replaces or is refused", [](TestCase &t)
        {
            using namespace launcher::mapping;
            Mapping m = defaults();
            t.Equals(boundTo(m, kHostL3), 1, "the stick click drives L3 today");
            t.Equals(boundTo(m, kHostGuide), -1, "the guide button drives nothing");
            t.Equals(boundTo(m, kHostNone), -1, "and 'none' is bound to nothing, however many rows are unbound");

            // A free host button: no conflict, the row moves, the old host button is released.
            Conflict free = rebind(m, 12, kHostGuide, Resolution::Ask);
            t.IsTrue(free.kind == Conflict::Kind::None, "guide is free: no conflict");
            t.Equals(m.pad[rowOf(12)].host, kHostGuide, "triangle is on guide");
            t.Equals(boundTo(m, kHostFaceUp), -1, "and the top face button drives nothing now");

            // A taken host button, asked: nothing moves and the conflict says what it is bound to.
            m = defaults();
            Conflict asked = rebind(m, 12, kHostL3, Resolution::Ask);
            t.IsTrue(asked.kind == Conflict::Kind::Taken, "the stick click is taken");
            t.Equals(asked.by, 1, "by L3");
            t.IsTrue(m == defaults(), "and asking moved nothing");

            // Swap: the two PS2 buttons exchange host buttons.
            Conflict swapped = rebind(m, 12, kHostL3, Resolution::Swap);
            t.IsTrue(swapped.kind == Conflict::Kind::Taken, "a resolved conflict still says what it was");
            t.Equals(m.pad[rowOf(12)].host, kHostL3, "triangle is on the stick click");
            t.Equals(m.pad[rowOf(1)].host, kHostFaceUp, "and L3 is on the top face button");
            t.IsFalse(isDefault(m), "which is not the default");

            // Replace: the other PS2 button is left unbound.
            m = defaults();
            rebind(m, 12, kHostL3, Resolution::Replace);
            t.Equals(m.pad[rowOf(12)].host, kHostL3, "triangle is on the stick click");
            t.Equals(m.pad[rowOf(1)].host, kHostNone, "and L3 is unbound");
            t.Equals(boundTo(m, kHostFaceUp), -1, "the top face button drives nothing");

            // Binding a button to the host button it already has is a no-op, not a conflict with itself.
            m = defaults();
            Conflict same = rebind(m, 12, kHostFaceUp, Resolution::Ask);
            t.IsTrue(same.kind == Conflict::Kind::None, "the same binding again is no conflict");
            t.IsTrue(m == defaults(), "and nothing moved");

            // Out-of-range ids are refused, and move nothing.
            Conflict bad = rebind(m, 99, kHostL3, Resolution::Swap);
            t.IsTrue(bad.kind == Conflict::Kind::Refused && m == defaults(), "an unknown PS2 button is refused");
            bad = rebind(m, 12, 99, Resolution::Swap);
            t.IsTrue(bad.kind == Conflict::Kind::Refused && m == defaults(), "and so is an unknown host button");
            bad = rebind(m, 12, kHostNone, Resolution::Ask);
            t.IsTrue(bad.kind == Conflict::Kind::None && m.pad[rowOf(12)].host == kHostNone, "'none' unbinds, and nothing can conflict with it");

            // Restore: the defaults again, whatever happened.
            t.IsTrue(restoreDefaults(m) == defaults(), "restoreDefaults is the defaults");
            t.IsTrue(isDefault(m), "in place");
        });
    });
}
