#pragma once
// Sprint 9 Q0 (2026-09-20): the host playback device the 989snd mix is rendered into, as numbers a test can hold.
//
// raylib opened it with miniaudio's low-latency defaults -- 10 ms periods, three of them, a 30 ms WASAPI buffer --
// and under gameplay load the device thread missed that deadline about forty times a minute: 41 sub-second dropouts
// in one mission minute at the owner's speaker (logs/parity/s9_q0_m51_trace, the JBL endpoint loopback) against
// two in the pre-device dump of the same minute, and none at all from PCSX2 on the same endpoint. PCSX2 runs 20 ms
// with time-stretching. The mix's own latency budget is generous: the game's 989snd model already schedules on a
// 240 Hz tick and nothing in it is a rhythm game.
#include <cstdint>

namespace ps2x
{
    struct MixDeviceSpec
    {
        uint32_t sampleRate = 48000;
        uint32_t channels = 2;
        uint32_t periodMs = 20;   // PCSX2's figure; twice the 10 ms that missed ~40 times a minute
        uint32_t periods = 4;     // 80 ms in flight: the device thread may be late by three whole periods
        uint32_t bufferMs() const { return periodMs * periods; }
    };

    inline MixDeviceSpec mixDeviceSpec() { return MixDeviceSpec{}; }
}
