// SOCOM II libnetb HLE — see socom2_libnetb.h and docs/research/10-libnetb-rpc.md.
//
// Two layers of the game reach libnetb:
//  * the "simple" RPCs (fno 1..0x35): sceInetCreate/Open/Close/Recv/Send/RecvFrom/SendTo,
//    Name2Address, interface queries, poll, inetctl events. Answered here from the send buffer
//    into the receive buffer with the exact word layouts of the IOP module.
//  * the libnetb_ex path (fno 100/0x65 + EE ring buffers filled by raw SIF DMA). The SCE-RT
//    platform layer (Medius/rt_udp/rt_tcp) uses it for all game traffic. Emulating the rings
//    would require intercepting SIF DMA to fake IOP addresses, so instead the EE functions that
//    move data through the rings are replaced by host implementations keyed on the cid stored in
//    the platform handle (+8). The rings are still allocated by the game (harmless).
//
// cid = host descriptor + 1 (cids are > 0). Addresses use sceInetAddress_t: {0, ip, 0, 0} with
// ip as a native u32 in host order; ports are ints in host order (-1 = any).
#include "socom2_libnetb.h"
#include "socom2_hostnet.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <deque>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

namespace socom2_libnetb
{
    namespace
    {
        using socom2_hostnet::Endpoint;
        using socom2_hostnet::Proto;

        constexpr int32_t kErrTimeout = -500;
        constexpr int32_t kErrAbort = -0x1f5;
        constexpr int32_t kErrRefused = -0x1ff;
        constexpr int32_t kErrInvalid = -0x200;
        constexpr int32_t kErrUnhandled = -0x21d;
        constexpr int32_t kErrNoEvent = -0x220;
        constexpr int32_t kErrDns = -0x203;
        constexpr uint32_t kIfId = 1u;

        enum SocketType : int32_t { kDgram = 0, kConnect = 1, kListen = 2, kRaw = 3 };

        struct Probe
        {
            uint32_t ip;
            uint16_t port;
        };

        struct Cid
        {
            bool used = false;
            int fd = -1;
            int32_t type = kDgram;
            Endpoint remote;
            bool connecting = false;
            bool closed = false;
            int32_t error = 0;
            std::deque<Probe> probes;   // raw "ICMP" probes answered locally
        };

        std::mutex g_mutex;
        std::array<Cid, 64> g_cids;
        bool g_verbose = std::getenv("PS2X_SOCOM2_NET_TRACE") != nullptr;

        uint32_t rd32(const uint8_t *rdram, uint32_t addr)
        {
            uint32_t v;
            std::memcpy(&v, rdram + (addr & PS2_RAM_MASK), 4);
            return v;
        }

        void wr32(uint8_t *rdram, uint32_t addr, uint32_t v)
        {
            std::memcpy(rdram + (addr & PS2_RAM_MASK), &v, 4);
        }

        uint8_t *ptr(uint8_t *rdram, uint32_t addr) { return rdram + (addr & PS2_RAM_MASK); }

        void writeAddress(uint8_t *rdram, uint32_t addr, uint32_t ip)
        {
            wr32(rdram, addr, 0u);
            wr32(rdram, addr + 4u, ip);
            wr32(rdram, addr + 8u, 0u);
            wr32(rdram, addr + 12u, 0u);
        }

        Cid *cidEntry(int32_t cid)
        {
            if (cid <= 0 || cid > static_cast<int32_t>(g_cids.size()))
                return nullptr;
            Cid &c = g_cids[cid - 1];
            return c.used ? &c : nullptr;
        }

        int32_t allocCid(int fd, int32_t type)
        {
            for (size_t i = 0; i < g_cids.size(); ++i)
            {
                if (!g_cids[i].used)
                {
                    g_cids[i] = Cid{};
                    g_cids[i].used = true;
                    g_cids[i].fd = fd;
                    g_cids[i].type = type;
                    return static_cast<int32_t>(i + 1);
                }
            }
            return 0;
        }

        void trace(const std::string &s)
        {
            if (g_verbose)
                std::cout << "[socom2/libnetb] " << s << std::endl;
        }

        std::string ipStr(uint32_t ip) { return socom2_hostnet::ipToString(ip); }

