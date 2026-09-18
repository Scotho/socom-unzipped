#pragma once
// Sprint 7 Task 9 (owner request 2026-09-18): the capture devices the launcher offers, behind an interface, so
// the list logic is testable without a sound card. The miniaudio implementation is mic_devices.cpp, which is
// compiled into the launcher executable only.
#include <cmath>
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace launcher
{
    // RMS of the frames, in dB full scale. -inf for digital silence: a meter that read 0 dB for silence would
    // sit at the top of its bar with nothing plugged in.
    inline float micLevelDb(const float *frames, size_t n)
    {
        if (frames == nullptr || n == 0)
            return -INFINITY;
        double sum = 0.0;
        for (size_t i = 0; i < n; ++i)
            sum += static_cast<double>(frames[i]) * static_cast<double>(frames[i]);
        const double rms = std::sqrt(sum / static_cast<double>(n));
        if (rms <= 0.0)
            return -INFINITY;
        return static_cast<float>(20.0 * std::log10(rms));
    }

    class MicDevices
    {
    public:
        virtual ~MicDevices() = default;
        // The capture devices the host reports, in the host's order. Empty when there are none or the audio
        // backend would not start -- the panel then shows "None" alone.
        virtual std::vector<std::string> list() = 0;
        // Open `name` for capture and start filling the meter. False when it will not open.
        //
        // Sprint 7 review finding F8, the meter's ownership of the device. The launcher holds the capture
        // device open for its level meter, and on Windows a shared-mode device opened twice is not guaranteed
        // to the second opener -- so while the game runs, the launcher must not be holding it. The contract
        // both halves of the pair keep:
        //   * startMeter(name) stops whatever was open first, then opens `name`. Calling it with a name that
        //     is already open re-opens it; calling it with "" or an unknown name leaves nothing open and
        //     returns false. It is the only call that touches the host audio backend at any cost.
        //   * stopMeter() closes the device and the context if either is open and does nothing at all if
        //     neither is: idempotent, safe before any start, safe twice in a row, and cheap enough to call on
        //     every Launch. After it, levelDb() is -inf again.
        // So the launcher can hand the device to the game for the length of a run and take it back after,
        // with no state of its own to keep beyond the device name the player picked.
        virtual bool startMeter(const std::string &name) = 0;
        // The last callback's RMS in dB (-inf until one arrives, and again after stopMeter()).
        virtual float levelDb() const = 0;
        // Idempotent and cheap; see startMeter above.
        virtual void stopMeter() = 0;
    };

    // "None", then the devices.
    inline std::vector<std::string> micLabels(MicDevices &devices)
    {
        std::vector<std::string> labels = {"None"};
        for (const std::string &name : devices.list())
            labels.push_back(name);
        return labels;
    }

    std::unique_ptr<MicDevices> makeMicDevices();
}
