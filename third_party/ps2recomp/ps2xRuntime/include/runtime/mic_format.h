#pragma once
// Sprint 8 Goal 3 Task 1: the microphone arithmetic, kept free of any device so ps2x_tests can check it in
// CI, in the VM and on a machine with no microphone -- the same rule runtime/gs/gs_gl_target_extent.h follows
// for GL. RETRACTS host_mic.h's "16 kHz" FORMAT ASSUMPTION: the game asks lgAudOpen for 11025 Hz mono 16-bit
// (game/analysis/socom2_game.elf.decomp.c:48341, openparam+0x04 = 0x2b11), so a resample is always needed.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

struct MicFormat
{
    uint32_t rate = 11025u;
    uint8_t channels = 1u;
    uint8_t bits = 16u;

    [[nodiscard]] size_t bytesPerFrame() const { return static_cast<size_t>(channels) * bits / 8u; }
    [[nodiscard]] bool supported() const
    {
        return channels == 1u && bits == 16u && rate >= 4000u && rate <= 48000u;
    }
};

// Mono linear interpolation with a carried fractional phase, so back-to-back calls join without a step.
// Returns frames written. `phase` is the position, in input frames, of the next output sample. `consumed`,
// when given, receives the input frames the stream has advanced past -- floor(phase + step * written) -- which
// the caller must drop from the front of its buffer before the next call; the one or two frames after them are
// the lookahead the next call's first sample interpolates from, and they must be kept (Sprint 10 Q7, KNOWN 110 b).
inline size_t micResampleLinear(const int16_t *in, size_t inFrames, uint32_t inRate,
                                int16_t *out, size_t outFrames, uint32_t outRate, double &phase,
                                size_t *consumed = nullptr)
{
    if (consumed != nullptr)
        *consumed = 0u;
    if (in == nullptr || out == nullptr || inFrames == 0u || outFrames == 0u || inRate == 0u || outRate == 0u)
        return 0u;
    if (inRate == outRate)
    {
        const size_t n = inFrames < outFrames ? inFrames : outFrames;
        for (size_t i = 0; i < n; ++i)
            out[i] = in[i];
        if (consumed != nullptr)
            *consumed = n;
        return n;
    }
    const double step = static_cast<double>(inRate) / static_cast<double>(outRate);
    if (phase < 0.0)
        phase = 0.0;
    size_t written = 0u;
    while (written < outFrames)
    {
        // The position is the same product micFramesNeeded floors (phase + step * k), not a running sum: a
        // sum that drifts across an integer boundary the product does not cross reads one frame past the
        // buffer micFramesNeeded sized, and the read comes up one sample short.
        const double pos = phase + step * static_cast<double>(written);
        const size_t i0 = static_cast<size_t>(pos);
        if (i0 + 1u >= inFrames)
            break;
        const double frac = pos - static_cast<double>(i0);
        const double v = static_cast<double>(in[i0]) * (1.0 - frac) + static_cast<double>(in[i0 + 1u]) * frac;
        out[written++] = static_cast<int16_t>(v < -32768.0 ? -32768.0 : (v > 32767.0 ? 32767.0 : v));
    }
    const double end = phase + step * static_cast<double>(written);
    const size_t whole = static_cast<size_t>(end);
    if (consumed != nullptr)
        *consumed = whole;
    phase = end - static_cast<double>(whole);   // keep only the fraction; the caller drops `consumed` frames
    return written;
}

// How many input frames micResampleLinear needs in its buffer to produce `outFrames`, starting at `phase`.
// The last output sits at phase + step * (outFrames - 1) and the interpolation reads in[i0 + 1], so the
// buffer must reach floor(that) + 2. Using outFrames rather than outFrames - 1 here asks for one frame more
// than the resampler can ever read, which is what makes the "never asks for more input than it was given"
// case in socom2_audio_tests.cpp fail at 11025 Hz (801 frames wanted out of 800 given).
inline size_t micFramesNeeded(size_t outFrames, uint32_t inRate, uint32_t outRate, double phase)
{
    if (outFrames == 0u || inRate == 0u || outRate == 0u)
        return 0u;
    if (phase < 0.0)
        phase = 0.0;
    if (inRate == outRate)
        return outFrames;
    const double step = static_cast<double>(inRate) / static_cast<double>(outRate);
    const double last = phase + step * static_cast<double>(outFrames - 1u);
    return static_cast<size_t>(last) + 2u;
}

// A consuming source (the host's 16 kHz ring: what micRead hands over is gone) pulled through the resampler
// one game read at a time. Sprint 10 Q7 (KNOWN 110 b): lgaud used to read micFramesNeeded() frames and let the
// resampler's phase account for floor(phase + step * out) of them; the difference -- the lookahead frame -- was
// dropped from the stream on about half the reads at every non-integer step. The feed keeps what the
// resampler has not finished with as the head of the next buffer, and owes the source frames it could not
// drop after a short read.
struct MicResampleFeed
{
    std::vector<int16_t> buffer;   // carried lookahead, then what the source handed over this read
    double phase = 0.0;
    size_t debt = 0u;              // frames the stream advanced past that the buffer never held (a short read)

    void reset()
    {
        buffer.clear();
        phase = 0.0;
        debt = 0u;
    }

    // Fills `out` with up to outFrames at outRate, drawing on `read(int16_t *dst, size_t frames) -> size_t got`
    // for what the buffer lacks. Returns frames written.
    template <class Read>
    size_t pull(int16_t *out, size_t outFrames, uint32_t inRate, uint32_t outRate, Read &&read)
    {
        if (out == nullptr || outFrames == 0u || inRate == 0u || outRate == 0u)
            return 0u;
        while (debt != 0u)
        {
            int16_t sink[64];
            const size_t ask = debt < sizeof(sink) / sizeof(sink[0]) ? debt : sizeof(sink) / sizeof(sink[0]);
            const size_t got = read(sink, ask);
            if (got == 0u)
                return 0u;
            debt -= got;
        }
        const size_t need = micFramesNeeded(outFrames, inRate, outRate, phase);
        if (buffer.size() < need)
        {
            const size_t had = buffer.size();
            buffer.resize(need);
            const size_t got = read(buffer.data() + had, need - had);
            buffer.resize(had + got);
        }
        size_t consumed = 0u;
        const size_t written = micResampleLinear(buffer.data(), buffer.size(), inRate, out, outFrames, outRate, phase, &consumed);
        if (consumed >= buffer.size())
        {
            debt = consumed - buffer.size();
            buffer.clear();
        }
        else
            buffer.erase(buffer.begin(), buffer.begin() + static_cast<std::ptrdiff_t>(consumed));
        return written;
    }
};

// The 44-byte PCM WAV hostMicWavHeader writes, read back. dataSize == 0xFFFFFFFF means "read to the end of the
// file" (host_mic.h:94-98: a killed run leaves the two size fields unpatched). 16-bit PCM only.
bool micWavRead(const std::string &path, std::vector<int16_t> &samples, MicFormat &format, std::string &error);
