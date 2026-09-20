#pragma once

// Sprint 9 Goal 1: a zip writer for the diagnostics bundle. STORE only (method 0, no compression), no
// zip64, no data descriptors, no encryption: three fixed-layout records and a CRC-32, so there is no
// dependency to vendor and nothing to audit but this file. The archive is built in memory -- the
// bundle is a few megabytes at most (launcher/diagnostics.h clips the log).

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ZipStore
{
    struct Entry
    {
        std::string name;   // '/'-separated, relative, UTF-8
        std::string data;
    };

    // IEEE 802.3 CRC-32 (reflected, polynomial 0xEDB88320). Pass the previous result to continue.
    uint32_t crc32(const uint8_t *data, size_t size, uint32_t crc = 0u);

    bool nameAllowed(const std::string &name);

    // "YYYYMMDD_HHMMSS" -> MS-DOS date and time words. False (outputs untouched) when it is not one.
    bool dosDateTime(const std::string &stamp, uint16_t &date, uint16_t &time);

    // The archive's bytes; empty when a name is not allowed or a zip32 limit would be passed.
    std::string build(const std::vector<Entry> &entries, uint16_t dosDate = 0x0021, uint16_t dosTime = 0);
}
