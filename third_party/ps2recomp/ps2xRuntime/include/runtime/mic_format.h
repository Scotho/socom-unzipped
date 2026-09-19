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
// Returns frames written. `phase` is the position, in input frames, of the next output sample.
inline size_t micResampleLinear(const int16_t *in, size_t inFrames, uint32_t inRate,
                                int16_t *out, size_t outFrames, uint32_t outRate, double &phase)
{
    if (in == nullptr || out == nullptr || inFrames == 0u || outFrames == 0u || inRate == 0u || outRate == 0u)
        return 0u;
    if (inRate == outRate)
    {
        const size_t n = inFrames < outFrames ? inFrames : outFrames;
        for (size_t i = 0; i < n; ++i)
            out[i] = in[i];
        return n;
    }
    const double step = static_cast<double>(inRate) / static_cast<double>(outRate);
    size_t written = 0u;
    while (written < outFrames)
    {
        const double pos = phase;
        if (pos < 0.0)
            break;
        const size_t i0 = static_cast<size_t>(pos);
        if (i0 + 1u >= inFrames)
            break;
        const double frac = pos - static_cast<double>(i0);
        const double v = static_cast<double>(in[i0]) * (1.0 - frac) + static_cast<double>(in[i0 + 1u]) * frac;
        out[written++] = static_cast<int16_t>(v < -32768.0 ? -32768.0 : (v > 32767.0 ? 32767.0 : v));
        phase += step;
    }
    phase -= static_cast<double>(static_cast<size_t>(phase));   // keep only the fraction; the caller drops the frames
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

// The 44-byte PCM WAV hostMicWavHeader writes, read back. dataSize == 0xFFFFFFFF means "read to the end of the
// file" (host_mic.h:94-98: a killed run leaves the two size fields unpatched). 16-bit PCM only.
bool micWavRead(const std::string &path, std::vector<int16_t> &samples, MicFormat &format, std::string &error);
