#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_syscalls.h"
#include "ps2_stubs.h"
#include "Kernel/Stubs/CD.h"
#include "Kernel/Stubs/MemoryCard.h"

#include <filesystem>
#include <fstream>
#include <vector>
#include <cstring>
#include <chrono>

using namespace ps2_syscalls;

namespace
{
    // Guest memory address ranges for test data
    constexpr uint32_t GUEST_STRING_AREA_START = 0x1000;
    constexpr uint32_t GUEST_BUFFER_AREA_START = 0x2000;
    constexpr uint32_t GUEST_STACK_AREA_START = 0x6000;
    constexpr uint32_t GUEST_MC_SYNC_CMD_ADDR = GUEST_BUFFER_AREA_START + 0x1C00;
    constexpr uint32_t GUEST_MC_SYNC_RESULT_ADDR = GUEST_BUFFER_AREA_START + 0x1C04;
    constexpr uint32_t GUEST_MC_TABLE_ADDR = GUEST_BUFFER_AREA_START + 0x2000;
    
    // Common file I/O flag combinations
    constexpr uint32_t PS2_FIO_WRITE_CREATE_TRUNC = 
        PS2_FIO_O_WRONLY | PS2_FIO_O_CREAT | PS2_FIO_O_TRUNC;

    struct SceMcStDateTime
    {
        uint8_t resv2;
        uint8_t sec;
        uint8_t min;
        uint8_t hour;
        uint8_t day;
        uint8_t month;
        uint16_t year;
    };

    struct SceMcTblGetDir
    {
        SceMcStDateTime create;
        SceMcStDateTime modify;
        uint32_t fileSizeByte;
        uint16_t attrFile;
        uint16_t reserve1;
        uint32_t reserve2;
        uint32_t pdaAplNo;
        char entryName[32];
    };

    static_assert(sizeof(SceMcTblGetDir) == 64, "sceMcTblGetDir size mismatch");

    void setRegU32(R5900Context &ctx, int reg, uint32_t value)
    {
        ctx.r[reg] = _mm_set_epi64x(0, static_cast<int64_t>(value));
    }

    int32_t getRegS32(const R5900Context *ctx, int reg)
    {
        return static_cast<int32_t>(::getRegU32(ctx, reg));
    }

    void writeGuestString(uint8_t *rdram, uint32_t addr, const std::string &value)
    {
        std::memcpy(rdram + addr, value.c_str(), value.size() + 1);
    }

    void writeGuestU32(uint8_t *rdram, uint32_t addr, uint32_t value)
    {
        std::memcpy(rdram + addr, &value, sizeof(value));
    }

    int32_t readGuestS32(const uint8_t *rdram, uint32_t addr)
    {
        int32_t value = 0;
        std::memcpy(&value, rdram + addr, sizeof(value));
        return value;
    }

    uint32_t readGuestU32(const uint8_t *rdram, uint32_t addr)
    {
        uint32_t value = 0;
        std::memcpy(&value, rdram + addr, sizeof(value));
        return value;
    }

    void clearContext(R5900Context &ctx)
    {
        std::memset(&ctx, 0, sizeof(ctx));
    }

    int32_t syncMc(std::vector<uint8_t> &rdram, int32_t *cmdOut = nullptr)
    {
        R5900Context syncCtx{};
        setRegU32(syncCtx, 4, 0u);
        setRegU32(syncCtx, 5, GUEST_MC_SYNC_CMD_ADDR);
        setRegU32(syncCtx, 6, GUEST_MC_SYNC_RESULT_ADDR);
        ps2_stubs::sceMcSync(rdram.data(), &syncCtx, nullptr);

        if (cmdOut)
        {
            *cmdOut = readGuestS32(rdram.data(), GUEST_MC_SYNC_CMD_ADDR);
        }
        return readGuestS32(rdram.data(), GUEST_MC_SYNC_RESULT_ADDR);
    }

    struct TempPaths
    {
        std::filesystem::path base;
        std::filesystem::path mcRoot;
        std::filesystem::path cdRoot;

        ~TempPaths()
        {
            std::error_code ec;
            std::filesystem::remove_all(base, ec);
        }
    };

    TempPaths makeTempPaths()
    {
        TempPaths paths;
        const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
        paths.base = std::filesystem::temp_directory_path()
                   / ("ps2recomp-mc0-" + std::to_string(now));
        paths.mcRoot = paths.base / "mcroot";
        paths.cdRoot = paths.base / "cdroot";
        std::filesystem::create_directories(paths.mcRoot);
        std::filesystem::create_directories(paths.cdRoot);
        return paths;
    }

    struct TestContext
    {
        TempPaths paths;
        std::vector<uint8_t> rdram;
        R5900Context ctx;

        TestContext() : paths(makeTempPaths()), rdram(PS2_RAM_SIZE, 0)
        {
            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = paths.cdRoot;
            ioPaths.hostRoot = paths.cdRoot;
            ioPaths.cdRoot = paths.cdRoot;
            ioPaths.mcRoot = paths.mcRoot;
            PS2Runtime::setIoPaths(ioPaths);
        }
    };

    // The game's IsMemCardInserted (0x27E1B0 -> func_3A1650) issues exactly this:
    // sceMcGetInfo(port, slot=0, &type, &free, &format) with the fifth argument
    // in $t0, then sceMcSync, and decides on `type == 2` alone.
    void mcGetInfo(TestContext &test,
                   int32_t port,
                   uint32_t typeAddr,
                   uint32_t freeAddr,
                   uint32_t formatAddr)
    {
        writeGuestU32(test.rdram.data(), typeAddr, 0xDEADBEEFu);
        writeGuestU32(test.rdram.data(), freeAddr, 0xDEADBEEFu);
        writeGuestU32(test.rdram.data(), formatAddr, 0xDEADBEEFu);

        clearContext(test.ctx);
        setRegU32(test.ctx, 4, static_cast<uint32_t>(port));
        setRegU32(test.ctx, 5, 0u);
        setRegU32(test.ctx, 6, typeAddr);
        setRegU32(test.ctx, 7, freeAddr);
        setRegU32(test.ctx, 8, formatAddr);
        ps2_stubs::sceMcGetInfo(test.rdram.data(), &test.ctx, nullptr);
    }
}

