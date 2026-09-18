#include "socom2_hostnet.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define NOGDI
#define NOUSER
#include <winsock2.h>
#include <ws2tcpip.h>
#else
// The BSD half. Same call graph throughout; only the spellings differ.
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <errno.h>
#include <poll.h>
#endif

#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace socom2_hostnet
{
    // Defined below, forward-declared here because loadHosts() (file-local) calls it. Not in the
    // public header: it exists so socom2_libnetb_tests.cpp can drive the PS2X_SOCOM2_SERVER
    // parse without touching the process environment or re-running init().
    uint32_t parseServerAddress(const std::string &value);

    // The platform's error reporting, at namespace scope for the same reason parseServerAddress
    // is: socom2_libnetb_tests.cpp drives them directly, and "what does this platform call
    // would-block" is the one piece of the BSD/Winsock split a test can check without a network.
    // hostnetLastError() is WSAGetLastError() on Windows and errno elsewhere.
    int hostnetLastError();
    bool hostnetWouldBlock(int err);

    namespace
    {
#ifdef _WIN32
        using SocketHandle = SOCKET;
        constexpr SocketHandle kInvalidSocket = INVALID_SOCKET;
        using SockLen = int;        // the address-length in/out parameter of accept/getsockname
        using IoLen = int;          // the size argument of send/recv
        using IoResult = int;       // what send/recv return
        using SendBuf = const char *;
        using RecvBuf = char *;
#else
        using SocketHandle = int;
        constexpr SocketHandle kInvalidSocket = -1;
        using SockLen = socklen_t;
        using IoLen = size_t;
        using IoResult = ssize_t;
        using SendBuf = const void *;
        using RecvBuf = void *;
#endif

        constexpr int kMaxSockets = 64;

        struct Entry
        {
            SocketHandle s = kInvalidSocket;
            Proto proto = Proto::Tcp;
            bool used = false;
            bool connecting = false;
            bool blocking = false;
        };

        std::mutex g_mutex;
        // Total bytes received on every socket this table owns. The PS2 inet stack exposes
        // interface statistics through sceInetInterfaceControl, and SOCOM II uses one of them as a
        // "has anything arrived lately" tick (see rxBytes() in the header). Guarded by g_mutex,
        // which every receive path already holds.
        uint64_t g_rxBytes = 0;
        std::array<Entry, kMaxSockets> g_table;
        bool g_initialized = false;
        std::string g_lastError;
        std::map<std::string, uint32_t> g_hosts;

        // Would-block is tested before the switch rather than as a case of it because EWOULDBLOCK
        // and EAGAIN are the same value on Linux, which a switch cannot spell twice. The Windows
        // arm maps the same codes to the same guest errnos it always did.
        int mapError()
        {
            const int e = hostnetLastError();
            if (hostnetWouldBlock(e))
                return -11;                       // EAGAIN
#ifdef _WIN32
            switch (e)
            {
            case WSAEINPROGRESS: return -115;     // EINPROGRESS
            case WSAECONNREFUSED: return -111;
            case WSAETIMEDOUT: return -110;
            case WSAEHOSTUNREACH: return -113;
            case WSAENOTCONN: return -107;
            case WSAECONNRESET: return -104;
            case WSAEADDRINUSE: return -98;
            default: return -5;                   // EIO
            }
#else
            switch (e)
            {
            case EINPROGRESS: return -115;
            case ECONNREFUSED: return -111;
            case ETIMEDOUT: return -110;
            case EHOSTUNREACH: return -113;
            case ENOTCONN: return -107;
            case ECONNRESET: return -104;
            case EADDRINUSE: return -98;
            default: return -5;                   // EIO
            }
#endif
        }

        void hostnetSetLastError(int err)
        {
#ifdef _WIN32
            WSASetLastError(err);
#else
            errno = err;
#endif
        }

        void hostnetClose(SocketHandle s)
        {
#ifdef _WIN32
            ::closesocket(s);
#else
            ::close(s);
#endif
        }

        // 0 on success, non-zero on failure -- the ioctlsocket convention the call sites expect.
        int hostnetSetNonBlocking(SocketHandle s, bool nonBlocking)
        {
#ifdef _WIN32
            u_long nb = nonBlocking ? 1u : 0u;
            return ::ioctlsocket(s, FIONBIO, &nb);
#else
            const int flags = ::fcntl(s, F_GETFL, 0);
            if (flags < 0)
                return -1;
            const int want = nonBlocking ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
            return ::fcntl(s, F_SETFL, want) < 0 ? -1 : 0;
#endif
        }

        int hostnetReadableBytes(SocketHandle s, int *bytes)
        {
#ifdef _WIN32
            u_long n = 0;
            if (::ioctlsocket(s, FIONREAD, &n) != 0)
                return -1;
            *bytes = static_cast<int>(n);
#else
            int n = 0;
            if (::ioctl(s, FIONREAD, &n) != 0)
                return -1;
            *bytes = n;
#endif
            return 0;
        }

        Entry *entry(int fd)
        {
            if (fd < 0 || fd >= kMaxSockets || !g_table[fd].used)
                return nullptr;
            return &g_table[fd];
        }

        sockaddr_in toAddr(const Endpoint &ep)
        {
            sockaddr_in a{};
            a.sin_family = AF_INET;
            a.sin_port = htons(ep.port);
            a.sin_addr.s_addr = htonl(ep.ip);
            return a;
        }

        Endpoint fromAddr(const sockaddr_in &a)
        {
            Endpoint ep;
            ep.ip = ntohl(a.sin_addr.s_addr);
            ep.port = ntohs(a.sin_port);
            return ep;
        }

        uint32_t parseIp(const std::string &s)
        {
            in_addr a{};
            if (inet_pton(AF_INET, s.c_str(), &a) == 1)
                return ntohl(a.s_addr);
            return 0;
        }

        void loadHosts()
        {
            uint32_t server = 0x7f000001u;
            if (const char *env = std::getenv("PS2X_SOCOM2_SERVER"))
            {
                const uint32_t ip = parseServerAddress(env);
                if (ip)
                    server = ip;
            }
            for (const char *name : {"socom2-prod.pdonline.scea.com", "socom2-prod.svo.pdonline.scea.com",
                                     "socom2-prod.muis.pdonline.scea.com", "gate1.us.dnas.playstation.org",
                                     "gate1.jp.dnas.playstation.org", "gate1.eu.dnas.playstation.org",
                                     "updates.pdonline.scea.com"})
                g_hosts[name] = server;
            if (const char *env = std::getenv("PS2X_SOCOM2_HOSTS"))
            {
                std::stringstream ss(env);
                std::string item;
                while (std::getline(ss, item, ','))
                {
                    const auto eq = item.find('=');
                    if (eq == std::string::npos)
                        continue;
                    const uint32_t ip = parseIp(item.substr(eq + 1));
                    if (ip)
                        g_hosts[item.substr(0, eq)] = ip;
                }
            }
        }
    }

    int hostnetLastError()
    {
#ifdef _WIN32
        return WSAGetLastError();
#else
        return errno;
#endif
    }

    bool hostnetWouldBlock(int err)
    {
#ifdef _WIN32
        return err == WSAEWOULDBLOCK;
#else
        return err == EWOULDBLOCK || err == EAGAIN;
#endif
    }

    // PS2X_SOCOM2_SERVER is a numeric IPv4 literal or a DNS name -- a hosted server is reached by
    // name. Returns host byte order IPv4, or 0 when the value is neither, so the caller keeps
    // whatever it had. Winsock is already up where it has to be: init() runs WSAStartup before
    // loadHosts(), which is the only caller inside the runtime, and getaddrinfo needs nothing
    // earlier than that. On BSD sockets there is nothing to start.
    uint32_t parseServerAddress(const std::string &value)
    {
        if (const uint32_t ip = parseIp(value))
            return ip;

        addrinfo hints{};
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;
        addrinfo *res = nullptr;
        uint32_t ip = 0;
        if (getaddrinfo(value.c_str(), nullptr, &hints, &res) == 0 && res)
        {
            for (const addrinfo *p = res; p; p = p->ai_next)
            {
                if (p->ai_family == AF_INET && p->ai_addr)
                {
                    ip = ntohl(reinterpret_cast<const sockaddr_in *>(p->ai_addr)->sin_addr.s_addr);
                    break;
                }
            }
        }
        if (res)
            freeaddrinfo(res);
        if (!ip)
            std::cerr << "[socom2/hostnet] PS2X_SOCOM2_SERVER=\"" << value
                      << "\" is neither an IPv4 address nor a name that resolves; ignoring it"
                      << std::endl;
        return ip;
    }

    bool init()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_initialized)
            return true;
