// Sprint 19 task B1: the function-coverage bitmap (PS2X_COVERAGE, runtime/coverage_bitmap.h).
//
// One bit per dense function-table slot, set when PS2Runtime::lookupFunction hands out that slot's function --
// the path every dispatched call (JAL, JALR) takes. These cases drive it through lookupFunction on the test
// function table and check the dump's layout, which tools_py/coverage_bitmap.py reads.
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "runtime/coverage_bitmap.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace
{
    uint32_t le32(const std::vector<uint8_t> &b, size_t off)
    {
        uint32_t v = 0;
        std::memcpy(&v, b.data() + off, 4);
        return v;
    }

    void retNothing(uint8_t *, R5900Context *, PS2Runtime *) {}
}

void register_coverage_bitmap_tests()
{
    MiniTest::Case("CoverageBitmap", [](TestCase &tc)
    {
        tc.Run("off by default: lookups mark nothing and the dump is empty", [](TestCase &t)
        {
            ps2_coverage::disable();
            PS2Runtime runtime;
            runtime.registerFunction(0x00300000u, retNothing);
            (void)runtime.lookupFunction(0x00300000u);
            t.IsFalse(ps2_coverage::enabled(), "not enabled unless asked");
            t.IsTrue(ps2_coverage::serialize().empty(), "nothing to dump");
            runtime.registerFunction(0x00300000u, nullptr);
        });

        tc.Run("a dispatched lookup marks its slot; an unregistered pc marks nothing", [](TestCase &t)
        {
            PS2Runtime runtime;
            runtime.registerFunction(0x00300000u, retNothing);
            ps2_coverage::enable(g_ps2RecompiledFunctionTableBase, g_ps2RecompiledFunctionTableSlotCount);
            t.IsTrue(ps2_coverage::enabled(), "enabled");
            const uint32_t slot = (0x00300000u - g_ps2RecompiledFunctionTableBase) >> 2;
            t.IsFalse(ps2_coverage::hit(slot), "not hit before the call");
            (void)runtime.lookupFunction(0x00300000u);
            (void)runtime.lookupFunction(0x00300000u);
            t.IsTrue(ps2_coverage::hit(slot), "hit after the lookup");
            t.IsFalse(ps2_coverage::hit(slot + 1u), "the next slot is untouched");
            (void)runtime.lookupFunction(0x00300010u);   // no function there: the missing-function path
            t.IsFalse(ps2_coverage::hit(slot + 4u), "a pc with no function is not counted as covered");
            t.Equals(ps2_coverage::hitCount(), static_cast<uint32_t>(1u), "one slot hit in all");
            ps2_coverage::disable();
            runtime.registerFunction(0x00300000u, nullptr);
        });

        tc.Run("the dump: magic, table base, slot count, then the bits LSB first", [](TestCase &t)
        {
            PS2Runtime runtime;
            runtime.registerFunction(0x00300004u, retNothing);
            ps2_coverage::enable(g_ps2RecompiledFunctionTableBase, g_ps2RecompiledFunctionTableSlotCount);
            (void)runtime.lookupFunction(0x00300004u);
            const std::vector<uint8_t> bytes = ps2_coverage::serialize();
            const uint32_t slots = g_ps2RecompiledFunctionTableSlotCount;
            t.Equals(bytes.size(), static_cast<size_t>(16u + (slots + 7u) / 8u), "header plus one bit per slot");
            t.IsTrue(std::memcmp(bytes.data(), "PS2XCOV1", 8) == 0, "magic");
            t.Equals(le32(bytes, 8), g_ps2RecompiledFunctionTableBase, "table base");
            t.Equals(le32(bytes, 12), slots, "slot count");
            const uint32_t slot = (0x00300004u - g_ps2RecompiledFunctionTableBase) >> 2;
            t.Equals(static_cast<int>(bytes[16u + (slot >> 3)]), 1 << (slot & 7u), "the one bit, in its byte");

            const std::string path = (std::filesystem::temp_directory_path() / "ps2x_coverage_test.bin").string();
            t.IsTrue(ps2_coverage::writeDump(path), "written");
            std::ifstream in(path, std::ios::binary);
            const std::vector<uint8_t> onDisk((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
            t.IsTrue(onDisk == bytes, "the file holds exactly the serialised bitmap");
            in.close();
            std::remove(path.c_str());
            ps2_coverage::disable();
            runtime.registerFunction(0x00300004u, nullptr);
        });
    });
}