        int32_t mapHostError(int e)
        {
            switch (e)
            {
            case -111: return kErrRefused;
            case -110: return kErrTimeout;
            case -11: return kErrTimeout;
            case -104: return -0x1fe;
            case -107: return -0x1fc;
            default: return kErrAbort;
            }
        }

        // ---- simple RPCs -----------------------------------------------------------------

        int32_t doCreate(uint8_t *rdram, uint32_t send)
        {
            const int32_t type = static_cast<int32_t>(rd32(rdram, send + 4u));
            int32_t localPort = static_cast<int32_t>(rd32(rdram, send + 8u));
            // PS2X_SOCOM2_UDP_SHIFT=n: a second client on the same host must not bind the game's
            // fixed UDP ports (3658/3659); shift its local UDP ports by n (PCSX2 client B does the
            // same with the 0F6FC6CF.clientB.pnach). Peers learn the real port from the packets.
            static const int32_t s_udpShift = [] { const char *e = std::getenv("PS2X_SOCOM2_UDP_SHIFT"); return e ? std::atoi(e) : 0; }();
            if (s_udpShift != 0 && localPort > 0 && type != kConnect && type != kListen)
                localPort += s_udpShift;
            const uint32_t remoteIp = rd32(rdram, send + 16u);
            const int32_t remotePort = static_cast<int32_t>(rd32(rdram, send + 28u));
            const Proto proto = (type == kConnect || type == kListen) ? Proto::Tcp : Proto::Udp;
            const int fd = socom2_hostnet::createSocket(proto);
            if (fd < 0)
                return kErrAbort;
            if (localPort > 0 || type == kListen)
            {
                Endpoint local;
                local.port = static_cast<uint16_t>(localPort > 0 ? localPort : 0);
                if (socom2_hostnet::bindSocket(fd, local) < 0)
                {
                    socom2_hostnet::closeSocket(fd);
                    return -0x1f9;
                }
            }
            if (type == kListen)
                socom2_hostnet::listenSocket(fd, 4);
            const int32_t cid = allocCid(fd, type);
            if (cid == 0)
            {
                socom2_hostnet::closeSocket(fd);
                return -0x1f8;
            }
            Cid *c = cidEntry(cid);
            c->remote.ip = remoteIp;
            c->remote.port = static_cast<uint16_t>(remotePort > 0 ? remotePort : 0);
            trace("create type=" + std::to_string(type) + " local=" + std::to_string(localPort) + " remote=" + ipStr(remoteIp) +
                  ":" + std::to_string(remotePort) + " -> cid " + std::to_string(cid));
            return cid;
        }

        int32_t doOpen(int32_t cid, int32_t timeoutMs)
        {
            Cid *c = cidEntry(cid);
            if (!c)
                return -0x1fc;
            if (c->type != kConnect)
                return 0;
            int r = c->connecting ? socom2_hostnet::connectStatus(c->fd) : socom2_hostnet::connectSocket(c->fd, c->remote);
            if (r == 1)
            {
                c->connecting = true;
                const int waitMs = timeoutMs < 0 ? 10000 : timeoutMs;
                const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(waitMs);
                while (r == 1 && std::chrono::steady_clock::now() < deadline)
                {
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    r = socom2_hostnet::connectStatus(c->fd);
                }
            }
            if (r == 0)
            {
                c->connecting = false;
                trace("open cid " + std::to_string(cid) + " connected to " + ipStr(c->remote.ip) + ":" + std::to_string(c->remote.port));
                return 0;
            }
            if (r == 1)
                return kErrTimeout;
            c->connecting = false;
            c->error = mapHostError(r);
            trace("open cid " + std::to_string(cid) + " failed " + std::to_string(r));
            return c->error;
        }

        int32_t doClose(int32_t cid)
        {
            Cid *c = cidEntry(cid);
            if (!c)
                return -0x1fc;
            socom2_hostnet::closeSocket(c->fd);
            *c = Cid{};
            trace("close cid " + std::to_string(cid));
            return 0;
        }

        // Wait up to timeoutMs for readability (timeout < 0 = 10 s cap, 0 = poll).
        bool waitReadable(Cid *c, int32_t timeoutMs)
        {
            const int waitMs = timeoutMs < 0 ? 10000 : timeoutMs;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(waitMs);
            for (;;)
            {
                const int m = socom2_hostnet::poll(c->fd, 0);
                if (m > 0 && (m & 5))
                    return true;
                if (std::chrono::steady_clock::now() >= deadline)
                    return false;
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
        }
    }