#ifdef _WIN32
        WSADATA wsa{};
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        {
            g_lastError = "WSAStartup failed";
            return false;
        }
        const char *stackName = "Winsock";
#else
        // BSD sockets need no start-up call at all.
        const char *stackName = "BSD sockets";
#endif
        loadHosts();
        g_initialized = true;
        std::cout << "[socom2/hostnet] " << stackName << " ready; retail hostnames -> " << ipToString(g_hosts["socom2-prod.muis.pdonline.scea.com"]) << std::endl;
        return true;
    }

    void shutdown()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        for (auto &e : g_table)
        {
            if (e.used && e.s != kInvalidSocket)
                hostnetClose(e.s);
            e = Entry{};
        }
#ifdef _WIN32
        if (g_initialized)
            WSACleanup();
#endif
        g_initialized = false;
    }

    int createSocket(Proto proto)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        for (int i = 0; i < kMaxSockets; ++i)
        {
            if (g_table[i].used)
                continue;
            SocketHandle s = ::socket(AF_INET, proto == Proto::Tcp ? SOCK_STREAM : SOCK_DGRAM,
                                      proto == Proto::Tcp ? IPPROTO_TCP : IPPROTO_UDP);
            if (s == kInvalidSocket)
                return mapError();
            hostnetSetNonBlocking(s, true);
            g_table[i] = Entry{s, proto, true, false, false};
            return i;
        }
        return -24; // EMFILE
    }

    int closeSocket(int fd)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        hostnetClose(e->s);
        *e = Entry{};
        return 0;
    }

    int bindSocket(int fd, const Endpoint &local)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a = toAddr(local);
        if (local.ip == 0)
            a.sin_addr.s_addr = INADDR_ANY;
        return ::bind(e->s, reinterpret_cast<sockaddr *>(&a), sizeof(a)) == 0 ? 0 : mapError();
    }

    int listenSocket(int fd, int backlog)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        return ::listen(e->s, backlog) == 0 ? 0 : mapError();
    }

    int acceptSocket(int fd, Endpoint *peer)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        SockLen len = sizeof(a);
        SocketHandle s = ::accept(e->s, reinterpret_cast<sockaddr *>(&a), &len);
        if (s == kInvalidSocket)
            return mapError();
        for (int i = 0; i < kMaxSockets; ++i)
        {
            if (g_table[i].used)
                continue;
            hostnetSetNonBlocking(s, true);
            g_table[i] = Entry{s, Proto::Tcp, true, false, false};
            if (peer)
                *peer = fromAddr(a);
            return i;
        }
        hostnetClose(s);
        return -24;
    }

    int connectSocket(int fd, const Endpoint &remote)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a = toAddr(remote);
        if (::connect(e->s, reinterpret_cast<sockaddr *>(&a), sizeof(a)) == 0)
        {
            e->connecting = false;
            return 0;
        }
        const int err = hostnetLastError();
        if (e->proto == Proto::Udp)
            return mapError();
