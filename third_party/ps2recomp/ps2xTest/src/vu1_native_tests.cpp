#include "MiniTest.h"
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"
#include "runtime/ps2_vu1.h"

#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace
{
    struct Vu1NativeFixture
    {
        PS2Memory mem;
        GS gs;
        uint8_t *code = nullptr;
        uint8_t *data = nullptr;

        bool initialize()
        {
            if (!mem.initialize())
                return false;
            gs.init(mem.getGSVRAM(), static_cast<uint32_t>(PS2_GS_VRAM_SIZE), &mem.gs());
            code = mem.getVU1Code();
            data = mem.getVU1Data();
            if (code == nullptr || data == nullptr)
                return false;
            std::memset(code, 0, PS2_VU1_CODE_SIZE);
            std::memset(data, 0, PS2_VU1_DATA_SIZE);
            return true;
        }
    };

    constexpr uint32_t kVuUpperNop = 0x000002FFu;
    constexpr uint32_t kVuLowerNop = 0x8000033Cu;
    constexpr uint32_t kVuUpperEBit = 1u << 30;

    void writePair(uint8_t *code, uint32_t pc, uint32_t lower, uint32_t upper)
    {
        std::memcpy(code + pc, &lower, sizeof(lower));
        std::memcpy(code + pc + sizeof(lower), &upper, sizeof(upper));
    }

    // The image key the interpreter uses: FNV-1a over the whole 16 KB of code memory.
    uint64_t imageHash(const uint8_t *image, size_t size)
    {
        uint64_t hash = 1469598103934665603ull;
        for (size_t i = 0; i < size; ++i)
        {
            hash ^= image[i];
            hash *= 1099511628211ull;
        }
        return hash;
    }

    // Three NOP pairs, the second one carrying the E bit: entered at pc 0 the microcode runs the
    // pair at 8 (E), then one more pair at 16, and ends with pc past it.
    constexpr uint32_t kProgramEndPc = 24u;

    void writeThreePairProgram(uint8_t *code)
    {
        writePair(code, 0u, kVuLowerNop, kVuUpperNop);
        writePair(code, 8u, kVuLowerNop, kVuUpperNop | kVuUpperEBit);
        writePair(code, 16u, kVuLowerNop, kVuUpperNop);
    }

    bool nativeEnds(VU1Interpreter &vu, uint64_t)
    {
        vu.state().vi[10] = 0x1234;
        return true;
    }

    bool nativeHandsBack(VU1Interpreter &vu, uint64_t)
    {
        vu.state().vi[11] = 0x5678;
        vu.state().pc = 8u; // hand the rest of the program back at the E-bit pair
        return false;
    }
}

void register_vu1_native_tests()
{
    // PS2X_VU1_NATIVE is read once per process into a static in VU1Interpreter::run(), so it has
    // to be set before the first microprogram runs -- registration happens before MiniTest::Run().
#ifdef _WIN32
    _putenv_s("PS2X_VU1_NATIVE", "1");
#else
    setenv("PS2X_VU1_NATIVE", "1", 1);
#endif

    MiniTest::Case("VU1Native", [](TestCase &tc)
    {
        tc.Run("native program for (hash, entry pc) runs instead of the microcode", [](TestCase &t)
        {
            Vu1NativeFixture fx;
            t.IsTrue(fx.initialize(), "fixture should initialize");
            writeThreePairProgram(fx.code);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{imageHash(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeEnds}};

            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 0u, 0u, 0u, 64u);
            vu.setNativeProgramsOverride(nullptr, 0u);

            t.Equals(vu.state().vi[10], 0x1234, "the native program should have run");
            t.Equals(vu.state().pc, 0u, "the microcode should not have run: pc stays at the entry");
        });

        tc.Run("hand-back resumes the microcode at the pc the native program set", [](TestCase &t)
        {
            Vu1NativeFixture fx;
            t.IsTrue(fx.initialize(), "fixture should initialize");
            writeThreePairProgram(fx.code);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{imageHash(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeHandsBack}};

            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 0u, 0u, 0u, 64u);
            vu.setNativeProgramsOverride(nullptr, 0u);

            t.Equals(vu.state().vi[11], 0x5678, "the native program should have run first");
            t.Equals(vu.state().pc, kProgramEndPc,
                     "the microcode should have resumed at pc 8 and reached the E bit");
            t.IsFalse(vu.state().ebit, "the E bit should be cleared once the program ended");
        });

        tc.Run("a different entry pc is not intercepted", [](TestCase &t)
        {
            Vu1NativeFixture fx;
            t.IsTrue(fx.initialize(), "fixture should initialize");
            writeThreePairProgram(fx.code);
            fx.mem.markVU1CodeModified();
            const Vu1NativeProgram table[] = {{imageHash(fx.code, PS2_VU1_CODE_SIZE), 0u, &nativeEnds}};

            VU1Interpreter vu;
            vu.setNativeProgramsOverride(table, 1u);
            vu.execute(fx.code, PS2_VU1_CODE_SIZE, fx.data, PS2_VU1_DATA_SIZE, fx.gs, &fx.mem, 8u, 0u, 0u, 64u);
            vu.setNativeProgramsOverride(nullptr, 0u);

            t.Equals(vu.state().vi[10], 0, "the native program registered for entry pc 0 must not run at entry pc 8");
            t.Equals(vu.state().pc, kProgramEndPc, "the microcode should have run from pc 8 to the end");
        });
    });
}
