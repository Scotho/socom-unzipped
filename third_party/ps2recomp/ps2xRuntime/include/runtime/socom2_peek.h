// Sprint 13 Task C3 (#39): the pure half of PS2X_PEEK, the PC sampler's guest-word dump.
//
// PS2X_PEEK="<item>[,<item>...]", each item "<chain>[:<words>]". A chain is a base address and, in the order
// written, '*' (follow the pointer at the current address) and "+0xOFF" (add an offset): "0x408c58" reads the
// static word there, "*0x408c58+0x10a0" the word 0x10a0 into the object the static points at. Every sampler
// period prints one row, `[peek] @<addr>: <hex8>(<float>) ...` per item, which tools_py/parity reads by
// address (verdict_core._ITEM, music_state_poll.parse_peek_row) and counts by line (sp_death_probe.read_log,
// freeze_trace.parse_log, guest_probe).
//
// Before #39 the loop did two things silently. An item asking for more than 64 words got 64 and a row that
// looked whole; an item whose chain did not resolve (a null or unmapped pointer on the way) got no cell at
// all, so a quiet run and a dead chain read the same. Now the first over-cap sighting of each item prints one
// `[peek-cap]` line naming the item and the cap, and a chain that does not resolve gets a cell that says
// `unresolved` and why. The warning is `[peek-cap]`, not `[peek]`, on purpose: every consumer above counts a
// line that starts with "[peek]" as a row, so a warning under that tag would shift their row index by one.
// The unresolved cell is `@<chain as written>: unresolved (<why>)`, which no row parser's item pattern
// matches (it wants hex digits then eight-digit words), so it is visible to a reader and inert to the tools.
#pragma once

#include <cstdint>
#include <cstdlib>
#include <functional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace socom2_peek
{
    // The most words one item is served per row. A larger block is split into items.
    constexpr uint32_t kMaxWords = 64u;

    struct Item
    {
        std::string text;    // the item as written, for the warning and the unresolved cell
        std::string chain;   // the part before ':'
        uint32_t words = 1u; // what the item asked for (1 when it names no count)
    };

    // Split the knob's value into items, exactly as the sampler always has: ',' separates, the first ':' in
    // an item starts its word count, a missing count is 1.
    inline std::vector<Item> parseSpec(const std::string &spec)
    {
        std::vector<Item> items;
        size_t pos = 0;
        while (pos < spec.size())
        {
            size_t end = spec.find(',', pos);
            if (end == std::string::npos)
                end = spec.size();
            Item item;
            item.text = spec.substr(pos, end - pos);
            item.chain = item.text;
            pos = end + 1;
            const size_t colon = item.chain.find(':');
            if (colon != std::string::npos)
            {
                item.words = static_cast<uint32_t>(std::strtoul(item.chain.c_str() + colon + 1, nullptr, 0));
                item.chain = item.chain.substr(0, colon);
            }
            items.push_back(std::move(item));
        }
        return items;
    }

    // What a row serves of an item that asked for `asked` words.
    inline uint32_t servedWords(uint32_t asked)
    {
        return asked < kMaxWords ? asked : kMaxWords;
    }

    inline bool overCap(const Item &item)
    {
        return item.words > kMaxWords;
    }

    // Lower-case hex, no prefix, no padding (the row's own address style).
    inline std::string hex(uint32_t v)
    {
        static const char digits[] = "0123456789abcdef";
        std::string s;
        do
        {
            s.insert(s.begin(), digits[v & 0xFu]);
            v >>= 4;
        } while (v != 0u);
        return s;
    }

    // Reads one guest word; false when the address is not mapped.
    using ReadWord = std::function<bool(uint32_t addr, uint32_t &out)>;

    struct Resolved
    {
        bool ok = false;
        uint32_t addr = 0u;
        std::string why;   // empty when ok
    };

    // Walk a chain. The rules are the sampler's own, unchanged: a leading '*' parses the base that follows it
    // and then dereferences it; '*' later dereferences the current address; "+N" adds N; a pointer that reads
    // back 0 ends the walk as unresolved (a null link), as does one the reader cannot map.
    inline Resolved resolve(const std::string &chain, const ReadWord &read)
    {
        Resolved r;
        uint32_t addr = 0u;
        size_t i = 0;
        bool haveBase = false;
        auto numberAt = [&chain](size_t from, size_t &to) {
            to = from;
            while (to < chain.size() && chain[to] != '*' && chain[to] != '+')
                ++to;
            return static_cast<uint32_t>(std::strtoul(chain.substr(from, to - from).c_str(), nullptr, 0));
        };
        while (i < chain.size())
        {
            const char ch = chain[i];
            if (ch == '*')
            {
                if (!haveBase)
                {
                    size_t j = 0;
                    addr = numberAt(i + 1, j);   // leading '*': the base number that follows comes first
                    haveBase = true;
                    i = j;
                }
                else
                {
                    ++i;
                }
                uint32_t next = 0u;
                if (!read(addr, next))
                {
                    r.why = "pointer at 0x" + hex(addr) + " is not mapped";
                    return r;
                }
                if (next == 0u)
                {
                    r.why = "null pointer at 0x" + hex(addr);
                    return r;
                }
                addr = next;
            }
            else if (ch == '+')
            {
                size_t j = 0;
                addr += numberAt(i + 1, j);
                i = j;
            }
            else
            {
                size_t j = 0;
                addr = numberAt(i, j);
                haveBase = true;
                i = j;
            }
        }
        r.ok = true;
        r.addr = addr;
        return r;
    }

    // The cell a row carries for an item whose chain did not resolve (or whose final address is not mapped).
    inline std::string unresolvedCell(const Item &item, const std::string &why)
    {
        return " @" + item.chain + ": unresolved (" + why + ")";
    }

    // The one line an over-cap item earns, the first time it is seen.
    inline std::string capWarning(const Item &item, uint32_t index)
    {
        return "[peek-cap] item " + std::to_string(index) + " \"" + item.text + "\" asks for " + std::to_string(item.words) +
               " words; PS2X_PEEK serves at most " + std::to_string(kMaxWords) + " per item, so its cells carry the first " +
               std::to_string(kMaxWords) + " (split it into items to read the rest)";
    }

    // Once per item for the life of the sampler: the spec never changes during a run, so the item's index
    // names it. The sampler thread is the only caller.
    class CapWarnings
    {
    public:
        bool firstSighting(uint32_t index)
        {
            return m_seen.insert(index).second;
        }

    private:
        std::set<uint32_t> m_seen;
    };

}
