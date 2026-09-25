// sceInetInterfaceControl code 0x200 (socom2_libnetb.cpp) must MOVE when traffic arrives. SOCOM II
// resets its "last network activity" timestamp only when this word changes; a constant pinned the
// online player in place (Sprint 4, abf35bb). PS2X_SOCOM2_NET_STATS=0 restores the constant on purpose.
#include "MiniTest.h"
#include "launcher/launcher_config.h"
#include "ps2_runtime.h"
#include "ps2x/exit_codes.h"
#include "socom2_hostnet.h"
#include "socom2_libnetb.h"

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#ifndef _WIN32
// F6: the EINTR case below needs a raw socket, a real signal and a real timer.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

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

    // Sprint 13 V8, also not in the header: what PS2X_SOCOM2_SERVER becomes, and the table half of it.
    uint32_t serverForKnob(const char *value, std::string &refusal);
    void testApplyServer(const char *value);

#ifndef _WIN32
    // F6, also not in the header: the poll(2) wrapper that resumes across EINTR. A signal
    // is the only way to observe the retry, so the test drives this directly -- the public
    // poll() would answer "writable" at once on any socket and never reach the wait.
    int hostnetPollRestarting(int nativeFd, short events, short *revents, int timeoutMs);
#endif
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
            const int got = recvFrom(fd, buf, sizeof(buf), &from);
            // F8: the platform error code belongs to THAT recvFrom, so it is read before any
            // assertion -- MiniTest reports through stdio, which is free to set errno itself.
            const int err = hostnetLastError();
            t.Equals(got, -11, "an empty non-blocking socket must map to the guest's EAGAIN");
            t.IsTrue(hostnetWouldBlock(err), "hostnetWouldBlock must recognise the code the empty socket just set");

            t.Equals(closeSocket(fd), 0, "closeSocket must release the table entry");
        });

        // F6: SA_RESTART does not restart poll(2). The Linux host sampler (PS2X_HOST_PROF) raises
        // SIGPROF on every thread ~200 times a second, so a bare ::poll() came back -1/EINTR and
        // mapError() turned that into -5 (EIO): switching the profiler on killed online play. The
        // wait must instead resume with the time it has left and end as a plain timeout.
        tc.Run("a poll wait interrupted by a signal times out rather than failing", [](TestCase &t)
        {
#ifdef _WIN32
            t.IsTrue(true, "skipped on Windows: EINTR is a POSIX condition -- Winsock select() never "
                           "returns it, and the SIGPROF sampler that provokes it is Linux-only");
            return;
#else
            using namespace socom2_hostnet;
            const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
            t.IsTrue(fd >= 0, "a UDP socket to wait on");
            if (fd < 0)
                return;
            sockaddr_in addr{};
            addr.sin_family = AF_INET;
            addr.sin_addr.s_addr = htonl(0x7f000001u);
            addr.sin_port = 0;
            ::bind(fd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr));

            // A 10 ms repeating SIGALRM stands in for the sampler: the 100 ms wait below is
            // interrupted roughly ten times. The handler does nothing; being delivered is the point.
            struct sigaction sa;
            struct sigaction previous;
            std::memset(&sa, 0, sizeof(sa));
            std::memset(&previous, 0, sizeof(previous));
            sa.sa_handler = [](int) {};
            sigemptyset(&sa.sa_mask);
            sa.sa_flags = 0;   // SA_RESTART would change nothing here: poll() is never restarted
            ::sigaction(SIGALRM, &sa, &previous);
            itimerval timer{};
            timer.it_value.tv_usec = 10000;
            timer.it_interval.tv_usec = 10000;
            ::setitimer(ITIMER_REAL, &timer, nullptr);

            const auto start = std::chrono::steady_clock::now();
            short revents = 0;
            const int n = hostnetPollRestarting(fd, POLLIN, &revents, 100);
            const long long elapsedMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                                            std::chrono::steady_clock::now() - start)
                                            .count();

            const itimerval off{};
            ::setitimer(ITIMER_REAL, &off, nullptr);
            ::sigaction(SIGALRM, &previous, nullptr);
            ::close(fd);

            t.Equals(n, 0, "an interrupted wait on a socket with no data must report a timeout (0), "
                           "not an error the guest reads as a dead socket");
            t.IsTrue(elapsedMs >= 90, "and it must have waited out the 100 ms it was given, not "
                                      "returned at the first signal");
            t.IsTrue(elapsedMs < 2000, "and it must recompute the remaining time, not restart the "
                                       "full timeout on every signal");
