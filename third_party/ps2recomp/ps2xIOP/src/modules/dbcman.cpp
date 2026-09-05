#include "module_factories.h"

#include <array>
#include <cstdint>
#include <mutex>
#include <sstream>
#include <string>

// DBCMAN ("Dbc_Manager", Sony's device-bus/controller broker on the IOP) HLE.
//
// The EE side is libdbc (sceDbc*), statically linked into the game at 0x18fcb8..0x190bc8. Every
// synchronous call uses one 0x280-byte buffer (0x1d62c0) as both the send and the receive area,
// so a reply is written *into the request*. Field offsets (decoded from the libdbc wrappers, see
// docs/research/08-controller-and-dbcman.md):
//
//   rpc     name                 request fields                         reply fields
//   0x1363  CheckVersion         -                                      +0x00 version (0x0320)
//   0x1304  SetWorkAddr          +0x04 EE work address                  +0x00 ok (nonzero)
//   0x1301  CreateSocket         +0x00..+0x2c descriptor                +0x24 socket number
//   0x1302  DeleteSocket         +0x00 socket                           +0x04 ok
//   0x1303  GetDepNumber         +0x00 socket                           +0x04 dep number
//   0x1315  InitSocket           +0x00 socket                           +0x04 ok
//   0x1316  ResetSocket          +0x00 socket                           +0x04 ok
//   0x1317  GetDeviceStatus      +0x00 socket                           +0x04 status
//   0x131d  (vib/act param)      +0x08=2, +0x10, +0x14                  +0x04 result
//   0x1318  SRData               +0x08 send len, +0x0c recv len, +0x10  +0x0c recv count, +0x210 data, +0x410 status
//   0x1319  SendData             +0x08 len, +0x0c data                  +0x08 count, +0x20c status
//   0x131a  ReceiveData          +0x08 max len                          +0x08 count, +0x0c data, +0x20c status
//   0x131b  SendData2 (async)    separate 0x1090 buffer at 0x1d6540     -
//   0x131c  SendData3 (async)    separate 0x2090 buffer at 0x1d7640     -
//
// The work address is a table of 32 words that DBCMAN keeps updated by SIF DMA: entry [socket]
// == 1 means that socket's device is connected. libdbc consults it before GetDepNumber.
//
// This implementation answers with a consistent "one DualShock2 on socket 0, nothing received"
// state. Leaving the reply untouched is NOT safe: sceDbcReceiveData copies +0x08 bytes back into
// the caller's buffer, and the wrappers send an uninitialised length there, so an unanswered call
// memcpy's a huge count out of the 0x1d62c0 buffer and smashes the heap (found 2026-09-05).

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kDbcManSid = 0x80001300u;
        constexpr uint32_t kRpcCreateSocket = 0x80001301u;
        constexpr uint32_t kRpcDeleteSocket = 0x80001302u;
        constexpr uint32_t kRpcGetDepNumber = 0x80001303u;
        constexpr uint32_t kRpcSetWorkAddr = 0x80001304u;
        constexpr uint32_t kRpcInitSocket = 0x80001315u;
        constexpr uint32_t kRpcResetSocket = 0x80001316u;
        constexpr uint32_t kRpcGetDeviceStatus = 0x80001317u;
        constexpr uint32_t kRpcSRData = 0x80001318u;
        constexpr uint32_t kRpcSendData = 0x80001319u;
        constexpr uint32_t kRpcReceiveData = 0x8000131au;
        constexpr uint32_t kRpcSendData2 = 0x8000131bu;
        constexpr uint32_t kRpcSendData3 = 0x8000131cu;
        constexpr uint32_t kRpcSetActParam = 0x8000131du;
        constexpr uint32_t kRpcCheckVersion = 0x80001363u;
        constexpr uint32_t kDbcManVersion = 0x0320u;
        constexpr uint32_t kMaxRpcLogs = 48u;
        constexpr uint32_t kLinkTableWords = 32u;
        constexpr uint32_t kConnectedSockets = 1u;   // socket 0 = the HLE DualShock2

        class DbcmanService final : public IopService
        {
        public:
            explicit DbcmanService(IopHost &host)
                : m_host(host)
            {
            }

            [[nodiscard]] std::string_view name() const override
            {
                return "dbcman";
            }

            [[nodiscard]] std::span<const uint32_t> sids() const override
            {
                return kSids;
            }

            void reset() override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_rpcLogCount = 0u;
                m_workAddress = 0u;
                m_nextSocket = 0u;
            }

            [[nodiscard]] RpcResult handleRpc(const RpcRequest &request) override
            {
                RpcResult result;
                if (request.sid != kDbcManSid)
                {
                    return result;
                }

                result.handled = true;
                result.resultAddress = request.receive.address;
                if (request.receive.address == 0u || request.receive.size == 0u)
                {
                    return result;
                }

                const uint32_t buffer = request.receive.address;
                const char *what = "unknown";
                bool known = true;
                switch (request.function)
                {
                case kRpcCheckVersion:
                {
                    what = "CheckVersion";
                    const uint32_t wordCount = request.receive.size / sizeof(uint32_t);
                    const uint32_t count = wordCount < 4u ? wordCount : 4u;
                    for (uint32_t index = 0u; index < count; ++index)
                    {
                        writeWord(buffer + index * sizeof(uint32_t), kDbcManVersion);
                    }
                    break;
                }
                case kRpcSetWorkAddr:
                {
                    what = "SetWorkAddr";
                    uint32_t workAddress = 0u;
                    (void)m_host.readGuest(request.send.address + 0x04u, &workAddress, sizeof(workAddress));
                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        m_workAddress = workAddress;
                    }
                    publishLinkTable(workAddress);
                    writeWord(buffer + 0x00u, 1u);
                    break;
                }
                case kRpcCreateSocket:
                {
                    what = "CreateSocket";
                    uint32_t socket = 0u;
                    uint32_t workAddress = 0u;
                    {
                        std::lock_guard<std::mutex> lock(m_mutex);
                        socket = m_nextSocket++;
                        workAddress = m_workAddress;
                    }
                    publishLinkTable(workAddress);
                    writeWord(buffer + 0x24u, socket);
                    break;
                }
                case kRpcDeleteSocket:
                case kRpcInitSocket:
                case kRpcResetSocket:
                case kRpcGetDeviceStatus:
                    what = request.function == kRpcDeleteSocket ? "DeleteSocket"
                         : request.function == kRpcInitSocket ? "InitSocket"
                         : request.function == kRpcResetSocket ? "ResetSocket"
                                                                : "GetDeviceStatus";
                    writeWord(buffer + 0x04u, 1u);
                    break;
                case kRpcGetDepNumber:
                    what = "GetDepNumber";
                    writeWord(buffer + 0x04u, 0u);
                    break;
                case kRpcSetActParam:
                    what = "SetActParam";
                    writeWord(buffer + 0x04u, 0u);
                    break;
                case kRpcSRData:
                    what = "SRData";
                    writeWord(buffer + 0x0cu, 0u);     // received count
                    writeWord(buffer + 0x410u, 0u);    // status
                    break;
                case kRpcSendData:
                    what = "SendData";
                    writeWord(buffer + 0x20cu, 0u);    // status (count at +0x08 echoes the request)
                    break;
                case kRpcReceiveData:
                    what = "ReceiveData";
                    writeWord(buffer + 0x08u, 0u);     // received count: nothing pending
                    writeWord(buffer + 0x20cu, 0u);    // status ok
                    break;
                case kRpcSendData2:
                case kRpcSendData3:
                    what = request.function == kRpcSendData2 ? "SendData2" : "SendData3";
                    break;                              // async, no reply fields are read
                default:
                    known = false;
                    break;
                }

                bool shouldLog = false;
                {
                    std::lock_guard<std::mutex> lock(m_mutex);
                    if (m_rpcLogCount < kMaxRpcLogs)
                    {
                        ++m_rpcLogCount;
                        shouldLog = true;
                    }
                }

                if (shouldLog)
                {
                    std::ostringstream message;
                    message << (known ? "[DBCMAN] " : "[DBCMAN:stub] ")
                            << what
                            << " rpc=0x" << std::hex << request.function
                            << " send=0x" << request.send.address
                            << " sendSize=0x" << request.send.size
                            << " recv=0x" << request.receive.address
                            << " recvSize=0x" << request.receive.size;
                    m_host.log(LogLevel::Info, message.str());
                }
                return result;
            }

            void appendDebugMetrics(std::vector<DebugMetric> &metrics) const override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                metrics.push_back({"rpc_logs", m_rpcLogCount, false});
                metrics.push_back({"work_address", m_workAddress, true});
                metrics.push_back({"sockets", m_nextSocket, false});
            }

        private:
            void writeWord(uint32_t address, uint32_t value)
            {
                (void)m_host.writeGuest(address, &value, sizeof(value));
            }

            // Link table at the EE work address: word [socket] == 1 means connected.
            void publishLinkTable(uint32_t workAddress)
            {
                if (workAddress == 0u)
                {
                    return;
                }
                for (uint32_t index = 0u; index < kLinkTableWords; ++index)
                {
                    writeWord(workAddress + index * sizeof(uint32_t), index < kConnectedSockets ? 1u : 0u);
                }
            }

            inline static constexpr std::array<uint32_t, 1> kSids{kDbcManSid};

            IopHost &m_host;
            mutable std::mutex m_mutex;
            uint32_t m_rpcLogCount = 0u;
            uint32_t m_workAddress = 0u;
            uint32_t m_nextSocket = 0u;
        };
    }

    std::unique_ptr<IopService> createDbcmanService(IopHost &host)
    {
        return std::make_unique<DbcmanService>(host);
    }
}
