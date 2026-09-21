#include "launcher/mapping.h"

#include "json_reader.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>

namespace launcher::mapping
{
    namespace
    {
        // socom2_host_input.cpp's kPadButtons and socom2_host_input.h's kSocom2Keys as they were on 2026-09-21,
        // row for row. mapping_tests.cpp holds these to the literal old arrays; do not reorder them.
        constexpr PadBinding kDefaultPad[kPs2ButtonCount] = {
            {kHostDpadUp, kPs2Up}, {kHostDpadRight, kPs2Right},
            {kHostDpadDown, kPs2Down}, {kHostDpadLeft, kPs2Left},
            {kHostFaceUp, kPs2Triangle}, {kHostFaceRight, kPs2Circle},
            {kHostFaceDown, kPs2Cross}, {kHostFaceLeft, kPs2Square},
            {kHostL1, kPs2L1}, {kHostR1, kPs2R1},
            {kHostL2, kPs2L2}, {kHostR2, kPs2R2},
            {kHostSelect, kPs2Select}, {kHostStart, kPs2Start},
            {kHostL3, kPs2L3}, {kHostR3, kPs2R3},
        };
        constexpr KeyBinding kDefaultKeys[] = {
            {257, kPs2Start}, {256, kPs2Start}, {259, kPs2Select},                        // Enter, Escape (owner 2026-09-20), Backspace
            {265, kPs2Up}, {262, kPs2Right}, {264, kPs2Down}, {263, kPs2Left},            // arrows
            {'Z', kPs2Square}, {'X', kPs2Cross}, {32, kPs2Cross}, {'C', kPs2Circle}, {'V', kPs2Triangle},
            {'Q', kPs2L1}, {'E', kPs2R1}, {'1', kPs2L2}, {'3', kPs2R2}, {'2', kPs2L3}, {'4', kPs2R3},
        };

        constexpr const char *kPs2Names[kPs2ButtonCount] = {
            "select", "l3", "r3", "start", "up", "right", "down", "left",
            "l2", "r2", "l1", "r1", "triangle", "circle", "cross", "square"};

        constexpr const char *kHostNames[kHostButtonMax + 1] = {
            "none", "dpad_up", "dpad_right", "dpad_down", "dpad_left", "face_up", "face_right", "face_down", "face_left",
            "l1", "l2", "r1", "r2", "select", "guide", "start", "l3", "r3"};

        struct NamedKey
        {
            int key;
            const char *name;
        };
        constexpr NamedKey kNamedKeys[] = {
            {257, "enter"}, {256, "escape"}, {259, "backspace"}, {258, "tab"}, {32, "space"},
            {265, "up"}, {264, "down"}, {263, "left"}, {262, "right"},
        };

        std::string lower(const std::string &s)
        {
            std::string out = s;
            for (char &c : out)
                c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            return out;
        }

        // The FNV-1a 64 step, byte by byte; the four-byte fields go in little-endian whatever the host is.
        void mix(uint64_t &h, uint8_t byte)
        {
            h ^= byte;
            h *= 0x100000001b3ull;
        }
        void mix32(uint64_t &h, uint32_t v)
        {
            for (int shift = 0; shift < 32; shift += 8)
                mix(h, static_cast<uint8_t>(v >> shift));
        }

        std::vector<std::string> splitOn(const std::string &text, char sep)
        {
            std::vector<std::string> parts;
            std::string cur;
            for (char c : text)
            {
                if (c == sep)
                {
                    parts.push_back(cur);
                    cur.clear();
                }
                else
                    cur.push_back(c);
            }
            parts.push_back(cur);
            return parts;
        }

        // "a=b" -> a, b; false when there is no '=' or either side is empty.
        bool splitPair(const std::string &item, std::string &left, std::string &right)
        {
            const size_t eq = item.find('=');
            if (eq == std::string::npos)
                return false;
            left = item.substr(0, eq);
            right = item.substr(eq + 1);
            return !left.empty() && !right.empty();
        }
    }

    Mapping defaults()
    {
        Mapping m;
        for (int i = 0; i < kPs2ButtonCount; ++i)
            m.pad[static_cast<size_t>(i)] = kDefaultPad[i];
        m.keys.assign(std::begin(kDefaultKeys), std::end(kDefaultKeys));
        return m;
    }

    bool isDefault(const Mapping &m)
    {
        return m == defaults();
    }

    int rowOf(uint8_t button)
    {
        for (int i = 0; i < kPs2ButtonCount; ++i)
            if (kDefaultPad[i].button == button)
                return i;
        return -1;
    }

    int boundTo(const Mapping &m, int host)
    {
        if (host == kHostNone)
            return -1;
        for (const PadBinding &b : m.pad)
            if (b.host == host)
                return b.button;
        return -1;
    }

    uint64_t hash(const Mapping &m)
    {
        uint64_t h = 0xcbf29ce484222325ull;
        for (const PadBinding &b : m.pad)
        {
            mix32(h, static_cast<uint32_t>(b.host));
            mix(h, b.button);
        }
        mix32(h, static_cast<uint32_t>(m.keys.size()));
        for (const KeyBinding &k : m.keys)
        {
            mix32(h, static_cast<uint32_t>(k.key));
            mix(h, k.button);
        }
        return h;
    }

