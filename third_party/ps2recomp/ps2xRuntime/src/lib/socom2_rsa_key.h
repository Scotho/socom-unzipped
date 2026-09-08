// Fixed SOCOM II client RSA key pair (full 512-bit modulus, top bits set, e = 17); generated offline
// (seed 0x50434f4d). A full 512-bit N is required so the server's 512-bit RC4 session key never
// exceeds N (a 511-bit N loses a bit and breaks the RC4 handshake). Used instead of
// rt_crypt's runtime prime search (FUN_0062b168).  LargeInt layout: 32 little-endian u32 limbs.
#pragma once
#include <cstdint>
static const uint32_t kSocom2RsaN[32] = {0xc407aa89u, 0xc3f384c9u, 0xf88a4521u, 0xc1957a96u, 0x4d0e28d2u, 0x33459627u, 0x7d5c2384u, 0x8b94e0ecu, 0xee2021a4u, 0xddc8891du, 0x00234cb6u, 0x105b8de6u, 0x1a3d27eeu, 0xeebd9e98u, 0xcf41ae69u, 0xea9e1b0eu, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u};
static const uint32_t kSocom2RsaD[32] = {0xdb9382f1u, 0xc15ae3bbu, 0x642ad20cu, 0x0ab39533u, 0x69219156u, 0xa0757e6eu, 0x8ab3664fu, 0x98c28774u, 0xebaf18f3u, 0x413afb26u, 0xd2dd34aeu, 0x410bde70u, 0x34e4cf82u, 0xafa12ea5u, 0x974f8da6u, 0x45015340u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u};
