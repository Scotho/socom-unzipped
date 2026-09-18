#pragma once
// Sprint 7 Task 10 (owner request 2026-09-18): the one line PS2X_FPS_OVERLAY draws, formatted where it can be
// tested. Three numbers, because two of them answer different questions: the HOST's frame rate says whether the
// window is keeping up, and the GUEST's vsync rate says whether the game is -- research/29's render-stall shape
// is exactly the case where the first is fine and the second is not.
#include <cmath>
#include <cstdio>
#include <string>

inline std::string fpsOverlayLine(int hostFps, double guestVsyncHz, double frameMs)
{
    char host[16];
    if (hostFps < 0)
        std::snprintf(host, sizeof(host), "--");
    else
        std::snprintf(host, sizeof(host), "%d", hostFps);
    char guest[16];
    if (!std::isfinite(guestVsyncHz) || guestVsyncHz < 0.0)
        std::snprintf(guest, sizeof(guest), "--");
    else
        std::snprintf(guest, sizeof(guest), "%.1f", guestVsyncHz);
    char frame[16];
    if (!std::isfinite(frameMs) || frameMs < 0.0)
        std::snprintf(frame, sizeof(frame), "--");
    else
        std::snprintf(frame, sizeof(frame), "%.1f", frameMs);
    return std::string(host) + " fps  guest " + guest + " Hz  " + frame + " ms";
}
