// lgaud.irx (Logitech USB headset audio, liblgaud 1.08) — SIF RPC service 'BLIP'.
// SOCOM II calls lgAudInit at startup and halts if the module version is not 1.08; a headset
// is optional, so this first version only reports a valid driver with no device attached.
#include "module_factories.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <sstream>
#include <string>

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kLgAudSid = 0x50494c42u;      // 'BLIP'
        constexpr uint32_t kRpcInit = 0x10u;             // lgAudInit: version / capabilities
        constexpr uint32_t kLgAudVersion = 0x0108u;      // checked against 0x108 by the EE client
        constexpr uint32_t kMaxStreamBytes = 0x800u;     // "RPC server with max stream size: %d bytes"
        constexpr uint32_t kMaxUnknownRpcLogs = 32u;

        class LgAudService final : public IopService
        {
        public:
            explicit LgAudService(IopHost &host) : m_host(host) {}

            [[nodiscard]] std::string_view name() const override { return "lgaud"; }
            [[nodiscard]] std::span<const uint32_t> sids() const override { return kSids; }

            void reset() override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_unknownRpcLogCount = 0u;
            }

            [[nodiscard]] RpcResult handleRpc(const RpcRequest &request) override
            {
                RpcResult result;
                if (request.sid != kLgAudSid)
                    return result;
                result.handled = true;
                result.resultAddress = request.receive.address;
                if (request.receive.address == 0u || request.receive.size == 0u)
                    return result;

                std::array<uint32_t, 12> reply{};
                if (request.function == kRpcInit)
                {
                    reply[0] = 0u;                 // status
                    reply[1] = 0u;                 // capability flags OR'd into the client's flags word
                    reply[2] = kLgAudVersion;      // must equal 0x108
                    reply[8] = kMaxStreamBytes;    // stream buffer size the EE must allocate (+0x40)
                    m_host.log(LogLevel::Info, "[lgaud] lgAudInit -> version 1.08, no headset");
                }
                else
                {
                    // Device queries (rpc 1 = lgAudGetDeviceInfo(index), 2 = open, ...): the EE enumerates
                    // devices until a query fails, so report "no device" for everything else.
                    reply[0] = 0x80000001u;
                    bool shouldLog = false;
                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        if (m_unknownRpcLogCount < kMaxUnknownRpcLogs)
                        {
                            ++m_unknownRpcLogCount;
                            shouldLog = true;
                        }
                    }
                    if (shouldLog)
                    {
                        std::ostringstream m;
                        m << "[lgaud:stub] rpc=0x" << std::hex << request.function
                          << " send=0x" << request.send.address << "/" << request.send.size
                          << " recv=0x" << request.receive.address << "/" << request.receive.size;
                        m_host.log(LogLevel::Info, m.str());
                    }
                }
                const uint32_t bytes = std::min<uint32_t>(request.receive.size, static_cast<uint32_t>(reply.size() * 4u));
                (void)m_host.writeGuest(request.receive.address, reply.data(), bytes);
                return result;
            }

            void appendDebugMetrics(std::vector<DebugMetric> &metrics) const override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                metrics.push_back({"unknown_rpc_logs", m_unknownRpcLogCount, false});
            }

        private:
            inline static constexpr std::array<uint32_t, 1> kSids{kLgAudSid};
            IopHost &m_host;
            mutable std::mutex m_mutex;
            uint32_t m_unknownRpcLogCount = 0u;
        };
    }

    std::unique_ptr<IopService> createLgAudService(IopHost &host)
    {
        return std::make_unique<LgAudService>(host);
    }
}
