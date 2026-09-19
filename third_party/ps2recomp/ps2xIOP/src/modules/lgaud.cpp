// lgaud.irx (Logitech USB headset audio, liblgaud 1.08) — SIF RPC service 'BLIP'.
// SOCOM II calls lgAudInit at startup and halts if the module version is not 1.08. Sprint 8 Goal 3 Task 2
// turns the rest of the module from "no device" into a real service over the message block the game's own
// decompiled client library gives us, field by field (game/analysis/socom2_game.elf.decomp.c:90811-91800).
//
// The contract, re-derived from the listing rather than guessed:
//   * ONE 0x840-byte buffer, DAT_003dcfb4, is passed as BOTH send and receive on every call (:90956, :91033,
//     :91102). R112: the whole send block is copied out below BEFORE a single reply word is written, or we
//     would clobber the handle and the byte count we are about to use.
//   * status at +0x00, state at +0x04 (the EE merges it as DAT_003dcfb8 = (DAT_003dcfb8 & ~2) | reply+0x04,
//     :91037, :91108, and FUN_00245568 clears the latch when the merged value is exactly 1).
//   * deviceIndex at +0x08 (:91027), handle at +0x0c both ways (:91097, :91036), the Read/Write flag byte at
//     +0x12 (:91100), byteCount at +0x20 (:91101, :91107), PCM payload at +0x30 (:91106 -- the EE memcpys
//     from reply+0x30, there is no separate EE buffer named in the block).
//   * 0x01 Enumerate's device-info block is 0x14c bytes at +0x20; the only reader in the image is
//     FUN_0034ba60 (:247050-247081), which scans entryCount at block+0x62 for Logitech feature 0x5622.
//   * The live capture loop (:211455-211545) asks 0x08 for 0x500 - fill bytes about 17 times a second and
//     copes with a short return by simply not advancing, so serving fewer bytes is correct, not a failure.
//
// Everything here stays off unless the runtime has a capture source: micAvailable() is false with neither
// PS2X_MIC_FAKE nor PS2X_MIC_DEVICE set, and then every reply is byte for byte what it was before this goal.
// Nothing in this module reads the environment or touches a device -- it asks IopHost, exactly as snd989.cpp
// asks audioIsPlaying rather than owning a mixer (snd989.cpp:1271).
#include "../module_factories.h"
#include "runtime/mic_format.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kLgAudSid = 0x50494c42u;      // 'BLIP'

        // The function table (docs/KNOWN.md:101 and the decomp call sites named against each).
        constexpr uint32_t kRpcEnumerate = 0x01u;        // :90956, send 0x20 / recv 0x170
        constexpr uint32_t kRpcOpen = 0x02u;             // :91033, send 0x30 / recv 0x20
        constexpr uint32_t kRpcClose = 0x03u;            // :91063
        constexpr uint32_t kRpcStartRecording = 0x04u;   // :91358
        constexpr uint32_t kRpcStopRecording = 0x05u;    // :91384, name ASSUMED (shares 0x04's error string)
        constexpr uint32_t kRpcStartPlayback = 0x06u;    // :91411
        constexpr uint32_t kRpcStopPlayback = 0x07u;     // :91438
        constexpr uint32_t kRpcRead = 0x08u;             // :91102, send 0x30 / recv ((n+0x3f)>>4)<<4
        constexpr uint32_t kRpcWrite = 0x09u;            // :91146
        constexpr uint32_t kRpcGetMixer = 0x0bu;         // :91234
        constexpr uint32_t kRpcSetMixer = 0x0cu;         // :91274
        constexpr uint32_t kRpcSetPlaybackVolume = 0x0du; // :91495, name ASSUMED from its callers
        constexpr uint32_t kRpcSetRecordGain = 0x0eu;    // :91524, driven by the capture loop's AGC :211504
        constexpr uint32_t kRpcEnumHint = 0x0fu;         // :91788, async, end function 0x245568
        constexpr uint32_t kRpcInit = 0x10u;             // version / capabilities
        constexpr uint32_t kRpcResumePlayback = 0x11u;   // :91465
        constexpr uint32_t kRpcAvailableRecording = 0x12u; // :91330 -- defined, and with NO caller in the image
        constexpr uint32_t kRpcRemainingPlayback = 0x13u; // :91302
        constexpr uint32_t kRpcPrepareForReboot = 0x14u; // :91552, handle = -1
        constexpr uint32_t kRpcWriteVag = 0x15u;         // :91189

        // The message block, bytes from the start of DAT_003dcfb4.
        constexpr uint32_t kMsgStatus = 0x00u;
        constexpr uint32_t kMsgState = 0x04u;
        constexpr uint32_t kMsgDeviceIndex = 0x08u;
        constexpr uint32_t kMsgHandle = 0x0cu;
        constexpr uint32_t kMsgMixerChannel = 0x10u;
        constexpr uint32_t kMsgMixerLevel = 0x11u;
        constexpr uint32_t kMsgFlag = 0x12u;
        constexpr uint32_t kMsgByteCount = 0x20u;
        constexpr uint32_t kMsgOpenParam = 0x20u;        // 14 bytes, :91028-91032
        constexpr uint32_t kMsgMixerStruct = 0x20u;      // 16 bytes, :91234/:91274
        constexpr uint32_t kMsgPayload = 0x30u;
        constexpr uint32_t kMaxPayload = 0x7d0u;         // DAT_003dcfac = 0x800 - 0x30, :90880
        constexpr uint32_t kEnumBlock = 0x20u;
        constexpr uint32_t kEnumBlockBytes = 0x14cu;
        constexpr uint32_t kEnumEntryCount = 0x62u;      // :247063, the bound of the vendor-extension scan
        constexpr uint32_t kEnumNameBytes = 98u;         // block 0x00..0x61, no reader anywhere in the image

        // The state word at reply +0x04, and what the EE does with it. EVERY client call merges it as
        // DAT_003dcfb8 = DAT_003dcfb8 & ~2 | reply[+0x04] (:90991, :91037, :91067, :91108, :91760, ...);
        // the async EnumHint's end function then writes the merged word into the voice object's +0x44
        // (:91762) and clears the latch only when it is EXACTLY 1 (:91761-91764). The per-frame voice tick
        // FUN_0030ec10 polls 0x0f while +0x44 != 1 (:211016) and runs Enumerate + lgAudOpen only when it
        // reads exactly 1 (:211024), writing 2 to +0x44 itself straight afterwards (:211025-211028).
        //
        // So bit0 is a CHANGE EVENT, sticky on the EE side until the word reads 1; bit1 is refreshed from
        // every reply by the `& ~2` and SUPPRESSES that trigger. Sprint 8 Goal 3 Task 2 shipped bit1 named
        // "present" and answered 3 then 2, which pins the merged word at 3 and means the tick NEVER opens:
        // that is the 30x-0x0f / 0x-0x02 signature of the s8_voice_read launch. Retracted here. The
        // sequence that works is 1 once, then 2 for ever, and 2 on every other successful call.
        constexpr uint32_t kStateChanged = 1u;   // bit0: the device list changed, rescan
        constexpr uint32_t kStateSteady = 2u;    // bit1: nothing to rescan -- the tick's own idle value
        constexpr uint32_t kStatusOk = 0u;
        constexpr uint32_t kStatusNoDevice = 0x80000001u;
        constexpr uint32_t kStatusBadParam = 0x80000004u;

        constexpr uint32_t kLgAudVersion = 0x0108u;      // checked against 0x108 by the EE client
        constexpr uint32_t kMaxStreamBytes = 0x800u;     // "RPC server with max stream size: %d bytes"
        constexpr uint32_t kMaxUnknownRpcLogs = 32u;
        constexpr uint32_t kDefaultReplyBytes = 48u;     // the 12 words this module has always written
        constexpr uint32_t kMaxReplyBytes = 0x840u;      // the EE's own buffer, :90871-90878
        // HostMic::kSampleRate (runtime/host_mic.h): the ring is 16 kHz mono s16 and lgAudOpen asks for
        // 11025 (openparam+0x04 = 0x2b11, :48341), so Read always resamples. The module never sees HostMic.
        constexpr uint32_t kRingSampleRate = 16000u;
        // A handle that is neither 0 nor -1, the two values the game tests (:48348, :211480).
        constexpr uint32_t kHandleTag = 0x4c470000u;     // 'LG'
        constexpr char kDeviceName[] = "SOCOM Unzipped Headset";

        // Everything the send block carries, copied out before a byte of reply is written (R112).
        struct Request
        {
            uint32_t function = 0u;
            uint32_t deviceIndex = 0u;
            uint32_t handle = 0u;
            uint32_t byteCount = 0u;
            uint8_t flag = 0u;
            uint8_t mixerChannel = 0u;
            uint8_t mixerLevel = 0u;
            std::array<uint8_t, 14> openParam{};
            std::array<uint8_t, 16> mixerStruct{};
        };

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
                m_open = false;
                m_recording = false;
                m_handle = 0u;
                m_hintSent = false;
                m_bytesRead = 0u;
                m_phase = 0.0;
                m_format = MicFormat{};
                m_playbackFormat = MicFormat{};
                m_payload.clear();
                m_gain.fill(0u);
                m_mixer.fill(0u);
                m_bytesWritten = 0u;
                m_openLogged = false;
                m_enumLogged = false;
                m_readCalls = 0u;
                m_seen.fill(false);
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

                std::lock_guard<std::mutex> lock(m_mutex);

                // R112: the EE passes DAT_003dcfb4 as BOTH send and receive (decomp :90956, :91033, :91102).
                // Every field we need must be copied out BEFORE a single reply word is written, or we would
                // clobber the handle and the byte count we are about to use.
                Request in{};
                in.function = request.function;
                in.deviceIndex = readWord(request.send, kMsgDeviceIndex);
                in.handle = readWord(request.send, kMsgHandle);
                in.byteCount = readWord(request.send, kMsgByteCount);
                in.flag = readByte(request.send, kMsgFlag);
                in.mixerChannel = readByte(request.send, kMsgMixerChannel);
                in.mixerLevel = readByte(request.send, kMsgMixerLevel);
                if (request.function == kRpcOpen)
                    readBlock(request.send, kMsgOpenParam, in.openParam.data(), in.openParam.size());
                else if (request.function == kRpcSetMixer)
                    readBlock(request.send, kMsgMixerStruct, in.mixerStruct.data(), in.mixerStruct.size());
                else if (request.function == kRpcWrite || request.function == kRpcWriteVag)
                {
                    const uint32_t bytes = std::min<uint32_t>(in.byteCount, kMaxPayload);
                    m_payload.assign(bytes, 0u);
                    if (bytes != 0u)
                        readBlock(request.send, kMsgPayload, m_payload.data(), m_payload.size());
                }

                // Only now is the reply built. The buffer is zeroed first, as snd989's services do.
                const uint32_t replyRoom = std::min<uint32_t>(request.receive.size, kMaxReplyBytes);
                m_reply.assign(replyRoom, 0u);
                uint32_t replyBytes = std::min<uint32_t>(replyRoom, kDefaultReplyBytes);
                dispatch(request, in, replyBytes);
                (void)m_host.writeGuest(request.receive.address, m_reply.data(),
                                        std::min<uint32_t>(replyBytes, replyRoom));
                return result;
            }

            void appendDebugMetrics(std::vector<DebugMetric> &metrics) const override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                metrics.push_back({"unknown_rpc_logs", m_unknownRpcLogCount, false});
                metrics.push_back({"mic_open", m_open ? 1u : 0u, false});
                metrics.push_back({"mic_recording", m_recording ? 1u : 0u, false});
                metrics.push_back({"mic_bytes_read", m_bytesRead, false});
                metrics.push_back({"mic_bytes_written", m_bytesWritten, false});
                metrics.push_back({"record_gain", m_gain[0], false});
            }

        private:
            inline static constexpr std::array<uint32_t, 1> kSids{kLgAudSid};

            // ---- reading the send block ------------------------------------------------------------
            uint32_t readWord(const GuestBuffer &send, uint32_t offset) const
            {
                uint32_t value = 0u;
                readBlock(send, offset, &value, sizeof(value));
                return value;
            }
            uint8_t readByte(const GuestBuffer &send, uint32_t offset) const
            {
                uint8_t value = 0u;
                readBlock(send, offset, &value, sizeof(value));
                return value;
            }
            void readBlock(const GuestBuffer &send, uint32_t offset, void *destination, size_t size) const
            {
                std::memset(destination, 0, size);
                if (send.address == 0u || static_cast<uint64_t>(offset) + size > send.size)
                    return;
                (void)m_host.readGuest(send.address + offset, destination, size);
            }

            // ---- writing the reply -----------------------------------------------------------------
            void putWord(uint32_t offset, uint32_t value)
            {
                if (static_cast<uint64_t>(offset) + 4u > m_reply.size())
                    return;
                std::memcpy(m_reply.data() + offset, &value, sizeof(value));
            }
            void putBlock(uint32_t offset, const void *source, size_t size)
            {
                if (static_cast<uint64_t>(offset) + size > m_reply.size())
                    return;
                std::memcpy(m_reply.data() + offset, source, size);
            }

            void answer(uint32_t status, uint32_t state)
            {
                putWord(kMsgStatus, status);
                putWord(kMsgState, state);
            }

            [[nodiscard]] bool deviceHere() const { return m_host.micAvailable(); }

            void dispatch(const RpcRequest &request, const Request &in, uint32_t &replyBytes)
            {
                // The OFF path, pinned: with no capture source the module answers exactly what it answered
                // before this goal -- 0x80000001 to every function but 0x10, and the same [lgaud:stub] line
                // for the first 32 of them. The gate exports no mic knob, so this is the path it exercises.
                // Observability, with a device attached, that [lgaud:stub] used to give for free: ONE line
                // the first time the game reaches each function number, at most 0x20 lines a run. Without it
                // a run cannot tell "the game never called 0x02" from "0x02 was refused silently", which is
                // exactly the question s8_voice_open left open.
                if (in.function < m_seen.size() && !m_seen[in.function])
                {
                    m_seen[in.function] = true;
                    std::ostringstream m;
                    m << "[lgaud] first call fn=0x" << std::hex << in.function
                      << " send=0x" << request.send.address << "/" << request.send.size
                      << " recv=0x" << request.receive.address << "/" << request.receive.size
                      << " index=" << std::dec << in.deviceIndex << " handle=0x" << std::hex << in.handle;
                    m_host.log(LogLevel::Info, m.str());
                }
                if (in.function != kRpcInit && !deviceHere())
                {
                    unknown(request);
                    answer(kStatusNoDevice, 0u);
                    return;
                }

                switch (in.function)
                {
                case kRpcInit:
                    // Unchanged from the first version of this module: the EE halts without 1.08 at word 2,
                    // and takes the 0x800 at word 8 as the stream buffer it must allocate (its 0x840 = + 0x40).
                    answer(kStatusOk, 0u);
                    putWord(0x08u, kLgAudVersion);
                    putWord(0x20u, kMaxStreamBytes);
                    m_host.log(LogLevel::Info,
                               deviceHere() ? "[lgaud] lgAudInit -> version 1.08, a headset is present"
                                            : "[lgaud] lgAudInit -> version 1.08, no headset");
                    return;

                case kRpcEnumerate:
                    enumerate(in, replyBytes);
                    return;

                case kRpcEnumHint:
                    // Async (end function 0x245568): one word of state. "Changed" exactly ONCE after a device
                    // appears -- the EE clears the latch only when the merged value is 1 (:91755-91762), so a
                    // "changed" repeated forever is what makes the game re-enumerate forever (KNOWN.md:101).
                    if (!deviceHere())
                    {
                        answer(kStatusNoDevice, 0u);
                        return;
                    }
                    if (!m_hintSent)
                    {
                        // Exactly 1, on its own: with bit1 clear the EE's merge reads 1, the latch resets and
                        // the tick opens. Answering 3 here (bit1 set) is what kept it from ever opening.
                        m_hintSent = true;
                        m_host.log(LogLevel::Info, "[lgaud] lgAudEnumHint -> change event (state 1, once)");
                        answer(kStatusOk, kStateChanged);
                        return;
                    }
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcOpen:
                    open(in);
                    return;

                case kRpcClose:
                case kRpcPrepareForReboot:
                    // The runtime owns HostMic's lifetime (ps2_runtime.cpp); closing a handle leaves the
                    // device alone. PrepareForReboot arrives with handle -1 and means the same thing here.
                    m_open = false;
                    m_recording = false;
                    m_handle = 0u;
                    m_phase = 0.0;
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcStartRecording:
                    if (!m_open || in.handle != m_handle)
                    {
                        answer(kStatusNoDevice, kStateSteady);
                        return;
                    }
                    m_recording = true;
                    m_bytesRead = 0u;
                    m_phase = 0.0;
                    m_host.log(LogLevel::Info, "[lgaud] lgAudStartRecording");
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcStopRecording:
                    // 0x05 shares 0x04's error string and is only ever called on the way out, so treating it
                    // as StopRecording is harmless if the ASSUMED name is wrong (docs/KNOWN.md:101).
                    m_recording = false;
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcStartPlayback:
                case kRpcStopPlayback:
                case kRpcResumePlayback:
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcRead:
                    read(request, in, replyBytes);
                    return;

                case kRpcAvailableRecording:
                    available(in, replyBytes);
                    return;

                case kRpcWrite:
                case kRpcWriteVag:
                    // Hearing the other player is Task 5, deliberately after the capture path is proven: the
                    // payload is counted and discarded, and the game is told every byte was taken so it never
                    // stalls waiting for us.
                    if (!m_open)
                    {
                        answer(kStatusNoDevice, kStateSteady);
                        return;
                    }
                    // The game has already Nellymoser-decoded the other player and duplicated each sample
                    // L/R (:211305-211380), so this payload is plain PCM at the playback half of the
                    // openparam. Handing it to the host is what writes PS2X_MIC_DUMP_PLAYBACK; the host
                    // discards it when no dump is open. Mixing it into 989snd is Task 5.
                    m_bytesWritten += static_cast<uint32_t>(m_payload.size());
                    if (!m_payload.empty())
                        m_host.micPlaybackWrite(m_payload.data(), m_payload.size(), m_playbackFormat.rate,
                                                m_playbackFormat.channels);
                    answer(kStatusOk, kStateSteady);
                    putWord(kMsgByteCount, static_cast<uint32_t>(m_payload.size()));
                    return;

                case kRpcRemainingPlayback:
                    // 0 remaining, so the game never waits on us.
                    answer(m_open ? kStatusOk : kStatusNoDevice, kStateSteady);
                    putWord(kMsgByteCount, 0u);
                    return;

                case kRpcGetMixer:
                    if (!m_open)
                    {
                        answer(kStatusNoDevice, kStateSteady);
                        return;
                    }
                    answer(kStatusOk, kStateSteady);
                    putBlock(kMsgMixerStruct, m_mixer.data(), m_mixer.size());
                    return;

                case kRpcSetMixer:
                    if (!m_open)
                    {
                        answer(kStatusNoDevice, kStateSteady);
                        return;
                    }
                    m_mixer = in.mixerStruct;
                    answer(kStatusOk, kStateSteady);
                    return;

                case kRpcSetPlaybackVolume:
                case kRpcSetRecordGain:
                    // The capture loop nudges 0x0e every fifth pass, clamped to 0x14..100 in steps of 5
                    // (:211504-211527). A module that refuses it leaves the game fighting its own AGC.
                    if (!m_open)
                    {
                        answer(kStatusNoDevice, kStateSteady);
                        return;
                    }
                    if (in.mixerChannel < m_gain.size())
                        m_gain[in.mixerChannel] = in.mixerLevel;
                    answer(kStatusOk, kStateSteady);
                    return;

                default:
                    unknown(request);
                    answer(kStatusNoDevice, 0u);
                    return;
                }
            }

            void enumerate(const Request &in, uint32_t &replyBytes)
            {
                // "One device" is expressed exactly as the four enumerating callers read it (:48334-48346,
                // :86588-86603, :247060-247078, :211684): status 0 for index 0, 0x80000001 for every index
                // above it, so the walk stops after one.
                if (in.deviceIndex != 0u || !deviceHere())
                {
                    if (!m_enumLogged)
                    {
                        m_enumLogged = true;
                        std::ostringstream m;
                        m << "[lgaud] lgAudGetDeviceInfo(" << in.deviceIndex << ") -> no device";
                        m_host.log(LogLevel::Info, m.str());
                    }
                    answer(kStatusNoDevice, 0u);
                    return;
                }
                if (!m_enumLogged)
                {
                    // Once per service. 0x01 is polled thousands of times a run (docs/KNOWN.md:101), so this
                    // says "the game asked, and got a device" exactly once -- with a device attached there is
                    // no [lgaud:stub] line left to read that off, and a run has to be able to tell the
                    // difference between "Enumerate answered one device" and "Enumerate was never called".
                    m_enumLogged = true;
                    m_host.log(LogLevel::Info, "[lgaud] lgAudGetDeviceInfo(0) -> one device, 0 vendor entries");
                }
                answer(kStatusOk, kStateSteady);
                std::array<uint8_t, kEnumBlockBytes> block{};
                const size_t nameBytes = std::min<size_t>(std::strlen(kDeviceName), kEnumNameBytes - 1u);
                std::memcpy(block.data(), kDeviceName, nameBytes);
                // R113: entryCount 0 is a complete, valid answer meaning "no Logitech vendor extensions".
                // FUN_0034ba60 (:247060) then scans nothing and moves on; no caller reads the name at all.
                block[kEnumEntryCount] = 0u;
                putBlock(kEnumBlock, block.data(), block.size());
                replyBytes = std::max<uint32_t>(replyBytes,
                                                std::min<uint32_t>(static_cast<uint32_t>(m_reply.size()),
                                                                   kEnumBlock + kEnumBlockBytes));
            }

            void open(const Request &in)
            {
                if (in.deviceIndex != 0u || !deviceHere())
                {
                    std::ostringstream m;
                    m << "[lgaud] lgAudOpen(index " << in.deviceIndex << ") -> no device";
                    m_host.log(LogLevel::Info, m.str());
                    answer(kStatusNoDevice, 0u);
                    return;
                }
                // The openparam the game builds is {Mode=2, pad, channels=1, bits=0x10, rate=0x2b11,
                // latency=500} (:48336-48342). The EE refuses to call at all when Mode is 0 (:91022).
                MicFormat format{};
                format.channels = in.openParam[2];
                format.bits = in.openParam[3];
                format.rate = static_cast<uint32_t>(in.openParam[4]) |
                              (static_cast<uint32_t>(in.openParam[5]) << 8);
                if (!format.supported())
                {
                    // R114: a rate or a width we cannot serve is refused at Open rather than served wrong,
                    // and it says so once so the reason reaches the run log.
                    if (!m_openLogged)
                    {
                        m_openLogged = true;
                        std::ostringstream m;
                        m << "[lgaud] lgAudOpen refused: " << int(format.channels) << "ch/" << int(format.bits)
                          << "bit/" << format.rate << "Hz is outside mono 16-bit 4000..48000";
                        m_host.log(LogLevel::Warning, m.str());
                    }
                    answer(kStatusBadParam, kStateSteady);
                    return;
                }
                m_format = format;
                // The playback half (openparam +0x08..+0x0d, :91031-91032). On the voice path it is
                // 2ch/16-bit/8000 Hz (:211843-211852); the tuner path leaves it zero.
                m_playbackFormat.channels = in.openParam[8] == 0u ? 1u : in.openParam[8];
                m_playbackFormat.bits = in.openParam[9] == 0u ? 16u : in.openParam[9];
                m_playbackFormat.rate = (static_cast<uint32_t>(in.openParam[10]) |
                                         (static_cast<uint32_t>(in.openParam[11]) << 8));
                if (m_playbackFormat.rate == 0u)
                    m_playbackFormat.rate = format.rate;
                m_handle = m_host.allocateIopHandle(IopHandleKind::RpcPacket) | kHandleTag;
                m_open = true;
                m_recording = false;
                m_phase = 0.0;
                m_bytesRead = 0u;
                {
                    // The first time this project has ever seen the game's real openparam.
                    std::ostringstream m;
                    m << "[lgaud] lgAudOpen mode=" << int(in.openParam[0]) << " rec=" << int(in.openParam[2])
                      << "ch/" << int(in.openParam[3]) << "bit/" << m_format.rate << "Hz"
                      << " play=" << int(in.openParam[8]) << "ch/" << int(in.openParam[9]) << "bit/"
                      << (static_cast<uint32_t>(in.openParam[10]) | (static_cast<uint32_t>(in.openParam[11]) << 8))
                      << "Hz -> handle 0x" << std::hex << m_handle;
                    m_host.log(LogLevel::Info, m.str());
                }
                answer(kStatusOk, kStateSteady);
                putWord(kMsgHandle, m_handle);
            }

            void read(const RpcRequest &request, const Request &in, uint32_t &replyBytes)
            {
                if (!m_open || in.handle != m_handle)
                {
                    answer(kStatusNoDevice, kStateSteady);
                    return;
                }
                // The game asks for `byteCount` bytes at the rate it opened with; our ring is 16 kHz mono s16.
                // Frames out = bytes / 2 (MicFormat::supported() has already pinned mono 16-bit).
                const uint32_t asked = std::min<uint32_t>(in.byteCount, kMaxPayload);
                const uint32_t roomInReply = static_cast<uint32_t>(m_reply.size()) > kMsgPayload
                                                 ? static_cast<uint32_t>(m_reply.size()) - kMsgPayload
                                                 : 0u;
                const size_t wantFrames = std::min<uint32_t>(asked, roomInReply) / 2u;
                uint32_t bytes = 0u;
                if (wantFrames != 0u)
                {
                    const size_t needFrames = micFramesNeeded(wantFrames, kRingSampleRate, m_format.rate, m_phase);
                    m_scratch.assign(needFrames, 0);
                    const size_t gotFrames = m_host.micRead(m_scratch.data(), needFrames);
                    m_out.assign(wantFrames, 0);
                    const size_t outFrames = micResampleLinear(m_scratch.data(), gotFrames, kRingSampleRate,
                                                              m_out.data(), wantFrames, m_format.rate, m_phase);
                    bytes = static_cast<uint32_t>(outFrames * 2u);
                }
                // Reply words first, then the payload -- the EE memcpys from reply+0x30 for reply[0x20] bytes.
                // A short read, including a read of nothing, is a success: the capture loop simply does not
                // advance its fill (:211489).
                answer(kStatusOk, kStateSteady);
                putWord(kMsgByteCount, bytes);
                if (bytes != 0u)
                {
                    putBlock(kMsgPayload, m_out.data(), bytes);
                    // Exactly what the game is about to read, at the rate it opened with.
                    m_host.micGameRead(m_out.data(), bytes / 2u, m_format.rate);
                }
                m_bytesRead += bytes;
                // One line per 256 Reads: the capture loop asks about 17 times a second (:211485), so this is
                // a heartbeat every ~15 s rather than a log the size of the run.
                if ((m_readCalls++ % 256u) == 0u)
                {
                    std::ostringstream m;
                    m << "[lgaud] lgAudRead #" << m_readCalls << " asked=" << asked << " served=" << bytes
                      << " total=" << m_bytesRead;
                    m_host.log(LogLevel::Info, m.str());
                }
                replyBytes = std::max<uint32_t>(replyBytes,
                                                std::min<uint32_t>(static_cast<uint32_t>(m_reply.size()),
                                                                   kMsgPayload + bytes));
                (void)request;
                (void)in.flag;
            }

            void available(const Request &in, uint32_t &replyBytes)
            {
                if (!m_open || in.handle != m_handle)
                {
                    answer(kStatusNoDevice, kStateSteady);
                    return;
                }
                // R116: IopHost has no "how full is the ring" seam, and FUN_00244820 (:91320) has NO CALLER
                // anywhere in the image -- the live capture path calls 0x08 directly and reads the actual
                // count back out of the reply. So this answers the payload cap: "as much as you may ask for",
                // which is true, costs nothing, and is never on the path the proof runs through.
                answer(kStatusOk, kStateSteady);
                putWord(kMsgByteCount, kMaxPayload);
                replyBytes = std::max<uint32_t>(replyBytes, std::min<uint32_t>(
                                                                static_cast<uint32_t>(m_reply.size()), 0x30u));
            }

            void unknown(const RpcRequest &request)
            {
                if (m_unknownRpcLogCount >= kMaxUnknownRpcLogs)
                    return;
                ++m_unknownRpcLogCount;
                std::ostringstream m;
                m << "[lgaud:stub] rpc=0x" << std::hex << request.function
                  << " send=0x" << request.send.address << "/" << request.send.size
                  << " recv=0x" << request.receive.address << "/" << request.receive.size;
                m_host.log(LogLevel::Info, m.str());
            }

            IopHost &m_host;
            mutable std::mutex m_mutex;
            uint32_t m_unknownRpcLogCount = 0u;

            bool m_open = false;
            bool m_recording = false;
            bool m_hintSent = false;
            bool m_openLogged = false;
            bool m_enumLogged = false;
            uint32_t m_readCalls = 0u;
            std::array<bool, 0x20> m_seen{};
            uint32_t m_handle = 0u;
            MicFormat m_format{};
            MicFormat m_playbackFormat{};
            uint64_t m_bytesRead = 0u;
            uint64_t m_bytesWritten = 0u;
            double m_phase = 0.0;
            std::array<uint8_t, 4> m_gain{};
            std::array<uint8_t, 16> m_mixer{};
            std::vector<uint8_t> m_payload;
            std::vector<int16_t> m_scratch;
            std::vector<int16_t> m_out;
            std::vector<uint8_t> m_reply;
        };
    }

    std::unique_ptr<IopService> createLgAudService(IopHost &host)
    {
        return std::make_unique<LgAudService>(host);
    }
}
