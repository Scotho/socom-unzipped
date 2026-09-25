// Sprint 13 Task C3, issue #39: PS2X_PEEK capped every item at 64 words silently and skipped an unresolved
// chain without a cell. The sampler loop lives in the overrides file (not linked here, socom2_link_stubs.cpp);
// everything it decides is runtime/socom2_peek.h's, which these cases drive against a fake guest memory.
#include "MiniTest.h"
#include "runtime/socom2_peek.h"

#include <cstdint>
#include <map>
#include <regex>
#include <string>
#include <vector>

namespace
{
    // A sparse guest memory: a word is mapped when it is in the map.
    socom2_peek::ReadWord reader(const std::map<uint32_t, uint32_t> &mem)
    {
        return [&mem](uint32_t addr, uint32_t &out) {
            const auto it = mem.find(addr);
            if (it == mem.end())
                return false;
            out = it->second;
            return true;
        };
    }
}

void register_socom2_peek_tests()
{
    MiniTest::Case("Socom2Peek", [](TestCase &tc)
    {
        tc.Run("the spec splits into items with their word counts, as the sampler always read it", [](TestCase &t)
        {
            const auto items = socom2_peek::parseSpec("0x408c58,*0x408c58+0x10a0:3,0x49e158:80");
            t.Equals(items.size(), static_cast<size_t>(3), "three items");
            t.Equals(items[0].chain, std::string("0x408c58"), "a bare address");
            t.Equals(items[0].words, 1u, "no count is one word");
            t.Equals(items[1].chain, std::string("*0x408c58+0x10a0"), "a chain");
            t.Equals(items[1].words, 3u, "its count");
            t.Equals(items[2].words, 80u, "the count as asked, before any cap");
            t.Equals(items[2].text, std::string("0x49e158:80"), "and the item as written, for the lines that name it");
        });

        // #39's first half: an item over the cap is served 64 words and earns ONE line that names it and the cap.
        tc.Run("an item over 64 words is served 64 and warned about once, by name", [](TestCase &t)
        {
            const auto items = socom2_peek::parseSpec("0x100:4,0x49e158:80");
            t.IsFalse(socom2_peek::overCap(items[0]), "4 words is under the cap");
            t.IsTrue(socom2_peek::overCap(items[1]), "80 is over it");
            t.Equals(socom2_peek::servedWords(4u), 4u, "under the cap: all of it");
            t.Equals(socom2_peek::servedWords(64u), 64u, "at the cap: all of it");
            t.Equals(socom2_peek::servedWords(80u), socom2_peek::kMaxWords, "over the cap: 64");
            const std::string line = socom2_peek::capWarning(items[1], 1u);
            t.IsTrue(line.rfind("[peek-cap] ", 0) == 0, "its own tag: a [peek] line would be counted as a row by the tools");
            t.IsTrue(line.find("0x49e158:80") != std::string::npos, "names the item as written");
            t.IsTrue(line.find("item 1") != std::string::npos, "and its position");
            t.IsTrue(line.find("80") != std::string::npos && line.find("64") != std::string::npos, "says what it asked and the cap");
            socom2_peek::CapWarnings warned;
            t.IsTrue(warned.firstSighting(1u), "the first sample warns");
            t.IsFalse(warned.firstSighting(1u), "the next sample does not: once per item per run");
            t.IsTrue(warned.firstSighting(2u), "another over-cap item warns for itself");
        });

        tc.Run("a chain resolves through each pointer and offset in the order written", [](TestCase &t)
        {
            const std::map<uint32_t, uint32_t> mem = {{0x408c58u, 0x01200000u}, {0x012010a0u, 0x00300000u}};
            const auto rd = reader(mem);
            socom2_peek::Resolved r = socom2_peek::resolve("0x408c58", rd);
            t.IsTrue(r.ok && r.addr == 0x408c58u, "a bare address is itself");
            r = socom2_peek::resolve("*0x408c58+0x10a0", rd);
            t.IsTrue(r.ok, "one pointer then an offset");
            t.Equals(r.addr, 0x012010a0u, "lands inside the object");
            r = socom2_peek::resolve("*0x408c58+0x10a0*", rd);
            t.IsTrue(r.ok, "and a second pointer");
            t.Equals(r.addr, 0x00300000u, "follows it");
            r = socom2_peek::resolve("0x408c58*+0x4", rd);
            t.IsTrue(r.ok, "a trailing-style chain");
            t.Equals(r.addr, 0x01200004u, "reads the same");
        });

        // #39's second half: an unresolved chain writes a cell that says so, never no cell.
        tc.Run("an unresolved chain gets a cell that says unresolved and why", [](TestCase &t)
        {
            const std::map<uint32_t, uint32_t> mem = {{0x488de8u, 0x01300000u}, {0x013000bcu, 0u}};
            const auto rd = reader(mem);
            socom2_peek::Resolved r = socom2_peek::resolve("*0x488de8+0xbc*", rd);
            t.IsFalse(r.ok, "the camera's follow pointer is null in a spawn image: the chain does not resolve");
            t.IsTrue(r.why.find("null pointer at 0x13000bc") != std::string::npos, "the reason names the null link");
            const auto items = socom2_peek::parseSpec("*0x488de8+0xbc*:4");
            const std::string cell = socom2_peek::unresolvedCell(items[0], r.why);
            t.Equals(cell, std::string(" @*0x488de8+0xbc*: unresolved (null pointer at 0x13000bc)"), "the row's cell");
            t.IsTrue(cell.find("unresolved") != std::string::npos, "unresolved in the value column");
            r = socom2_peek::resolve("*0x500000", rd);
            t.IsFalse(r.ok, "a pointer the reader cannot map");
            t.IsTrue(r.why.find("not mapped") != std::string::npos, "says so");
        });

        tc.Run("the unresolved cell is inert to the row parsers", [](TestCase &t)
        {
            // The readers' own item pattern, verbatim: tools_py/parity/verdict_core.py:282 and
            // verdict_replay.py:218 (`@<hex>:` then one or more eight-hex-digit words each followed by '('),
            // and music_state_poll.py's _PEEK_ITEM_RE (the same with a single space). Run over a whole row: the
            // resolved cell is read, the unresolved cells beside it -- including one whose chain is bare hex
            // and whose reason carries hex -- are not.
            const std::regex item(R"(@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+))");
            const std::regex musicItem(R"(@([0-9a-fA-F]+):((?: [0-9a-fA-F]{8}\([^)]*\))+))");
            const auto items = socom2_peek::parseSpec("*0x488de8+0xbc*:4,488de8*,0x408c58");
            std::string row = "[peek]";
            row += socom2_peek::unresolvedCell(items[0], "null pointer at 0x13000bc");
            row += socom2_peek::unresolvedCell(items[1], "null pointer at 0x488de8");
            row += " @408c58: 01200000(1.05879e-38)";
            for (const std::regex *re : {&item, &musicItem})
            {
                std::vector<std::string> addrs;
                for (auto it = std::sregex_iterator(row.begin(), row.end(), *re); it != std::sregex_iterator(); ++it)
                    addrs.push_back((*it)[1].str());
                t.Equals(addrs.size(), static_cast<size_t>(1), "exactly one item read out of the row");
                t.IsTrue(!addrs.empty() && addrs[0] == "408c58", "and it is the resolved one");
            }
        });
    });
}
