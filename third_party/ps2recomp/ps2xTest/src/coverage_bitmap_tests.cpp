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
        // The module's state is process-wide and other cases enable it, so this pins disable(), not the process
        // default (that is installFromEnvironment's: nothing happens without PS2X_COVERAGE).
        tc.Run("disabled: lookups mark nothing, the dump is empty and flush writes nothing", [](TestCase &t)
        {
            const std::filesystem::path path = std::filesystem::temp_directory_path() / "ps2x_coverage_off_test.bin";
            std::error_code ec;
            std::filesystem::remove(path, ec);
            ps2_coverage::enable(g_ps2RecompiledFunctionTableBase, g_ps2RecompiledFunctionTableSlotCount, path.string());
            ps2_coverage::disable();
            PS2Runtime runtime;
            runtime.registerFunction(0x00300000u, retNothing);
            (void)runtime.lookupFunction(0x00300000u);
            t.IsFalse(ps2_coverage::enabled(), "not enabled after disable");
            t.IsTrue(ps2_coverage::serialize().empty(), "nothing to dump");
            t.IsFalse(ps2_coverage::flush(), "flush reports nothing written");
            t.IsFalse(std::filesystem::exists(path), "and no file appears at the path enable was given");
            runtime.registerFunction(0x00300000u, nullptr);
        });

        // K1 (review of #143): the runner leaves through std::_Exit, which runs no atexit hook, so the final write
        // is an explicit flush() from main.cpp. It writes the same bytes writeDump does, to the path enable() took.
        tc.Run("flush writes the dump to the path enable was given", [](TestCase &t)
        {
            const std::filesystem::path path = std::filesystem::temp_directory_path() / "ps2x_coverage_flush_test.bin";
            std::error_code ec;
            std::filesystem::remove(path, ec);
            PS2Runtime runtime;
            runtime.registerFunction(0x00300008u, retNothing);
            ps2_coverage::enable(g_ps2RecompiledFunctionTableBase, g_ps2RecompiledFunctionTableSlotCount, path.string());
            (void)runtime.lookupFunction(0x00300008u);
            const std::vector<uint8_t> bytes = ps2_coverage::serialize();
            t.IsTrue(ps2_coverage::flush(), "flush reports the dump written");
            std::vector<uint8_t> onDisk;
            {
                std::ifstream in(path, std::ios::binary);
                onDisk.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
            }
            t.Equals(onDisk.size(), static_cast<size_t>(16u + (g_ps2RecompiledFunctionTableSlotCount + 7u) / 8u),
                     "header plus one bit per slot");
            t.IsTrue(onDisk == bytes, "the file holds exactly the serialised bitmap");
            std::filesystem::remove(path, ec);
            ps2_coverage::disable();
            runtime.registerFunction(0x00300008u, nullptr);
        });

        // K2: the temporary file is renamed over the old dump with nothing removed first, so a kill between the
        // steps leaves the previous dump in place; the rename must still replace an existing file (Windows too).
        tc.Run("writeDump replaces an existing dump and leaves no temporary file", [](TestCase &t)
        {
            const std::filesystem::path path = std::filesystem::temp_directory_path() / "ps2x_coverage_replace_test.bin";
            {
                std::ofstream old(path, std::ios::binary | std::ios::trunc);
                old << "an older dump";
            }
            ps2_coverage::enable(g_ps2RecompiledFunctionTableBase, g_ps2RecompiledFunctionTableSlotCount);
            const std::vector<uint8_t> bytes = ps2_coverage::serialize();
            t.IsTrue(ps2_coverage::writeDump(path.string()), "written over the old file");
            std::vector<uint8_t> onDisk;
            {
                std::ifstream in(path, std::ios::binary);
                onDisk.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
            }
            t.IsTrue(onDisk == bytes, "the new dump replaced the old");
            t.IsFalse(std::filesystem::exists(path.string() + ".tmp"), "no temporary file left behind");
            std::error_code ec;
            std::filesystem::remove(path, ec);
            ps2_coverage::disable();
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
