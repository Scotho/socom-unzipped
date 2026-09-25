// Sprint 13 Task C8 (audit F8): SOCOM II's msifrpc HLE (socom2_msifrpc.cpp) under test.
//
// libnetb's EE library reaches LIBNETB.IRX through msifrpc: bind (FUN_001bd050), call (FUN_001bd320), unbind
// (FUN_001bd200). The HLE answers them synchronously on the host, dispatching the libnetb service 0x80001201 to
// socom2_libnetb::call. These cases drive a whole bind -> call -> unbind round-trip through the real handlers with
// the EE ABI's registers (a0..a3, then t0..t2 for the fifth to seventh arguments), against the host implementation
// the transport fronts: the interface list and three interface-control codes, whose answers need no network.
// Documentation of the transport's behaviour, not a defect's RED; the one limit it pins is that only the blocking
// mode (0) is answered -- a no-wait call returns -1 undispatched (libnetb's wrappers only ever pass 0).
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"
#include "socom2_libnetb.h"
#include "socom2_msifrpc.h"

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace
{
    constexpr uint32_t kRa = 0x00245b10u;
    constexpr uint32_t kClient = 0x00080000u;   // the msifrpc client struct (u32 fields, see socom2_msifrpc.cpp)
    constexpr uint32_t kSend = 0x00081000u;
    constexpr uint32_t kRecv = 0x00082000u;
    constexpr uint32_t kRecvSize = 0x40u;
    constexpr uint32_t kLibnetbSid = 0x80001201u;

    struct Guest
    {
        std::vector<uint8_t> rdram = std::vector<uint8_t>(PS2_RAM_SIZE, 0u);
        R5900Context ctx{};

        uint32_t rd(uint32_t addr) const
        {
            uint32_t v = 0u;
            std::memcpy(&v, rdram.data() + addr, 4);
            return v;
        }
        void wr(uint32_t addr, uint32_t v) { std::memcpy(rdram.data() + addr, &v, 4); }
        uint32_t field(uint32_t index) const { return rd(kClient + index * 4u); }

        uint32_t enter(void (*fn)(uint8_t *, R5900Context *, PS2Runtime *))
        {
            SET_GPR_U32(&ctx, 31, kRa);
            ctx.pc = 0u;
            fn(rdram.data(), &ctx, nullptr);
            return GPR_U32((&ctx), 2);
        }

        // bind(client, sid, 0, bufSize, ...)
        uint32_t bind(uint32_t sid, uint32_t bufSize)
        {
            SET_GPR_U32(&ctx, 4, kClient);
            SET_GPR_U32(&ctx, 5, sid);
            SET_GPR_U32(&ctx, 6, 0u);
            SET_GPR_U32(&ctx, 7, bufSize);
            return enter(ps2_stubs::socom2_MsifBind);
        }

        // call(client, fno, mode, send, sendSize, recv, recvSize, cb, cbArg): the recv buffer is pre-filled with
        // 0xAA (and 16 bytes past it) so what the call wrote and what it left are both visible.
        uint32_t call(uint32_t fno, const std::vector<uint32_t> &send, uint32_t mode = 0u)
        {
            std::memset(rdram.data() + kRecv, 0xAA, kRecvSize + 16u);
            for (size_t i = 0; i < send.size(); ++i)
                wr(kSend + static_cast<uint32_t>(i) * 4u, send[i]);
            SET_GPR_U32(&ctx, 4, kClient);
            SET_GPR_U32(&ctx, 5, fno);
            SET_GPR_U32(&ctx, 6, mode);
            SET_GPR_U32(&ctx, 7, kSend);
            SET_GPR_U32(&ctx, 8, static_cast<uint32_t>(send.size() * 4u));
            SET_GPR_U32(&ctx, 9, kRecv);
            SET_GPR_U32(&ctx, 10, kRecvSize);
            return enter(ps2_stubs::socom2_MsifCall);
        }

        uint32_t unbind()
        {
            SET_GPR_U32(&ctx, 4, kClient);
            SET_GPR_U32(&ctx, 5, 0u);
            return enter(ps2_stubs::socom2_MsifUnbind);
        }

        bool recvUntouched() const
        {
            for (uint32_t i = 0; i < kRecvSize + 16u; ++i)
                if (rdram[kRecv + i] != 0xAAu)
                    return false;
            return true;
        }
    };
}

