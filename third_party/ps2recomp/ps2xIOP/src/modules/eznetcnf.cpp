// EZNETCNF.IRX / EZNETCTL.IRX (SCEA "easy netcnf" wrappers over Sony's netcnf/inetctl) — SIF
// RPC services 0x75499128 (eznetcnf) and 0x75488909 (eznetctl). SOCOM II's LOGIN TO SOCOM II
// ONLINE screen lists the network configurations saved on the memory card through eznetcnf and
// brings the interface up through eznetctl before the Medius client starts. The EE clients live
// at FUN_001e8530.. (eznetcnf) and FUN_001e89e8.. (eznetctl) in the game decomp.
//
// Host networking needs no PS2 interface configuration, so this service answers with one
// always-valid configuration and an interface that is "connected" immediately.
//
// eznetcnf (buffer 0x130 bytes, send == receive):
//   fno 0 ezNetCnfGetCount(path)                    send +0x10 path        -> [0] count
//   fno 1 ezNetCnfGetCombinationList(path,flags,list) send [0] EE list pointer, [4] flags, +0x10 path
//                                                   -> list written to EE RAM, [0] count
//   fno 2 ezNetCnfGetNetcnfifData(path,name,dest)   send [0] EE dest pointer, +0x10 path,
//                                                   +0x110 combination name -> [0] result (0 ok)
// The combination list (FUN_001e8810/FUN_001e8890): 48-byte header {count, default(1-based)}
// then 104-byte entries {int flags(>=0 valid), +8 hardware string, +40 setting name}.
//
// eznetctl:
//   fno 0 (4 bytes)      -> [0] IOP buffer address for the netcnfif data (0 = "not running")
//   fno 1 (4 bytes)      -> [0] handle (>0) after the EE DMA'd 0x1340 bytes of netcnfif data
//   fno 2 (0x130 bytes)  two strings at +0x10 / +0x110 (login/password?) -> [0] result
//   fno 3 (0x110 bytes)  status: [0] error(0), [1] handle, [2] link (1 = up, 0 = failed),
//                        [3] state (3 = connected, 5 = error with message at +0x10)
#include "module_factories.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <sstream>
#include <string>

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kEzNetCnfSid = 0x75499128u;
        constexpr uint32_t kEzNetCtlSid = 0x75488909u;
        constexpr uint32_t kNetcnfifSize = 0x1340u;
        constexpr uint32_t kListHeaderSize = 48u;
        constexpr uint32_t kListEntrySize = 104u;
        constexpr char kSettingName[] = "Setting 1";
        constexpr char kHardwareName[] = "SCE/Ethernet (Network Adaptor)";

        class EzNetCnfService final : public IopService
        {
        public:
            explicit EzNetCnfService(IopHost &host) : m_host(host) {}

            [[nodiscard]] std::string_view name() const override { return "eznetcnf"; }
            [[nodiscard]] std::span<const uint32_t> sids() const override { return kSids; }

            void reset() override
            {
                m_iopBuffer = 0u;
                m_handle = 0u;
            }

            [[nodiscard]] RpcResult handleRpc(const RpcRequest &request) override
            {
                RpcResult result;
                if (request.sid != kEzNetCnfSid && request.sid != kEzNetCtlSid)
                    return result;
                result.handled = true;
                result.resultAddress = request.receive.address;

                std::array<uint32_t, 0x130 / 4> reply{};
                std::string path = readString(request.send.address + 0x10u, 0x100u);

                if (request.sid == kEzNetCnfSid)
                {
                    switch (request.function)
                    {
                    case 0u: // GetCount
                        reply[0] = 1u;
                        log("[eznetcnf] GetCount(" + path + ") -> 1");
                        break;
                    case 1u: // GetCombinationList
                    {
                        uint32_t words[2]{};
                        (void)m_host.readGuest(request.send.address, words, sizeof(words));
                        const uint32_t listAddr = words[0];   // FUN_001e8740: [0] list pointer, [4] flags
                        writeList(listAddr);
                        reply[0] = 1u;
                        std::ostringstream m;
                        m << "[eznetcnf] GetCombinationList(" << path << ", list=0x" << std::hex << listAddr
                          << ", flags=" << std::dec << words[1] << ") -> 1 entry";
                        log(m.str());
                        break;
                    }
                    case 2u: // GetNetcnfifData
                    {
                        uint32_t dest = 0u;
                        (void)m_host.readGuest(request.send.address, &dest, sizeof(dest));
                        if (dest != 0u)
                            (void)m_host.zeroGuest(dest, kNetcnfifSize);
                        reply[0] = 0u;
                        std::ostringstream m;
                        m << "[eznetcnf] GetNetcnfifData(" << path << ", " << readString(request.send.address + 0x110u, 0x20u)
                          << ", dest=0x" << std::hex << dest << ") -> 0";
                        log(m.str());
                        break;
                    }
                    default:
                        reply[0] = static_cast<uint32_t>(-1);
                        logUnknown(request);
                        break;
                    }
                }
                else
                {
                    switch (request.function)
                    {
                    case 0u: // buffer address for the netcnfif data
                        if (m_iopBuffer == 0u)
                            m_iopBuffer = m_host.allocateGuest(kNetcnfifSize, 64u);
                        reply[0] = m_iopBuffer;
                        log("[eznetctl] netcnfif buffer -> " + hex(m_iopBuffer));
                        break;
                    case 1u: // start with the DMA'd data
                        m_handle = 1u;
                        reply[0] = m_handle;
                        log("[eznetctl] start -> handle 1 (host networking, interface up)");
                        break;
                    case 2u:
                        reply[0] = 0u;
                        log("[eznetctl] fno 2 (" + path + ", " + readString(request.send.address + 0x110u, 0x20u) + ") -> 0");
                        break;
                    case 3u: // status
                        reply[0] = 0u;
                        reply[1] = m_handle;
                        reply[2] = 1u;     // link up
                        reply[3] = 3u;     // connected
                        break;
                    case 5u: // FUN_001e8e38(value): setter, e.g. timeout / retry policy
                    case 6u: // FUN_001e8eb0(value): setter
                        reply[0] = 0u;
                        break;
                    default:
                        reply[0] = static_cast<uint32_t>(-1);
                        logUnknown(request);
                        break;
                    }
                }

                if (request.receive.address != 0u && request.receive.size != 0u)
                {
                    const uint32_t bytes = std::min<uint32_t>(request.receive.size, static_cast<uint32_t>(reply.size() * 4u));
                    (void)m_host.writeGuest(request.receive.address, reply.data(), bytes);
                }
                return result;
            }

        private:
            static std::string hex(uint32_t v)
            {
                std::ostringstream m;
                m << "0x" << std::hex << v;
                return m.str();
            }

            std::string readString(uint32_t address, uint32_t max) const
            {
                std::string s;
                for (uint32_t i = 0; i < max; ++i)
                {
                    char c = 0;
                    if (!m_host.readGuest(address + i, &c, 1) || c == 0)
                        break;
                    s.push_back(c);
                }
                return s;
            }

            void writeList(uint32_t listAddr) const
            {
                if (listAddr == 0u)
                    return;
                std::array<uint8_t, kListHeaderSize + kListEntrySize> block{};
                uint32_t count = 1u, def = 1u;
                std::memcpy(block.data(), &count, 4);
                std::memcpy(block.data() + 4, &def, 4);
                uint8_t *entry = block.data() + kListHeaderSize;
                std::memcpy(entry + 8, kHardwareName, sizeof(kHardwareName));   // shown under HARDWARE:
                std::memcpy(entry + 40, kSettingName, sizeof(kSettingName));    // the list row
                (void)m_host.writeGuest(listAddr, block.data(), static_cast<uint32_t>(block.size()));
            }

            void log(const std::string &m) const { m_host.log(LogLevel::Info, m); }

            void logUnknown(const RpcRequest &request) const
            {
                std::ostringstream m;
                m << "[eznet:stub] sid=0x" << std::hex << request.sid << " rpc=0x" << request.function
                  << " send=0x" << request.send.address << "/" << std::dec << request.send.size
                  << " recv=0x" << std::hex << request.receive.address << "/" << std::dec << request.receive.size;
                log(m.str());
            }

            inline static constexpr std::array<uint32_t, 2> kSids{kEzNetCnfSid, kEzNetCtlSid};
            IopHost &m_host;
            uint32_t m_iopBuffer = 0u;
            uint32_t m_handle = 0u;
        };
    }

    std::unique_ptr<IopService> createEzNetCnfService(IopHost &host)
    {
        return std::make_unique<EzNetCnfService>(host);
    }
}
