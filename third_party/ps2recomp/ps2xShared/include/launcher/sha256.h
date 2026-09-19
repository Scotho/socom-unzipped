#pragma once
#include <cstddef>
#include <cstdint>
#include <string>

namespace sha256
{
    // Lower-case hex digest of `bytes`.
    std::string hex(const uint8_t *bytes, size_t count);
}
