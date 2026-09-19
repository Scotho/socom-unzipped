// Sprint 8 Goal 3 Task 2: the lgaud service driven the way the game drives it, against the message block
// recovered field by field from the game's own decompiled client library
// (game/analysis/socom2_game.elf.decomp.c:90811-91800, and the capture loop at :211455-211545).
//
// Every case here is device-free: the "microphone" is a scripted vector on the test host, so these run in CI,
// in the Linux VM and on a machine with no capture hardware at all. The harness passes ONE address as BOTH
// send and receive, because that is exactly what the game does (DAT_003dcfb4 twice, :90956 / :91033 / :91102)
// and it is the single structural rule the module has to respect (R112).
#include "MiniTest.h"
#include "module_factories.h"
#include "ps2x/iop/iop_host.h"
#include "runtime/mic_format.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace
{
    // A minimal IopHost: guest memory, a handle allocator, and a scripted capture source. The shape is
    // Snd989TestHost's (socom2_audio_tests.cpp:106-178) with the two Task 1 seams overridden.
    class LgAudTestHost final : public ps2x::iop::IopHost
    {
    public:
        std::vector<uint8_t> memory = std::vector<uint8_t>(0x10000u, 0u);
        std::vector<int16_t> micFrames;      // 16 kHz mono, what the "device" holds
        size_t micCursor = 0u;
        bool micOn = false;
        std::vector<std::string> logs;

        // What the module served to 0x08, at the rate lgAudOpen asked for, and what it was handed for 0x09.
        std::vector<int16_t> gameRead;
        uint32_t gameReadRate = 0u;
        std::vector<uint8_t> playback;
        uint32_t playbackRate = 0u;
        uint8_t playbackChannels = 0u;

        void micGameRead(const int16_t *frames, size_t count, uint32_t rate) override
        {
            gameRead.insert(gameRead.end(), frames, frames + count);
            gameReadRate = rate;
        }
        void micPlaybackWrite(const uint8_t *pcm, size_t bytes, uint32_t rate, uint8_t channels) override
        {
            playback.insert(playback.end(), pcm, pcm + bytes);
            playbackRate = rate;
            playbackChannels = channels;
        }

        [[nodiscard]] bool micAvailable() const override { return micOn; }
        size_t micRead(int16_t *out, size_t frames) override
        {
            const size_t have = micFrames.size() - micCursor;
            const size_t take = frames < have ? frames : have;
            for (size_t i = 0; i < take; ++i)
                out[i] = micFrames[micCursor + i];
            micCursor += take;
            return take;
        }

        bool readGuest(uint32_t address, void *destination, size_t size) const override
        {
            if (!fits(address, size))
                return false;
            if (size != 0u)
                std::memcpy(destination, memory.data() + address, size);
            return true;
        }
        bool writeGuest(uint32_t address, const void *source, size_t size) override
        {
            if (!fits(address, size))
                return false;
            if (size != 0u)
                std::memcpy(memory.data() + address, source, size);
            return true;
        }
        bool zeroGuest(uint32_t address, size_t size) override
        {
            if (!fits(address, size))
                return false;
            std::fill(memory.begin() + address, memory.begin() + address + size, uint8_t{0});
            return true;
        }
        bool normalizeGuestAddress(uint32_t address, uint32_t &normalized) const override
        {
            normalized = address & 0x1FFFFFFFu;
            return normalized < memory.size();
        }
        uint32_t allocateIopHandle(ps2x::iop::IopHandleKind) override { return m_nextHandle += 0x40u; }
        uint32_t allocateGuest(uint32_t size, uint32_t) override
        {
            if (size == 0u || m_nextAlloc + size > memory.size())
                return 0u;
            const uint32_t address = m_nextAlloc;
            m_nextAlloc += size;
            return address;
        }
        void freeGuest(uint32_t) override {}
        void audioCommand(uint32_t, uint32_t, ps2x::iop::GuestBuffer, ps2x::iop::GuestBuffer) override {}
        std::string hostPath(ps2x::iop::HostPathKind) const override { return std::string(); }
        std::string translateGuestPath(std::string_view path) const override { return std::string(path); }
        uint64_t openHostFile(std::string_view) override { return 0u; }
        bool hostFileSize(uint64_t, uint64_t &) const override { return false; }
        bool readHostFile(uint64_t, uint64_t, void *, size_t, size_t &bytesRead) override
        {
            bytesRead = 0u;
            return false;
        }
        void closeHostFile(uint64_t) override {}
        int32_t memoryCard(const ps2x::iop::MemoryCardRequest &) override { return 0; }
        bool hasGuestFunction(uint32_t) const override { return false; }
        bool invokeGuestFunction(uint64_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t *) override
        {
            return false;
        }
        void log(ps2x::iop::LogLevel, std::string_view message) override { logs.emplace_back(message); }

    private:
        bool fits(uint32_t address, size_t size) const
        {
            return static_cast<uint64_t>(address) + size <= memory.size();
        }
        uint32_t m_nextHandle = 0x8000u;
        uint32_t m_nextAlloc = 0x4000u;
    };

    // The EE side of the state word, transcribed from the listing: EVERY lgaud client call merges the
    // reply's +0x04 into DAT_003dcfb8 as `DAT_003dcfb8 = DAT_003dcfb8 & ~2 | reply[+4]`
    // (decomp :90991, :91037, :91067, :91108, ... and :91760 for the async EnumHint), the async end
    // function FUN_00245568 then writes the merged word into the voice object's +0x44 (:91762) and clears
    // the latch only when it is EXACTLY 1 (:91761-91764). lgAudGetState (FUN_00243be8, :90921-90924) reads
    // it with the same rule and no RPC.
    struct EeStateWord
    {
        uint32_t latch = 0u;                       // DAT_003dcfb8, zero before the first call

        uint32_t merge(uint32_t replyState)
        {
            latch = (latch & 0xfffffffdu) | replyState;
            const uint32_t observed = latch;       // what lands in the voice object's +0x44
            if (latch == 1u)
                latch = 0u;
            return observed;
        }
    };

    struct LgAudHarness
    {
        static constexpr uint32_t kSid = 0x50494c42u;      // 'BLIP'
        static constexpr uint32_t kBuf = 0x2000u;          // send AND receive: the game passes DAT_003dcfb4 twice

        LgAudTestHost host;
        std::unique_ptr<ps2x::iop::detail::IopService> service{ps2x::iop::detail::createLgAudService(host)};

        uint32_t call(uint32_t fno, uint32_t sendBytes, uint32_t recvBytes)
        {
            ps2x::iop::RpcRequest request{};
            request.sid = kSid;
            request.function = fno;
            request.send = {kBuf, sendBytes};
            request.receive = {kBuf, recvBytes};
            (void)service->handleRpc(request);
            return word(0x00);
        }
        void put32(uint32_t off, uint32_t v) { (void)host.writeGuest(kBuf + off, &v, sizeof(v)); }
        void put8(uint32_t off, uint8_t v) { (void)host.writeGuest(kBuf + off, &v, sizeof(v)); }
        void put16(uint32_t off, uint16_t v) { (void)host.writeGuest(kBuf + off, &v, sizeof(v)); }
        uint32_t word(uint32_t off) const
        {
            uint32_t v = 0u;
            (void)host.readGuest(kBuf + off, &v, sizeof(v));
            return v;
        }
        // The reply's state word fed through the EE's merge, i.e. what the game would see at voice+0x44.
        uint32_t merged(EeStateWord &ee) const { return ee.merge(word(0x04)); }
        uint8_t byte(uint32_t off) const
        {
            uint8_t v = 0u;
            (void)host.readGuest(kBuf + off, &v, sizeof(v));
            return v;
        }
        uint64_t metric(const char *name) const
        {
            std::vector<ps2x::iop::DebugMetric> metrics;
            service->appendDebugMetrics(metrics);
            for (const ps2x::iop::DebugMetric &m : metrics)
                if (m.name == name)
                    return m.value;
            return ~uint64_t{0};
        }
        // Enumerate(0) + Open(11025 mono 16-bit) + StartRecording, the game's own order (:48334-48347).
        uint32_t openAt(uint32_t rate)
        {
            put32(0x08, 0u);
            (void)call(0x01, 0x20u, 0x170u);
            put32(0x08, 0u);
            put8(0x20, 2u);        // Mode = capture
            put8(0x22, 1u);        // record channels
            put8(0x23, 0x10u);     // record bits
            put16(0x24, static_cast<uint16_t>(rate));
            put16(0x26, 500u);     // record latency
            (void)call(0x02, 0x30u, 0x20u);
            const uint32_t handle = word(0x0c);
            put32(0x0c, handle);
            (void)call(0x04, 0x20u, 0x20u);
            return handle;
        }
    };
}