void register_socom2_msifrpc_tests()
{
    MiniTest::Case("SOCOM2Msifrpc", [](TestCase &tc)
    {
        tc.Run("bind fills the client struct the wrappers read and reports success", [](TestCase &t)
        {
            Guest g;
            for (uint32_t i = 0; i < 16u; ++i)
                g.wr(kClient + i * 4u, 0xDEADBEEFu);
            t.Equals(g.bind(kLibnetbSid, 0x2000u), 0u, "bind returns 0");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
            t.Equals(g.field(4), kLibnetbSid, "[4] the service id");
            t.Equals(g.field(5), 0u, "[5] the IOP buffer: none");
            t.Equals(g.field(9), 1u, "[9] the IOP handle: non-zero = bound");
            t.Equals(g.field(11), 0u, "[11] the unbind result cleared");
            t.Equals(g.field(12), 0x2000u, "[12] the buffer size (the wrappers check +0x30)");
            t.Equals(g.field(0), 0xDEADBEEFu, "[0] the packet pointer is not the HLE's");
        });

        tc.Run("a bind, three calls and an unbind round-trip through the libnetb service", [](TestCase &t)
        {
            Guest g;
            g.bind(kLibnetbSid, 0x2000u);

            // sceInetGetInterfaceList(max): one interface.
            t.Equals(g.call(8u, {4u}), 0u, "transport ok: the result word is in recv[0]");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
            t.Equals(g.rd(kRecv), 1u, "recv[0]: one interface");
            t.Equals(g.rd(kRecv + 4u), 1u, "recv[1]: its id");
            t.Equals(g.rd(kRecv + 8u), 0u, "the rest of the recv buffer is cleared");
            t.Equals(static_cast<unsigned>(g.rdram[kRecv + kRecvSize]), 0xAAu, "nothing written past recvSize");

            // The same call made directly on the host implementation writes the same bytes: the transport adds nothing.
            std::vector<uint8_t> viaTransport(g.rdram.begin() + kRecv, g.rdram.begin() + kRecv + kRecvSize);
            std::memset(g.rdram.data() + kRecv, 0x55, kRecvSize);
            socom2_libnetb::call(g.rdram.data(), 8u, kSend, 4u, kRecv, kRecvSize);
            t.IsTrue(std::memcmp(viaTransport.data(), g.rdram.data() + kRecv, kRecvSize) == 0,
                     "msifrpc call == socom2_libnetb::call, byte for byte");

            // sceInetInterfaceControl(id 1, code 2 = the interface name, len 16).
            t.Equals(g.call(9u, {1u, 2u, 16u}), 0u, "transport ok");
            t.Equals(g.rd(kRecv), 0u, "recv[0]: the control's own result 0");
            t.Equals(std::string(reinterpret_cast<const char *>(g.rdram.data() + kRecv + 12u)), std::string("smap0"),
                     "the name at recv+12");

            // Code 8: the interface state -- attached and up.
            t.Equals(g.call(9u, {1u, 8u, 4u}), 0u, "transport ok");
            t.Equals(g.rd(kRecv + 12u), 3u, "recv[3]: attached + up");

            t.Equals(g.unbind(), 1u, "unbind returns 1 (the wrapper loops until it does)");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
            t.Equals(g.field(9), 0u, "[9] cleared: unbound");
        });

        tc.Run("a call to a service the HLE does not answer fails and writes nothing", [](TestCase &t)
        {
            Guest g;
            g.bind(0x80001300u, 0x100u);
            t.Equals(g.call(8u, {4u}), 0xFFFFFFFFu, "-1: unknown service");
            t.IsTrue(g.recvUntouched(), "the recv buffer is left as it was");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("a call on a client never bound fails and writes nothing", [](TestCase &t)
        {
            Guest g;   // the client struct is zero: sid 0
            t.Equals(g.call(8u, {4u}), 0xFFFFFFFFu, "-1: no service bound");
            t.IsTrue(g.recvUntouched(), "the recv buffer is left as it was");
        });

        tc.Run("only the blocking mode is answered", [](TestCase &t)
        {
            Guest g;
            g.bind(kLibnetbSid, 0x2000u);
            t.Equals(g.call(8u, {4u}, 1u), 0xFFFFFFFFu, "mode 1 (no-wait) returns -1 undispatched");
            t.IsTrue(g.recvUntouched(), "the recv buffer is left as it was");
        });

        tc.Run("init has nothing to set up and returns to the caller", [](TestCase &t)
        {
            Guest g;
            SET_GPR_U32(&g.ctx, 2, 0x1234u);
            t.Equals(g.enter(ps2_stubs::socom2_MsifInit), 0x1234u, "v0 untouched");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });
    });
}
