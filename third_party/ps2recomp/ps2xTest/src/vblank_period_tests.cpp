// macOS fork: the VBlank period (runtime/vblank_period.h) -- today's 16,667 us, or NTSC's 1001/60000 s under
// PS2X_VBLANK_NTSC, which is what T0's hblank clock (15,734 Hz, 262.5 lines a field) and the CD and MPEG timing assume.
#include "MiniTest.h"
#include "runtime/vblank_period.h"

void register_vblank_period_tests()
{
    MiniTest::Case("VBlankPeriod", [](TestCase &tc)
    {
        tc.Run("the default stays 16,667 us; NTSC is 16,683,333 ns, and both in EE cycles", [](TestCase &t)
        {
            using namespace ps2x_vblank;
            t.Equals(static_cast<long long>(period(false).count()), 16667000LL, "default");
            t.Equals(static_cast<long long>(period(true).count()), 16683333LL, "NTSC 59.94 Hz");
            t.Equals(static_cast<unsigned long long>(periodCycles(false, 294912000ull)), 4915299ull, "default in cycles (rounded up)");
            t.Equals(static_cast<unsigned long long>(periodCycles(true, 294912000ull)), 4920116ull, "NTSC in cycles (rounded up)");
        });
    });
}