void register_socom2_lgaud_tests()
{
    MiniTest::Case("SOCOM2LgAud", [](TestCase &tc)
    {
        tc.Run("Enumerate/Open/StartRecording/Read returns the fake microphone's bytes, resampled to 11025", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.resize(16000);                        // one second at the ring's rate
            for (size_t i = 0; i < h.host.micFrames.size(); ++i)
                h.host.micFrames[i] = static_cast<int16_t>(i % 1000 * 30 - 15000);

            h.put32(0x08, 0u);
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0u, "Enumerate(0) answers one device");
            t.Equals(uint32_t(h.byte(0x20u + 0x62u)), 0u, "and no vendor-extension entries (decomp :247063)");
            h.put32(0x08, 1u);
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0x80000001u, "Enumerate(1) answers no device: that is 'one device'");

            h.put32(0x08, 0u);
            h.put8(0x20, 2u);      // Mode = capture
            h.put8(0x22, 1u);      // channels
            h.put8(0x23, 0x10u);   // bits
            h.put16(0x24, 0x2b11u);                                // 11025, decomp :48341
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0u, "Open succeeds");
            const uint32_t handle = h.word(0x0c);
            t.IsTrue(handle != 0u && handle != 0xffffffffu, "and hands back a usable handle at +0x0c");
            t.Equals(h.word(0x04) & 2u, 2u, "the state word says a device is present");

            h.put32(0x0c, handle);
            t.Equals(h.call(0x04, 0x20u, 0x20u), 0u, "StartRecording succeeds");

            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x500u);                                  // what the capture loop asks for (:211485)
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0u, "Read succeeds");
            const uint32_t got = h.word(0x20);
            t.IsTrue(got > 0u && got <= 0x500u, "it returns at most what was asked for");
            t.Equals(got % 2u, 0u, "and a whole number of 16-bit frames");
            int16_t first = 0;
            (void)h.host.readGuest(LgAudHarness::kBuf + 0x30u, &first, sizeof(first));
            t.IsTrue(first != 0, "the payload at +0x30 carries the microphone, not zeros");
            t.IsTrue(h.word(0x00) == 0u, "a short read is a success, not an error");

            // 0x500 bytes is 640 frames at 11025 Hz; at 16 kHz that is ~929 frames out of the ring, so the
            // resample is really happening and the ring is drained faster than the reply fills.
            t.IsTrue(h.host.micCursor > 640u, "more input frames were consumed than output frames served");
            t.Equals(h.metric("mic_bytes_read"), uint64_t(got), "and the module counted what it served");
        });

        tc.Run("R112: the send block is read before a byte of reply is written", [](TestCase &t)
        {
            // Send and receive are ONE buffer. A module that zeroed the receive buffer first would destroy
            // the handle at +0x0c and the count at +0x20 that it is about to use, and this Read would come
            // back "no device" (handle 0 is not open).
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.assign(16000, int16_t{1234});
            const uint32_t handle = h.openAt(11025u);
            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x200u);
            t.Equals(h.call(0x08, 0x30u, 0x230u), 0u, "Read succeeds with send == recv");
            t.Equals(h.word(0x20), 0x200u, "the served count is the count that was asked for, not a zeroed 0");
            int16_t sample = 0;
            (void)h.host.readGuest(LgAudHarness::kBuf + 0x30u, &sample, sizeof(sample));
            t.Equals(static_cast<int>(sample), 1234, "and the payload is the microphone's, not the send block's");
        });

        tc.Run("the merged state word passes through exactly 1 once, which is what makes the game open", [](TestCase &t)
        {
            // The per-frame voice tick FUN_0030ec10 polls 0x0f while voice+0x44 != 1 (:211016) and opens the
            // device -- Enumerate(0) then lgAudOpen, FUN_0030fef0 :211683-211695 -- only when it finds
            // +0x44 == 1 (:211024), after which it writes 2 there itself (:211025-211028). So the module's
            // job is to make the MERGED word read exactly 1 once after a device appears, and never again:
            // 1 twice is an open every frame, 1 never is the 30x-0x0f / 0x-0x02 signature of s8_voice_read.
            LgAudHarness h;
            EeStateWord ee;
            h.host.micOn = true;

            (void)h.call(0x10, 0x20u, 0x30u);
            t.Equals(h.merged(ee), 0u, "lgAudInit leaves the latch alone");
            h.put32(0x08, 0u);
            (void)h.call(0x01, 0x20u, 0x170u);
            const uint32_t afterEnumerate = h.merged(ee);
            t.IsTrue(afterEnumerate != 1u, "Enumerate alone must not trigger the rescan");

            (void)h.call(0x0f, 0x20u, 0x20u);
            t.Equals(h.merged(ee), 1u, "the first hint after a device appears merges to exactly 1");

            // Everything after it -- more hints, and the Open/gain calls the tick makes on the way through,
            // each of which merges its own reply state (:91037, :91498, :91527) -- must never read 1 again.
            const uint32_t handle = h.openAt(8000u);
            t.IsTrue(handle != 0u, "the device opens at the voice path's own 8000 Hz");
            for (int i = 0; i < 64; ++i)
            {
                (void)h.call(0x0f, 0x20u, 0x20u);
                const uint32_t m = h.merged(ee);
                t.IsTrue(m != 1u, "a steady hint never re-triggers the open");
                t.Equals(m, 2u, "and settles on 2, the value the tick writes to +0x44 itself (:211025)");
            }
        });

        tc.Run("the voice path's own openparam: mode 3, 8000 Hz record and playback (decomp :211843-211852)", [](TestCase &t)
        {
            // FUN_00310080's defaults, never overwritten on the voice path: record 1ch/16bit/8000/2000 and
            // playback 2ch/16bit/8000/2000, Mode 3 (FUN_0030fef0 :211683). 11025 is the TUNER path's
            // openparam (FUN_001e7f98 :48336-48342), not this one -- the module must honour whatever it is
            // sent rather than assume either.
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.resize(16000);
            for (size_t i = 0; i < h.host.micFrames.size(); ++i)
                h.host.micFrames[i] = static_cast<int16_t>((i % 211) * 140 - 14000);

            h.put32(0x08, 0u);
            (void)h.call(0x01, 0x20u, 0x170u);
            h.put32(0x08, 0u);
            h.put8(0x20, 3u);          // Mode 3: capture AND playback
            h.put8(0x22, 1u);          // record channels
            h.put8(0x23, 0x10u);       // record bits
            h.put16(0x24, 8000u);      // record rate
            h.put16(0x26, 2000u);      // record latency
            h.put8(0x28, 2u);          // playback channels
            h.put8(0x29, 0x10u);       // playback bits
            h.put16(0x2a, 8000u);      // playback rate
            h.put16(0x2c, 2000u);      // playback latency
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0u, "Open succeeds at the voice path's own format");
            const uint32_t handle = h.word(0x0c);
            h.put32(0x0c, handle);
            t.Equals(h.call(0x04, 0x20u, 0x20u), 0u, "StartRecording succeeds");

            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x500u);
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0u, "Read succeeds");
            const uint32_t served = h.word(0x20);
            t.IsTrue(served > 0u, "and serves bytes");
            t.Equals(h.host.gameRead.size(), size_t(served / 2u), "the host was handed exactly what was served");
            t.Equals(h.host.gameReadRate, 8000u, "at the rate lgAudOpen asked for, not the ring's 16000");
            // 640 output frames at 8000 Hz cost exactly 2x that many at the ring's 16 kHz: the resample
            // really happened, and micFramesNeeded asked for neither more nor less than it could use.
            t.Equals(h.host.micCursor, size_t(served / 2u) * 2u, "two input frames per output frame, 16k -> 8k");

            // 0x09 Write: the playback half, decoded PCM on its way to the headset (:211380).
            std::vector<uint8_t> pcm(0x200);
            for (size_t i = 0; i < pcm.size(); ++i)
                pcm[i] = static_cast<uint8_t>(i & 0xFFu);
            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, static_cast<uint32_t>(pcm.size()));
            for (size_t i = 0; i < pcm.size(); ++i)
                h.put8(static_cast<uint32_t>(0x30u + i), pcm[i]);
            t.Equals(h.call(0x09, 0x230u, 0x30u), 0u, "Write is accepted");
            t.Equals(h.host.playback.size(), pcm.size(), "and the payload reaches the host");
            t.Equals(uint32_t(h.host.playback[7]), 7u, "byte for byte");
            t.Equals(h.host.playbackRate, 8000u, "at the playback rate from openparam +0x0a");
            t.Equals(uint32_t(h.host.playbackChannels), 2u, "and its channel count from openparam +0x08");
        });

        tc.Run("with no device the merged state word never reaches 1, so the tick never opens", [](TestCase &t)
        {
            LgAudHarness h;
            EeStateWord ee;
            h.host.micOn = false;
            for (int i = 0; i < 16; ++i)
            {
                (void)h.call(0x0f, 0x20u, 0x20u);
                t.Equals(h.merged(ee), 0u, "no device: no change event, no rescan, no open");
            }
        });

        tc.Run("Open refuses a format we cannot serve, and never with a half-open handle", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            h.put32(0x08, 0u);
            h.put8(0x20, 2u);
            h.put8(0x22, 2u);      // stereo capture
            h.put8(0x23, 0x10u);
            h.put16(0x24, 0x2b11u);
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0x80000004u, "stereo is a bad parameter, not a missing device");
            t.Equals(h.metric("mic_open"), uint64_t{0}, "and nothing was opened");

            h.put32(0x0c, 0u);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x100u);
            t.Equals(h.call(0x08, 0x30u, 0x130u), 0x80000001u, "a Read against no open handle is refused");
        });

        tc.Run("a Read with an empty ring is a success that serves nothing", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            const uint32_t handle = h.openAt(11025u);    // micFrames is empty: the ring has nothing in it
            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x500u);
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0u, "the capture loop simply does not advance (:211489)");
            t.Equals(h.word(0x20), 0u, "zero bytes served");
        });

        tc.Run("GetAvailableRecordingBytes reports inside the payload cap and consumes nothing", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.resize(16000);
            const uint32_t handle = h.openAt(11025u);
            const size_t before = h.host.micCursor;
            h.put32(0x0c, handle);
            t.Equals(h.call(0x12, 0x20u, 0x30u), 0u, "0x12 succeeds");
            t.Equals(h.host.micCursor, before, "and reads nothing out of the ring");
            const uint32_t avail = h.word(0x20);
            t.IsTrue(avail <= 0x7d0u, "clamped to the 0x7d0 payload cap (decomp :90880)");
            t.IsTrue(avail > 0u, "with a full second in the ring there is something to report");
        });

        tc.Run("the mixer family stores what the capture loop's AGC sets", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            const uint32_t handle = h.openAt(11025u);

            // 0x0e SetRecordGain(handle, 0, 0x32): what the game sets right after Open (:48346).
            h.put32(0x0c, handle);
            h.put8(0x10, 0u);
            h.put8(0x11, 0x32u);
            t.Equals(h.call(0x0e, 0x20u, 0x20u), 0u, "SetRecordGain is accepted, so the game stops fighting itself");
            t.Equals(h.metric("record_gain"), uint64_t{0x32}, "and the level survives the call");

            // 0x0e again, the AGC's next nudge (steps of 5, clamped 0x14..100, :211504-211527).
            h.put32(0x0c, handle);
            h.put8(0x10, 0u);
            h.put8(0x11, 0x37u);
            t.Equals(h.call(0x0e, 0x20u, 0x20u), 0u, "and again every fifth pass");
            t.Equals(h.metric("record_gain"), uint64_t{0x37}, "the newest level wins");

            // 0x0c SetMixer / 0x0b GetMixer: the 16-byte struct at +0x20 round-trips, including the u16 the
            // EE reads back out of reply +0x2c (:91240).
            h.put32(0x0c, handle);
            for (uint32_t i = 0; i < 16u; ++i)
                h.put8(0x20u + i, static_cast<uint8_t>(0xA0u + i));
            t.Equals(h.call(0x0c, 0x30u, 0x30u), 0u, "SetMixer is accepted");
            h.put32(0x0c, handle);
            for (uint32_t i = 0; i < 16u; ++i)
                h.put8(0x20u + i, 0u);
            t.Equals(h.call(0x0b, 0x30u, 0x30u), 0u, "GetMixer is accepted");
            t.Equals(uint32_t(h.byte(0x20u)), 0xA0u, "the struct comes back at +0x20");
            t.Equals(h.word(0x2cu) & 0xFFFFu, 0xADACu, "including the u16 the EE reads at reply +0x2c");
        });

        tc.Run("Close and PrepareForReboot leave the device alone and refuse the next Read", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = true;
            h.host.micFrames.assign(16000, int16_t{500});
            const uint32_t handle = h.openAt(11025u);
            h.put32(0x0c, handle);
            t.Equals(h.call(0x03, 0x20u, 0x20u), 0u, "Close succeeds");
            t.Equals(h.metric("mic_open"), uint64_t{0}, "the handle is gone");
            t.IsTrue(h.host.micAvailable(), "but the runtime still owns the capture source");
            h.put32(0x0c, handle);
            h.put8(0x12, 1u);
            h.put32(0x20, 0x100u);
            t.Equals(h.call(0x08, 0x30u, 0x130u), 0x80000001u, "a Read on the closed handle is refused");

            const uint32_t reopened = h.openAt(11025u);
            t.IsTrue(reopened != 0u && reopened != 0xffffffffu, "and the device opens again");
            h.put32(0x0c, 0xffffffffu);
            t.Equals(h.call(0x14, 0x20u, 0x20u), 0u, "PrepareForReboot (handle -1) succeeds");
            t.Equals(h.metric("mic_open"), uint64_t{0}, "and closes whatever was open");
        });

        tc.Run("with no microphone the module answers exactly what it answered before this goal", [](TestCase &t)
        {
            LgAudHarness h;
            h.host.micOn = false;                               // PS2X_MIC_DEVICE and PS2X_MIC_FAKE both unset
            t.Equals(h.call(0x10, 0x20u, 0x30u), 0u, "lgAudInit still succeeds");
            t.Equals(h.word(0x08), 0x108u, "version 1.08 at reply word 2, which the EE halts without");
            t.Equals(h.word(0x20), 0x800u, "0x800 at reply word 8, which is where the EE's 0x840 comes from");
            t.Equals(h.call(0x01, 0x20u, 0x170u), 0x80000001u, "Enumerate: no device");
            t.Equals(h.call(0x02, 0x30u, 0x20u), 0x80000001u, "Open: no device");
            t.Equals(h.call(0x0f, 0x20u, 0x20u), 0x80000001u, "EnumHint: no device");
            t.Equals(h.call(0x08, 0x30u, 0x530u), 0x80000001u, "Read: no device");
            t.Equals(h.word(0x04), 0u, "and the state word never claims a device is present");

            // The same [lgaud:stub] line as before, for the first 32 unknown calls and no more.
            size_t stubs = 0u;
            for (const std::string &line : h.host.logs)
                if (line.rfind("[lgaud:stub]", 0) == 0)
                    ++stubs;
            t.Equals(stubs, size_t{4}, "one stub line per non-init call, exactly as before this goal");
            for (int i = 0; i < 40; ++i)
                (void)h.call(0x01, 0x20u, 0x170u);
            stubs = 0u;
            for (const std::string &line : h.host.logs)
                if (line.rfind("[lgaud:stub]", 0) == 0)
                    ++stubs;
            t.Equals(stubs, size_t{32}, "and it still stops at 32");
        });
    });
}