    std::string hashHex(const Mapping &m)
    {
        char out[32];
        std::snprintf(out, sizeof(out), "%016llx", static_cast<unsigned long long>(hash(m)));
        return out;
    }

    const char *ps2ButtonName(uint8_t button)
    {
        return button < kPs2ButtonCount ? kPs2Names[button] : "";
    }

    int ps2ButtonFromName(const std::string &name)
    {
        for (int i = 0; i < kPs2ButtonCount; ++i)
            if (name == kPs2Names[i])
                return i;
        return -1;
    }

    const char *hostButtonName(int host)
    {
        return host >= 0 && host <= kHostButtonMax ? kHostNames[host] : kHostNames[kHostNone];
    }

    int hostButtonFromName(const std::string &name)
    {
        for (int i = 0; i <= kHostButtonMax; ++i)
            if (name == kHostNames[i])
                return i;
        return -1;
    }

    std::string keyName(int key)
    {
        for (const NamedKey &n : kNamedKeys)
            if (n.key == key)
                return n.name;
        // raylib's codes for the printable keys are the capitals / the ASCII of the character; a name is its
        // lower case so "x" and "1" read as the key cap does.
        if (key > 32 && key < 127)
            return std::string(1, static_cast<char>(std::tolower(key)));
        return "key:" + std::to_string(key);
    }

    int keyFromName(const std::string &raw)
    {
        const std::string name = lower(raw);
        if (name.empty())
            return -1;
        for (const NamedKey &n : kNamedKeys)
            if (name == n.name)
                return n.key;
        if (name.size() == 1)
        {
            const unsigned char c = static_cast<unsigned char>(name[0]);
            if (c > 32 && c < 127)
                return std::toupper(c);
        }
        if (name.rfind("key:", 0) == 0)
        {
            const std::string digits = name.substr(4);
            if (digits.empty())
                return -1;
            for (char c : digits)
                if (!std::isdigit(static_cast<unsigned char>(c)))
                    return -1;
            return std::atoi(digits.c_str());
        }
        return -1;
    }

    std::string toEnv(const Mapping &m)
    {
        std::string out = "pad:";
        for (size_t i = 0; i < m.pad.size(); ++i)
        {
            if (i > 0)
                out.push_back(',');
            out += ps2ButtonName(m.pad[i].button);
            out.push_back('=');
            out += hostButtonName(m.pad[i].host);
        }
        out += ";keys:";
        for (size_t i = 0; i < m.keys.size(); ++i)
        {
            if (i > 0)
                out.push_back(',');
            out += keyName(m.keys[i].key);
            out.push_back('=');
            out += ps2ButtonName(m.keys[i].button);
        }
        return out;
    }

    bool fromEnv(const char *value, Mapping &out)
    {
        out = defaults();
        if (value == nullptr || value[0] == '\0')
            return true;
        const std::string text(value);
        const size_t semi = text.find(';');
        if (text.rfind("pad:", 0) != 0 || semi == std::string::npos || text.compare(semi + 1, 5, "keys:") != 0)
            return false;
        const std::string padPart = text.substr(4, semi - 4);
        const std::string keyPart = text.substr(semi + 6);

        Mapping m = defaults();
        bool seen[kPs2ButtonCount] = {};
        for (const std::string &item : splitOn(padPart, ','))
        {
            std::string left, right;
            if (!splitPair(item, left, right))
                return false;
            const int button = ps2ButtonFromName(left);
            const int host = hostButtonFromName(right);
            if (button < 0 || host < 0 || seen[button])
                return false;
            seen[button] = true;
            m.pad[static_cast<size_t>(rowOf(static_cast<uint8_t>(button)))].host = host;
        }
        for (bool s : seen)
            if (!s)
                return false;   // a whole table or nothing: a missing row is not "the default", it is a truncated value
        m.keys.clear();
        if (!keyPart.empty())
        {
            for (const std::string &item : splitOn(keyPart, ','))
            {
                std::string left, right;
                if (!splitPair(item, left, right))
                    return false;
                const int key = keyFromName(left);
                const int button = ps2ButtonFromName(right);
                if (key < 0 || button < 0)
                    return false;
                m.keys.push_back(KeyBinding{key, static_cast<uint8_t>(button)});
            }
        }
        out = m;
        return true;
    }

