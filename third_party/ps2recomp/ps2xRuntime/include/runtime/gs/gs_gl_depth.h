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
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

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

    // ---- #104: the ZBUF format clamp and the fragment z floor, ported from PCSX2 (GPL-3.0+, commit 81526d4dc7) ----
    //
    // PCSX2 GSRendererHW::EmulateZbuffer: "On the real GS we appear to do clamping on the max z value the format
    // allows. Clamping is done after rasterization." -- saturation to the format maximum, never bit truncation:
    // max_z = 0xFFFFFFFF >> (fmt * 8). zpsm is GSZbufReg::psm (0x30 | ZBUF bits 24-27); PCSX2's fmt is 0 for Z32,
    // 1 for Z24, 2 for Z16 and Z16S, and 3 for any other value (GSLocalMemory's default).
    inline uint32_t formatMaxZ(uint8_t zpsm)
    {
        unsigned fmt = 3u;
        switch (zpsm & 0x0Fu)
        {
        case 0x0: fmt = 0u; break;
        case 0x1: fmt = 1u; break;
        case 0x2:
        case 0xA: fmt = 2u; break;
        default: break;
        }
        return 0xFFFFFFFFu >> (fmt * 8u);
    }

    inline uint32_t saturateToFormat(uint32_t z, uint8_t zpsm)
    {
        return std::min(z, formatMaxZ(zpsm));
    }

    // z * 2^-32 without rounding (double); the float32 attribute() of it is what the GPU sees.
    inline double exactScale(uint32_t z)
    {
        return static_cast<double>(z) * (1.0 / 4294967296.0);
    }

    // The format maximum as a float32 attribute: exact for Z24 and Z16; Z32's rounds to 1.0 like every z near it.
    inline float formatMaxAttribute(uint8_t zpsm)
    {
        return attribute(static_cast<double>(formatMaxZ(zpsm)));
    }

    // PCSX2 PR #13795 (bin/resources/shaders/opengl/tfx_fs.glsl): "On the PS2 you only have integer depth
    // available", so the interpolated z is floored to the 2^-32 grid before the depth test and write. The GLSL the
    // floor program carries, byte for byte; floorToGrid is its CPU replica in the same float32 steps.
    inline constexpr const char *kFloorGlsl = "floor(z * exp2(32.0)) * exp2(-32.0)";

    inline float floorToGrid(float z)
    {
        const float scaled = z * 4294967296.0f;
        const float whole = std::floor(scaled);
        const float back = whole * (1.0f / 4294967296.0f);
        return back;
    }

    // PCSX2 GSRendererHW.h DepthRead / DepthWrite on the TEST register (ATE bit 0, ATST 1-3, AFAIL 12-13, ZTE 16,
    // ZTST 17-18) and ZBUF.ZMSK.
    inline bool depthRead(uint64_t test)
    {
        const uint32_t ztst = static_cast<uint32_t>((test >> 17) & 3u);
        return ((test >> 16) & 1u) != 0u && (ztst == 2u || ztst == 3u);
    }

    inline bool depthWrite(uint64_t test, bool zmask)
    {
        const bool ate = (test & 1u) != 0u;
        const uint32_t atst = static_cast<uint32_t>((test >> 1) & 7u);
        const uint32_t afail = static_cast<uint32_t>((test >> 12) & 3u);
        if (ate && atst == 0u && afail != 2u)   // alpha test NEVER and not ZB_ONLY: nothing reaches the z buffer
            return false;
        const bool zte = ((test >> 16) & 1u) != 0u;
        if (zte && ((test >> 17) & 3u) == 0u)   // ZTST NEVER: every pixel fails
            return false;
        return !zmask && zte;                   // ZTE == 0 blocks the write on the real GS
    }

    // PS2X_GS_ZFLOOR: a Flag, on unless set to 0 (0 = the old path: no floor, no format clamp).
    inline bool zfloorDefault()
    {
        return true;
    }

    // PCSX2 PR #13851: the floor only where z is interpolated (not points, sprites or equal vertex z) and the draw
    // writes z, or reads it under ZTST GREATER ("otherwise there can be false passing if the incoming Z is not
    // floored when the buffer value is floored"). An AA1 line never writes z (its coverage is below 0x80).
    inline bool floorApplies(bool knob, uint64_t test, bool zmask, bool flatZ, bool aa1Line)
    {
        if (!knob || flatZ)
            return false;
        const bool write = !aa1Line && depthWrite(test, zmask);
        return write || (depthRead(test) && ((test >> 17) & 3u) == 3u);
    }

    // One draw's z handling (EmulateZbuffer): the floor program or not, and the format clamp where PCSX2 puts it
    // -- in the vertex for flat z, in the fragment (after the floor) for interpolated z -- only when the draw
    // writes z and its largest vertex z is past the format maximum. maxAttr is 1.0 when no clamp applies.
    struct ZPlan
    {
        bool floor = false;
        bool vertexClamp = false;
        bool fragmentClamp = false;
        float maxAttr = 1.0f;
    };

    inline ZPlan plan(bool knob, uint64_t test, bool zmask, uint8_t zpsm, bool flatZ, bool aa1Line, float maxVertexAttr)
    {
        ZPlan p;
        if (!knob)
            return p;
        p.floor = floorApplies(knob, test, zmask, flatZ, aa1Line);
        const float maxAttr = formatMaxAttribute(zpsm);
        if (!aa1Line && depthWrite(test, zmask) && maxVertexAttr > maxAttr)
        {
            p.vertexClamp = flatZ;
            p.fragmentClamp = !flatZ;
            p.maxAttr = maxAttr;
        }
        return p;
    }

    // The fragment shader's depth statements: the floor program floors (PCSX2 #13795/#13851) and clamps to uZMax;
    // the base program writes gl_FragDepth only in the FragDepth mode, as before.
    inline std::string fragmentDepthGlsl(Mode mode, bool floorProgram)
    {
        if (floorProgram)
            return std::string("    // PCSX2 PR #13795/#13851 (tfx_fs.glsl): integer GS z, floored before the depth test.\n"
                               "    float z = vDepth;\n"
                               "    z = ") + kFloorGlsl + ";\n"
                               "    gl_FragDepth = min(z, uZMax);   // PCSX2 EmulateZbuffer: saturate to the ZBUF format\n";
        if (mode == Mode::FragDepth)
            return "    gl_FragDepth = vDepth;\n";
        return "";
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
