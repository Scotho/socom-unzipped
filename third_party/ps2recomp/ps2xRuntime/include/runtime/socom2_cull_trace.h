#pragma once
// SOCOM II's box-frustum cull (FUN_00290c30 -> FUN_00294ac0, research/31 section 16), recomputed in plain IEEE
// arithmetic so a trace of the guest's own answers can be checked against it. The guest runs each of the eight
// world-space corners of an object's box through the camera's 4x4 in VU0 macro mode --
//   clip = vf4 * x + vf5 * y + vf6 * z + vf7 * w   (the four qwords at camera + 0x330, applied as rows)
// -- then `VCLIPw.xyz clip, clip` judges x, y and z against |clip.w| (bit 0: x > +w, bit 1: x < -w, bits 2/3 y,
// bits 4/5 z), ANDs the six bits over the corners (nonzero: every corner beyond one plane, the box is culled)
// and ORs them (nonzero: some corner beyond some plane, the box straddles the frustum). It returns
// AND | (OR << 8); the caller (FUN_00290c30) masks the AND with the camera's plane mask (camera + 0x564).
#include <cmath>
#include <cstdint>

namespace socom2_cull
{
    // `m` holds the four row qwords in order (vf4, vf5, vf6, vf7), sixteen floats. `corners[i]` is x, y, z, w.
    inline void boxClipMasks(const float m[16], const float corners[8][4], uint32_t &andMask, uint32_t &orMask)
    {
        andMask = 0x3Fu;
        orMask = 0u;
        for (int i = 0; i < 8; ++i)
        {
            float c[4];
            for (int lane = 0; lane < 4; ++lane)
                c[lane] = m[0 * 4 + lane] * corners[i][0] + m[1 * 4 + lane] * corners[i][1] +
                          m[2 * 4 + lane] * corners[i][2] + m[3 * 4 + lane] * corners[i][3];
            const float w = std::fabs(c[3]);
            uint32_t f = 0u;
            if (c[0] > w) f |= 0x01u;
            if (c[0] < -w) f |= 0x02u;
            if (c[1] > w) f |= 0x04u;
            if (c[1] < -w) f |= 0x08u;
            if (c[2] > w) f |= 0x10u;
            if (c[2] < -w) f |= 0x20u;
            andMask &= f;
            orMask |= f;
        }
    }

    inline uint32_t packResult(uint32_t andMask, uint32_t orMask)
    {
        return (andMask & 0x3Fu) | ((orMask & 0x3Fu) << 8);
    }
}
