// High-level emulation of Sony's 989snd IOP sound library (989SND.IRX) as used by
// SOCOM II. Protocol notes: docs/research/06-989snd-rpc.md.
//
// First version: every RPC is answered with plausible success values, an in-memory model
// of banks / bank-sound instances / VAG streams is kept, commands are logged at debug
// level, and the play/stop/volume family is forwarded to IopHost::audioCommand so a
// 989snd-aware host backend can pick them up. Stream-safe CD reads (the EE's sceCdRead
// replacement while streaming is active) are serviced from the CD image.

#include "../module_factories.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace ps2x::iop::detail
{
    namespace
    {
        constexpr uint32_t kSndSid = 0x00123456u;
        constexpr uint32_t kStreamSid = 0x00123457u;

        // Command numbers on the "snd" server (see the research document for the full table).
        enum Snd989Fno : uint32_t
        {
            kStartSoundSystem = 0x00,
            kStopSoundSystem = 0x01,
            kBankLoadEx = 0x02,
            kBankLoadByLoc = 0x03,
            kBankLoadEx2 = 0x04,
            kBankLoadByLoc2 = 0x05,
            kUnloadBank = 0x06,
            kUnloadBankData = 0x07,
            kResolveBankXrefs = 0x08,
            kSetMasterVolume = 0x09,
            kGetMasterVolume = 0x0A,
            kSetPlaybackMode = 0x0B,
            kGetPlaybackMode = 0x0C,
            kSetMixerMode = 0x0D,
            kSetReverbType = 0x0E,
            kSetReverbDepth = 0x0F,
            kAutoReverb = 0x10,
            kPlaySound = 0x11,
            kPlaySoundNoReturn = 0x12,
            kPauseSound = 0x13,
            kContinueSound = 0x14,
            kStopSound = 0x15,
            kPauseAllSoundsInGroup = 0x16,
            kContinueAllSoundsInGroup = 0x17,
            kStopAllSounds = 0x18,
            kSoundIsStillPlaying = 0x19,
            kSetSoundVolPan = 0x1B,
            kSetSoundParam1E = 0x1E,
            kSetSoundPitchBend = 0x1F,
            kSetSoundPitchModifier = 0x20,
            kSetSoundParams = 0x21,
            kAutoVol = 0x22,
            kInitVagStreaming = 0x2A,
            kPlayVagStreamByLoc = 0x2C,
            kPauseVagStream = 0x2D,
            kContinueVagStream = 0x2E,
            kStopVagStream = 0x2F,
            kStopAllVagStreams = 0x34,
            kShutdownVagStreaming = 0x35,
            kStreamCdIdle = 0x36,
            kStreamSafeCdRead = 0x38,
            kPcmStreamOpen = 0x3B,
            kPcmStreamClose = 0x3C,
            kPcmStreamStop = 0x3D,
            kPcmStreamStart = 0x3E,
            kPcmStreamPosition = 0x40,
            kGetVoiceStatus = 0x42,
            kCallExtension = 0x4C,
            kBatch = 0x4D,
            kSetGroupVoiceRange = 0x4E,
            kSetReverb = 0x50,
            kBankLoadFromIop = 0x57,
            kBankLoadFromIopImage = 0x59,
            kStopAllSoundsInGroup = 0x61,
            kSetExternalInputMix = 0x64,
            kGetGlobalReg = 0x66,
            kSetGlobalReg = 0x67,
        };

        constexpr uint32_t kMaxCommandWords = 16u;
        constexpr uint32_t kMaxBatchCommands = 512u;
        constexpr uint32_t kSoundSlots = 64u;
        constexpr uint32_t kMaxStreamSlots = 32u;
        constexpr uint32_t kGroupCount = 17u;
        constexpr uint32_t kGlobalRegCount = 33u;
        constexpr uint32_t kSectorBytes = 2048u;
        constexpr uint32_t kEeRamSize = 32u * 1024u * 1024u;
        constexpr uint32_t kDefaultMasterVolume = 0x400u;
        constexpr uint32_t kHandleTypeStream = 4u;
        constexpr uint32_t kHandleTypeSound = 5u;
        constexpr uint32_t kFakeBankBase = 0x00A00000u; // "IOP" addresses handed to the EE as bank handles
        constexpr uint32_t kFakeBankStride = 0x00010000u;
        // The PCM ring the EE DMAs into. The game's ELF loads at 0x100000 and the runtime mirrors the kernel area only up
        // to 0x80000, so 0xA0000..0xA6000 is nobody's: the old 0x900000 sat inside the game's heap, where the game's own
        // writes turned the title music to scratch (research/32 section 7). It must stay under 16 MB: the EE masks
        // snd_PcmStreamPosition's answer to 24 bits before subtracting it (FUN_0030a3b0).
        constexpr uint32_t kFakePcmBuffer = 0x000A0000u;
        constexpr uint32_t kBankMagicSBlk = 0x6B6C4253u; // "SBlk"
        constexpr uint32_t kBankMagicSBv2 = 0x32764253u; // "SBv2"
        constexpr uint32_t kDstrmModuleId = 0x12C4E67Au;
        constexpr uint32_t kMaxCdReadBytes = 16u * 1024u * 1024u;

        // A bank sound is reported as finished after this long unless it is stopped earlier.
        constexpr std::chrono::milliseconds kSoundLifetime{2500};

        template <typename T>
        bool readGuestPod(const IopHost &host, uint32_t address, T &value)
        {
            value = {};
            return host.readGuest(address, &value, sizeof(value));
        }

        template <typename T>
        bool writeGuestPod(IopHost &host, uint32_t address, const T &value)
        {
            return host.writeGuest(address, &value, sizeof(value));
        }

        std::string hexString(uint32_t value)
        {
            char buffer[16];
            std::snprintf(buffer, sizeof(buffer), "0x%08x", value);
            return buffer;
        }

        const char *commandName(uint32_t fno)
        {
            switch (fno)
            {
            case kStartSoundSystem: return "snd_StartSoundSystem";
            case kStopSoundSystem: return "snd_StopSoundSystem";
            case kBankLoadEx: return "snd_BankLoadEx";
            case kBankLoadByLoc: return "snd_BankLoadByLoc";
            case kBankLoadEx2: return "snd_BankLoadEx(chunk2)";
            case kBankLoadByLoc2: return "snd_BankLoadByLoc(chunk2)";
            case kUnloadBank: return "snd_UnloadBank";
            case kUnloadBankData: return "snd_UnloadBankData";
            case kResolveBankXrefs: return "snd_ResolveBankXREFS";
            case kSetMasterVolume: return "snd_SetMasterVolume";
            case kGetMasterVolume: return "snd_GetMasterVolume";
            case kSetPlaybackMode: return "snd_SetPlaybackMode";
            case kGetPlaybackMode: return "snd_GetPlaybackMode";
            case kSetMixerMode: return "snd_SetMixerMode";
            case kSetReverbType: return "snd_SetReverbType";
            case kSetReverbDepth: return "snd_SetReverbDepth";
            case kAutoReverb: return "snd_AutoReverb";
            case kPlaySound: return "snd_PlaySoundVolPanPMPB";
            case kPlaySoundNoReturn: return "snd_PlaySoundVolPanPMPBNoReturn";
            case kPauseSound: return "snd_PauseSound";
            case kContinueSound: return "snd_ContinueSound";
            case kStopSound: return "snd_StopSound";
            case kPauseAllSoundsInGroup: return "snd_PauseAllSoundsInGroup";
            case kContinueAllSoundsInGroup: return "snd_ContinueAllSoundsInGroup";
            case kStopAllSounds: return "snd_StopAllSounds";
            case kSoundIsStillPlaying: return "snd_SoundIsStillPlaying";
            case kSetSoundVolPan: return "snd_SetSoundVolPan";
            case kSetSoundParam1E: return "snd_SetSoundParam1E";
            case kSetSoundPitchBend: return "snd_SetSoundPitchBend";
            case kSetSoundPitchModifier: return "snd_SetSoundPitchModifier";
            case kSetSoundParams: return "snd_SetSoundParams";
            case kAutoVol: return "snd_AutoVol";
            case kInitVagStreaming: return "snd_InitVAGStreamingEx";
            case kPlayVagStreamByLoc: return "snd_PlayVAGStreamByLoc";
            case kPauseVagStream: return "snd_PauseVAGStream";
            case kContinueVagStream: return "snd_ContinueVAGStream";
            case kStopVagStream: return "snd_StopVAGStream";
            case kStopAllVagStreams: return "snd_StopAllVAGStreams";
            case kShutdownVagStreaming: return "snd_ShutdownVAGStreaming";
            case kStreamCdIdle: return "snd_StreamCdIdle";
            case kStreamSafeCdRead: return "snd_StreamSafeCdRead";
            case kPcmStreamOpen: return "snd_PcmStreamOpen";
            case kPcmStreamClose: return "snd_PcmStreamClose";
            case kPcmStreamStop: return "snd_PcmStreamStop";
            case kPcmStreamStart: return "snd_PcmStreamStart";
            case kPcmStreamPosition: return "snd_PcmStreamPosition";
            case kGetVoiceStatus: return "snd_GetVoiceStatus";
            case kCallExtension: return "snd_CallExtension";
            case kBatch: return "snd_Batch";
            case kSetGroupVoiceRange: return "snd_SetGroupVoiceRange";
            case kSetReverb: return "snd_SetReverb";
            case kBankLoadFromIop: return "snd_BankLoadFromIOP";
            case kBankLoadFromIopImage: return "snd_BankLoadFromIOPImage";
            case kStopAllSoundsInGroup: return "snd_StopAllSoundsInGroup";
            case kSetExternalInputMix: return "snd_SetExternalInputMix";
            case kGetGlobalReg: return "snd_GetGlobalReg";
            case kSetGlobalReg: return "snd_SetGlobalReg";
            default: return "snd_Unknown";
            }
        }

        struct CommandArgs
        {
            std::array<uint32_t, kMaxCommandWords> words{};
            uint32_t address = 0u;
            uint32_t bytes = 0u;
            uint32_t wordCount = 0u;

            [[nodiscard]] uint32_t u32(uint32_t index) const
            {
                return index < wordCount ? words[index] : 0u;
            }

            [[nodiscard]] int32_t s32(uint32_t index) const
            {
                return static_cast<int32_t>(u32(index));
            }

            [[nodiscard]] int16_t s16(uint32_t index) const
            {
                return static_cast<int16_t>(u32(index) & 0xFFFFu);
            }

            [[nodiscard]] GuestBuffer guestBuffer() const
            {
                return GuestBuffer{address, bytes};
            }
        };

        struct Bank
        {
            uint32_t handle = 0u;
            bool loaded = false;
            bool byLocation = false;
            uint32_t sector = 0u;
            uint32_t byteOffset = 0u;
            std::string path;
            uint32_t fileType = 0u;
            uint32_t magic = 0u;
            uint32_t version = 0u;
            uint32_t bankId = 0u;
            int16_t numSounds = 0;
            uint32_t blockBytes = 0u;
            uint32_t vagDataBytes = 0u;
        };

        struct SoundSlot
        {
            uint32_t handle = 0u;
            bool active = false;
            bool paused = false;
            uint32_t bank = 0u;
            uint32_t sound = 0u;
            int32_t volume = 0;
            int32_t pan = 0;
            int16_t pitchMod = 0;
            int16_t pitchBend = 0;
            std::chrono::steady_clock::time_point started{};
        };

        struct StreamSlot
        {
            uint32_t handle = 0u;
            bool active = false;
            bool paused = false;
            uint32_t sector1 = 0u;
            uint32_t sector2 = 0u;
            uint32_t offset1 = 0u;
            uint32_t offset2 = 0u;
            int32_t volume = 0;
            int32_t pan = 0;
            uint32_t group = 0u;
            uint32_t parent = 0u;
            uint32_t flags = 0u;
        };

        struct Model
        {
            bool started = false;
            uint32_t startFlags = 0u;
            uint32_t statusBlockAddress = 0u;
            int32_t playbackMode = 0;
            std::array<int32_t, kGroupCount> masterVolume{};
            std::array<std::pair<int16_t, int16_t>, 16> groupVoiceRange{};
            std::array<int8_t, kGlobalRegCount> globalRegs{};
            std::array<int32_t, 2> reverbType{};
            std::array<int32_t, 2> reverbDepth{};
            bool externalInputMix = false;

            std::vector<Bank> banks;
            uint32_t lastBank = 0u;
            std::array<SoundSlot, kSoundSlots> sounds{};
            uint32_t nextUid = 1u;

            bool streamingInitialised = false;
            uint32_t streamCount = 0u;
            uint32_t streamBufferBytes = 0u;
            std::array<StreamSlot, kMaxStreamSlots> streams{};

            bool pcmStreamOpen = false;
            uint32_t pcmBuffer = 0u;      // the ring the EE DMAs PCM into (a guest allocation, research/32 section 7)
            uint32_t pcmBufferBytes = 0u;
            int32_t pcmVolume = 0x400;
            uint32_t pcmChannels = 2u;
            bool dstrmInitialised = false;
        };

        class Snd989Service final : public IopService
        {
        public:
            explicit Snd989Service(IopHost &host)
                : m_host(host)
            {
                resetLocked();
            }

            ~Snd989Service() override
            {
                if (m_metrics.unknownBankRejects > 8u)
                {
                    logWarning("unknown-bank rejects: " + std::to_string(m_metrics.unknownBankRejects) +
                               " in all, " + std::to_string(m_metrics.unknownBankRejects - 8u) +
                               " more than the 8 logged in full");
                }
                closeCdImage();
            }

            [[nodiscard]] std::string_view name() const override
            {
                return "989snd";
            }

            [[nodiscard]] std::span<const uint32_t> sids() const override
            {
                return kSids;
            }

            void reset() override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                resetLocked();
            }

            [[nodiscard]] RpcResult handleRpc(const RpcRequest &request) override
            {
                RpcResult result{};
                if (request.sid != kSndSid && request.sid != kStreamSid)
                {
                    return result;
                }

                std::lock_guard<std::mutex> lock(m_mutex);
                ++m_metrics.rpcCalls;

                if (request.sid == kStreamSid)
                {
                    handleStreamServer(request);
                }
                else if (request.function == kBatch)
                {
                    handleBatch(request);
                }
                else
                {
                    handleSingle(request);
                }

                result.handled = true;
                result.resultAddress = request.receive.address;
                return result;
            }

            void onSifTransfer(const SifTransfer &transfer) override
            {
                if (transfer.kind != SifTransferKind::SetDma || transfer.phase != SifTransferPhase::AfterCopy)
                    return;
                uint32_t buffer = 0u, bytes = 0u;
                {
                    std::lock_guard<std::mutex> lock(m_mutex);
                    buffer = m_model.pcmBuffer;
                    bytes = m_model.pcmBufferBytes;
                }
                if (buffer == 0u || bytes == 0u || transfer.size == 0u)
                    return;
                const uint64_t dst = transfer.destinationAddress & 0x1FFFFFFFu;
                const uint64_t base = buffer & 0x1FFFFFFFu;
                if (dst + transfer.size <= base || dst >= base + bytes)
                    return;
                const uint64_t from = std::max<uint64_t>(dst, base);
                const uint64_t to = std::min<uint64_t>(dst + transfer.size, base + bytes);
                static const bool trace = std::getenv("PS2X_MPEG_TRACE") != nullptr;
                if (trace)
                {
                    // one line per SIF DMA into the PCM ring: where the EE copied it from (research/32 section 7.1)
                    std::fprintf(stderr, "[989snd:PcmDma] src=0x%08x dst=0x%08x bytes=%u ring_off=%u\n",
                                 transfer.sourceAddress, transfer.destinationAddress, transfer.size,
                                 static_cast<unsigned>(from - base));
                }
                std::vector<uint8_t> copy(static_cast<size_t>(to - from));
                if (m_host.readGuest(transfer.destinationAddress + static_cast<uint32_t>(from - dst), copy.data(), copy.size()))
                    m_host.audioPcmWrite(static_cast<uint32_t>(from - base), copy.data(), copy.size());
            }

            void appendDebugMetrics(std::vector<DebugMetric> &metrics) const override
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                metrics.push_back({"rpc_calls", m_metrics.rpcCalls});
                metrics.push_back({"batched_commands", m_metrics.batchedCommands});
                metrics.push_back({"banks_loaded", m_metrics.banksLoaded});
                metrics.push_back({"bank_load_failures", m_metrics.bankLoadFailures});
                metrics.push_back({"sounds_played", m_metrics.soundsPlayed});
                metrics.push_back({"streams_played", m_metrics.streamsPlayed});
                metrics.push_back({"cd_reads", m_metrics.cdReads});
                metrics.push_back({"cd_read_failures", m_metrics.cdReadFailures});
                metrics.push_back({"unknown_commands", m_metrics.unknownCommands});
                metrics.push_back({"unknown_bank_rejects", m_metrics.unknownBankRejects});
                metrics.push_back({"active_sounds", countActiveSounds()});
                metrics.push_back({"status_block", m_model.statusBlockAddress, true});
            }

        private:
            struct Metrics
            {
                uint64_t rpcCalls = 0u;
                uint64_t batchedCommands = 0u;
                uint64_t banksLoaded = 0u;
                uint64_t bankLoadFailures = 0u;
                uint64_t soundsPlayed = 0u;
                uint64_t streamsPlayed = 0u;
                uint64_t cdReads = 0u;
                uint64_t cdReadFailures = 0u;
                uint64_t unknownCommands = 0u;
                uint64_t unknownBankRejects = 0u;
            };

            inline static constexpr std::array<uint32_t, 2> kSids{kSndSid, kStreamSid};

            void resetLocked()
            {
                m_model = {};
                m_model.masterVolume.fill(static_cast<int32_t>(kDefaultMasterVolume));
                for (auto &range : m_model.groupVoiceRange)
                {
                    range = {0, 0x2F};
                }
                closeCdImage();
            }

            // ---- logging -------------------------------------------------------------------

            void logDebug(const std::string &message)
            {
                m_host.log(LogLevel::Debug, "989snd: " + message);
            }

            void logWarning(const std::string &message)
            {
                m_host.log(LogLevel::Warning, "989snd: " + message);
            }

            void logCommand(uint32_t fno, const CommandArgs &args, uint32_t result, bool hasResult)
            {
                // Polled every frame (or in a busy loop while a level loads): log the first few
                // and then every 4096th, otherwise the run log is 800k lines of idle polls.
                if (fno == kStreamCdIdle || fno == kPcmStreamPosition)
                {
                    static uint32_t s_polls[2] = {0u, 0u};
                    uint32_t &n = s_polls[fno == kStreamCdIdle ? 0 : 1];
                    ++n;
                    if (n > 4u && (n & 0xFFFu) != 0u)
                        return;
                }
                std::string message = commandName(fno);
                message += " (fno ";
                message += hexString(fno);
                message += ")";
                const uint32_t shown = std::min<uint32_t>(args.wordCount, 8u);
                for (uint32_t i = 0; i < shown; ++i)
                {
                    message += i == 0 ? " [" : ", ";
                    message += hexString(args.words[i]);
                }
                if (shown != 0u)
                {
                    message += args.wordCount > shown ? ", ...]" : "]";
                }
                if (hasResult)
                {
                    message += " -> ";
                    message += hexString(result);
                }
                logDebug(message);
            }

            // ---- RPC plumbing --------------------------------------------------------------

            bool loadArgs(uint32_t address, uint32_t bytes, CommandArgs &args) const
            {
                args = {};
                args.address = address;
                args.bytes = bytes;
                if (address == 0u || bytes == 0u)
                {
                    return true;
                }
                const uint32_t clamped = std::min<uint32_t>(bytes, kMaxCommandWords * 4u);
                std::array<uint8_t, kMaxCommandWords * 4u> raw{};
                if (!m_host.readGuest(address, raw.data(), clamped))
                {
                    return false;
                }
                args.wordCount = (clamped + 3u) / 4u;
                for (uint32_t i = 0; i < args.wordCount; ++i)
                {
                    std::memcpy(&args.words[i], raw.data() + i * 4u, sizeof(uint32_t));
                }
                return true;
            }

            void writeReplyWord(const GuestBuffer &receive, uint32_t index, uint32_t value)
            {
                const uint32_t offset = index * 4u;
                if (receive.address == 0u || offset + 4u > receive.size)
                {
                    return;
                }
                (void)writeGuestPod(m_host, receive.address + offset, value);
            }

            void handleSingle(const RpcRequest &request)
            {
                CommandArgs args;
                if (!loadArgs(request.send.address, request.send.size, args))
                {
                    logWarning("could not read arguments for fno " + hexString(request.function));
                }
                bool hasResult = false;
                const uint32_t value = execute(request.function, args, hasResult);
                writeReplyWord(request.receive, 0u, 0xFFFFFFFFu);
                writeReplyWord(request.receive, 1u, value);
                writeReplyWord(request.receive, 2u, 0xFFFFFFFFu);
            }

            void handleBatch(const RpcRequest &request)
            {
                uint32_t count = 0u;
                if (request.send.address == 0u || !readGuestPod(m_host, request.send.address, count))
                {
                    logWarning("batch with unreadable header");
                    writeReplyWord(request.receive, 0u, 0xFFFFFFFFu);
                    writeReplyWord(request.receive, 1u, 0xFFFFFFFFu);
                    return;
                }
                count = std::min<uint32_t>(count, kMaxBatchCommands);
                const uint32_t end = request.send.address + request.send.size;
                uint32_t cursor = request.send.address + 4u;

                writeReplyWord(request.receive, 0u, 0xFFFFFFFFu);
                for (uint32_t i = 0; i < count; ++i)
                {
                    uint32_t header = 0u;
                    if (cursor + 4u > end || !readGuestPod(m_host, cursor, header))
                    {
                        logWarning("batch truncated at command " + std::to_string(i));
                        break;
                    }
                    const uint32_t fno = header & 0xFFFFu;
                    const uint32_t argBytes = (header >> 16) & 0xFFFFu;
                    const uint32_t paddedBytes = (argBytes + 3u) & ~3u;
                    const uint32_t argAddress = cursor + 4u;

                    CommandArgs args;
                    if (!loadArgs(argAddress, std::min(argBytes, end > argAddress ? end - argAddress : 0u), args))
                    {
                        logWarning("batch: could not read arguments for fno " + hexString(fno));
                    }
                    bool hasResult = false;
                    const uint32_t value = execute(fno, args, hasResult);
                    writeReplyWord(request.receive, 1u + i, value);
                    ++m_metrics.batchedCommands;

                    cursor = argAddress + paddedBytes;
                }
                writeReplyWord(request.receive, 1u + count, 0xFFFFFFFFu);
            }

            void handleStreamServer(const RpcRequest &request)
            {
                CommandArgs args;
                if (!loadArgs(request.send.address, request.send.size, args))
                {
                    logWarning("stream server: could not read arguments");
                }
                uint32_t value = 0u;
                switch (request.function)
                {
                case kBankLoadEx:
                case kBankLoadByLoc:
                case kBankLoadEx2:
                case kBankLoadByLoc2:
                case kBankLoadFromIop:
                case kBankLoadFromIopImage:
                {
                    bool hasResult = false;
                    value = execute(request.function, args, hasResult);
                    break;
                }
                default:
                    ++m_metrics.unknownCommands;
                    logWarning("stream server: unknown fno " + hexString(request.function));
                    break;
                }
                if (request.receive.size >= 4u)
                {
                    writeReplyWord(request.receive, 0u, value);
                }
                else
                {
                    (void)m_host.zeroGuest(request.receive.address, request.receive.size);
                }
            }

            // ---- command execution ---------------------------------------------------------

            uint32_t execute(uint32_t fno, const CommandArgs &args, bool &hasResult)
            {
                hasResult = false;
                uint32_t value = 0u;
                switch (fno)
                {
                case kStartSoundSystem:
                    m_model.statusBlockAddress = args.u32(0);
                    m_model.startFlags = args.u32(1);
                    m_model.started = true;
                    break;

                case kStopSoundSystem:
                    stopAllSounds();
                    stopAllStreams();
                    m_model.started = false;
                    break;

                case kBankLoadEx:
                case kBankLoadEx2:
                    value = loadBankByName(args);
                    hasResult = true;
                    break;

                case kBankLoadByLoc:
                case kBankLoadByLoc2:
                    value = loadBankByLocation(args.u32(0), args.u32(1));
                    hasResult = true;
                    break;

                case kBankLoadFromIop:
                case kBankLoadFromIopImage:
                    logWarning("bank load from IOP memory is not supported");
                    ++m_metrics.bankLoadFailures;
                    hasResult = true;
                    break;

                case kUnloadBank:
                    unloadBank(args.u32(0));
                    hasResult = true;
                    break;

                case kUnloadBankData:
                case kResolveBankXrefs:
                    break;

                case kSetMasterVolume:
                {
                    const uint32_t group = args.u32(0);
                    const int32_t volume = std::clamp(args.s32(1), 0, static_cast<int32_t>(kDefaultMasterVolume));
                    if (group < kGroupCount && group != 15u)
                    {
                        m_model.masterVolume[group] = volume;
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kGetMasterVolume:
                {
                    const uint32_t group = args.u32(0);
                    value = group < kGroupCount ? static_cast<uint32_t>(m_model.masterVolume[group]) : 0u;
                    hasResult = true;
                    break;
                }

                case kSetPlaybackMode:
                    m_model.playbackMode = static_cast<int16_t>(args.u32(0) & 0xFFFFu);
                    break;

                case kGetPlaybackMode:
                    value = static_cast<uint32_t>(m_model.playbackMode);
                    hasResult = true;
                    break;

                case kSetMixerMode:
                    break;

                case kSetReverbType:
                    applyPerCore(args.u32(0), [&](uint32_t core)
                                 { m_model.reverbType[core] = args.s32(1); });
                    break;

                case kSetReverbDepth:
                    applyPerCore(args.u32(0), [&](uint32_t core)
                                 { m_model.reverbDepth[core] = args.s32(1); });
                    break;

                case kAutoReverb:
                    applyPerCore(args.u32(0), [&](uint32_t core)
                                 { m_model.reverbDepth[core] = args.s32(1); });
                    break;

                case kSetReverb:
                    applyPerCore(args.u32(0), [&](uint32_t core)
                                 {
                                     m_model.reverbType[core] = args.s32(1);
                                     m_model.reverbDepth[core] = args.s32(2);
                                 });
                    break;

                case kPlaySound:
                case kPlaySoundNoReturn:
                    value = playSound(fno, args);
                    hasResult = fno == kPlaySound;
                    break;

                case kPauseSound:
                    setSoundPaused(args.u32(0), true);
                    forwardAudio(fno, args);
                    break;

                case kContinueSound:
                    setSoundPaused(args.u32(0), false);
                    forwardAudio(fno, args);
                    break;

                case kStopSound:
                    stopSound(args.u32(0));
                    forwardAudio(fno, args);
                    break;

                case kPauseAllSoundsInGroup:
                    for (auto &slot : m_model.sounds)
                    {
                        if (slot.active)
                        {
                            slot.paused = true;
                        }
                    }
                    forwardAudio(fno, args);
                    break;

                case kContinueAllSoundsInGroup:
                    for (auto &slot : m_model.sounds)
                    {
                        if (slot.active)
                        {
                            slot.paused = false;
                        }
                    }
                    forwardAudio(fno, args);
                    break;

                case kStopAllSounds:
                case kStopAllSoundsInGroup:
                    stopAllSounds();
                    forwardAudio(fno, args);
                    break;

                case kSoundIsStillPlaying:
                    value = soundIsStillPlaying(args.u32(0));
                    hasResult = true;
                    break;

                case kSetSoundVolPan:
                {
                    SoundSlot *slot = findSound(args.u32(0));
                    if (slot != nullptr)
                    {
                        if (args.s32(1) != 0x7FFFFFFF)
                        {
                            slot->volume = args.s32(1);
                        }
                        if (args.s32(2) != -2)
                        {
                            slot->pan = args.s32(2);
                        }
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kSetSoundParams:
                {
                    SoundSlot *slot = findSound(args.u32(0));
                    if (slot != nullptr)
                    {
                        const uint32_t mask = args.u32(1);
                        if ((mask & 1u) != 0u)
                        {
                            slot->volume = args.s32(2);
                        }
                        if ((mask & 6u) != 0u)
                        {
                            slot->pan = args.s32(3);
                        }
                        if ((mask & 8u) != 0u)
                        {
                            slot->pitchMod = args.s16(4);
                        }
                        if ((mask & 0x10u) != 0u)
                        {
                            slot->pitchBend = args.s16(5);
                        }
                        value = slot->handle;
                    }
                    forwardAudio(fno, args);
                    hasResult = true;
                    break;
                }

                case kSetSoundPitchBend:
                {
                    SoundSlot *slot = findSound(args.u32(0));
                    if (slot != nullptr)
                    {
                        slot->pitchBend = args.s16(1);
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kSetSoundPitchModifier:
                {
                    SoundSlot *slot = findSound(args.u32(0));
                    if (slot != nullptr)
                    {
                        slot->pitchMod = args.s16(1);
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kSetSoundParam1E:
                    forwardAudio(fno, args);
                    break;

                case kAutoVol:
                {
                    SoundSlot *slot = findSound(args.u32(0));
                    if (slot != nullptr)
                    {
                        if (args.s32(1) == -4)
                        {
                            // fade out and stop: treat as an immediate stop in the model
                            slot->active = false;
                        }
                        else
                        {
                            slot->volume = args.s32(1);
                        }
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kInitVagStreaming:
                    value = initVagStreaming(args);
                    hasResult = true;
                    break;

                case kPlayVagStreamByLoc:
                    value = playVagStream(args);
                    hasResult = true;
                    break;

                case kPauseVagStream:
                case kContinueVagStream:
                {
                    StreamSlot *slot = findStream(args.u32(0));
                    if (slot != nullptr)
                    {
                        slot->paused = fno == kPauseVagStream;
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kStopVagStream:
                {
                    StreamSlot *slot = findStream(args.u32(0));
                    if (slot != nullptr)
                    {
                        slot->active = false;
                    }
                    forwardAudio(fno, args);
                    break;
                }

                case kStopAllVagStreams:
                    stopAllStreams();
                    forwardAudio(fno, args);
                    break;

                case kShutdownVagStreaming:
                    stopAllStreams();
                    forwardAudio(fno, args);
                    m_model.streamingInitialised = false;
                    m_model.streamCount = 0u;
                    break;

                case kStreamCdIdle:
                    value = 1u; // never busy: reads complete synchronously
                    hasResult = true;
                    break;

                case kStreamSafeCdRead:
                    value = streamSafeCdRead(args.u32(0), args.u32(1), args.u32(2));
                    hasResult = true;
                    break;

                case kPcmStreamOpen:
                {
                    // {bytes, p2, vol, p4, channels, mode}: the ring the EE will DMA PCM into. A real guest allocation,
                    // so the copies land somewhere of ours (the fixed 0x900000 landed in the game's own memory) and
                    // onSifTransfer can hand the bytes to the host mixer.
                    m_model.pcmStreamOpen = true;
                    m_model.pcmBufferBytes = args.u32(0);
                    m_model.pcmVolume = args.s32(2);
                    m_model.pcmChannels = args.u32(4) ? args.u32(4) : 2u;
                    if (m_model.pcmBuffer == 0u)
                        m_model.pcmBuffer = kFakePcmBuffer;
                    value = m_model.pcmBuffer != 0u ? m_model.pcmBuffer : kFakePcmBuffer;
                    hasResult = true;
                    break;
                }

                case kPcmStreamClose:
                    m_model.pcmStreamOpen = false;
                    forwardAudio(fno, args);
                    break;

                case kPcmStreamStop:
                    forwardAudio(fno, args);
                    break;

                case kPcmStreamStart:
                {
                    // {buf, size, end, freq, channels}: the host gets the ring size, the rate (0 = 48000), the channels
                    // (0 = the open call's) and the open call's volume.
                    forwardAudio(kPcmStreamStop, args);   // the audioCommand path, as before
                    const uint32_t channels = args.u32(4) ? args.u32(4) : m_model.pcmChannels;
                    const int32_t words[5] = {static_cast<int32_t>(args.u32(1) ? args.u32(1) : m_model.pcmBufferBytes),
                                              static_cast<int32_t>(args.u32(3)), static_cast<int32_t>(channels), m_model.pcmVolume,
                                              static_cast<int32_t>(m_model.pcmBuffer)};
                    m_host.audioNotify(kPcmStreamStart, words, 5u);
                    break;
                }

                case kPcmStreamPosition:
                {
                    // The IRX answers sceSdBlockTransStatus: the DMA's current IOP address. The EE (FUN_0030a3b0) masks it to
                    // 24 bits and subtracts the ring address it was given at open, so this is ring + play offset.
                    uint32_t position = 0u;
                    value = m_host.audioPcmPosition(position) ? ((m_model.pcmBuffer + position) & 0xFFFFFFu) : 0u;
                    hasResult = true;
                    {
                        static const bool trace = std::getenv("PS2X_MPEG_TRACE") != nullptr;
                        if (trace)
                        {
                            // every poll (research/32 section 7.1: the game fills the ring up to this position each wake)
                            std::fprintf(stderr, "[989snd:PcmPos] play_off=%u\n", position);
                        }
                    }
                    break;
                }

                case kGetVoiceStatus:
                    value = 0u;
                    hasResult = true;
                    break;

                case kCallExtension:
                    value = callExtension(args);
                    hasResult = true;
                    break;

                case kSetGroupVoiceRange:
                {
                    const uint32_t group = args.u32(0);
                    if (group < m_model.groupVoiceRange.size())
                    {
                        m_model.groupVoiceRange[group] = {
                            static_cast<int16_t>(std::max(args.s32(1), 0)),
                            static_cast<int16_t>(std::min(args.s32(2), 0x2F))};
                    }
                    break;
                }

                case kSetExternalInputMix:
                    m_model.externalInputMix = args.u32(0) != 0u;
                    break;

                case kSetGlobalReg:
                {
                    const uint32_t index = args.u32(0);
                    if (index >= 1u && index < kGlobalRegCount)
                    {
                        m_model.globalRegs[index] = static_cast<int8_t>(args.u32(1) & 0xFFu);
                    }
                    break;
                }

                case kGetGlobalReg:
                {
                    const uint32_t index = args.u32(0);
                    value = index >= 1u && index < kGlobalRegCount
                                ? static_cast<uint32_t>(static_cast<int32_t>(m_model.globalRegs[index]))
                                : 0u;
                    hasResult = true;
                    break;
                }

                default:
                    ++m_metrics.unknownCommands;
                    logWarning("unhandled fno " + hexString(fno) + " (" + std::to_string(args.bytes) + " arg bytes)");
                    break;
                }

                logCommand(fno, args, value, hasResult);
                return value;
            }

            template <typename Fn>
            void applyPerCore(uint32_t coreMask, Fn &&fn)
            {
                if ((coreMask & 1u) != 0u)
                {
                    fn(0u);
                }
                if ((coreMask & 2u) != 0u)
                {
                    fn(1u);
                }
            }

            void forwardAudio(uint32_t fno, const CommandArgs &args)
            {
                m_host.audioCommand(kSndSid, fno, args.guestBuffer(), GuestBuffer{});
                if (fno == kPlaySound || fno == kPlaySoundNoReturn || fno == kPlayVagStreamByLoc)
                    return;   // playSound / playVagStream notify with their handle
                int32_t words[16] = {};
                const uint32_t count = std::min<uint32_t>(args.bytes / 4u, 16u);
                for (uint32_t i = 0; i < count; ++i)
                    words[i] = args.s32(i);
                m_host.audioNotify(fno, words, count);
            }

            // ---- handles -------------------------------------------------------------------

            uint32_t makeHandle(uint32_t type, uint32_t slot)
            {
                uint32_t uid = m_model.nextUid++ & 0xFFFFu;
                if (uid == 0u)
                {
                    uid = m_model.nextUid++ & 0xFFFFu;
                }
                return (type << 24) | ((slot & 0xFFu) << 16) | uid;
            }

            SoundSlot *findSound(uint32_t handle)
            {
                if (handle == 0u)
                {
                    return nullptr;
                }
                if (handle == 0xFFFFFFFFu)
                {
                    return nullptr; // the IRX reports error 100 for -1 handles (only banks accept -1)
                }
                if (((handle >> 24) & 0x1Fu) != kHandleTypeSound)
                {
                    return nullptr;
                }
                const uint32_t index = (handle >> 16) & 0xFFu;
                if (index >= kSoundSlots)
                {
                    return nullptr;
                }
                SoundSlot &slot = m_model.sounds[index];
                return slot.active && slot.handle == handle ? &slot : nullptr;
            }

            StreamSlot *findStream(uint32_t handle)
            {
                if (handle == 0u || ((handle >> 24) & 0x1Fu) != kHandleTypeStream)
                {
                    return nullptr;
                }
                const uint32_t index = (handle >> 16) & 0xFFu;
                if (index >= kMaxStreamSlots)
                {
                    return nullptr;
                }
                StreamSlot &slot = m_model.streams[index];
                return slot.active && slot.handle == handle ? &slot : nullptr;
            }

            uint64_t countActiveSounds() const
            {
                uint64_t count = 0u;
                for (const auto &slot : m_model.sounds)
                {
                    if (slot.active)
                    {
                        ++count;
                    }
                }
                return count;
            }

            // ---- bank sounds ---------------------------------------------------------------

            uint32_t playSound(uint32_t fno, const CommandArgs &args)
            {
                uint32_t bank = args.u32(0);
                if (bank == 0xFFFFFFFFu)
                {
                    bank = m_model.lastBank;
                }
                if (bank == 0u || findBank(bank) == nullptr)
                {
                    rejectUnknownBank(bank);
                    return 0u;
                }

                const auto now = std::chrono::steady_clock::now();
                SoundSlot *target = nullptr;
                for (auto &slot : m_model.sounds)
                {
                    if (!slot.active || now - slot.started > kSoundLifetime)
                    {
                        target = &slot;
                        break;
                    }
                }
                if (target == nullptr)
                {
                    // steal the oldest voice, like the IRX voice allocator would
                    target = &m_model.sounds[0];
                    for (auto &slot : m_model.sounds)
                    {
                        if (slot.started < target->started)
                        {
                            target = &slot;
                        }
                    }
                }

                const uint32_t index = static_cast<uint32_t>(target - m_model.sounds.data());
                *target = {};
                target->handle = makeHandle(kHandleTypeSound, index);
                target->active = true;
                target->bank = bank;
                target->sound = args.u32(1);
                target->volume = args.s32(2);
                target->pan = args.s32(3);
                target->pitchMod = args.s16(4);
                target->pitchBend = args.s16(5);
                target->started = now;
                ++m_metrics.soundsPlayed;

                forwardAudio(fno, args);
                const int32_t words[7] = {static_cast<int32_t>(target->handle), static_cast<int32_t>(bank),
                                          static_cast<int32_t>(target->sound), target->volume, target->pan,
                                          target->pitchMod, target->pitchBend};
                m_host.audioNotify(fno, words, 7u);
                return target->handle;
            }

            // 971 rejects in one run (2026-09-18) for banks the log shows loaded, with no unload between. Dump
            // the whole bank table once per process at the first reject -- one launch then says whether the slot
            // was cleared or the handle is stale -- and rate-limit the reject line itself to the first 8 and
            // every 256th after that; the destructor reports what was suppressed.
            void rejectUnknownBank(uint32_t bank)
            {
                static bool s_tableDumped = false;
                if (!s_tableDumped)
                {
                    s_tableDumped = true;
                    std::string table = "bank table at the first unknown-bank reject (requested " + hexString(bank) +
                                        ", " + std::to_string(m_model.banks.size()) + " entries, lastBank " +
                                        hexString(m_model.lastBank) + ")";
                    for (const auto &entry : m_model.banks)
                    {
                        table += "\n  handle " + hexString(entry.handle) + " loaded=" + (entry.loaded ? "1" : "0") +
                                 " id=" + hexString(entry.bankId) + " sector " + std::to_string(entry.sector) + "+" +
                                 std::to_string(entry.byteOffset);
                        if (!entry.path.empty())
                        {
                            table += " path " + entry.path;
                        }
                    }
                    logWarning(table);
                }
                ++m_metrics.unknownBankRejects;
                if (m_metrics.unknownBankRejects <= 8u || (m_metrics.unknownBankRejects % 256u) == 0u)
                {
                    logDebug("play request for unknown bank " + hexString(bank) + " (reject " +
                             std::to_string(m_metrics.unknownBankRejects) + ")");
                }
            }

            void setSoundPaused(uint32_t handle, bool paused)
            {
                SoundSlot *slot = findSound(handle);
                if (slot != nullptr)
                {
                    slot->paused = paused;
                }
            }

            void stopSound(uint32_t handle)
            {
                if (SoundSlot *slot = findSound(handle); slot != nullptr)
                {
                    slot->active = false;
                    return;
                }
                // snd_StopSound is also how the game stops a VAG stream (a type-4 handle): free the model's
                // stream slot too, or the slot leaks and every later snd_PlayVAGStreamByLoc is refused with
                // "no free VAG stream slot" (237 of them in the owner's run of 2026-09-18). The mixer stop is
                // the caller's forwardAudio(kStopSound, ...) in execute(), which is unchanged.
                if (StreamSlot *stream = findStream(handle); stream != nullptr)
                {
                    stream->active = false;
                }
            }

            void stopAllSounds()
            {
                for (auto &slot : m_model.sounds)
                {
                    slot.active = false;
                }
            }

            uint32_t soundIsStillPlaying(uint32_t handle)
            {
                if (handle == 0xFFFFFFFFu)
                {
                    return 0xFFFFFFFFu;
                }
                {
                    bool playing = false;
                    if (m_host.audioIsPlaying(handle, playing))   // the host mixer's answer, when it has one
                    {
                        if (!playing)
                        {
                            if (SoundSlot *slot = findSound(handle))
                                slot->active = false;
                            return 0u;
                        }
                        return handle;
                    }
                }
                SoundSlot *slot = findSound(handle);
                if (slot == nullptr)
                {
                    return 0u;
                }
                const auto now = std::chrono::steady_clock::now();
                if (!slot->paused && now - slot->started > kSoundLifetime)
                {
                    slot->active = false;
                    return 0u;
                }
                return slot->handle;
            }

            // ---- banks ---------------------------------------------------------------------

            Bank *findBank(uint32_t handle)
            {
                for (auto &bank : m_model.banks)
                {
                    if (bank.loaded && bank.handle == handle)
                    {
                        return &bank;
                    }
                }
                return nullptr;
            }

            Bank &allocateBank()
            {
                for (auto &bank : m_model.banks)
                {
                    if (!bank.loaded)
                    {
                        const uint32_t handle = bank.handle;
                        bank = {};
                        bank.handle = handle;
                        return bank;
                    }
                }
                Bank bank;
                bank.handle = kFakeBankBase + static_cast<uint32_t>(m_model.banks.size()) * kFakeBankStride;
                m_model.banks.push_back(bank);
                return m_model.banks.back();
            }

            uint32_t loadBankByName(const CommandArgs &args)
            {
                const uint32_t fileOffset = args.u32(0);
                std::string path;
                if (args.address != 0u && args.bytes > 4u)
                {
                    std::vector<char> raw(std::min<uint32_t>(args.bytes - 4u, 256u) + 1u, '\0');
                    if (m_host.readGuest(args.address + 4u, raw.data(), raw.size() - 1u))
                    {
                        path = raw.data();
                    }
                }

                Bank &bank = allocateBank();
                bank.byLocation = false;
                bank.path = path;
                bank.byteOffset = fileOffset;
                bank.loaded = true;

                const std::string hostPath = path.empty() ? std::string() : m_host.translateGuestPath(path);
                const uint64_t handle = hostPath.empty() ? 0u : m_host.openHostFile(hostPath);
                if (handle == 0u)
                {
                    ++m_metrics.bankLoadFailures;
                    logWarning("snd_BankLoadEx: cannot open '" + path + "' (" + hostPath + "); returning empty bank " +
                               hexString(bank.handle));
                }
                else
                {
                    parseBankHeader(bank, handle, fileOffset);
                    m_host.closeHostFile(handle);
                }
                finishBankLoad(bank);
                return bank.handle;
            }

            uint32_t loadBankByLocation(uint32_t sector, uint32_t byteOffset)
            {
                Bank &bank = allocateBank();
                bank.byLocation = true;
                bank.sector = sector;
                bank.byteOffset = byteOffset;
                bank.loaded = true;

                const uint64_t image = cdImage();
                if (image == 0u)
                {
                    ++m_metrics.bankLoadFailures;
                    logWarning("snd_BankLoadByLoc: CD image unavailable; returning empty bank " + hexString(bank.handle));
                }
                else
                {
                    parseBankHeader(bank, image, static_cast<uint64_t>(sector) * kSectorBytes + byteOffset);
                }
                finishBankLoad(bank);
                return bank.handle;
            }

            void parseBankHeader(Bank &bank, uint64_t file, uint64_t base)
            {
                std::array<uint32_t, 8> attributes{};
                size_t bytesRead = 0u;
                if (!m_host.readHostFile(file, base, attributes.data(), sizeof(attributes), bytesRead) ||
                    bytesRead != sizeof(attributes))
                {
                    ++m_metrics.bankLoadFailures;
                    logWarning("bank header unreadable at offset " + std::to_string(base));
                    return;
                }
                bank.fileType = attributes[0];
                const uint32_t chunk0Offset = attributes[2];
                bank.blockBytes = attributes[3];
                bank.vagDataBytes = attributes[1] > 1u ? attributes[5] : 0u;
                if (bank.fileType != 1u && bank.fileType != 3u)
                {
                    ++m_metrics.bankLoadFailures;
                    logWarning("bank at offset " + std::to_string(base) + " has unexpected type " +
                               std::to_string(bank.fileType));
                    return;
                }

                std::array<uint32_t, 16> block{};
                if (!m_host.readHostFile(file, base + chunk0Offset, block.data(), sizeof(block), bytesRead) ||
                    bytesRead != sizeof(block))
                {
                    ++m_metrics.bankLoadFailures;
                    logWarning("bank block unreadable");
                    return;
                }
                bank.magic = block[0];
                bank.version = block[1];
                bank.bankId = block[3];
                bank.numSounds = static_cast<int16_t>(block[5] >> 16);   // NumSounds is the s16 at 0x16 (research/32 section 1)
                if (bank.magic != kBankMagicSBlk && bank.magic != kBankMagicSBv2)
                {
                    logWarning("bank block has unknown magic " + hexString(bank.magic));
                    return;
                }
                // The host mixer plays from the bytes themselves: chunk 0 (the block) and chunk 1 (the VAG data).
                const uint32_t chunk1Offset = attributes[1] > 1u ? attributes[4] : 0u;
                if (bank.blockBytes == 0u || bank.blockBytes > (8u << 20) || bank.vagDataBytes > (64u << 20))
                    return;
                std::vector<uint8_t> blockBytes(bank.blockBytes);
                std::vector<uint8_t> vagBytes(bank.vagDataBytes);
                if (!m_host.readHostFile(file, base + chunk0Offset, blockBytes.data(), blockBytes.size(), bytesRead) ||
                    bytesRead != blockBytes.size())
                {
                    logWarning("bank block chunk unreadable");
                    return;
                }
                if (!vagBytes.empty() &&
                    (!m_host.readHostFile(file, base + chunk1Offset, vagBytes.data(), vagBytes.size(), bytesRead) ||
                     bytesRead != vagBytes.size()))
                {
                    logWarning("bank VAG chunk unreadable");
                    return;
                }
                m_host.audioBank(bank.handle, blockBytes.data(), blockBytes.size(), vagBytes.data(), vagBytes.size());
            }

            void finishBankLoad(Bank &bank)
            {
                m_model.lastBank = bank.handle;
                ++m_metrics.banksLoaded;
                std::string message = "bank loaded -> " + hexString(bank.handle);
                if (bank.byLocation)
                {
                    message += " sector " + std::to_string(bank.sector) + "+" + std::to_string(bank.byteOffset);
                }
                else
                {
                    message += " '" + bank.path + "'";
                }
                message += " type " + std::to_string(bank.fileType) + " magic " + hexString(bank.magic) +
                           " sounds " + std::to_string(bank.numSounds) + " block " + std::to_string(bank.blockBytes) +
                           "B vag " + std::to_string(bank.vagDataBytes) + "B";
                logDebug(message);
            }

            void unloadBank(uint32_t handle)
            {
                {
                    const int32_t words[1] = {static_cast<int32_t>(handle)};
                    m_host.audioNotify(kUnloadBank, words, 1u);
                }
                Bank *bank = findBank(handle);
                if (bank == nullptr)
                {
                    logDebug("snd_UnloadBank: unknown bank " + hexString(handle));
                    return;
                }
                for (auto &slot : m_model.sounds)
                {
                    if (slot.active && slot.bank == handle)
                    {
                        slot.active = false;
                    }
                }
                bank->loaded = false;
                if (m_model.lastBank == handle)
                {
                    m_model.lastBank = 0u;
                }
            }

            // ---- VAG streams ---------------------------------------------------------------

            uint32_t initVagStreaming(const CommandArgs &args)
            {
                if (m_model.streamingInitialised)
                {
                    logWarning("snd_InitVAGStreamingEx called twice");
                    return 0u;
                }
                const uint32_t requested = args.u32(0);
                m_model.streamCount = std::clamp<uint32_t>(requested, 1u, kMaxStreamSlots);
                uint32_t bufferBytes = (args.u32(1) >> 12) << 12;
                if (bufferBytes < 0x2000u)
                {
                    bufferBytes = 0x2000u;
                }
                m_model.streamBufferBytes = bufferBytes;
                m_model.streamingInitialised = true;
                for (auto &slot : m_model.streams)
                {
                    slot = {};
                }
                return 1u;
            }

            uint32_t playVagStream(const CommandArgs &args)
            {
                if (!m_model.streamingInitialised)
                {
                    logWarning("snd_PlayVAGStreamByLoc before streaming init");
                    return 0u;
                }
                const uint32_t parent = args.u32(5);
                StreamSlot *target = nullptr;
                if (parent != 0u)
                {
                    // queued after an existing stream: reuse its slot in the model
                    target = findStream(parent);
                }
                if (target == nullptr)
                {
                    for (uint32_t i = 0; i < m_model.streamCount; ++i)
                    {
                        if (!m_model.streams[i].active)
                        {
                            target = &m_model.streams[i];
                            break;
                        }
                    }
                }
                if (target == nullptr)
                {
                    logDebug("no free VAG stream slot");
                    return 0u;
                }
                const uint32_t index = static_cast<uint32_t>(target - m_model.streams.data());
                const bool reused = target->active;
                if (!reused)
                {
                    *target = {};
                    target->handle = makeHandle(kHandleTypeStream, index);
                }
                target->active = true;
                target->paused = false;
                target->sector1 = args.u32(0);
                target->sector2 = args.u32(1);
                target->offset1 = args.u32(2) & 0xFFFFu;
                target->volume = static_cast<int32_t>(args.u32(2) >> 16);
                target->offset2 = args.u32(3) & 0xFFFFu;
                target->pan = static_cast<int32_t>(args.u32(3) >> 16);
                target->group = args.u32(4);
                target->parent = parent;
                target->flags = args.u32(7);
                ++m_metrics.streamsPlayed;
                forwardAudio(kPlayVagStreamByLoc, args);
                const int32_t words[9] = {static_cast<int32_t>(target->handle), static_cast<int32_t>(target->sector1),
                                          static_cast<int32_t>(target->sector2), static_cast<int32_t>(target->offset1), target->volume,
                                          static_cast<int32_t>(target->offset2), target->pan, static_cast<int32_t>(target->group),
                                          static_cast<int32_t>(target->flags)};
                m_host.audioNotify(kPlayVagStreamByLoc, words, 9u);
                return target->handle;
            }

            void stopAllStreams()
            {
                for (auto &slot : m_model.streams)
                {
                    slot.active = false;
                }
            }

            // ---- stream-safe CD access -----------------------------------------------------

            uint64_t cdImage()
            {
                if (m_cdImage == 0u && !m_cdImageFailed)
                {
                    const std::string path = m_host.hostPath(HostPathKind::CdImage);
                    m_cdImage = path.empty() ? 0u : m_host.openHostFile(path);
                    if (m_cdImage == 0u)
                    {
                        m_cdImageFailed = true;
                        logWarning("CD image not available (" + path + ")");
                    }
                }
                return m_cdImage;
            }

            void closeCdImage()
            {
                if (m_cdImage != 0u)
                {
                    m_host.closeHostFile(m_cdImage);
                    m_cdImage = 0u;
                }
                m_cdImageFailed = false;
            }

            void writeStatusBlock(uint32_t busy, uint32_t error)
            {
                if (m_model.statusBlockAddress == 0u)
                {
                    return;
                }
                (void)writeGuestPod(m_host, m_model.statusBlockAddress + 0x10u, error);
                (void)writeGuestPod(m_host, m_model.statusBlockAddress, busy);
            }

            uint32_t streamSafeCdRead(uint32_t sector, uint32_t sectors, uint32_t destination)
            {
                ++m_metrics.cdReads;
                uint32_t error = 0u; // SCECdErNO
                bool ok = sectors != 0u && destination != 0u;
                uint32_t normalized = 0u;
                if (ok && (!m_host.normalizeGuestAddress(destination, normalized) || normalized >= kEeRamSize))
                {
                    ok = false;
                }
                const uint64_t image = ok ? cdImage() : 0u;
                if (image == 0u)
                {
                    ok = false;
                }
                if (ok)
                {
                    uint64_t remaining = std::min<uint64_t>(static_cast<uint64_t>(sectors) * kSectorBytes, kMaxCdReadBytes);
                    remaining = std::min<uint64_t>(remaining, kEeRamSize - normalized);
                    uint64_t fileOffset = static_cast<uint64_t>(sector) * kSectorBytes;
                    uint32_t guestCursor = destination;
                    std::vector<uint8_t> chunk(64u * 1024u);
                    while (remaining != 0u)
                    {
                        const size_t want = static_cast<size_t>(std::min<uint64_t>(remaining, chunk.size()));
                        size_t got = 0u;
                        if (!m_host.readHostFile(image, fileOffset, chunk.data(), want, got) || got == 0u)
                        {
                            ok = false;
                            break;
                        }
                        if (!m_host.writeGuest(guestCursor, chunk.data(), got))
                        {
                            ok = false;
                            break;
                        }
                        fileOffset += got;
                        guestCursor += static_cast<uint32_t>(got);
                        remaining -= got;
                        if (got < want)
                        {
                            break; // end of image: pad silently like a short CD read
                        }
                    }
                }
                if (!ok)
                {
                    ++m_metrics.cdReadFailures;
                    error = 0xFFFFFFFFu; // matches the IRX when sceCdRead fails without an error code
                    logWarning("snd_StreamSafeCdRead failed: sector " + std::to_string(sector) + " x" +
                               std::to_string(sectors) + " -> " + hexString(destination));
                }
                writeStatusBlock(0u, error);
                return 1u;
            }

            // ---- extension modules (989DSTRM) ----------------------------------------------

            uint32_t callExtension(const CommandArgs &args)
            {
                const uint32_t moduleId = args.u32(0);
                const uint32_t function = args.u32(1);
                if (moduleId != kDstrmModuleId)
                {
                    logWarning("extension call to unknown module " + hexString(moduleId));
                    return 0u;
                }
                switch (function)
                {
                case 0u:
                    m_model.dstrmInitialised = true;
                    return 1u;
                case 1u:
                    ++m_metrics.streamsPlayed;
                    m_host.audioCommand(kSndSid, kCallExtension, args.guestBuffer(), GuestBuffer{});
                    return 1u;
                default:
                    return 1u;
                }
            }

            IopHost &m_host;
            mutable std::mutex m_mutex;
            Model m_model;
            Metrics m_metrics;
            uint64_t m_cdImage = 0u;
            bool m_cdImageFailed = false;
        };
    }

    std::unique_ptr<IopService> createSnd989Service(IopHost &host)
    {
        return std::make_unique<Snd989Service>(host);
    }
}