    void call(uint8_t *rdram, uint32_t fno, uint32_t send, uint32_t sendSize, uint32_t recv, uint32_t recvSize)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        socom2_hostnet::init();
        auto p = [&](uint32_t i) { return rd32(rdram, send + i * 4u); };
        auto r = [&](uint32_t i, uint32_t v) { wr32(rdram, recv + i * 4u, v); };
        if (recv != 0u && recvSize != 0u && recv != send)
            std::memset(ptr(rdram, recv), 0, recvSize);

        switch (fno)
        {
        case 1: // sceInetCreate
        {
            const int32_t cid = doCreate(rdram, send);
            r(0, static_cast<uint32_t>(cid));
            break;
        }
        case 2: // sceInetOpen(cid, timeout)
            r(0, static_cast<uint32_t>(doOpen(static_cast<int32_t>(p(0)), static_cast<int32_t>(p(1)))));
            break;
        case 3: // sceInetClose(cid, timeout)
            r(0, static_cast<uint32_t>(doClose(static_cast<int32_t>(p(0)))));
            break;
        case 4: // sceInetRecv(cid, flags, len, timeout) -> p[0] n, p[1] flags, data at p[2]
        {
            Cid *c = cidEntry(static_cast<int32_t>(p(0)));
            const uint32_t len = p(2);
            const int32_t timeout = static_cast<int32_t>(p(3));
            if (!c) { r(0, static_cast<uint32_t>(-0x1fc)); break; }
            if (timeout != 0)
                waitReadable(c, timeout);
            int n = socom2_hostnet::recv(c->fd, ptr(rdram, recv + 8u), len);
            uint32_t flags = 0;
            if (n == 0) { flags = 4; }
            else if (n == -11) { n = kErrTimeout; }
            else if (n < 0) { n = mapHostError(n); }
            r(0, static_cast<uint32_t>(n));
            r(1, flags);
            break;
        }
        case 5: // sceInetSend(cid, flags, len, timeout, data at p[4])
        {
            Cid *c = cidEntry(static_cast<int32_t>(p(0)));
            if (!c) { r(0, static_cast<uint32_t>(-0x1fc)); break; }
            int n = socom2_hostnet::send(c->fd, ptr(rdram, send + 16u), p(2));
            if (n < 0) n = mapHostError(n);
            r(0, static_cast<uint32_t>(n));
            r(1, 0u);
            break;
        }
        case 6: // sceInetName2Address: name at byte 0x14 -> p[0] result, address at p[1..4]
        {
            std::string name(reinterpret_cast<const char *>(ptr(rdram, send + 0x14u)));
            const uint32_t ip = socom2_hostnet::resolve(name);
            if (ip == 0) { r(0, static_cast<uint32_t>(kErrDns)); trace("resolve " + name + " failed"); break; }
            r(0, 0u);
            writeAddress(rdram, recv + 4u, ip);
            trace("resolve " + name + " -> " + ipStr(ip));
            break;
        }
        case 7: // sceInetAddress2String(outlen, addr at p[1..4]) -> string at byte 0x14
        {
            const std::string s = ipStr(p(2));
            const uint32_t outlen = p(0);
            std::snprintf(reinterpret_cast<char *>(ptr(rdram, recv + 0x14u)), outlen ? outlen : 16u, "%s", s.c_str());
            r(0, 0u);
            break;
        }
        case 8: // sceInetGetInterfaceList(max) -> count, ids
            r(0, 1u);
            r(1, kIfId);
            break;
        case 9: // sceInetInterfaceControl(id, code, len) payload at p[3]
        {
            const uint32_t code = p(1);
            const uint32_t len = p(2);
            r(0, 0u);
            switch (code)
            {
            case 2: std::snprintf(reinterpret_cast<char *>(ptr(rdram, recv + 12u)), len ? len : 16u, "%s", "smap0"); break;
            case 3: std::snprintf(reinterpret_cast<char *>(ptr(rdram, recv + 12u)), len ? len : 32u, "%s", "SCE Ethernet (Network Adaptor)"); break;
            case 8: r(3, 3u); break;                                    // attached + up
            case 9: writeAddress(rdram, recv + 12u, socom2_hostnet::localIp()); break;
            case 0xb: writeAddress(rdram, recv + 12u, 0xffffff00u); break;
            case 0x200: r(3, 0u); break;
            default: break;
            }
            break;
        }
        case 0xd: // sceInetRecvFrom(cid, flags, len, timeout) -> n, flags, from addr p[2..5], port p[6], data p[7]
        {
            Cid *c = cidEntry(static_cast<int32_t>(p(0)));
            const uint32_t len = p(2);
            const int32_t timeout = static_cast<int32_t>(p(3));
            if (!c) { r(0, static_cast<uint32_t>(-0x1fc)); break; }
            if (timeout != 0)
                waitReadable(c, timeout);
            Endpoint from;
            int n = socom2_hostnet::recvFrom(c->fd, ptr(rdram, recv + 0x1cu), len, &from);
            if (n == -11) n = kErrTimeout;
            else if (n < 0) n = mapHostError(n);
            r(0, static_cast<uint32_t>(n));
            r(1, 0u);
            if (n >= 0)
            {
                writeAddress(rdram, recv + 8u, from.ip);
                r(6, from.port);
            }
            break;
        }
        case 0xe: // sceInetSendTo(cid, flags, len, timeout, port p[4], addr p[5..8], data p[9])
        {
            Cid *c = cidEntry(static_cast<int32_t>(p(0)));
            if (!c) { r(0, static_cast<uint32_t>(-0x1fc)); break; }
            Endpoint to;
            to.ip = p(6);
            to.port = static_cast<uint16_t>(p(4));
            int n = socom2_hostnet::sendTo(c->fd, ptr(rdram, send + 0x24u), p(2), to);
            if (n < 0) n = mapHostError(n);
            r(0, static_cast<uint32_t>(n));
            r(1, 0u);
            break;
        }
        case 0xf: // sceInetAbort
            r(0, 0u);
            break;
        case 0x12: // sceInetAddress2Name -> name at byte 0x20
        {
            const std::string s = ipStr(p(5));
            std::snprintf(reinterpret_cast<char *>(ptr(rdram, recv + 0x20u)), p(1) ? p(1) : 16u, "%s", s.c_str());
            r(0, 0u);
            break;
        }
        case 0x13: // sceInetControl(cid, code, len) payload at p[3]
        {
            Cid *c = cidEntry(static_cast<int32_t>(p(0)));
            const uint32_t code = p(1);
            r(0, 0u);
            if (!c) { r(0, static_cast<uint32_t>(-0x1fc)); break; }
            if (code == 1)
            {
                const uint32_t info = recv + 12u;
                Endpoint local, peer;
                socom2_hostnet::localName(c->fd, &local);
                const bool tcp = (c->type == kConnect || c->type == kListen);
                if (tcp)
                    socom2_hostnet::peerName(c->fd, &peer);
                else
                    peer = c->remote;
                wr32(rdram, info + 0u, static_cast<uint32_t>(p(0)));
                wr32(rdram, info + 4u, tcp ? 1u : 2u);
                wr32(rdram, info + 8u, static_cast<uint32_t>(std::max(0, socom2_hostnet::readable(c->fd))));
                wr32(rdram, info + 12u, 0u);
                writeAddress(rdram, info + 0x10u, local.ip);
                wr32(rdram, info + 0x20u, local.port);
                writeAddress(rdram, info + 0x24u, peer.ip);
                wr32(rdram, info + 0x34u, peer.port);
                wr32(rdram, info + 0x38u, tcp ? (c->type == kListen ? 4u : 7u) : 3u);
            }
            break;
        }
        case 0x14: // sceInetPoll(nfds, timeout, fds at p[2..])
        {
            const uint32_t nfds = p(0);
            uint32_t ready = 0;
            for (uint32_t i = 0; i < nfds && i < 32u; ++i)
            {
                const int32_t cid = static_cast<int32_t>(p(2 + i * 2));
                const uint32_t events = p(3 + i * 2);
                Cid *c = cidEntry(cid);
                uint32_t revents = 0;
                if (c)
                {
                    const int m = socom2_hostnet::poll(c->fd, 0);
                    if (m > 0)
                        revents = static_cast<uint32_t>(m) & 7u;
                }
                if (revents)
                    ++ready;
                r(2 + i * 2, static_cast<uint32_t>(cid));
                r(3 + i * 2, (events & 0xffffu) | (revents << 16));
            }
            r(0, ready);
            break;
        }
        case 0x1e: case 0x1f: case 0x20: case 0x32: case 0x33: case 0x34:
            r(0, 0u);
            break;
        case 0x21: // wait interface attached
            r(0, 1u); r(1, kIfId); r(2, 0u);
            break;
        case 0x22: // wait interface started
            r(0, 4u); r(1, kIfId); r(2, 0u);
            break;
        case 0x23:
            r(0, static_cast<uint32_t>(kErrNoEvent)); r(1, static_cast<uint32_t>(-1));
            break;
        case 0x35: // sceInetCtlGetState
            r(0, 0u); r(1, 3u);
            break;
        case 0x66: // libnetb_ex close(cid, timeout)
            r(0, static_cast<uint32_t>(doClose(static_cast<int32_t>(p(0)))));
            break;
        case 0x64: case 0x65: // start async recv/send: never reached (EE path replaced)
            r(8, 0u);
            break;
        case 0x67:
            break;
        default:
            std::cout << "[socom2/libnetb] unhandled fno=0x" << std::hex << fno << std::dec << " send=" << sendSize << " recv=" << recvSize << std::endl;
            r(0, static_cast<uint32_t>(kErrUnhandled));
            break;
        }
    }

