// irx_differential: drive the disc's real LIBSD.IRX + 989SND.IRX + 989DSTRM.IRX on PR #244's ps2xIOP emulator
// from a line-oriented REPL, so a Python driver can replay the 989snd RPC sequence a real run logged and compare
// the IRX's answers with our snd989 model's (docs/research/40-upstream-divergence.md §8).
//
// stdin commands (one per line):
//   load <guest path> [argument string]     sceSifLoadModule; prints LOAD ...
//   rpc <snd|stream> <fno> [hex words...]   one sceSifCallRpc on the 989snd server; prints RPC ...
//   tick <ee cycles>                        advance the IOP by EE cycle accounting; prints TICK ...
//   peek <guest addr> <words>               dump guest words (the EE status block); prints PEEK ...
//   snap                                    debug snapshot; prints SNAP ...
//   quit
// Every host log line is echoed as "LOG <level> <text>".

#include "ps2x/iop/iop_host.h"
#include "ps2x/iop/iop_subsystem.h"
#include "ps2x/iop/iop_types.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

using namespace ps2x::iop;
namespace fs = std::filesystem;

namespace
{
    constexpr uint32_t kSndSid = 0x00123456u;
    constexpr uint32_t kStreamSid = 0x00123457u;
    // The EE's own buffers (research/06 §1.2, §1.4), so the IRX sees the addresses the game uses.
    constexpr uint32_t kSndSend = 0x489040u;
    constexpr uint32_t kSndRecv = 0x489000u;
    constexpr uint32_t kStreamSend = 0x48db00u;
    constexpr uint32_t kStreamRecv = 0x48dac0u;
    constexpr uint32_t kGuestBytes = 32u * 1024u * 1024u;

    std::string upper(std::string s)
    {
        for (char &c : s)
            c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        return s;
    }

    class Host final : public IopHost
    {
    public:
        Host(std::string cdRoot, std::string cdImage)
            : m_cdRoot(std::move(cdRoot)), m_cdImage(std::move(cdImage)), guest(kGuestBytes, 0u)
        {
        }

