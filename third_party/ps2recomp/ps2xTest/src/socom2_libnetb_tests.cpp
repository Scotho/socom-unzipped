// sceInetInterfaceControl code 0x200 (socom2_libnetb.cpp) must MOVE when traffic arrives. SOCOM II
// resets its "last network activity" timestamp only when this word changes; a constant pinned the
// online player in place (Sprint 4, abf35bb). PS2X_SOCOM2_NET_STATS=0 restores the constant on purpose.
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "socom2_hostnet.h"
#include "socom2_libnetb.h"

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>

namespace
{
    constexpr uint32_t kSendAddr = 0x1000u;
    constexpr uint32_t kRecvAddr = 0x2000u;
    constexpr uint32_t kRecvSize = 0x40u;

    void setNetStatsEnv(const char *value)
    {
#ifdef _WIN32
        _putenv_s("PS2X_SOCOM2_NET_STATS", value ? value : "");
#else
        if (value)
            setenv("PS2X_SOCOM2_NET_STATS", value, 1);
        else
            unsetenv("PS2X_SOCOM2_NET_STATS");
#endif
        socom2_libnetb::testResetKnobs();
    }

    // sceInetInterfaceControl(id 1, code 0x200, len 4) through the RPC dispatcher; the word is p[3].
    uint32_t queryStatsWord(std::vector<uint8_t> &rdram)
    {
        const uint32_t send[3] = {1u, 0x200u, 4u};
        std::memcpy(rdram.data() + kSendAddr, send, sizeof(send));
        socom2_libnetb::call(rdram.data(), 9u, kSendAddr, sizeof(send), kRecvAddr, kRecvSize);
        uint32_t word = 0u;
        std::memcpy(&word, rdram.data() + kRecvAddr + 12u, sizeof(word));
        return word;
    }

    // One UDP datagram over loopback, received through the host socket table every libnetb receive
    // path uses. Returns the byte count recvFrom reported (<= 0 on failure).
    int deliverPacket()
    {
        using namespace socom2_hostnet;
        if (!init())
            return -1;
        const int rx = createSocket(Proto::Udp);
        const int tx = createSocket(Proto::Udp);
        int got = -1;
        Endpoint local;
        if (rx >= 0 && tx >= 0 && bindSocket(rx, Endpoint{0x7f000001u, 0u}) == 0 && localName(rx, &local) == 0)
        {
            static const char kPayload[] = "moves";
            if (sendTo(tx, kPayload, sizeof(kPayload), local) == static_cast<int>(sizeof(kPayload)))
            {
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (readable(rx) <= 0 && std::chrono::steady_clock::now() < deadline)
                    std::this_thread::sleep_for(std::chrono::milliseconds(2));
                char buf[64];
                Endpoint from;
                got = recvFrom(rx, buf, sizeof(buf), &from);
            }
        }
        if (rx >= 0)
            closeSocket(rx);
        if (tx >= 0)
            closeSocket(tx);
        return got;
    }
}

void register_socom2_libnetb_tests()
{
    MiniTest::Case("SOCOM2Libnetb", [](TestCase &tc)
    {
        tc.Run("InterfaceControl 0x200 moves when a packet is delivered", [](TestCase &t)
        {
            setNetStatsEnv(nullptr); // the shipped default: stats on
            std::vector<uint8_t> rdram(PS2_RAM_SIZE, 0u);
            const uint32_t before = queryStatsWord(rdram);
            const int n = deliverPacket();
            t.IsTrue(n > 0, "a loopback UDP datagram should be received");
            const uint32_t after = queryStatsWord(rdram);
            t.IsTrue(after != before, "code 0x200 must change after a delivered packet (a constant pins the online player)");
            t.Equals(after - before, static_cast<uint32_t>(n), "code 0x200 should advance by the bytes received");
        });

        tc.Run("InterfaceControl 0x200 stays constant with PS2X_SOCOM2_NET_STATS=0", [](TestCase &t)
        {
            setNetStatsEnv("0");
            std::vector<uint8_t> rdram(PS2_RAM_SIZE, 0u);
            const uint32_t before = queryStatsWord(rdram);
            const int n = deliverPacket();
            t.IsTrue(n > 0, "a loopback UDP datagram should be received");
            const uint32_t after = queryStatsWord(rdram);
            t.Equals(after, before, "PS2X_SOCOM2_NET_STATS=0 must keep code 0x200 constant (the defect's reproduction knob)");
            setNetStatsEnv(nullptr);
        });
    });
}