#endif
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

            // A name that cannot resolve returns 0; serverForKnob turns that into a refusal (below).
            const uint32_t bad = socom2_hostnet::parseServerAddress("no-such-host.invalid");
            t.Equals(bad, 0u, "an unresolvable name must report failure rather than a stale address");
        });

        // Sprint 13 V8 (KNOWN section 4's hazard row; carry-backlog row 91): a PS2X_SOCOM2_SERVER that does not
        // resolve silently became 127.0.0.1, so a stranger whose DNS failed met an unexplained "cannot connect".
        // Now the value is refused: the retail names resolve to nothing and the log carries the server-unresolved
        // [notice] line, which the launcher's LAST RUN appends to the run's own exit sentence. Ruling S13-R9: a
        // notice, not an exit code -- the process's exit code is left as it was (65 or 72 say more).
        tc.Run("a PS2X_SOCOM2_SERVER that does not resolve is refused with a LAST RUN notice, never loopback", [](TestCase &t)
        {
            t.IsTrue(socom2_hostnet::init(), "hostnet init must succeed");
            std::string refusal;
            t.Equals(socom2_hostnet::serverForKnob(nullptr, refusal), 0x7f000001u, "unset: the local Horizon stack, as always");
            t.IsTrue(refusal.empty(), "unset is not a refusal");
            t.Equals(socom2_hostnet::serverForKnob("", refusal), 0x7f000001u, "empty is unset");
            t.Equals(socom2_hostnet::serverForKnob("192.0.2.5", refusal), 0xc0000205u, "an address is taken as it is (TEST-NET-1)");
            t.IsTrue(refusal.empty(), "an address is not a refusal");

            const uint32_t bad = socom2_hostnet::serverForKnob("no-such-host.invalid", refusal);
            t.Equals(bad, 0u, "a name that does not resolve is refused, not loopback");
            t.Equals(refusal, ExitCodes::noticeLine(ExitCodes::kServerUnresolved),
                     "the refusal is the server-unresolved [notice] line: " + refusal);
            t.Equals(launcher::lastRunLine(0, "boot\n" + refusal + "\n"),
                     std::string("The last run exited normally. The server name on the ONLINE page did not resolve, so the "
                                 "game stayed offline. Check your connection or the name."),
                     "LAST RUN appends the sentence to a clean exit");
            t.Equals(launcher::lastRunLine(65, refusal + "\n"),
                     std::string(ExitCodes::find(65)->sentence) + " " + ExitCodes::kServerUnresolved.sentence,
                     "and to the slow renderer's 65, which it no longer overwrites");
            t.IsNull(ExitCodes::find(75), "no exit code 75 anywhere");

            // The table half: every retail name refused, the exit code untouched; then put back as init() left it.
            const int exitBefore = ps2ProcessExitCode();
            setPs2ProcessExitCode(65);
            socom2_hostnet::testApplyServer("no-such-host.invalid");
            t.Equals(socom2_hostnet::resolve("socom2-prod.muis.pdonline.scea.com"), 0u,
                     "the game's lookup of the retail name fails (kErrDns), instead of reaching loopback or Sony");
            t.Equals(socom2_hostnet::resolve("gate1.us.dnas.playstation.org"), 0u, "every retail name, DNAS too");
            t.Equals(ps2ProcessExitCode(), 65, "the process's exit code is left as it was");
            socom2_hostnet::testApplyServer(nullptr);
            t.Equals(socom2_hostnet::resolve("socom2-prod.muis.pdonline.scea.com"), 0x7f000001u, "restored to loopback");
            setPs2ProcessExitCode(exitBefore);
        });
    });
}