#ifdef _WIN32
        if (hostnetWouldBlock(err) || err == WSAEINPROGRESS || err == WSAEALREADY)
#else
        // A repeated connect() on a socket that finished connecting answers EISCONN here, where
        // Winsock answers WSAEISCONN only from a blocking retry the guest never makes.
        if (err == EISCONN)
        {
            e->connecting = false;
            return 0;
        }
        if (hostnetWouldBlock(err) || err == EINPROGRESS || err == EALREADY)
#endif
        {
            e->connecting = true;
            return 1;
        }
        return mapError();
    }

    int connectStatus(int fd)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        if (!e->connecting)
            return 0;
#ifdef _WIN32
        fd_set w, x;
        FD_ZERO(&w);
        FD_ZERO(&x);
        FD_SET(e->s, &w);
        FD_SET(e->s, &x);
        timeval tv{0, 0};
        const int n = ::select(0, nullptr, &w, &x, &tv);
        if (n <= 0)
            return 1;
        if (FD_ISSET(e->s, &x))
        {
            int err = 0;
            SockLen len = sizeof(err);
            getsockopt(e->s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char *>(&err), &len);
            e->connecting = false;
            hostnetSetLastError(err);
            return mapError();
        }
#else
        // select(0, ...) is a Winsock spelling -- POSIX counts descriptors -- and poll() says the
        // same thing without the FD_SETSIZE ceiling. A refused connect surfaces as POLLERR here
        // and, on some kernels, only as SO_ERROR on a descriptor that also reads as writable, so
        // both are consulted before the socket is called connected.
        pollfd pfd{};
        pfd.fd = e->s;
        pfd.events = POLLOUT;
        const int n = ::poll(&pfd, 1, 0);
        if (n <= 0)
            return 1;
        int err = 0;
        SockLen len = sizeof(err);
        getsockopt(e->s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char *>(&err), &len);
        if ((pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0 || err != 0)
        {
            e->connecting = false;
            hostnetSetLastError(err);
            return mapError();
        }
#endif
        e->connecting = false;
        return 0;
    }

    int send(int fd, const void *data, uint32_t size)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        const IoResult n = ::send(e->s, static_cast<SendBuf>(data), static_cast<IoLen>(size), 0);
        return n >= 0 ? static_cast<int>(n) : mapError();
    }

    int recv(int fd, void *data, uint32_t size)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        const IoResult n = ::recv(e->s, static_cast<RecvBuf>(data), static_cast<IoLen>(size), 0);
        if (n > 0)
            g_rxBytes += static_cast<uint64_t>(n);
        return n >= 0 ? static_cast<int>(n) : mapError();
    }

    int sendTo(int fd, const void *data, uint32_t size, const Endpoint &remote)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a = toAddr(remote);
        const IoResult n = ::sendto(e->s, static_cast<SendBuf>(data), static_cast<IoLen>(size), 0,
                                    reinterpret_cast<sockaddr *>(&a), sizeof(a));
        return n >= 0 ? static_cast<int>(n) : mapError();
    }

    int recvFrom(int fd, void *data, uint32_t size, Endpoint *remote)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        SockLen len = sizeof(a);
        const IoResult n = ::recvfrom(e->s, static_cast<RecvBuf>(data), static_cast<IoLen>(size), 0,
                                      reinterpret_cast<sockaddr *>(&a), &len);
        if (n < 0)
            return mapError();
        if (n > 0)
            g_rxBytes += static_cast<uint64_t>(n);
        if (remote)
            *remote = fromAddr(a);
        return static_cast<int>(n);
    }

    int localName(int fd, Endpoint *local)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        SockLen len = sizeof(a);
        if (getsockname(e->s, reinterpret_cast<sockaddr *>(&a), &len) != 0)
            return mapError();
        if (local)
        {
            *local = fromAddr(a);
            if (local->ip == 0)
                local->ip = localIp();
        }
        return 0;
    }

    int peerName(int fd, Endpoint *peer)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        SockLen len = sizeof(a);
        if (getpeername(e->s, reinterpret_cast<sockaddr *>(&a), &len) != 0)
            return mapError();
        if (peer)
            *peer = fromAddr(a);
        return 0;
    }

    int setBlocking(int fd, bool blocking)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        e->blocking = blocking;
        return hostnetSetNonBlocking(e->s, !blocking) == 0 ? 0 : mapError();
    }

    int poll(int fd, int timeoutMs)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