        bool readGuest(uint32_t address, void *destination, size_t size) const override
        {
            if ((!destination && size != 0u) || address > guest.size() || size > guest.size() - address)
                return false;
            if (size)
                std::memcpy(destination, guest.data() + address, size);
            return true;
        }
        bool writeGuest(uint32_t address, const void *source, size_t size) override
        {
            if ((!source && size != 0u) || address > guest.size() || size > guest.size() - address)
                return false;
            if (size)
                std::memcpy(guest.data() + address, source, size);
            return true;
        }
        bool zeroGuest(uint32_t address, size_t size) override
        {
            if (address > guest.size() || size > guest.size() - address)
                return false;
            if (size)
                std::memset(guest.data() + address, 0, size);
            return true;
        }
        bool normalizeGuestAddress(uint32_t address, uint32_t &normalized) const override
        {
            normalized = address & 0x1FFFFFFFu;
            return normalized <= guest.size();
        }
        uint32_t allocateIopHandle(IopHandleKind) override { return ++m_handles; }
        uint32_t allocateGuest(uint32_t size, uint32_t alignment) override
        {
            const uint32_t align = std::max<uint32_t>(alignment, 16u);
            m_guestBump = (m_guestBump + align - 1u) & ~(align - 1u);
            const uint32_t at = m_guestBump;
            m_guestBump += size;
            return at;
        }
        void freeGuest(uint32_t) override {}
        void audioCommand(uint32_t sid, uint32_t function, GuestBuffer send, GuestBuffer receive) override
        {
            std::printf("LOG Info audioCommand sid=%08x fn=%u send=%08x/%u recv=%08x/%u\n", sid, function,
                        send.address, send.size, receive.address, receive.size);
        }
        std::string hostPath(HostPathKind kind) const override
        {
            switch (kind)
            {
            case HostPathKind::CdRoot: return m_cdRoot;
            case HostPathKind::CdImage: return m_cdImage;
            default: return {};
            }
        }
        // "cdrom0:\RUN\IRX\SOUND\989SND.IRX;1" (or the lowercase, forward-slash form our runtime logs) -> the
        // extracted disc's file, resolved case-insensitively component by component.
        std::string translateGuestPath(std::string_view path) const override
        {
            std::string p(path);
            if (const auto colon = p.find(':'); colon != std::string::npos)
                p = p.substr(colon + 1);
            if (const auto semi = p.find(';'); semi != std::string::npos)
                p = p.substr(0, semi);
            std::replace(p.begin(), p.end(), '\\', '/');
            fs::path cur(m_cdRoot);
            std::stringstream ss(p);
            std::string part;
            while (std::getline(ss, part, '/'))
            {
                if (part.empty())
                    continue;
                bool found = false;
                std::error_code ec;
                for (const auto &entry : fs::directory_iterator(cur, ec))
                {
                    if (upper(entry.path().filename().string()) == upper(part))
                    {
                        cur = entry.path();
                        found = true;
                        break;
                    }
                }
                if (!found)
                    return {};
            }
            return cur.string();
        }
        uint64_t openHostFile(std::string_view path) override
        {
            std::FILE *fp = std::fopen(std::string(path).c_str(), "rb");
            if (!fp)
                return 0u;
            m_files.push_back(fp);
            return static_cast<uint64_t>(m_files.size());
        }
        bool hostFileSize(uint64_t handle, uint64_t &size) const override
        {
            std::FILE *fp = file(handle);
            if (!fp)
                return false;
#ifdef _WIN32
            const long long cur = _ftelli64(fp);
            _fseeki64(fp, 0, SEEK_END);
            size = static_cast<uint64_t>(_ftelli64(fp));
            _fseeki64(fp, cur, SEEK_SET);
#else
            const off_t cur = ftello(fp);
            fseeko(fp, 0, SEEK_END);
            size = static_cast<uint64_t>(ftello(fp));
            fseeko(fp, cur, SEEK_SET);
#endif
            return true;
        }
        bool readHostFile(uint64_t handle, uint64_t offset, void *destination, size_t size, size_t &bytesRead) override
        {
            bytesRead = 0u;
            std::FILE *fp = file(handle);
            if (!fp)
                return false;
            // The disc image is 4.3 GB: a 32-bit fseek wrapped the bank sectors past 2 GB (research/40 §8).
#ifdef _WIN32
            if (_fseeki64(fp, static_cast<long long>(offset), SEEK_SET) != 0)
                return false;
#else
            if (fseeko(fp, static_cast<off_t>(offset), SEEK_SET) != 0)
                return false;
#endif
            bytesRead = std::fread(destination, 1, size, fp);
            return true;
        }
        void closeHostFile(uint64_t handle) override
        {
            if (std::FILE *fp = file(handle))
            {
                std::fclose(fp);
                m_files[handle - 1u] = nullptr;
            }
        }
        int32_t memoryCard(const MemoryCardRequest &) override { return 0; }
        bool hasGuestFunction(uint32_t) const override { return false; }
        bool invokeGuestFunction(uint64_t, uint32_t address, uint32_t a0, uint32_t a1, uint32_t, uint32_t, uint32_t *) override
        {
            std::printf("LOG Info invokeGuestFunction %08x(%08x, %08x) (EE callback, not run)\n", address, a0, a1);
            return false;
        }
        void log(LogLevel level, std::string_view message) override
        {
            static const char *names[] = {"Debug", "Info", "Warning", "Error"};
            std::string text(message);
            std::replace(text.begin(), text.end(), '\n', ' ');
            std::printf("LOG %s %s\n", names[static_cast<uint32_t>(level) & 3u], text.c_str());
        }

        std::vector<uint8_t> guest;

    private:
        std::FILE *file(uint64_t handle) const
        {
            return (handle == 0u || handle > m_files.size()) ? nullptr : m_files[handle - 1u];
        }
        std::string m_cdRoot;
        std::string m_cdImage;
        std::vector<std::FILE *> m_files;
        uint32_t m_handles = 0u;
        uint32_t m_guestBump = 0x01000000u;
    };

    uint32_t parseHex(const std::string &s)
    {
        return static_cast<uint32_t>(std::stoul(s, nullptr, 16));
    }
}

