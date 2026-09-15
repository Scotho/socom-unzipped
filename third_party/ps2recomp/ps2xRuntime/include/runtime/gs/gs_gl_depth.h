#pragma once

// How the GL backend carries an integer GS z into the GL depth test (research/26).
//
// The GS compares integer z (`z >= stored` for GEQUAL, gs_cpu_backend.cpp). The GL backend stores
// depth in a GL_DEPTH_COMPONENT32F attachment, so the comparison is exact only if the value that
// reaches the depth buffer is still z / 2^32 with no rounding on the way. These functions are the
// CPU replica of that path, in the same float32 operations the GPU performs, so ps2xTest can check
// the mapping without a GL context.
//
//   attribute  appendVertex: aPos.z = min(z, 2^32 - 1) / 2^32, computed in double, stored float32
//   ndc        vertex shader: gl_Position.z (w = 1)
//   window     viewport transform with glDepthRange(0, 1), written to the float depth buffer

#include <algorithm>
#include <cstring>

namespace GsGlDepth
{
    enum class Mode : int
    {
        // PS2X_GS_DEPTH_LEGACY=1: gl_Position.z = aPos.z * 2 - 1 under the default
        // GL_NEGATIVE_ONE_TO_ONE clip range. Rounds window depth to multiples of 128 GS z units
        // below ~2^30 (float32 ulp near ndc -1 is 2^-24).
        Legacy = 0,
        // Default when available: glClipControl(GL_LOWER_LEFT, GL_ZERO_TO_ONE) and gl_Position.z =
        // aPos.z. Window depth = ndc, bit-exact for integer z < 2^24.
        ClipZeroToOne = 1,
        // Fallback without ARB_clip_control: clip as Legacy, but the fragment shader writes
        // gl_FragDepth from the interpolated aPos.z. Exact, but disables early-z.
        FragDepth = 2,
    };

    inline float attribute(double z)
    {
        return static_cast<float>(std::min<double>(z, 4294967295.0) / 4294967296.0);
    }

    // Each operation is its own statement so the host compiler cannot contract it into an FMA
    // that the GPU would not perform.
    // gl_Position.z as the vertex shader computes it.
    inline float ndc(Mode mode, float attr)
    {
        if (mode == Mode::ClipZeroToOne)
            return attr;
        const float twice = attr * 2.0f;
        const float n = twice - 1.0f;
        return n;
    }

    // The depth value written to the float depth buffer (glDepthRange(0, 1)).
    inline float windowFromZ(Mode mode, double z)
    {
        const float attr = attribute(z);
        const float n = ndc(mode, attr);
        switch (mode)
        {
        case Mode::ClipZeroToOne:
        {
            // GL_ZERO_TO_ONE: z_w = (f - n) * z_ndc + n = z_ndc.
            const float scaled = n * 1.0f;
            const float w = scaled + 0.0f;
            return w;
        }
        case Mode::FragDepth:
            // gl_FragDepth = the interpolated aPos.z, clamped to [0, 1]; clip-space z is ignored.
            return std::clamp(attr, 0.0f, 1.0f);
        case Mode::Legacy:
        default:
        {
            // GL_NEGATIVE_ONE_TO_ONE: z_w = (f - n) / 2 * z_ndc + (n + f) / 2.
            const float half = n * 0.5f;
            const float w = half + 0.5f;
            return w;
        }
        }
    }

    // PS2X_GS_DEPTH_LEGACY: set and not "0" requests the old mapping.
    inline bool legacyRequested(const char *env)
    {
        return env != nullptr && *env != 0 && std::strcmp(env, "0") != 0;
    }

    inline Mode choose(bool legacyRequestedByEnv, bool clipControlAvailable)
    {
        if (legacyRequestedByEnv)
            return Mode::Legacy;
        return clipControlAvailable ? Mode::ClipZeroToOne : Mode::FragDepth;
    }

    inline const char *name(Mode mode)
    {
        switch (mode)
        {
        case Mode::Legacy: return "legacy (z*2-1, NEGATIVE_ONE_TO_ONE)";
        case Mode::ClipZeroToOne: return "clip-control (GL_ZERO_TO_ONE, z exact)";
        case Mode::FragDepth: return "gl_FragDepth (z exact, no early-z)";
        }
        return "?";
    }
}
