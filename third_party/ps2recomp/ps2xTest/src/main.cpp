#include "MiniTest.h"
#include <cstdlib>
#include <iostream>

void register_code_generator_tests();
void register_r5900_decoder_tests();
void register_elf_analyzer_tests();
void register_pad_input_tests();
void register_ps2_runtime_io_tests();
void register_ps2_runtime_kernel_tests();
void register_ps2_runtime_interrupt_tests();
void register_ps2_memory_tests();
void register_ps2_vu1_tests();
void register_vu1_native_tests();
void register_ps2_vu_tests();
void register_ps2_gs_tests();
void register_ps2_iop_tests();
void register_ps2_sif_rpc_tests();
void register_ps2_sif_dma_tests();
void register_ps2_recompiler_tests();
void register_ps2_runtime_expansion_tests();
void register_socom2_libnetb_tests();
void reset_ps2_test_function_table();

namespace
{
    // Set name=value only when the environment has not already chosen a value.
    void setEnvDefault(const char *name, const char *value)
    {
        if (std::getenv(name))
            return;
#ifdef _WIN32
        _putenv_s(name, value);
#else
        setenv(name, value, 0);
#endif
    }
}

int main()
{
    // These tests cover the reference implementations, but the runtime defaults to the faster
    // paths this fork added for the game. Each is chosen per process from the environment and
    // read once, before any test runs, so select the reference ones here. An A/B run can
    // override the value-tested ones from the environment (setEnvDefault yields to a value
    // that is already set); PS2X_VU1_XGKICK_CYCLE_EXACT is the exception, see below.
    //   PS2X_GS_BACKEND: the OpenGL backend (gs_frontend.cpp) is the default and needs a real
    //     GL context, which a console test process has none of; the GS tests read back the CPU
    //     rasterizer's framebuffer.
    //   PS2X_VU1_FAST: the non-cycle-exact VU1 path (ps2_vu1_core.cpp) is the default and
    //     commits FMAC results immediately; the VU1 tests assert the architectural four-cycle
    //     writeback latency of the cycle-exact scheduler.
    //   PS2X_VU1_XGKICK_CYCLE_EXACT: XGKICK copies the whole packet at kick time by default;
    //     the PATH1 test asserts the per-cycle model, in which a store can still reach a qword
    //     that has not been transferred yet. This one is presence-tested, not value-tested
    //     (ps2_vu1_core.cpp:1073 takes the immediate path only when getenv returns nullptr),
    //     so once it is set here the per-cycle model is on for the whole process: setting it
    //     to 0 in the environment does NOT turn it back off, and there is no way to select
    //     the immediate copy for this test binary from the environment.
    setEnvDefault("PS2X_GS_BACKEND", "cpu");
    setEnvDefault("PS2X_VU1_FAST", "0");
    setEnvDefault("PS2X_VU1_XGKICK_CYCLE_EXACT", "1");

    MiniTest::BeforeEach(reset_ps2_test_function_table);

    register_code_generator_tests();
    register_r5900_decoder_tests();
    register_elf_analyzer_tests();
    register_pad_input_tests();
    register_ps2_runtime_io_tests();
    register_ps2_runtime_kernel_tests();
    register_ps2_runtime_interrupt_tests();
    register_ps2_memory_tests();
    register_ps2_vu1_tests();
    register_vu1_native_tests();
    register_ps2_vu_tests();
    register_ps2_gs_tests();
    register_ps2_iop_tests();
    register_ps2_sif_rpc_tests();
    register_ps2_sif_dma_tests();
    register_ps2_recompiler_tests();
    register_ps2_runtime_expansion_tests();
    register_socom2_libnetb_tests();
    int res = MiniTest::Run();
    std::cout.flush();
    std::cerr.flush();
    std::_Exit(res);
}