#ifdef _WIN32
        fd_set r, w, x;
        FD_ZERO(&r);
        FD_ZERO(&w);
        FD_ZERO(&x);
        FD_SET(e->s, &r);
        FD_SET(e->s, &w);
        FD_SET(e->s, &x);
        timeval tv{timeoutMs / 1000, (timeoutMs % 1000) * 1000};
        const int n = ::select(0, &r, &w, &x, &tv);
        if (n < 0)
            return mapError();
        int mask = 0;
        if (FD_ISSET(e->s, &r)) mask |= 1;
        if (FD_ISSET(e->s, &w)) mask |= 2;
        if (FD_ISSET(e->s, &x)) mask |= 4;
        return mask;
#else
        pollfd pfd{};
        pfd.fd = e->s;
        pfd.events = POLLIN | POLLOUT;
        const int n = ::poll(&pfd, 1, timeoutMs);
        if (n < 0)
            return mapError();
        int mask = 0;
        if (pfd.revents & POLLIN) mask |= 1;
        if (pfd.revents & POLLOUT) mask |= 2;
        if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) mask |= 4;
        return mask;
#endif
    }

    int readable(int fd)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        int n = 0;
        if (hostnetReadableBytes(e->s, &n) != 0)
            return mapError();
        return n;
    }

    uint32_t resolve(const std::string &name)
    {
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            auto it = g_hosts.find(name);
            if (it != g_hosts.end())
                return it->second;
        }
        if (const uint32_t ip = parseIp(name))
            return ip;
        addrinfo hints{};
        hints.ai_family = AF_INET;
        addrinfo *res = nullptr;
        if (getaddrinfo(name.c_str(), nullptr, &hints, &res) != 0 || !res)
            return 0;
        const uint32_t ip = ntohl(reinterpret_cast<sockaddr_in *>(res->ai_addr)->sin_addr.s_addr);
        freeaddrinfo(res);
        return ip;
    }

    uint64_t rxBytes()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        return g_rxBytes;
    }

    uint32_t localIp()
    {
        // The address a UDP socket would use towards the server: connect() on a datagram socket
        // performs no traffic but picks the source interface.
        uint32_t target = 0x7f000001u;
        {
            std::lock_guard<std::mutex> lock(g_mutex);
            auto it = g_hosts.find("socom2-prod.muis.pdonline.scea.com");
            if (it != g_hosts.end())
                target = it->second;
        }
        SocketHandle s = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (s == kInvalidSocket)
            return 0x7f000001u;
        sockaddr_in a{};
        a.sin_family = AF_INET;
        a.sin_port = htons(53);
        a.sin_addr.s_addr = htonl(target);
        uint32_t ip = 0x7f000001u;
        if (::connect(s, reinterpret_cast<sockaddr *>(&a), sizeof(a)) == 0)
        {
            sockaddr_in l{};
            SockLen len = sizeof(l);
            if (getsockname(s, reinterpret_cast<sockaddr *>(&l), &len) == 0)
                ip = ntohl(l.sin_addr.s_addr);
        }
        hostnetClose(s);
        return ip;
    }

    std::string ipToString(uint32_t ip)
    {
        std::ostringstream o;
        o << ((ip >> 24) & 255) << '.' << ((ip >> 16) & 255) << '.' << ((ip >> 8) & 255) << '.' << (ip & 255);
        return o.str();
    }

    const char *lastError()
    {
        return g_lastError.c_str();
    }
}