    std::string toJson(const Mapping &m, const std::string &indent)
    {
        const std::string in2 = indent + "  ";
        const std::string in3 = in2 + "  ";
        std::string out = "{\n";
        out += in2 + "\"pad\": {\n";
        for (size_t i = 0; i < m.pad.size(); ++i)
        {
            out += in3 + "\"" + ps2ButtonName(m.pad[i].button) + "\": \"" + hostButtonName(m.pad[i].host) + "\"";
            out += i + 1 < m.pad.size() ? ",\n" : "\n";
        }
        out += in2 + "},\n";
        out += in2 + "\"keys\": {\n";
        // A button's keys together, buttons in the order the table first names them, then the buttons with no
        // key at all (in the pad table's order) as empty lists -- so the block is complete and a grouped table
        // reads back exactly as it was.
        std::vector<uint8_t> order;
        for (const KeyBinding &k : m.keys)
            if (k.button < kPs2ButtonCount && std::find(order.begin(), order.end(), k.button) == order.end())
                order.push_back(k.button);
        for (const PadBinding &row : m.pad)
            if (std::find(order.begin(), order.end(), row.button) == order.end())
                order.push_back(row.button);
        for (size_t i = 0; i < order.size(); ++i)
        {
            out += in3 + "\"" + ps2ButtonName(order[i]) + "\": [";
            bool first = true;
            for (const KeyBinding &k : m.keys)
            {
                if (k.button != order[i])
                    continue;
                out += (first ? "\"" : ", \"") + keyName(k.key) + "\"";
                first = false;
            }
            out += i + 1 < order.size() ? "],\n" : "]\n";
        }
        out += in2 + "}\n";
        out += indent + "}";
        return out;
    }

    bool fromJson(const std::string &block, Mapping &out)
    {
        out = defaults();
        detail::JsonReader p(block);
        if (!p.take('{'))
            return false;
        Mapping m = defaults();
        if (p.take('}'))
        {
            out = m;
            return true;
        }
        for (;;)
        {
            std::string key;
            if (!p.string(key) || !p.take(':'))
                return false;
            if (key == "pad")
            {
                if (!p.take('{'))
                    return false;
                if (!p.take('}'))
                {
                    for (;;)
                    {
                        std::string name, value;
                        if (!p.string(name) || !p.take(':') || !p.string(value))
                            return false;
                        const int button = ps2ButtonFromName(name);
                        const int host = hostButtonFromName(value);
                        if (button >= 0 && host >= 0)   // a name from nowhere changes nothing
                            m.pad[static_cast<size_t>(rowOf(static_cast<uint8_t>(button)))].host = host;
                        if (p.take(','))
                            continue;
                        if (!p.take('}'))
                            return false;
                        break;
                    }
                }
            }
            else if (key == "keys")
            {
                if (!p.take('{'))
                    return false;
                if (!p.take('}'))
                {
                    for (;;)
                    {
                        std::string name;
                        if (!p.string(name) || !p.take(':') || !p.take('['))
                            return false;
                        std::vector<int> keys;
                        bool allKnown = true;
                        if (!p.take(']'))
                        {
                            for (;;)
                            {
                                std::string value;
                                if (!p.string(value))
                                    return false;
                                const int k = keyFromName(value);
                                if (k >= 0)
                                    keys.push_back(k);
                                else
                                    allKnown = false;
                                if (p.take(','))
                                    continue;
                                if (!p.take(']'))
                                    return false;
                                break;
                            }
                        }
                        const int button = ps2ButtonFromName(name);
                        // A list with a key this build cannot read is left alone whole: half a list would be a
                        // binding nobody wrote.
                        if (button >= 0 && allKnown)
                        {
                            // Replace that button's entries where the first of them was (or at the end).
                            std::vector<KeyBinding> next;
                            bool placed = false;
                            for (const KeyBinding &k : m.keys)
                            {
                                if (k.button != button)
                                {
                                    next.push_back(k);
                                    continue;
                                }
                                if (placed)
                                    continue;
                                for (int code : keys)
                                    next.push_back(KeyBinding{code, static_cast<uint8_t>(button)});
                                placed = true;
                            }
                            if (!placed)
                                for (int code : keys)
                                    next.push_back(KeyBinding{code, static_cast<uint8_t>(button)});
                            m.keys = next;
                        }
                        if (p.take(','))
                            continue;
                        if (!p.take('}'))
                            return false;
                        break;
                    }
                }
            }
            else if (!p.skipValue())
                return false;
            if (p.take(','))
                continue;
            if (!p.take('}'))
                return false;
            break;
        }
        out = m;
        return true;
    }

    Conflict rebind(Mapping &m, uint8_t button, int host, Resolution resolution)
    {
        Conflict c;
        const int row = rowOf(button);
        if (row < 0 || host < kHostNone || host > kHostButtonMax)
        {
            c.kind = Conflict::Kind::Refused;
            return c;
        }
        PadBinding &mine = m.pad[static_cast<size_t>(row)];
        if (mine.host == host)
            return c;   // already so: nothing to move, nothing in the way
        const int other = boundTo(m, host);
        if (other >= 0)
        {
            c.kind = Conflict::Kind::Taken;
            c.by = other;
            if (resolution == Resolution::Ask)
                return c;
            PadBinding &theirs = m.pad[static_cast<size_t>(rowOf(static_cast<uint8_t>(other)))];
            theirs.host = resolution == Resolution::Swap ? mine.host : kHostNone;
        }
        mine.host = host;
        return c;
    }

    Mapping &restoreDefaults(Mapping &m)
    {
        m = defaults();
        return m;
    }
}
