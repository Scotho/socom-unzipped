#include "socom2_hostnet.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define NOGDI
#define NOUSER
#include <winsock2.h>
#include <ws2tcpip.h>
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
    namespace
    {
        constexpr int kMaxSockets = 64;

        struct Entry
        {
            SOCKET s = INVALID_SOCKET;
            Proto proto = Proto::Tcp;
            bool used = false;
            bool connecting = false;
            bool blocking = false;
        };

        std::mutex g_mutex;
        std::array<Entry, kMaxSockets> g_table;
        bool g_initialized = false;
        std::string g_lastError;
        std::map<std::string, uint32_t> g_hosts;

        int mapError()
        {
            const int e = WSAGetLastError();
            switch (e)
            {
            case WSAEWOULDBLOCK: return -11;      // EAGAIN
            case WSAEINPROGRESS: return -115;     // EINPROGRESS
            case WSAECONNREFUSED: return -111;
            case WSAETIMEDOUT: return -110;
            case WSAEHOSTUNREACH: return -113;
            case WSAENOTCONN: return -107;
            case WSAECONNRESET: return -104;
            case WSAEADDRINUSE: return -98;
            default: return -5;                   // EIO
            }
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
                const uint32_t ip = parseIp(env);
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

    bool init()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        if (g_initialized)
            return true;
        WSADATA wsa{};
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
        {
            g_lastError = "WSAStartup failed";
            return false;
        }
        loadHosts();
        g_initialized = true;
        std::cout << "[socom2/hostnet] Winsock ready; retail hostnames -> " << ipToString(g_hosts["socom2-prod.muis.pdonline.scea.com"]) << std::endl;
        return true;
    }

    void shutdown()
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        for (auto &e : g_table)
        {
            if (e.used && e.s != INVALID_SOCKET)
                closesocket(e.s);
            e = Entry{};
        }
        if (g_initialized)
            WSACleanup();
        g_initialized = false;
    }

    int createSocket(Proto proto)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        for (int i = 0; i < kMaxSockets; ++i)
        {
            if (g_table[i].used)
                continue;
            SOCKET s = ::socket(AF_INET, proto == Proto::Tcp ? SOCK_STREAM : SOCK_DGRAM,
                                proto == Proto::Tcp ? IPPROTO_TCP : IPPROTO_UDP);
            if (s == INVALID_SOCKET)
                return mapError();
            u_long nb = 1;
            ioctlsocket(s, FIONBIO, &nb);
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
        closesocket(e->s);
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
        int len = sizeof(a);
        SOCKET s = ::accept(e->s, reinterpret_cast<sockaddr *>(&a), &len);
        if (s == INVALID_SOCKET)
            return mapError();
        for (int i = 0; i < kMaxSockets; ++i)
        {
            if (g_table[i].used)
                continue;
            u_long nb = 1;
            ioctlsocket(s, FIONBIO, &nb);
            g_table[i] = Entry{s, Proto::Tcp, true, false, false};
            if (peer)
                *peer = fromAddr(a);
            return i;
        }
        closesocket(s);
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
        const int err = WSAGetLastError();
        if (e->proto == Proto::Udp)
            return mapError();
        if (err == WSAEWOULDBLOCK || err == WSAEINPROGRESS || err == WSAEALREADY)
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
            int len = sizeof(err);
            getsockopt(e->s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char *>(&err), &len);
            e->connecting = false;
            WSASetLastError(err);
            return mapError();
        }
        e->connecting = false;
        return 0;
    }

    int send(int fd, const void *data, uint32_t size)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        const int n = ::send(e->s, static_cast<const char *>(data), static_cast<int>(size), 0);
        return n >= 0 ? n : mapError();
    }

    int recv(int fd, void *data, uint32_t size)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        const int n = ::recv(e->s, static_cast<char *>(data), static_cast<int>(size), 0);
        return n >= 0 ? n : mapError();
    }

    int sendTo(int fd, const void *data, uint32_t size, const Endpoint &remote)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a = toAddr(remote);
        const int n = ::sendto(e->s, static_cast<const char *>(data), static_cast<int>(size), 0,
                               reinterpret_cast<sockaddr *>(&a), sizeof(a));
        return n >= 0 ? n : mapError();
    }

    int recvFrom(int fd, void *data, uint32_t size, Endpoint *remote)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        int len = sizeof(a);
        const int n = ::recvfrom(e->s, static_cast<char *>(data), static_cast<int>(size), 0,
                                 reinterpret_cast<sockaddr *>(&a), &len);
        if (n < 0)
            return mapError();
        if (remote)
            *remote = fromAddr(a);
        return n;
    }

    int localName(int fd, Endpoint *local)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        sockaddr_in a{};
        int len = sizeof(a);
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
        int len = sizeof(a);
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
        u_long nb = blocking ? 0 : 1;
        e->blocking = blocking;
        return ioctlsocket(e->s, FIONBIO, &nb) == 0 ? 0 : mapError();
    }

    int poll(int fd, int timeoutMs)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
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
    }

    int readable(int fd)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        Entry *e = entry(fd);
        if (!e)
            return -9;
        u_long n = 0;
        if (ioctlsocket(e->s, FIONREAD, &n) != 0)
            return mapError();
        return static_cast<int>(n);
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
        SOCKET s = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (s == INVALID_SOCKET)
            return 0x7f000001u;
        sockaddr_in a{};
        a.sin_family = AF_INET;
        a.sin_port = htons(53);
        a.sin_addr.s_addr = htonl(target);
        uint32_t ip = 0x7f000001u;
        if (::connect(s, reinterpret_cast<sockaddr *>(&a), sizeof(a)) == 0)
        {
            sockaddr_in l{};
            int len = sizeof(l);
            if (getsockname(s, reinterpret_cast<sockaddr *>(&l), &len) == 0)
                ip = ntohl(l.sin_addr.s_addr);
        }
        closesocket(s);
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