    // ---- libnetb_ex EE replacements ---------------------------------------------------------
    // Platform handle (0x28 bytes): [0] type, [1] remote port, [2] cid, [3] max datagram,
    // [8] recv descriptor (EE), [9] send descriptor (EE); descriptor +0x0c = state (0 ok, 3 err).

    namespace
    {
        void ret(R5900Context *ctx, uint32_t v)
        {
            SET_GPR_U32(ctx, 2, v);
            ctx->pc = GPR_U32(ctx, 31);
        }

        Cid *handleCid(uint8_t *rdram, uint32_t handle)
        {
            if (handle == 0u)
                return nullptr;
            return cidEntry(static_cast<int32_t>(rd32(rdram, handle + 8u)));
        }
    }

    // FUN_002472c8(cd, buf, handle, timeout): open the connection behind the handle.
    void exOpen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 6);
        const int32_t timeout = static_cast<int32_t>(GPR_U32(ctx, 7));
        if (handle == 0u) { ret(ctx, static_cast<uint32_t>(kErrInvalid)); return; }
        const int32_t type = static_cast<int32_t>(rd32(rdram, handle));
        const int32_t cid = static_cast<int32_t>(rd32(rdram, handle + 8u));
        int32_t result = 0;
        if (type == kConnect)
        {
            result = doOpen(cid, timeout);
            // Non-blocking (timeout 0) connects: the original returns success with the descriptor
            // in state 1 (opening) and the IOP finishes the handshake; the client polls
            // FUN_00247bd8 (exConnected) until it reports connected. Mirror that.
            if (result == kErrTimeout)
                result = 0;
        }
        Cid *c = cidEntry(cid);
        const bool pending = (c && c->connecting);
        const uint32_t state = result == 0 ? (pending ? 1u : 0u) : 3u;
        for (uint32_t i = 8; i <= 9; ++i)
        {
            const uint32_t desc = rd32(rdram, handle + i * 4u);
            if (desc)
            {
                wr32(rdram, desc + 0x0cu, state);
                wr32(rdram, desc + 0x10u, static_cast<uint32_t>(cid));
                wr32(rdram, desc + 0x34u, static_cast<uint32_t>(type));
                wr32(rdram, desc + 0x00u, 0u);
            }
        }
        trace("exOpen handle=0x" + [&]{ std::ostringstream o; o << std::hex << handle; return o.str(); }() +
              " type=" + std::to_string(type) + " cid=" + std::to_string(cid) + " -> " + std::to_string(result));
        ret(ctx, static_cast<uint32_t>(result == 0 ? 0 : kErrAbort));
    }

    // FUN_002474f8(cd, buf, handle, dst, len, flags_out*): TCP receive, non-blocking.
    void exTcpRecv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 6);
        const uint32_t dst = GPR_U32(ctx, 7);
        const uint32_t len = GPR_U32(ctx, 8);
        const uint32_t flagsOut = GPR_U32(ctx, 9);
        Cid *c = handleCid(rdram, handle);
        if (!c || dst == 0u) { ret(ctx, static_cast<uint32_t>(kErrInvalid)); return; }
        if (flagsOut) wr32(rdram, flagsOut, 0u);
        if (c->closed) { if (flagsOut) wr32(rdram, flagsOut, 4u); ret(ctx, 0u); return; }
        int n = socom2_hostnet::recv(c->fd, ptr(rdram, dst), len);
        if (n == 0)
        {
            c->closed = true;
            if (flagsOut) wr32(rdram, flagsOut, 4u);
            trace("tcp recv cid " + std::to_string(c->fd + 1) + ": closed by peer");
            ret(ctx, 0u);
            return;
        }
        if (n == -11)
        {
            // Idle poll: trace the first few and then every 256th so the log shows the pump is alive.
            static uint32_t idle = 0;
            ++idle;
            if (g_verbose && (idle <= 4 || (idle & 0xffu) == 0u))
                trace("tcp recv cid " + std::to_string(c->fd + 1) + " max=" + std::to_string(len) + " -> would-block (#" + std::to_string(idle) + ")");
            ret(ctx, 0u);
            return;
        }
        if (n < 0) { trace("tcp recv cid " + std::to_string(c->fd + 1) + " host error " + std::to_string(n)); ret(ctx, static_cast<uint32_t>(kErrAbort)); return; }
        if (g_verbose)
        {
            std::ostringstream o;
            o << "tcp recv cid " << (c->fd + 1) << " max=" << len << " -> " << n << " [";
            for (int i = 0; i < std::min(n, 40); ++i)
                o << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(ptr(rdram, dst)[i]) << ' ';
            o << "]";
            trace(o.str());
        }
        ret(ctx, static_cast<uint32_t>(n));
    }

    // FUN_00247738(cd, buf, handle, src, len): TCP send.
    void exTcpSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 6);
        const uint32_t src = GPR_U32(ctx, 7);
        const uint32_t len = GPR_U32(ctx, 8);
        Cid *c = handleCid(rdram, handle);
        if (!c || src == 0u) { ret(ctx, static_cast<uint32_t>(kErrInvalid)); return; }
        int n = socom2_hostnet::send(c->fd, ptr(rdram, src), len);
        if (n == -11) n = 0;
        if (g_verbose)
        {
            std::ostringstream o;
            o << "tcp send cid " << (c->fd + 1) << " len=" << len << " -> " << n << " [";
            for (uint32_t i = 0; i < std::min<uint32_t>(len, 96u); ++i)
                o << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(ptr(rdram, src)[i]) << ' ';
            o << "]";
            trace(o.str());
        }
        if (n < 0) { ret(ctx, static_cast<uint32_t>(kErrAbort)); return; }
        ret(ctx, static_cast<uint32_t>(n));
    }

    // FUN_00247d30(handle, dst, maxlen, flags_out*, addr_out*, port_out*, len_out*, result_out*)
    void exUdpRecv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 4);
        const uint32_t dst = GPR_U32(ctx, 5);
        const uint32_t maxlen = GPR_U32(ctx, 6);
        const uint32_t flagsOut = GPR_U32(ctx, 7);
        const uint32_t addrOut = GPR_U32(ctx, 8);
        const uint32_t portOut = GPR_U32(ctx, 9);
        const uint32_t lenOut = GPR_U32(ctx, 10);
        const uint32_t resultOut = GPR_U32(ctx, 11);
        if (lenOut) wr32(rdram, lenOut, 0u);
        if (flagsOut) wr32(rdram, flagsOut, 0u);
        if (resultOut) wr32(rdram, resultOut, 0u);
        Cid *c = handleCid(rdram, handle);
        if (!c || dst == 0u || maxlen == 0u || !addrOut || !portOut || !lenOut || !resultOut) { ret(ctx, 2u); return; }
        if (c->type == kRaw)
        {
            if (!c->probes.empty())
            {
                const Probe pr = c->probes.front();
                c->probes.pop_front();
                uint16_t payload = pr.port;
                std::memcpy(ptr(rdram, dst), &payload, std::min<uint32_t>(2u, maxlen));
                writeAddress(rdram, addrOut, pr.ip);
                wr32(rdram, portOut, pr.port);
                wr32(rdram, lenOut, std::min<uint32_t>(2u, maxlen));
                wr32(rdram, resultOut, 2u);
                trace("probe reply from " + ipStr(pr.ip) + " port " + std::to_string(pr.port));
            }
            ret(ctx, 0u);
            return;
        }
        Endpoint from;
        int n = socom2_hostnet::recvFrom(c->fd, ptr(rdram, dst), maxlen, &from);
        if (n > 0)
        {
            writeAddress(rdram, addrOut, from.ip);
            wr32(rdram, portOut, from.port);
            wr32(rdram, lenOut, static_cast<uint32_t>(n));
            wr32(rdram, resultOut, static_cast<uint32_t>(n));
        }
        ret(ctx, 0u);
    }

    // FUN_00247fe8(handle, src, len, flags, addr*, port, sent_out*, result_out*)
    void exUdpSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 4);
        const uint32_t src = GPR_U32(ctx, 5);
        const uint32_t len = GPR_U32(ctx, 6);
        const uint32_t addr = GPR_U32(ctx, 8);
        const uint32_t port = GPR_U32(ctx, 9);
        const uint32_t sentOut = GPR_U32(ctx, 10);
        const uint32_t resultOut = GPR_U32(ctx, 11);
        if (sentOut) wr32(rdram, sentOut, 0u);
        if (resultOut) wr32(rdram, resultOut, 0u);
        Cid *c = handleCid(rdram, handle);
        if (!c || src == 0u || len == 0u || !addr || !sentOut || !resultOut) { ret(ctx, 2u); return; }
        Endpoint to;
        to.ip = rd32(rdram, addr + 4u);
        to.port = static_cast<uint16_t>(port);
        if (c->type == kRaw)
        {
            // ICMP reachability probe: answered locally as an echo from the target.
            uint16_t payloadPort = 0;
            std::memcpy(&payloadPort, ptr(rdram, src), std::min<uint32_t>(2u, len));
            c->probes.push_back(Probe{to.ip, payloadPort});
            wr32(rdram, sentOut, len);
            wr32(rdram, resultOut, len);
            trace("probe to " + ipStr(to.ip) + " port " + std::to_string(payloadPort) + " (answered locally)");
            ret(ctx, 0u);
            return;
        }
        int n = socom2_hostnet::sendTo(c->fd, ptr(rdram, src), len, to);
        if (n < 0)
        {
            wr32(rdram, resultOut, static_cast<uint32_t>(mapHostError(n)));
            ret(ctx, 1u);
            return;
        }
        wr32(rdram, sentOut, static_cast<uint32_t>(n));
        wr32(rdram, resultOut, static_cast<uint32_t>(n));
        ret(ctx, 0u);
    }

    // FUN_002479b8(handle, out*): bytes available (TCP) / pending accept (listen); *out = flags.
    void exAvailable(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 4);
        const uint32_t out = GPR_U32(ctx, 5);
        Cid *c = handleCid(rdram, handle);
        if (!c || out == 0u) { ret(ctx, static_cast<uint32_t>(kErrInvalid)); return; }
        wr32(rdram, out, c->closed ? 4u : 0u);
        if (c->type == kListen) { ret(ctx, 0u); return; }
        const int n = socom2_hostnet::readable(c->fd);
        ret(ctx, static_cast<uint32_t>(n < 0 ? 0 : n));
    }

    // FUN_00247bd8(handle, out*): *out = 1 when the connection is up; error code when it failed.
    void exConnected(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        const uint32_t handle = GPR_U32(ctx, 4);
        const uint32_t out = GPR_U32(ctx, 5);
        Cid *c = handleCid(rdram, handle);
        if (!c || out == 0u) { ret(ctx, static_cast<uint32_t>(kErrInvalid)); return; }
        wr32(rdram, out, 0u);
        if (c->error != 0) { ret(ctx, static_cast<uint32_t>(c->error)); return; }
        if (c->connecting)
        {
            const int r = socom2_hostnet::connectStatus(c->fd);
            if (r == 0) c->connecting = false;
            else if (r < 0) { c->error = mapHostError(r); ret(ctx, static_cast<uint32_t>(c->error)); return; }
        }
        wr32(rdram, out, c->connecting ? 0u : 1u);
        ret(ctx, 0u);
    }

    // FUN_00248350 / FUN_002483f8: start the IOP async threads — not needed on the host.
    void exStartAsync(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        ret(ctx, 0u);
    }
}