int main(int argc, char **argv)
{
    if (argc < 3)
    {
        std::fprintf(stderr, "usage: irx_differential <cd root dir> <cd image .iso>\n");
        return 2;
    }
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    Host host(argv[1], argv[2]);
    IopSubsystem iop(host);
    std::printf("READY\n");

    std::string line;
    while (std::getline(std::cin, line))
    {
        std::istringstream in(line);
        std::string cmd;
        in >> cmd;
        if (cmd.empty())
            continue;
        if (cmd == "quit")
            break;
        if (cmd == "load")
        {
            std::string path, args;
            in >> path;
            std::getline(in, args);
            if (!args.empty() && args[0] == ' ')
                args.erase(0, 1);
            const ModuleLoadResult r = args.empty() ? iop.loadModule(path)
                                                    : iop.loadModule(path, args.c_str(), static_cast<uint32_t>(args.size() + 1u));
            const DebugSnapshot s = iop.debugSnapshot();
            std::printf("LOAD %s handled=%d id=%d start=%d modules=%u threads=%u servers=%u\n", path.c_str(), r.handled ? 1 : 0,
                        r.moduleId, r.startResult, s.emulatorLoadedModules, s.emulatorThreads, s.emulatorRpcServers);
            continue;
        }
        if (cmd == "rpc")
        {
            std::string which, fnoText;
            in >> which >> fnoText;
            const bool stream = which == "stream";
            const uint32_t fno = parseHex(fnoText);
            std::vector<uint32_t> words;
            std::string w;
            while (in >> w)
                words.push_back(parseHex(w));
            const uint32_t send = stream ? kStreamSend : kSndSend;
            const uint32_t recv = stream ? kStreamRecv : kSndRecv;
            if (!words.empty())
                (void)host.writeGuest(send, words.data(), words.size() * 4u);
            (void)host.zeroGuest(recv, 0x40u);
            RpcRequest req{};
            req.sid = stream ? kStreamSid : kSndSid;
            req.function = fno;
            req.send = {send, static_cast<uint32_t>(words.size() * 4u)};
            req.receive = {recv, stream ? 4u : 0xCu};
            const uint64_t before = iop.debugSnapshot().emulatorInstructions;
            const RpcResult res = iop.handleRpc(req);
            const uint64_t after = iop.debugSnapshot().emulatorInstructions;
            uint32_t out[4] = {0u, 0u, 0u, 0u};
            (void)host.readGuest(recv, out, sizeof(out));
            std::printf("RPC %s fno=%02x handled=%d recv=%08x %08x %08x %08x instr=%llu\n", stream ? "stream" : "snd", fno,
                        res.handled ? 1 : 0, out[0], out[1], out[2], out[3], static_cast<unsigned long long>(after - before));
            continue;
        }
        if (cmd == "tick")
        {
            unsigned long long cycles = 0u;
            in >> cycles;
            const uint64_t before = iop.debugSnapshot().emulatorInstructions;
            iop.runEeCycles(cycles);
            const uint64_t after = iop.debugSnapshot().emulatorInstructions;
            std::printf("TICK cycles=%llu instr=%llu\n", cycles, static_cast<unsigned long long>(after - before));
            continue;
        }
        if (cmd == "peek")
        {
            std::string a;
            unsigned n = 0u;
            in >> a >> n;
            const uint32_t addr = parseHex(a);
            std::printf("PEEK %08x", addr);
            for (unsigned i = 0u; i < n; ++i)
            {
                uint32_t v = 0u;
                (void)host.readGuest(addr + 4u * i, &v, 4u);
                std::printf(" %08x", v);
            }
            std::printf("\n");
            continue;
        }
        if (cmd == "ipeek")   // IOP RAM words (an export table, a module's data)
        {
            std::string a;
            unsigned n = 0u;
            in >> a >> n;
            const uint32_t addr = parseHex(a);
            std::printf("IPEEK %08x", addr);
            for (unsigned i = 0u; i < n; ++i)
            {
                uint32_t v = 0u;
                (void)iop.readMemory(addr + 4u * i, &v, 4u);
                std::printf(" %08x", v);
            }
            std::printf("\n");
            continue;
        }
        if (cmd == "snap")
        {
            const DebugSnapshot s = iop.debugSnapshot();
            std::printf("SNAP cycles=%llu instr=%llu modules=%u threads=%u servers=%u diagnostics=%zu\n",
                        static_cast<unsigned long long>(s.emulatorCycles), static_cast<unsigned long long>(s.emulatorInstructions),
                        s.emulatorLoadedModules, s.emulatorThreads, s.emulatorRpcServers, s.diagnostics.size());
            for (const std::string &d : s.diagnostics)
                std::printf("LOG Diag %s\n", d.c_str());
            continue;
        }
        std::printf("ERR unknown command: %s\n", cmd.c_str());
    }
    return 0;
}
