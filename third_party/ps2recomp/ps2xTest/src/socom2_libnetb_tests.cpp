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
#include <string>
#include <thread>
#include <vector>

namespace socom2_hostnet
{
    // Not in socom2_hostnet.h: the PS2X_SOCOM2_SERVER parse used by loadHosts(), exposed for this
    // test so the value can be passed straight in instead of poking the process environment and
    // re-running init() (init() is one-shot, so an env-based test would depend on case order).
    uint32_t parseServerAddress(const std::string &value);

    // Also not in socom2_hostnet.h, for the same reason: the Winsock/BSD error split. Every guest
    // error code the table returns is produced by these two, so they are the one piece of the
    // platform half a test can pin down without a network.
    int hostnetLastError();
    bool hostnetWouldBlock(int err);
}

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

        // A hosted server is reached by DNS name, so PS2X_SOCOM2_SERVER must accept one. The
        // inet_pton-only parse dropped every non-numeric value and left the retail hostnames
        // pointed at the 127.0.0.1 default -- silently, which reads as "online is just broken".
        // The host socket table, end to end, through the public API only -- create, bind to an
        // ephemeral loopback port, read the port back, send a datagram to itself, wait for it to
        // become readable, receive it, close. On Windows this is the Winsock half that has always
        // shipped and it passes today; it is here because the same case has to pass on Linux once
        // socom2_hostnet.cpp grows its BSD half, and there it does not even compile yet (Task 8
        // watches it in the VM). No platform guard: this is the contract, not an implementation.
        tc.Run("hostnet UDP loopback round-trip through the public socket table", [](TestCase &t)
        {
            using namespace socom2_hostnet;
            t.IsTrue(init(), "hostnet init must succeed");

            const int fd = createSocket(Proto::Udp);
            t.IsTrue(fd >= 0, "createSocket(Udp) must return a table descriptor");
            if (fd < 0)
                return;

            t.Equals(bindSocket(fd, Endpoint{0x7f000001u, 0u}), 0, "bind to 127.0.0.1 port 0 must succeed");

            Endpoint bound{};
            t.Equals(localName(fd, &bound), 0, "localName must report the bound address");
            t.IsTrue(bound.port != 0, "port 0 must come back as the ephemeral port the OS chose");

            static const char kPayload[] = "hostnet";
            const int sent = sendTo(fd, kPayload, sizeof(kPayload), Endpoint{0x7f000001u, bound.port});
            t.Equals(sent, static_cast<int>(sizeof(kPayload)), "sendTo must report the whole datagram");

            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
            while (readable(fd) <= 0 && std::chrono::steady_clock::now() < deadline)
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            t.IsTrue(readable(fd) > 0, "the socket must become readable within a second");

            char buf[32] = {};
            Endpoint from{};
            const int got = recvFrom(fd, buf, sizeof(buf), &from);
            t.Equals(got, static_cast<int>(sizeof(kPayload)), "recvFrom must return the bytes that were sent");
            t.Equals(std::memcmp(buf, kPayload, sizeof(kPayload)), 0, "the payload must come back unchanged");
            t.Equals(from.port, bound.port, "the datagram must be reported as coming from the sending port");

            t.Equals(closeSocket(fd), 0, "closeSocket must release the table entry");
        });

        // The platform error split, with no network in it: a non-blocking socket with nothing
        // queued reports the platform's would-block code (WSAEWOULDBLOCK on Windows, EWOULDBLOCK
        // / EAGAIN on Linux), and hostnetWouldBlock() is the one place that difference lives.
        // Without it mapError() would need a switch that says EWOULDBLOCK and EAGAIN separately,
        // which on Linux is the same value twice and does not compile.
        tc.Run("hostnetWouldBlock answers for the platform's would-block code", [](TestCase &t)
        {
            using namespace socom2_hostnet;
            t.IsTrue(init(), "hostnet init must succeed");

            const int fd = createSocket(Proto::Udp);
            t.IsTrue(fd >= 0, "createSocket(Udp) must return a table descriptor");
            if (fd < 0)
                return;
            t.Equals(bindSocket(fd, Endpoint{0x7f000001u, 0u}), 0, "bind to 127.0.0.1 port 0 must succeed");

            char buf[8] = {};
            Endpoint from{};
            t.Equals(recvFrom(fd, buf, sizeof(buf), &from), -11,
                     "an empty non-blocking socket must map to the guest's EAGAIN");

            const int err = hostnetLastError();
            t.IsTrue(hostnetWouldBlock(err), "hostnetWouldBlock must recognise the code the empty socket just set");
            t.IsTrue(!hostnetWouldBlock(0), "hostnetWouldBlock must not treat success (0) as would-block");

            t.Equals(closeSocket(fd), 0, "closeSocket must release the table entry");
        });

        tc.Run("PS2X_SOCOM2_SERVER accepts a DNS name as well as a numeric IP", [](TestCase &t)
        {
            // getaddrinfo needs Winsock up; init() does WSAStartup and is idempotent.
            t.IsTrue(socom2_hostnet::init(), "hostnet init must succeed");

            const uint32_t numeric = socom2_hostnet::parseServerAddress("192.168.2.10");
            t.Equals(numeric, 0xc0a8020au, "a numeric IPv4 literal must still parse unchanged");

            // getaddrinfo("localhost") yields 127.0.0.1 or ::1; we ask for AF_INET, so 127.0.0.1.
            const uint32_t named = socom2_hostnet::parseServerAddress("localhost");
            t.Equals(named, 0x7f000001u, "a hostname must resolve, not be discarded");

            // A name that cannot resolve returns 0 so loadHosts() keeps its previous value.
            const uint32_t bad = socom2_hostnet::parseServerAddress("no-such-host.invalid");
            t.Equals(bad, 0u, "an unresolvable name must report failure rather than a stale address");
        });
    });
}