void register_ps2_runtime_io_tests()
{
    MiniTest::Case("PS2RuntimeIO", [](TestCase &tc)
    {
        tc.Run("mc0 directory creation", [](TestCase &t)
        {
            TestContext test;

            const std::string dirPath = "mc0:/SAVEDATA";
            const uint32_t dirAddr = GUEST_STRING_AREA_START;
            writeGuestString(test.rdram.data(), dirAddr, dirPath);

            setRegU32(test.ctx, 4, dirAddr);
            fioMkdir(test.rdram.data(), &test.ctx, nullptr);
            
            const int32_t result = getRegS32(&test.ctx, 2);
            t.IsTrue(result >= 0, "fioMkdir should succeed for mc0: directory");

            const std::filesystem::path expected = test.paths.mcRoot / "SAVEDATA";
            t.IsTrue(std::filesystem::exists(expected), 
                "Directory should exist under mcRoot");
            t.IsTrue(std::filesystem::is_directory(expected), 
                "Created path should be a directory");
        });

        tc.Run("mc0 file write operations", [](TestCase &t)
        {
            TestContext test;

            // Setup: create directory first
            const std::string dirPath = "mc0:/SAVEDATA";
            const uint32_t dirAddr = GUEST_STRING_AREA_START;
            writeGuestString(test.rdram.data(), dirAddr, dirPath);
            setRegU32(test.ctx, 4, dirAddr);
            fioMkdir(test.rdram.data(), &test.ctx, nullptr);

            // Test: open file for writing
            const std::string filePath = "mc0:/SAVEDATA/test.txt";
            const uint32_t fileAddr = GUEST_STRING_AREA_START + 0x100;
            writeGuestString(test.rdram.data(), fileAddr, filePath);

            setRegU32(test.ctx, 4, fileAddr);
            setRegU32(test.ctx, 5, PS2_FIO_WRITE_CREATE_TRUNC);
            fioOpen(test.rdram.data(), &test.ctx, nullptr);
            
            const int32_t fd = getRegS32(&test.ctx, 2);
            t.IsTrue(fd >= 0, "fioOpen should return valid file descriptor");

            // Write payload
            const std::string payload = "hello mc0";
            const uint32_t bufAddr = GUEST_BUFFER_AREA_START;
            std::memcpy(test.rdram.data() + bufAddr, payload.data(), payload.size());

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, bufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            fioWrite(test.rdram.data(), &test.ctx, nullptr);
            
            const int32_t bytesWritten = getRegS32(&test.ctx, 2);
            t.Equals(bytesWritten, static_cast<int32_t>(payload.size()), 
                "fioWrite should write all bytes");

            // Close file
            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            fioClose(test.rdram.data(), &test.ctx, nullptr);
            
            const int32_t closeResult = getRegS32(&test.ctx, 2);
            t.IsTrue(closeResult >= 0, "fioClose should succeed");

            // Verify on host filesystem
            const std::filesystem::path expectedPath = 
                test.paths.mcRoot / "SAVEDATA" / "test.txt";
            t.IsTrue(std::filesystem::exists(expectedPath), 
                "File should exist under mcRoot");

            std::ifstream in(expectedPath, std::ios::binary);
            std::string readback(
                (std::istreambuf_iterator<char>(in)), 
                std::istreambuf_iterator<char>());
            t.Equals(readback, payload, "File content should match written payload");
        });

        tc.Run("mc0 file read operations", [](TestCase &t)
        {
            TestContext test;

            // Setup: create directory and write file
            const std::string dirPath = "mc0:/SAVEDATA";
            const uint32_t dirAddr = GUEST_STRING_AREA_START;
            writeGuestString(test.rdram.data(), dirAddr, dirPath);
            setRegU32(test.ctx, 4, dirAddr);
            fioMkdir(test.rdram.data(), &test.ctx, nullptr);

            const std::string filePath = "mc0:/SAVEDATA/test.txt";
            const uint32_t fileAddr = GUEST_STRING_AREA_START + 0x100;
            writeGuestString(test.rdram.data(), fileAddr, filePath);

            // Write data
            const std::string payload = "hello mc0 read test";
            const uint32_t writeBufAddr = GUEST_BUFFER_AREA_START;
            std::memcpy(test.rdram.data() + writeBufAddr, payload.data(), payload.size());

            setRegU32(test.ctx, 4, fileAddr);
            setRegU32(test.ctx, 5, PS2_FIO_WRITE_CREATE_TRUNC);
            fioOpen(test.rdram.data(), &test.ctx, nullptr);
            int32_t fd = getRegS32(&test.ctx, 2);

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, writeBufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            fioWrite(test.rdram.data(), &test.ctx, nullptr);

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            fioClose(test.rdram.data(), &test.ctx, nullptr);

            // Test: read back via fioRead
            setRegU32(test.ctx, 4, fileAddr);
            setRegU32(test.ctx, 5, PS2_FIO_O_RDONLY);
            fioOpen(test.rdram.data(), &test.ctx, nullptr);
            fd = getRegS32(&test.ctx, 2);
            t.IsTrue(fd >= 0, "fioOpen for reading should succeed");

            // Read into different buffer area
            const uint32_t readBufAddr = GUEST_BUFFER_AREA_START + 0x1000;
            std::memset(test.rdram.data() + readBufAddr, 0, payload.size());

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, readBufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            fioRead(test.rdram.data(), &test.ctx, nullptr);

            const int32_t bytesRead = getRegS32(&test.ctx, 2);
            t.Equals(bytesRead, static_cast<int32_t>(payload.size()), 
                "fioRead should read all bytes");

            std::string readback(
                reinterpret_cast<const char*>(test.rdram.data() + readBufAddr),
                payload.size()
            );
            t.Equals(readback, payload, "fioRead content should match original");

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            fioClose(test.rdram.data(), &test.ctx, nullptr);
        });

        tc.Run("mc0 paths isolated from cdRoot", [](TestCase &t)
        {
            TestContext test;

            const std::string dirPath = "mc0:/ISOLATED";
            const std::string filePath = "mc0:/ISOLATED/test.txt";
            const uint32_t dirAddr = GUEST_STRING_AREA_START;
            const uint32_t fileAddr = GUEST_STRING_AREA_START + 0x100;
            
            writeGuestString(test.rdram.data(), dirAddr, dirPath);
            writeGuestString(test.rdram.data(), fileAddr, filePath);

            // Create directory and file on mc0:
            setRegU32(test.ctx, 4, dirAddr);
            fioMkdir(test.rdram.data(), &test.ctx, nullptr);

            setRegU32(test.ctx, 4, fileAddr);
            setRegU32(test.ctx, 5, PS2_FIO_WRITE_CREATE_TRUNC);
            fioOpen(test.rdram.data(), &test.ctx, nullptr);
            const int32_t fd = getRegS32(&test.ctx, 2);

            const std::string payload = "isolation test";
            const uint32_t bufAddr = GUEST_BUFFER_AREA_START;
            std::memcpy(test.rdram.data() + bufAddr, payload.data(), payload.size());

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, bufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            fioWrite(test.rdram.data(), &test.ctx, nullptr);

            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            fioClose(test.rdram.data(), &test.ctx, nullptr);

            // Verify isolation
            const std::filesystem::path expectedMc = 
                test.paths.mcRoot / "ISOLATED" / "test.txt";
            const std::filesystem::path unexpectedCd = 
                test.paths.cdRoot / "ISOLATED" / "test.txt";

            t.IsTrue(std::filesystem::exists(expectedMc), 
                "mc0: file should exist under mcRoot");
            t.IsFalse(std::filesystem::exists(unexpectedCd), 
                "mc0: file should NOT exist under cdRoot");

            // Verify mcRoot directory structure
            t.IsTrue(std::filesystem::exists(test.paths.mcRoot / "ISOLATED"), 
                "mc0: directory should exist under mcRoot");
            t.IsFalse(std::filesystem::exists(test.paths.cdRoot / "ISOLATED"), 
                "mc0: directory should NOT exist under cdRoot");
        });

        tc.Run("sceMc open write read and close roundtrip through sync", [](TestCase &t)
        {
            TestContext test;

            const uint32_t dirAddr = GUEST_STRING_AREA_START + 0x400;
            const uint32_t fileAddr = GUEST_STRING_AREA_START + 0x500;
            const uint32_t writeBufAddr = GUEST_BUFFER_AREA_START + 0x300;
            const uint32_t readBufAddr = GUEST_BUFFER_AREA_START + 0x500;
            const std::string payload = "libmc roundtrip";

            writeGuestString(test.rdram.data(), dirAddr, "/SAVEDATA");
            writeGuestString(test.rdram.data(), fileAddr, "/SAVEDATA/test.bin");
            std::memcpy(test.rdram.data() + writeBufAddr, payload.data(), payload.size());

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, dirAddr);
            ps2_stubs::sceMcMkdir(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 0, "sceMcMkdir should dispatch successfully");

            int32_t cmd = 0;
            t.Equals(syncMc(test.rdram, &cmd), 0, "sceMcMkdir should finish successfully");
            t.Equals(cmd, 0x0B, "sceMcSync should report MKDIR as the last command");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, fileAddr);
            setRegU32(test.ctx, 7, PS2_FIO_O_RDWR | PS2_FIO_O_CREAT | PS2_FIO_O_TRUNC);
            ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 0, "sceMcOpen should dispatch successfully");

            const int32_t fd = syncMc(test.rdram, &cmd);
            t.IsTrue(fd > 0, "sceMcOpen should produce a positive descriptor in sceMcSync");
            t.Equals(cmd, 0x02, "sceMcSync should report OPEN as the last command");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, writeBufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            ps2_stubs::sceMcWrite(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram, &cmd), static_cast<int32_t>(payload.size()),
                     "sceMcWrite should report the full byte count via sceMcSync");
            t.Equals(cmd, 0x06, "sceMcSync should report WRITE as the last command");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, PS2_FIO_SEEK_SET);
            ps2_stubs::sceMcSeek(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram, &cmd), 0, "sceMcSeek should rewind to offset zero");
            t.Equals(cmd, 0x04, "sceMcSync should report SEEK as the last command");

            std::memset(test.rdram.data() + readBufAddr, 0, payload.size());
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            setRegU32(test.ctx, 5, readBufAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(payload.size()));
            ps2_stubs::sceMcRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram, &cmd), static_cast<int32_t>(payload.size()),
                     "sceMcRead should report the full byte count via sceMcSync");
            t.Equals(cmd, 0x05, "sceMcSync should report READ as the last command");

            std::string readback(reinterpret_cast<const char *>(test.rdram.data() + readBufAddr), payload.size());
            t.Equals(readback, payload, "sceMcRead should fill the guest buffer with the written payload");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
            ps2_stubs::sceMcClose(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram, &cmd), 0, "sceMcClose should finish successfully");
            t.Equals(cmd, 0x03, "sceMcSync should report CLOSE as the last command");

            const std::filesystem::path hostPath = test.paths.mcRoot / "SAVEDATA" / "test.bin";
            t.IsTrue(std::filesystem::exists(hostPath), "sceMcOpen/sceMcWrite should create the host file under mcRoot");
        });

        tc.Run("sceMcGetDir includes dot entries and file metadata", [](TestCase &t)
        {
            TestContext test;

            std::filesystem::create_directories(test.paths.mcRoot / "SAVEDATA");
            const std::string hostPayload = "abc123";
            {
                std::ofstream out(test.paths.mcRoot / "SAVEDATA" / "game.dat", std::ios::binary);
                out.write(hostPayload.data(), static_cast<std::streamsize>(hostPayload.size()));
            }

            const uint32_t patternAddr = GUEST_STRING_AREA_START + 0x700;
            writeGuestString(test.rdram.data(), patternAddr, "/SAVEDATA/*");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, patternAddr);
            setRegU32(test.ctx, 7, 0u);
            // EE n32 ABI: arguments 5 and 6 travel in $t0/$t1
            setRegU32(test.ctx, 8, 8u);
            setRegU32(test.ctx, 9, GUEST_MC_TABLE_ADDR);

            ps2_stubs::sceMcGetDir(test.rdram.data(), &test.ctx, nullptr);

            int32_t cmd = 0;
            const int32_t entryCount = syncMc(test.rdram, &cmd);
            t.Equals(cmd, 0x0D, "sceMcSync should report GETDIR as the last command");
            t.Equals(entryCount, 3, "sceMcGetDir should return '.', '..', and the matching file");

            const auto *entries = reinterpret_cast<const SceMcTblGetDir *>(test.rdram.data() + GUEST_MC_TABLE_ADDR);
            t.Equals(std::string(entries[0].entryName), std::string("."), "sceMcGetDir should return '.' first");
            t.Equals(std::string(entries[1].entryName), std::string(".."), "sceMcGetDir should return '..' second");
            t.Equals(std::string(entries[2].entryName), std::string("game.dat"), "sceMcGetDir should include the matching file entry");
            t.Equals(entries[2].fileSizeByte, static_cast<uint32_t>(hostPayload.size()),
                     "sceMcGetDir should report the host file size");
            t.IsTrue((entries[2].attrFile & 0x0080u) != 0u,
                     "sceMcGetDir file entries should carry the closed-file attribute");
        });

        tc.Run("sceMcGetInfo reports formatted and unformatted states", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0x900;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0x904;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0x908;

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, typeAddr);
            setRegU32(test.ctx, 7, freeAddr);
            // EE n32 ABI: the fifth argument travels in $t0
            setRegU32(test.ctx, 8, formatAddr);
            ps2_stubs::sceMcGetInfo(test.rdram.data(), &test.ctx, nullptr);

            int32_t cmd = 0;
            t.Equals(syncMc(test.rdram, &cmd), 0, "formatted cards should report success through sceMcSync");
            t.Equals(cmd, 0x01, "sceMcSync should report GETINFO as the last command");
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 2, "sceMcGetInfo should report a PS2 memory card");
            t.Equals(readGuestS32(test.rdram.data(), formatAddr), 1, "sceMcGetInfo should report a formatted card");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            ps2_stubs::sceMcUnformat(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram, &cmd), 0, "sceMcUnformat should complete successfully");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, typeAddr);
            setRegU32(test.ctx, 7, freeAddr);
            setRegU32(test.ctx, 8, formatAddr);
            ps2_stubs::sceMcGetInfo(test.rdram.data(), &test.ctx, nullptr);

            t.Equals(syncMc(test.rdram, &cmd), -2, "unformatted cards should report sceMcResNoFormat through sceMcSync");
            t.Equals(readGuestS32(test.rdram.data(), formatAddr), 0, "sceMcGetInfo should report an unformatted card after sceMcUnformat");
        });

        // --- Simulated memory cards that persist (Sprint 8 Goal 11) -------------
        // The owner's save prompt reported "no memory card inserted". The game's
        // IsMemCardInserted (0x27E1B0 -> func_3A1650) is sceMcGetInfo + sceMcSync
        // and decides on `type == 2` alone, so these cover the answers the save
        // flow actually reads off an empty, a missing and a written card folder.

        tc.Run("an empty card directory is an inserted, formatted 8 MB PS2 card", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0x980;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0x984;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0x988;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            std::error_code ec;
            t.IsTrue(std::filesystem::is_empty(test.paths.mcRoot, ec),
                     "the card root starts empty, as a fresh launcher profile leaves it");

            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            int32_t cmd = 0;
            t.Equals(syncMc(test.rdram, &cmd), 0, "an empty card directory is a card, not an error");
            t.Equals(cmd, 0x01, "sceMcSync should report GETINFO as the last command");
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 2,
                     "an empty card directory must report type 2 (IsMemCardInserted accepts nothing else)");
            t.Equals(readGuestS32(test.rdram.data(), formatAddr), 1,
                     "an empty card directory is a formatted card");

            const int32_t freeClusters = readGuestS32(test.rdram.data(), freeAddr);
            t.IsTrue(freeClusters > 0, "an empty card reports free space");
            t.IsTrue(freeClusters <= 8000,
                     "an 8 MB PS2 card has at most 8000 free 1 KB clusters");
        });

        tc.Run("a missing card directory is created by the first card query", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0x9A0;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0x9A4;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0x9A8;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            std::error_code ec;
            std::filesystem::remove_all(test.paths.mcRoot, ec);
            t.IsFalse(std::filesystem::exists(test.paths.mcRoot, ec),
                      "the card directory is gone before the query");

            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(syncMc(test.rdram), 0, "a missing card directory is still an inserted card");
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 2,
                     "a missing card directory must report type 2");
            t.IsTrue(std::filesystem::exists(test.paths.mcRoot, ec),
                     "the runtime creates the card directory so the save can persist");
        });

        tc.Run("the save folder survives a second run and free space tracks its contents", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0x9C0;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0x9C4;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0x9C8;
            constexpr uint32_t dirAddr = GUEST_STRING_AREA_START + 0xC00;
            constexpr uint32_t fileAddr = GUEST_STRING_AREA_START + 0xC40;
            constexpr uint32_t patternAddr = GUEST_STRING_AREA_START + 0xCC0;
            constexpr uint32_t payloadAddr = GUEST_BUFFER_AREA_START + 0x3000;
            constexpr int32_t kPayloadBytes = 1000;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(syncMc(test.rdram), 0, "the empty card answers sceMcGetInfo");
            const int32_t freeBefore = readGuestS32(test.rdram.data(), freeAddr);

            writeGuestString(test.rdram.data(), dirAddr, "/BASCUS-97275SOCOMII");
            writeGuestString(test.rdram.data(), fileAddr, "/BASCUS-97275SOCOMII/SOCOM2.CFG");
            writeGuestString(test.rdram.data(), patternAddr, "/BASCUS-97275SOCOMII/*");
            for (int32_t i = 0; i < kPayloadBytes; ++i)
            {
                test.rdram[payloadAddr + static_cast<uint32_t>(i)] = static_cast<uint8_t>(i & 0xFF);
            }

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, dirAddr);
            ps2_stubs::sceMcMkdir(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "sceMcMkdir should create the SOCOM II save folder");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, fileAddr);
            setRegU32(test.ctx, 7, PS2_FIO_WRITE_CREATE_TRUNC);
            ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
            const int32_t writeFd = syncMc(test.rdram);
            t.IsTrue(writeFd > 0, "sceMcOpen should open the save file for writing");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(writeFd));
            setRegU32(test.ctx, 5, payloadAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(kPayloadBytes));
            ps2_stubs::sceMcWrite(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), kPayloadBytes, "sceMcWrite should write the whole save");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(writeFd));
            ps2_stubs::sceMcClose(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "sceMcClose should close the save");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, patternAddr);
            setRegU32(test.ctx, 7, 0u);
            setRegU32(test.ctx, 8, 8u);
            setRegU32(test.ctx, 9, GUEST_MC_TABLE_ADDR);
            ps2_stubs::sceMcGetDir(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 3, "sceMcGetDir should list the dot entries and the save file");
            const auto *entries = reinterpret_cast<const SceMcTblGetDir *>(test.rdram.data() + GUEST_MC_TABLE_ADDR);
            t.Equals(std::string(entries[2].entryName), std::string("SOCOM2.CFG"),
                     "sceMcGetDir should name the save file");
            t.Equals(entries[2].fileSizeByte, static_cast<uint32_t>(kPayloadBytes),
                     "sceMcGetDir should report the save's size");

            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(syncMc(test.rdram), 0, "the written card still answers sceMcGetInfo");
            const int32_t freeAfter = readGuestS32(test.rdram.data(), freeAddr);
            t.IsTrue(freeAfter < freeBefore,
                     "free clusters must drop once the card holds a save folder and a file");

            // A second run: libmc torn down and brought back up over the same directory.
            clearContext(test.ctx);
            ps2_stubs::sceMcEnd(test.rdram.data(), &test.ctx, nullptr);
            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, fileAddr);
            setRegU32(test.ctx, 7, PS2_FIO_O_RDONLY);
            ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
            const int32_t readFd = syncMc(test.rdram);
            t.IsTrue(readFd > 0, "the next run should reopen the persisted save");

            constexpr uint32_t readbackAddr = GUEST_BUFFER_AREA_START + 0x3800;
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(readFd));
            setRegU32(test.ctx, 5, readbackAddr);
            setRegU32(test.ctx, 6, static_cast<uint32_t>(kPayloadBytes));
            ps2_stubs::sceMcRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), kPayloadBytes, "the next run should read the whole save back");
            t.IsTrue(std::memcmp(test.rdram.data() + payloadAddr,
                                 test.rdram.data() + readbackAddr,
                                 static_cast<size_t>(kPayloadBytes)) == 0,
                     "the next run should read back the same bytes");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, static_cast<uint32_t>(readFd));
            ps2_stubs::sceMcClose(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "sceMcClose should close the reopened save");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, fileAddr);
            ps2_stubs::sceMcDelete(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "sceMcDelete should remove the save");
            std::error_code ec;
            t.IsFalse(std::filesystem::exists(test.paths.mcRoot / "BASCUS-97275SOCOMII" / "SOCOM2.CFG", ec),
                      "sceMcDelete should remove the host file");
        });

        tc.Run("guest memory-card paths cannot escape the card root", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t climbAddr = GUEST_STRING_AREA_START + 0xD00;
            constexpr uint32_t absoluteAddr = GUEST_STRING_AREA_START + 0xD80;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            const std::filesystem::path outside = test.paths.base / "escape.bin";
            writeGuestString(test.rdram.data(), climbAddr, "/../escape.bin");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, climbAddr);
            setRegU32(test.ctx, 7, PS2_FIO_WRITE_CREATE_TRUNC);
            ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
            t.IsTrue(syncMc(test.rdram) < 0, "a guest path that climbs above the card root is refused");

            std::error_code ec;
            t.IsFalse(std::filesystem::exists(outside, ec),
                      "a climbing path must not create a file beside the card root");
            t.IsFalse(std::filesystem::exists(test.paths.mcRoot / "escape.bin", ec),
                      "a climbing path must not be silently rewritten into the card root");

            // An absolute host path smuggled in as a guest path: on Windows
            // operator/= replaces the whole root when the component carries a drive.
            writeGuestString(test.rdram.data(), absoluteAddr, "/" + outside.generic_string());
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, absoluteAddr);
            setRegU32(test.ctx, 7, PS2_FIO_WRITE_CREATE_TRUNC);
            ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
            t.IsTrue(syncMc(test.rdram) < 0, "an absolute host path is refused as a guest card path");
            t.IsFalse(std::filesystem::exists(outside, ec),
                      "an absolute host path must not write outside the card root");
        });

        // Sprint 8 review MUST FIX: a component that ends in a space or a dot is NOT the name it looks
        // like on Win32 -- the Win32 path parser strips trailing spaces and dots, so ".. " is ".." and
        // "a." is "a". A guest component the card stub accepted as an ordinary name therefore became a
        // climb out of the card root once the host filesystem saw it. Rejected on BOTH platforms, so the
        // Linux build refuses the same paths the Windows build does rather than quietly diverging.
        tc.Run("a memory-card path component may not end in a space or a dot", [](TestCase &t)
        {
            t.IsFalse(ps2_stubs::isSafeMcPathComponent(".. "),
                      "'.. ' is '..' to Win32: a climb wearing a trailing space");
            t.IsFalse(ps2_stubs::isSafeMcPathComponent("..."),
                      "'...' collapses to '..' too");
            t.IsFalse(ps2_stubs::isSafeMcPathComponent("a."), "a trailing dot is not part of the name on Win32");
            t.IsFalse(ps2_stubs::isSafeMcPathComponent("a "), "and neither is a trailing space");
            t.IsFalse(ps2_stubs::isSafeMcPathComponent(""), "an empty component is still refused");
            t.IsFalse(ps2_stubs::isSafeMcPathComponent("C:"), "and a drive letter still is");

            t.IsTrue(ps2_stubs::isSafeMcPathComponent("a.b"), "a dot INSIDE the name is ordinary");
            t.IsTrue(ps2_stubs::isSafeMcPathComponent("BASCUS-97275SOCOMII"),
                     "the game's own save folder is still a legal component");
            t.IsTrue(ps2_stubs::isSafeMcPathComponent("SOCOM2.CFG"), "and so is its save file");
        });

        tc.Run("sceMcFormat empties the card directory", [](TestCase &t)
        {
            TestContext test;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            std::filesystem::create_directories(test.paths.mcRoot / "BASCUS-97275SOCOMII");
            {
                std::ofstream out(test.paths.mcRoot / "BASCUS-97275SOCOMII" / "SOCOM2.CFG", std::ios::binary);
                const std::string payload = "options";
                out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
            }

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            ps2_stubs::sceMcFormat(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "sceMcFormat should succeed");

            std::error_code ec;
            t.IsTrue(std::filesystem::exists(test.paths.mcRoot, ec),
                     "sceMcFormat should leave the card directory in place");
            t.IsTrue(std::filesystem::is_empty(test.paths.mcRoot, ec),
                     "sceMcFormat should empty the card directory");
        });

        tc.Run("the second card slot reads as empty unless PS2X_MC_DIR_SLOT1 names a card", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0xA00;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0xA04;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0xA08;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);

            mcGetInfo(test, 1, typeAddr, freeAddr, formatAddr);
            t.IsTrue(syncMc(test.rdram) < 0, "port 1 has no card, so sceMcGetInfo fails");
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 0,
                     "port 1 must report card type 0 (no card) without PS2X_MC_DIR_SLOT1");

            std::error_code ec;
            const std::filesystem::path slot1 =
                test.paths.mcRoot.parent_path() / (test.paths.mcRoot.filename().string() + "_slot1");
            t.IsFalse(std::filesystem::exists(slot1, ec),
                      "port 1 must not litter a _slot1 directory when nothing is plugged into it");
        });

        tc.Run("sceMcEnd resets libmc state so sync reports no active command", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t dirAddr = GUEST_STRING_AREA_START + 0xB00;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 0, "sceMcInit should succeed");

            writeGuestString(test.rdram.data(), dirAddr, "/SAVEDATA");
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, dirAddr);
            ps2_stubs::sceMcMkdir(test.rdram.data(), &test.ctx, nullptr);
            int32_t cmd = 0;
            t.Equals(syncMc(test.rdram, &cmd), 0, "sceMcMkdir should complete before teardown");
            t.Equals(cmd, 0x0B, "sceMcSync should report MKDIR before teardown");

            clearContext(test.ctx);
            ps2_stubs::sceMcEnd(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 0, "sceMcEnd should succeed");

            // libmc semantics: with no async command pending, sceMcSync returns -1
            // and leaves the cmd/result out-parameters untouched.
            R5900Context syncCtx{};
            setRegU32(syncCtx, 4, 0u);
            setRegU32(syncCtx, 5, GUEST_MC_SYNC_CMD_ADDR);
            setRegU32(syncCtx, 6, GUEST_MC_SYNC_RESULT_ADDR);
            ps2_stubs::sceMcSync(test.rdram.data(), &syncCtx, nullptr);
            t.Equals(getRegS32(&syncCtx, 2), -1,
                     "sceMcSync after sceMcEnd should report that no command is active");
        });

        tc.Run("sceIoctl cmd1 updates wait flag state", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t statusAddr = GUEST_BUFFER_AREA_START + 0x1800;
            const uint32_t busy = 1u;
            std::memcpy(test.rdram.data() + statusAddr, &busy, sizeof(busy));

            setRegU32(test.ctx, 4, 3u);          // fd
            setRegU32(test.ctx, 5, 1u);          // cmd
            setRegU32(test.ctx, 6, statusAddr);  // arg

            ps2_stubs::sceIoctl(test.rdram.data(), &test.ctx, nullptr);

            t.Equals(getRegS32(&test.ctx, 2), 0, "sceIoctl cmd1 should return success");

            uint32_t state = 0xFFFFFFFFu;
            std::memcpy(&state, test.rdram.data() + statusAddr, sizeof(state));
            t.Equals(state, 0u, "sceIoctl cmd1 should clear wait state from busy to ready");
        });

        tc.Run("sceCdSearchFile resolves movie filenames with zero-padded host leaf", [](TestCase &t)
        {
            TestContext test;

            std::filesystem::create_directories(test.paths.cdRoot / "movie");
            {
                std::ofstream out(test.paths.cdRoot / "movie" / "mv_016.pss", std::ios::binary);
                const std::string payload = "pss";
                out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
            }

            constexpr uint32_t fileAddr = GUEST_BUFFER_AREA_START + 0x1A00;
            constexpr uint32_t pathAddr = GUEST_STRING_AREA_START + 0xA00;
            writeGuestString(test.rdram.data(), pathAddr, "\\MOVIE\\MV_16.PSS;1");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, fileAddr);
            setRegU32(test.ctx, 5, pathAddr);
            ps2_stubs::sceCdSearchFile(test.rdram.data(), &test.ctx, nullptr);

            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdSearchFile should resolve the extracted movie file");
            t.Equals(readGuestU32(test.rdram.data(), fileAddr + 4), 3u,
                     "sceCdSearchFile should report the host file size");
            t.IsTrue(readGuestU32(test.rdram.data(), fileAddr + 0) >= 0x00100000u,
                     "sceCdSearchFile should assign a pseudo LSN for the resolved host file");
        });

        tc.Run("sceCdRead reads from explicit cdImage path", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t kSectorSize = 2048u;
            constexpr uint32_t bufAddr = GUEST_BUFFER_AREA_START + 0x1C80;
            const std::filesystem::path imagePath = test.paths.base / "disc.iso";
            {
                std::vector<uint8_t> sector(kSectorSize, 0);
                const char payload[] = "cd-image";
                std::memcpy(sector.data(), payload, sizeof(payload) - 1);

                std::ofstream out(imagePath, std::ios::binary);
                out.write(reinterpret_cast<const char *>(sector.data()),
                          static_cast<std::streamsize>(sector.size()));
            }

            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = test.paths.cdRoot;
            ioPaths.hostRoot = test.paths.cdRoot;
            ioPaths.cdRoot = test.paths.cdRoot;
            ioPaths.mcRoot = test.paths.mcRoot;
            ioPaths.cdImage = imagePath;
            PS2Runtime::setIoPaths(ioPaths);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 1u);
            setRegU32(test.ctx, 6, bufAddr);
            ps2_stubs::sceCdRead(test.rdram.data(), &test.ctx, nullptr);

            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdRead should succeed when cdImage is configured");
            t.Equals(std::memcmp(test.rdram.data() + bufAddr, "cd-image", 8), 0,
                     "sceCdRead should copy sector data from the configured image");
        });

        tc.Run("StRead after Read resumes at the stream LBN", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t kSectorSize = 2048u;
            constexpr uint32_t kImageSectors = 64u;
            constexpr uint32_t kStreamLbn = 10u;
            constexpr uint32_t kPlainReadLbn = 40u;
            constexpr uint32_t kPlainReadSectors = 4u;
            constexpr uint32_t stBufAddr = GUEST_BUFFER_AREA_START + 0x10000;
            constexpr uint32_t streamDestAddr = GUEST_BUFFER_AREA_START + 0x20000;
            constexpr uint32_t plainDestAddr = GUEST_BUFFER_AREA_START + 0x30000;
            constexpr uint32_t modeAddr = GUEST_BUFFER_AREA_START + 0x3F00;
            constexpr uint32_t errorAddr = GUEST_BUFFER_AREA_START + 0x3F80;

            // A disc image whose every sector is stamped with its own LBN, so a
            // read from the wrong sector is visible in the bytes, not just the cursor.
            const std::filesystem::path imagePath = test.paths.base / "stream.iso";
            {
                std::ofstream out(imagePath, std::ios::binary);
                for (uint32_t sector = 0; sector < kImageSectors; ++sector)
                {
                    std::vector<uint8_t> bytes(kSectorSize, static_cast<uint8_t>(sector & 0xFFu));
                    std::memcpy(bytes.data(), &sector, sizeof(sector));
                    out.write(reinterpret_cast<const char *>(bytes.data()),
                              static_cast<std::streamsize>(bytes.size()));
                }
            }

            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = test.paths.cdRoot;
            ioPaths.hostRoot = test.paths.cdRoot;
            ioPaths.cdRoot = test.paths.cdRoot;
            ioPaths.mcRoot = test.paths.mcRoot;
            ioPaths.cdImage = imagePath;
            PS2Runtime::setIoPaths(ioPaths);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 64u); // buffer sectors
            setRegU32(test.ctx, 5, 4u);  // banks
            setRegU32(test.ctx, 6, stBufAddr);
            ps2_stubs::sceCdStInit(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdStInit should accept the ring description");

            writeGuestU32(test.rdram.data(), modeAddr, 0u);
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, kStreamLbn);
            setRegU32(test.ctx, 5, modeAddr);
            ps2_stubs::sceCdStStart(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdStStart should start the stream");
            t.Equals(ps2_stubs::getCdDebugSnapshot().streamingLbn, kStreamLbn,
                     "sceCdStStart should park the stream cursor on the requested LBN");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 1u); // one sector
            setRegU32(test.ctx, 5, streamDestAddr);
            setRegU32(test.ctx, 6, 1u); // STMBLK
            setRegU32(test.ctx, 7, errorAddr);
            ps2_stubs::sceCdStRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdStRead should deliver one sector");
            t.Equals(readGuestU32(test.rdram.data(), streamDestAddr), kStreamLbn,
                     "the first stream sector should be the stream's own LBN");
            const uint32_t afterFirst = ps2_stubs::getCdDebugSnapshot().streamingLbn;
            t.Equals(afterFirst, kStreamLbn + 1u, "the stream cursor advanced by one sector");

            // A plain read of an unrelated file while the stream is open.
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, kPlainReadLbn);
            setRegU32(test.ctx, 5, kPlainReadSectors);
            setRegU32(test.ctx, 6, plainDestAddr);
            ps2_stubs::sceCdRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "the plain read should succeed");
            t.Equals(ps2_stubs::getCdDebugSnapshot().streamingLbn, afterFirst,
                     "a plain read must not move the stream cursor (CD.cpp:328 set it to lbn + sectors)");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 1u);
            setRegU32(test.ctx, 5, streamDestAddr + kSectorSize);
            setRegU32(test.ctx, 6, 1u);
            setRegU32(test.ctx, 7, errorAddr);
            ps2_stubs::sceCdStRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(ps2_stubs::getCdDebugSnapshot().streamingLbn, afterFirst + 1u,
                     "the next stream read resumes where the stream was");
            t.Equals(readGuestU32(test.rdram.data(), streamDestAddr + kSectorSize), afterFirst,
                     "the next stream read delivers the stream's next sector, not bytes after the plain read");

            // While a stream is open sceCdGetReadPos reports the stream cursor;
            // with no stream open it reports the plain-read cursor.
            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), afterFirst + 1u,
                     "sceCdGetReadPos should report the stream cursor while a stream is open");

            clearContext(test.ctx);
            ps2_stubs::sceCdStStop(test.rdram.data(), &test.ctx, nullptr);

            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), kPlainReadLbn + kPlainReadSectors,
                     "sceCdGetReadPos should report the plain-read cursor with no stream open");
        });
        // Sprint 7 Task 12b: sceCdGetReadPos reports whichever cursor the caller last moved (commit 5a1b6a8),
        // not "the stream while a stream is open" -- a plain sceCdRead during an open stream moves the plain-read
        // cursor and is the position the next sceCdGetReadPos is asking about.
        tc.Run("sceCdGetReadPos follows whichever cursor the caller last moved", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t kSectorSize = 2048u;
            constexpr uint32_t kImageSectors = 64u;
            constexpr uint32_t kStreamLbn = 12u;
            constexpr uint32_t kPlainReadLbn = 44u;
            constexpr uint32_t kPlainReadSectors = 3u;
            constexpr uint32_t stBufAddr = GUEST_BUFFER_AREA_START + 0x10000;
            constexpr uint32_t streamDestAddr = GUEST_BUFFER_AREA_START + 0x20000;
            constexpr uint32_t plainDestAddr = GUEST_BUFFER_AREA_START + 0x30000;
            constexpr uint32_t modeAddr = GUEST_BUFFER_AREA_START + 0x3F00;
            constexpr uint32_t errorAddr = GUEST_BUFFER_AREA_START + 0x3F80;

            const std::filesystem::path imagePath = test.paths.base / "readpos.iso";
            {
                std::ofstream out(imagePath, std::ios::binary);
                for (uint32_t sector = 0; sector < kImageSectors; ++sector)
                {
                    std::vector<uint8_t> bytes(kSectorSize, static_cast<uint8_t>(sector & 0xFFu));
                    std::memcpy(bytes.data(), &sector, sizeof(sector));
                    out.write(reinterpret_cast<const char *>(bytes.data()),
                              static_cast<std::streamsize>(bytes.size()));
                }
            }

            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = test.paths.cdRoot;
            ioPaths.hostRoot = test.paths.cdRoot;
            ioPaths.cdRoot = test.paths.cdRoot;
            ioPaths.mcRoot = test.paths.mcRoot;
            ioPaths.cdImage = imagePath;
            PS2Runtime::setIoPaths(ioPaths);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 64u);
            setRegU32(test.ctx, 5, 4u);
            setRegU32(test.ctx, 6, stBufAddr);
            ps2_stubs::sceCdStInit(test.rdram.data(), &test.ctx, nullptr);

            writeGuestU32(test.rdram.data(), modeAddr, 0u);
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, kStreamLbn);
            setRegU32(test.ctx, 5, modeAddr);
            ps2_stubs::sceCdStStart(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "sceCdStStart should start the stream");

            // The caller last moved the plain-read cursor, although the stream is still open:
            // sceCdRead leaves it at lbn + sectors (CD.cpp, the accepted-read branch).
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, kPlainReadLbn);
            setRegU32(test.ctx, 5, kPlainReadSectors);
            setRegU32(test.ctx, 6, plainDestAddr);
            ps2_stubs::sceCdRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "the plain read should succeed with the stream open");

            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), kPlainReadLbn + kPlainReadSectors,
                     "sceCdGetReadPos should report the plain-read cursor the caller just moved");

            // One stream read moves the stream cursor, and the answer follows it back.
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 1u);
            setRegU32(test.ctx, 5, streamDestAddr);
            setRegU32(test.ctx, 6, 1u); // STMBLK
            setRegU32(test.ctx, 7, errorAddr);
            ps2_stubs::sceCdStRead(test.rdram.data(), &test.ctx, nullptr);
            const uint32_t streamCursor = ps2_stubs::getCdDebugSnapshot().streamingLbn;
            t.Equals(streamCursor, kStreamLbn + 1u, "the stream cursor advanced by one sector");

            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), streamCursor,
                     "sceCdGetReadPos should report the stream cursor once the stream moved last");

            clearContext(test.ctx);
            ps2_stubs::sceCdStStop(test.rdram.data(), &test.ctx, nullptr);
        });

        // Sprint 7 review finding F11: sceCdInit cleared g_cdLastMovedWasStream but left g_cdReadLbn where the
        // last read had put it, so a re-init reported the old drive position instead of the start of the disc.
        tc.Run("sceCdInit resets the plain-read cursor as well as the last-moved flag", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t kSectorSize = 2048u;
            constexpr uint32_t kImageSectors = 64u;
            constexpr uint32_t kPlainReadLbn = 40u;
            constexpr uint32_t kPlainReadSectors = 4u;
            constexpr uint32_t plainDestAddr = GUEST_BUFFER_AREA_START + 0x30000;

            const std::filesystem::path imagePath = test.paths.base / "cdinit.iso";
            {
                std::ofstream out(imagePath, std::ios::binary);
                for (uint32_t sector = 0; sector < kImageSectors; ++sector)
                {
                    std::vector<uint8_t> bytes(kSectorSize, static_cast<uint8_t>(sector & 0xFFu));
                    std::memcpy(bytes.data(), &sector, sizeof(sector));
                    out.write(reinterpret_cast<const char *>(bytes.data()),
                              static_cast<std::streamsize>(bytes.size()));
                }
            }

            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = test.paths.cdRoot;
            ioPaths.hostRoot = test.paths.cdRoot;
            ioPaths.cdRoot = test.paths.cdRoot;
            ioPaths.mcRoot = test.paths.mcRoot;
            ioPaths.cdImage = imagePath;
            PS2Runtime::setIoPaths(ioPaths);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, kPlainReadLbn);
            setRegU32(test.ctx, 5, kPlainReadSectors);
            setRegU32(test.ctx, 6, plainDestAddr);
            ps2_stubs::sceCdRead(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(getRegS32(&test.ctx, 2), 1, "the plain read should succeed");

            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), kPlainReadLbn + kPlainReadSectors,
                     "the read moved the cursor to lbn + sectors");

            clearContext(test.ctx);
            ps2_stubs::sceCdInit(test.rdram.data(), &test.ctx, nullptr);

            clearContext(test.ctx);
            ps2_stubs::sceCdGetReadPos(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(::getRegU32(&test.ctx, 2), 0u,
                     "sceCdInit puts the drive back at sector 0: the stale cursor does not survive it");
        });
    });
}
