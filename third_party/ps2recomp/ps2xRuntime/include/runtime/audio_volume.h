#pragma once
// Sprint 7 Task 11 (owner request 2026-09-18): PS2X_AUDIO_VOLUME=<0..100>, the launcher's master volume, as a
// linear gain on the 989snd mix. Linear rather than dB because the slider is a percentage and a player who drags
// it to 50 expects half; the range is capped at 100 so the knob can never add gain to a mix that is already at
// full scale.
inline float volumeGain(int percent)
{
    if (percent <= 0)
        return 0.0f;
    if (percent >= 100)
        return 1.0f;
    return static_cast<float>(percent) / 100.0f;
}
