#pragma once

// Sprint 7 Task 1a (audit 2026-09-17 §2.2 F2, gap G6): what the GL backend needs from a stranger's
// machine, decided once.
//
// ensureGl() used to retry the whole shader compile every host frame on a machine that cannot run
// it: m_glReady was never set, the EE kept recording into m_pending, and the window stayed black
// while memory climbed. The probe below answers "can this machine run the GL backend" from three
// values the caller reads out of the context (GL_VERSION, dual-source draw buffers, clip control),
// and the Latch makes the answer final: one attempt, ever.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the wording and the latch
// without a context.

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include "ps2x/exit_codes.h"
#include "ps2x/knobs.h"

namespace GsGlCaps
{
    // The process exit code that says "the game ran, but on the CPU rasterizer". The number and its
    // sentence live in ps2x/exit_codes.h; this name stays because ps2_runtime.cpp:2628 sets it.
    constexpr int kExitCode = ExitCodes::kNoUsableGl;
    static_assert(kExitCode == 65, "Sprint 7 Task 1a's code does not move");

    struct Report
    {
        bool ok = true;
        std::string missing;   // ", "-joined, empty when ok
        std::string note;      // supported, but worth one line (clip control absent: fragment-depth mapping)
    };

    // PS2X_GS_GL_FORCE_FAIL: set and not "0" forces the unsupported path. On a machine that does
    // support GL this is the only way to reach the CPU fallback (the gate's second launch).
    inline bool forceFailRequested(const char *env)
    {
        return env != nullptr && *env != 0 && std::strcmp(env, "0") != 0;
    }

    // The leading "<major>.<minor>" of a GL_VERSION string ("3.3.0 NVIDIA 555.85", "4.6.0 Core
    // Profile"). Returns major * 10 + minor, or -1 when there is no such prefix.
    inline int parseVersion(const char *glVersion)
    {
        if (glVersion == nullptr)
            return -1;
        const char *p = glVersion;
        while (*p == ' ')
            ++p;
        if (*p < '0' || *p > '9')
            return -1;
        int major = 0;
        while (*p >= '0' && *p <= '9')
            major = major * 10 + (*p++ - '0');
        if (*p != '.')
            return -1;
        ++p;
        if (*p < '0' || *p > '9')
            return -1;
        int minor = 0;
        while (*p >= '0' && *p <= '9')
            minor = minor * 10 + (*p++ - '0');
        return major * 10 + minor;
    }

    // The testable form: the environment is a parameter, so the same call is reproducible.
    inline Report evaluate(const char *glVersion, bool dualSourceBlend, bool clipControl, const char *forceFailEnv)
    {
        Report report;
        if (forceFailRequested(forceFailEnv))
        {
            report.ok = false;
            report.missing = "forced (PS2X_GS_GL_FORCE_FAIL)";
            return report;
        }
        auto add = [&report](const std::string &what)
        {
            if (!report.missing.empty())
                report.missing += ", ";
            report.missing += what;
        };
        const int version = parseVersion(glVersion);
        if (version < 0)
            add("OpenGL 3.3 (no version string)");
        else if (version < 33)
            add("OpenGL 3.3");
        if (!dualSourceBlend)
            add("dual-source blending");
        // GL_ARB_clip_control gives exact-integer depth (research/26); without it GsGlDepth falls back to the
        // fragment-depth mapping, which runs the game. A note, not a reason for the CPU rasterizer.
        if (!clipControl)
            report.note = "GL_ARB_clip_control absent: depth uses the fragment-depth mapping (not exact-integer)";
        report.ok = report.missing.empty();
        return report;
    }

    inline Report evaluate(const char *glVersion, bool dualSourceBlend, bool clipControl)
    {
        return evaluate(glVersion, dualSourceBlend, clipControl, ps2x::knob("PS2X_GS_GL_FORCE_FAIL"));
    }

    // One attempt, ever. shouldAttempt() is false from the first fail() onwards, so ensureGl()
    // returns early instead of recompiling the shaders on every host frame.
    class Latch
    {
    public:
        bool shouldAttempt() const { return !m_failed; }
        void attempted() { ++m_attempts; }
        void fail(const Report &report)
        {
            m_failed = true;
            m_report = report;
            if (m_report.missing.empty())
                m_report.missing = "the GL shaders would not compile or link";
            m_report.ok = false;
        }
        bool failed() const { return m_failed; }
        const Report &report() const { return m_report; }
        uint32_t attempts() const { return m_attempts; }

    private:
        bool m_failed = false;
        uint32_t m_attempts = 0u;
        Report m_report;
    };
}
