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
#include <cstdlib>
#include <iostream>

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

namespace
{
    // Sprint 13 U2 (upstream ran-j/PS2Recomp #239's class): three distinct roots, a
    // directory beside them that none of them contains, and a file in it that no
    // guest path may reach.
    struct PathContainmentFixture
    {
        TempPaths paths;
        std::filesystem::path hostRoot;
        std::filesystem::path cdRoot;
        std::filesystem::path mcRoot;
        std::filesystem::path outside;
        std::filesystem::path secret;
        std::vector<uint8_t> rdram;
        R5900Context ctx{};

        PathContainmentFixture() : paths(makeTempPaths()), rdram(PS2_RAM_SIZE, 0)
        {
            const std::filesystem::path host = paths.base / "hostroot";
            outside = paths.base / "outside";
            secret = outside / "secret.txt";
            std::filesystem::create_directories(host);
            std::filesystem::create_directories(outside);
            std::ofstream(secret, std::ios::binary) << "outside every root";

            PS2Runtime::IoPaths ioPaths;
            ioPaths.elfDirectory = paths.cdRoot;
            ioPaths.hostRoot = host;
            ioPaths.cdRoot = paths.cdRoot;
            ioPaths.mcRoot = paths.mcRoot;
            PS2Runtime::setIoPaths(ioPaths);

            // Read the roots back: setIoPaths normalises them (and PS2X_MC_DIR may move mcRoot).
            const PS2Runtime::IoPaths &applied = PS2Runtime::getIoPaths();
            hostRoot = applied.hostRoot;
            cdRoot = applied.cdRoot;
            mcRoot = applied.mcRoot;
            std::filesystem::create_directories(mcRoot);
        }

        ~PathContainmentFixture()
        {
            // Links first, so nothing below ever walks through one.
            for (const std::filesystem::path &root : {hostRoot, cdRoot, mcRoot})
            {
                std::error_code ec;
                std::filesystem::remove(root / "escape", ec);
                std::filesystem::remove(root / "inner_link", ec);
            }
        }

        int32_t fio(void (*fn)(uint8_t *, R5900Context *, PS2Runtime *),
                    const std::string &guestPath,
                    uint32_t arg1 = 0u)
        {
            constexpr uint32_t pathAddr = GUEST_STRING_AREA_START + 0xE00;
            writeGuestString(rdram.data(), pathAddr, guestPath);
            clearContext(ctx);
            setRegU32(ctx, 4, pathAddr);
            setRegU32(ctx, 5, arg1);
            fn(rdram.data(), &ctx, nullptr);
            return getRegS32(&ctx, 2);
        }

        void closeIfOpen(int32_t fd)
        {
            if (fd >= 0)
            {
                clearContext(ctx);
                setRegU32(ctx, 4, static_cast<uint32_t>(fd));
                fioClose(rdram.data(), &ctx, nullptr);
            }
        }
    };

    // A directory link planted inside a root. A symlink where the platform lets the
    // test binary make one; on Windows without the symlink privilege, a junction,
    // which needs none and which the host filesystem follows just the same.
    bool plantDirectoryLink(const std::filesystem::path &link,
                            const std::filesystem::path &target,
                            std::string &kind)
    {
        std::error_code ec;
        std::filesystem::create_directory_symlink(target, link, ec);
        if (!ec)
        {
            kind = "symlink";
            return true;
        }
#ifdef _WIN32
        const std::string command = "cmd /c mklink /J \"" + link.string() + "\" \"" + target.string() + "\" >nul 2>&1";
        if (std::system(command.c_str()) == 0 && std::filesystem::exists(link, ec))
        {
            kind = "junction";
            return true;
        }
#endif
        return false;
    }

    // True when a translation was refused (empty) or lexically stays under `root`.
    bool refusedOrUnder(const std::string &translated, const std::filesystem::path &root)
    {
        if (translated.empty())
        {
            return true;
        }
        const std::filesystem::path rel =
            std::filesystem::path(translated).lexically_normal().lexically_relative(root.lexically_normal());
        return !rel.empty() && !rel.is_absolute() && *rel.begin() != "..";
    }

    struct RootUnderTest
    {
        const char *prefix;
        std::filesystem::path PathContainmentFixture::*root;
    };

    const RootUnderTest kRootsUnderTest[] = {
        {"host0:", &PathContainmentFixture::hostRoot},
        {"cdrom0:", &PathContainmentFixture::cdRoot},
        {"mc0:", &PathContainmentFixture::mcRoot},
    };
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

        tc.Run("sceMcGetDir on '..' at the card root lists the root instead of refusing the card", [](TestCase &t)
        {
            // 2026-09-22, the owner's playthrough finding 3: "i'm noticing i have no memory card data, and when
            // i start a mission and select control type, it asks to save, at which time i try and it fails ...
            // I restarted and it works the second time." A run to the control-type prompt on a VIRGIN card
            // logged five of `[mc] GetDir REFUSED path '..' (not normalisable)`, each answered DeniedPermit --
            // which the game reads as a card it cannot use. normalizeGuestMcPathLocked refused ".." whenever it
            // would pop past the root, and on a fresh card the current directory IS the root. Every filesystem
            // the API imitates answers "/.." with "/".
            TestContext test;
            std::filesystem::create_directories(test.paths.mcRoot / "SAVEDATA");

            const uint32_t patternAddr = GUEST_STRING_AREA_START + 0x780;
            writeGuestString(test.rdram.data(), patternAddr, "..");

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, patternAddr);
            setRegU32(test.ctx, 7, 0u);
            setRegU32(test.ctx, 8, 8u);
            setRegU32(test.ctx, 9, GUEST_MC_TABLE_ADDR);

            ps2_stubs::sceMcGetDir(test.rdram.data(), &test.ctx, nullptr);

            int32_t cmd = 0;
            const int32_t result = syncMc(test.rdram, &cmd);
            t.Equals(cmd, 0x0D, "the last command is GETDIR");
            t.IsTrue(result != -5, "'..' at the root is not DeniedPermit -- that refusal is what failed the save");
            t.IsTrue(result >= 0, "it is a listing: a count of entries, not an error code");
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

        // --- Sprint 10 Q7 item 4: the Sprint 8 branch review's card leftovers (KNOWN 110 d) ---------
        // (1) the 8000-cluster size was never enforced on writes; (2) a card root that cannot be a
        // directory read as an empty, formatted card; (3) GetInfo walked the directory recursively
        // under the mutex on every poll, and the game polls it many times a second in the menus.

        tc.Run("a write that would take the card past its 8000 clusters is refused with sceMcResFullDevice and nothing of it lands (KNOWN 110 d)", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0xA00;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0xA04;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0xA08;
            constexpr uint32_t dirAddr = GUEST_STRING_AREA_START + 0xE00;
            constexpr uint32_t fileAddr = GUEST_STRING_AREA_START + 0xE40;
            constexpr uint32_t secondAddr = GUEST_STRING_AREA_START + 0xE80;
            constexpr uint32_t payloadAddr = 0x100000u;                   // 8 MB of guest RAM from here
            constexpr int32_t kFillBytes = 7999 * 1024;                   // the folder's own cluster + 7999 = 8000

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);
            writeGuestString(test.rdram.data(), dirAddr, "/BASCUS-97275SOCOMII");
            writeGuestString(test.rdram.data(), fileAddr, "/BASCUS-97275SOCOMII/FILL.BIN");
            writeGuestString(test.rdram.data(), secondAddr, "/BASCUS-97275SOCOMII/MORE.BIN");
            for (int32_t i = 0; i < kFillBytes; ++i)
                test.rdram[payloadAddr + static_cast<uint32_t>(i)] = static_cast<uint8_t>(i * 7);

            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, dirAddr);
            ps2_stubs::sceMcMkdir(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "the save folder is created (one cluster)");

            auto openFor = [&](uint32_t nameAddr, uint32_t mode)
            {
                clearContext(test.ctx);
                setRegU32(test.ctx, 4, 0u);
                setRegU32(test.ctx, 5, 0u);
                setRegU32(test.ctx, 6, nameAddr);
                setRegU32(test.ctx, 7, mode);
                ps2_stubs::sceMcOpen(test.rdram.data(), &test.ctx, nullptr);
                return syncMc(test.rdram);
            };
            auto writeTo = [&](int32_t fd, uint32_t src, int32_t bytes)
            {
                clearContext(test.ctx);
                setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
                setRegU32(test.ctx, 5, src);
                setRegU32(test.ctx, 6, static_cast<uint32_t>(bytes));
                ps2_stubs::sceMcWrite(test.rdram.data(), &test.ctx, nullptr);
                return syncMc(test.rdram);
            };
            auto closeFd = [&](int32_t fd)
            {
                clearContext(test.ctx);
                setRegU32(test.ctx, 4, static_cast<uint32_t>(fd));
                ps2_stubs::sceMcClose(test.rdram.data(), &test.ctx, nullptr);
                return syncMc(test.rdram);
            };

            const int32_t fd = openFor(fileAddr, PS2_FIO_WRITE_CREATE_TRUNC);
            t.IsTrue(fd > 0, "the fill file opens for writing");
            t.Equals(writeTo(fd, payloadAddr, kFillBytes), kFillBytes, "7999 clusters fit beside the folder's one: the card is exactly full");
            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(syncMc(test.rdram), 0, "the full card still answers GetInfo");
            t.Equals(readGuestS32(test.rdram.data(), freeAddr), 0, "and reports no free cluster");

            t.Equals(writeTo(fd, payloadAddr, 1), -3, "one more byte needs a cluster the card does not have: sceMcResFullDevice");
            t.Equals(closeFd(fd), 0, "the fill file closes");
            std::error_code ec;
            t.Equals(static_cast<int64_t>(std::filesystem::file_size(test.paths.mcRoot / "BASCUS-97275SOCOMII" / "FILL.BIN", ec)),
                     static_cast<int64_t>(kFillBytes), "the refused byte never landed on the host file");

            const int32_t fd2 = openFor(secondAddr, PS2_FIO_WRITE_CREATE_TRUNC);
            t.IsTrue(fd2 > 0, "a second file can be opened (an empty file costs no data cluster)");
            t.Equals(writeTo(fd2, payloadAddr, 100), -3, "but its first byte has nowhere to go on a full card");
            t.Equals(closeFd(fd2), 0, "the second file closes");
            t.Equals(static_cast<int64_t>(std::filesystem::file_size(test.paths.mcRoot / "BASCUS-97275SOCOMII" / "MORE.BIN", ec)),
                     static_cast<int64_t>(0), "and stays empty");

            // Rewriting inside the file's existing clusters needs no new one.
            const int32_t fd3 = openFor(fileAddr, PS2_FIO_O_WRONLY);
            t.IsTrue(fd3 > 0, "the fill file reopens for writing");
            t.Equals(writeTo(fd3, payloadAddr, 512), 512, "overwriting the first 512 bytes allocates nothing and is accepted");
            t.Equals(closeFd(fd3), 0, "closed again");
        });

        tc.Run("a card root that cannot be a directory is not an empty formatted card: no card, and exit 72 for the launcher to explain (KNOWN 110 d)", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0xA20;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0xA24;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0xA28;

            // The launcher's profile folder is a FILE: create_directories fails, and the old code then read
            // "does not exist" as "holds nothing" -- an empty, formatted 8 MB card that no save could ever land on.
            std::error_code ec;
            std::filesystem::remove_all(test.paths.mcRoot, ec);
            {
                std::ofstream blocker(test.paths.mcRoot, std::ios::binary);
                blocker << "not a directory";
            }
            t.IsTrue(std::filesystem::is_regular_file(test.paths.mcRoot, ec), "the card root is a file before the query");
            setPs2ProcessExitCode(0);

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);
            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            const int32_t result = syncMc(test.rdram);
            t.IsTrue(result != 0, "GetInfo does not succeed on a card that cannot exist");
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 0, "no card is inserted (type 0), not an empty formatted one (type 2)");
            t.Equals(readGuestS32(test.rdram.data(), freeAddr), 0, "and it has no free space to offer");
            t.Equals(ps2ProcessExitCode(), 72, "the process will leave with card-dir-unwritable, the sentence the launcher already knows");
            // Polled again -- the game asks many times a second -- the answer holds and the code is not lost.
            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(readGuestS32(test.rdram.data(), typeAddr), 0, "still no card on the next poll");
            t.Equals(ps2ProcessExitCode(), 72, "the exit code stays");
            setPs2ProcessExitCode(0);
            std::filesystem::remove(test.paths.mcRoot, ec);
            std::filesystem::create_directories(test.paths.mcRoot, ec);
        });

        tc.Run("GetInfo counts the card's clusters once and again after the game's own writes, not on every poll (KNOWN 110 d)", [](TestCase &t)
        {
            TestContext test;

            constexpr uint32_t typeAddr = GUEST_BUFFER_AREA_START + 0xA40;
            constexpr uint32_t freeAddr = GUEST_BUFFER_AREA_START + 0xA44;
            constexpr uint32_t formatAddr = GUEST_BUFFER_AREA_START + 0xA48;
            constexpr uint32_t dirAddr = GUEST_STRING_AREA_START + 0xF00;

            clearContext(test.ctx);
            ps2_stubs::sceMcInit(test.rdram.data(), &test.ctx, nullptr);
            const uint64_t walksAtStart = ps2_stubs::getMemoryCardDebugSnapshot().directoryWalks;

            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(syncMc(test.rdram), 0, "the first poll answers");
            const int32_t freeFirst = readGuestS32(test.rdram.data(), freeAddr);
            t.Equals(ps2_stubs::getMemoryCardDebugSnapshot().directoryWalks - walksAtStart, uint64_t{1}, "the first poll walks the directory once");

            for (int i = 0; i < 20; ++i)
                mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(ps2_stubs::getMemoryCardDebugSnapshot().directoryWalks - walksAtStart, uint64_t{1}, "twenty more polls walk nothing");
            t.Equals(readGuestS32(test.rdram.data(), freeAddr), freeFirst, "and answer the same free count");

            // What the game itself changes is counted at its next poll.
            writeGuestString(test.rdram.data(), dirAddr, "/BASCUS-97275SOCOMII");
            clearContext(test.ctx);
            setRegU32(test.ctx, 4, 0u);
            setRegU32(test.ctx, 5, 0u);
            setRegU32(test.ctx, 6, dirAddr);
            ps2_stubs::sceMcMkdir(test.rdram.data(), &test.ctx, nullptr);
            t.Equals(syncMc(test.rdram), 0, "the game makes its save folder");
            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(ps2_stubs::getMemoryCardDebugSnapshot().directoryWalks - walksAtStart, uint64_t{2}, "the poll after a write walks again");
            t.Equals(readGuestS32(test.rdram.data(), freeAddr), freeFirst - 1, "and sees the folder's cluster");
            mcGetInfo(test, 0, typeAddr, freeAddr, formatAddr);
            t.Equals(ps2_stubs::getMemoryCardDebugSnapshot().directoryWalks - walksAtStart, uint64_t{2}, "and the next poll does not");
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

        // Sprint 13 U2: upstream #239's class. Every guest file path the EE fio calls, the
        // SifLoadElf path and the IOP host adapter hand to translatePs2Path must stay under
        // its root, or come back empty -- which every caller turns into the -1 the PS2 fio
        // library reports for a path it cannot open.
        tc.Run("a translated path with '..' cannot leave hostRoot, cdRoot or mcRoot", [](TestCase &t)
        {
            PathContainmentFixture fx;
            for (const RootUnderTest &r : kRootsUnderTest)
            {
                const std::string prefix = r.prefix;
                for (const std::string &climb : {std::string("../outside/secret.txt"),
                                                 std::string("/../outside/secret.txt"),
                                                 std::string("\\..\\outside\\secret.txt;1"),
                                                 std::string("sub/../../outside/secret.txt"),
                                                 std::string("./.. /outside/secret.txt"),
                                                 std::string("... /outside/secret.txt")})
                {
                    const std::string guest = prefix + climb;
                    t.Equals(translatePs2Path(guest.c_str()), std::string(),
                             "'" + guest + "' is refused, not translated to a host path");
                }

                const std::string readGuest = prefix + "../outside/secret.txt";
                const int32_t readFd = fx.fio(fioOpen, readGuest, PS2_FIO_O_RDONLY);
                fx.closeIfOpen(readFd);
                t.Equals(readFd, -1, "fioOpen('" + readGuest + "') fails with -1 instead of opening the file beside the root");

                const std::string createGuest = prefix + "../outside/created.txt";
                const int32_t createFd = fx.fio(fioOpen, createGuest, PS2_FIO_WRITE_CREATE_TRUNC);
                fx.closeIfOpen(createFd);
                t.Equals(createFd, -1, "fioOpen('" + createGuest + "', O_CREAT) fails with -1");
                t.IsFalse(std::filesystem::exists(fx.outside / "created.txt"),
                          "'" + createGuest + "' created nothing outside the root");

                const std::string mkdirGuest = prefix + "../outside/made_dir";
                t.Equals(fx.fio(fioMkdir, mkdirGuest), -1, "fioMkdir('" + mkdirGuest + "') fails with -1");
                t.IsFalse(std::filesystem::exists(fx.outside / "made_dir"),
                          "'" + mkdirGuest + "' made no directory outside the root");

                const std::string removeGuest = prefix + "../outside/secret.txt";
                t.Equals(fx.fio(fioRemove, removeGuest), -1, "fioRemove('" + removeGuest + "') fails with -1");
                t.IsTrue(std::filesystem::exists(fx.secret),
                         "'" + removeGuest + "' left the file outside the root in place");
                if (!std::filesystem::exists(fx.secret))
                {
                    std::ofstream(fx.secret, std::ios::binary) << "outside every root";
                }
            }

            // No device prefix: the path is the CD's.
            t.Equals(translatePs2Path("/../outside/secret.txt"), std::string(),
                     "a device-less climb is refused under cdRoot too");
        });

        tc.Run("a translated path carrying a drive letter is refused for hostRoot, cdRoot and mcRoot", [](TestCase &t)
        {
            PathContainmentFixture fx;
            const std::string absoluteSecret = fx.secret.string();
            const std::string genericSecret = fx.secret.generic_string();

            // The bare drive-letter path used to come back verbatim.
            t.Equals(translatePs2Path("C:\\Windows\\win.ini"), std::string(),
                     "a bare Windows drive path is not passed through to the host");
            t.Equals(translatePs2Path("c:/Windows/win.ini"), std::string(),
                     "nor in lower case with forward slashes");
            // On Windows the drive refuses it; on Linux the leading '/' makes it a CD path under cdRoot.
            t.IsTrue(refusedOrUnder(translatePs2Path(absoluteSecret.c_str()), fx.cdRoot),
                     "an absolute host path to a file outside every root is refused or kept under cdRoot");

            for (const RootUnderTest &r : kRootsUnderTest)
            {
                const std::string prefix = r.prefix;
                for (const std::string &drive : {std::string("C:\\Windows\\win.ini"),
                                                 std::string("/C:/Windows/win.ini"),
                                                 std::string("sub/C:/Windows/win.ini"),
                                                 std::string("C:secret.txt")})
                {
                    const std::string guest = prefix + drive;
                    t.Equals(translatePs2Path(guest.c_str()), std::string(),
                             "'" + guest + "' is refused, not translated to a host path");
                }
                const std::string smuggled = prefix + "/" + genericSecret;
                t.IsTrue(refusedOrUnder(translatePs2Path(smuggled.c_str()), fx.*(r.root)),
                         "'" + smuggled + "' is refused (a drive) or stays under its root (no drive)");

                const std::string readGuest = prefix + "/" + genericSecret;
                const int32_t readFd = fx.fio(fioOpen, readGuest, PS2_FIO_O_RDONLY);
                fx.closeIfOpen(readFd);
                t.Equals(readFd, -1, "fioOpen('" + readGuest + "') fails with -1");
            }

            const int32_t bareFd = fx.fio(fioOpen, absoluteSecret, PS2_FIO_O_RDONLY);
            fx.closeIfOpen(bareFd);
            t.Equals(bareFd, -1, "fioOpen of a bare absolute host path fails with -1");

            const std::string createAbsolute = (fx.outside / "created_abs.txt").string();
            const int32_t createFd = fx.fio(fioOpen, createAbsolute, PS2_FIO_WRITE_CREATE_TRUNC);
            fx.closeIfOpen(createFd);
            t.Equals(createFd, -1, "fioOpen(O_CREAT) of a bare absolute host path fails with -1");
            t.IsFalse(std::filesystem::exists(fx.outside / "created_abs.txt"),
                      "and creates nothing outside the roots");
        });

        tc.Run("a symlink planted inside hostRoot, cdRoot or mcRoot cannot lead outside it", [](TestCase &t)
        {
            PathContainmentFixture fx;
            for (const RootUnderTest &r : kRootsUnderTest)
            {
                const std::string prefix = r.prefix;
                const std::filesystem::path &root = fx.*(r.root);
                std::string kind;
                if (!plantDirectoryLink(root / "escape", fx.outside, kind))
                {
#ifdef _WIN32
                    std::cout << "[U2] no symlink or junction could be planted under " << root.string()
                              << "; the link case is skipped for " << prefix << std::endl;
                    continue;
#else
                    t.Fail("the symlink fixture under " + root.string() + " could not be created");
                    continue;
#endif
                }

                t.IsTrue(std::filesystem::exists(root / "escape" / "secret.txt"),
                         "the " + kind + " fixture under " + prefix + " really reaches the outside file");

                const std::string guest = prefix + "/escape/secret.txt";
                t.Equals(translatePs2Path(guest.c_str()), std::string(),
                         "'" + guest + "' through a " + kind + " to outside the root is refused");

                const int32_t readFd = fx.fio(fioOpen, guest, PS2_FIO_O_RDONLY);
                fx.closeIfOpen(readFd);
                t.Equals(readFd, -1, "fioOpen('" + guest + "') through the " + kind + " fails with -1");

                const std::string createGuest = prefix + "/escape/created_link.txt";
                const int32_t createFd = fx.fio(fioOpen, createGuest, PS2_FIO_WRITE_CREATE_TRUNC);
                fx.closeIfOpen(createFd);
                t.Equals(createFd, -1, "fioOpen('" + createGuest + "', O_CREAT) through the " + kind + " fails with -1");
                t.IsFalse(std::filesystem::exists(fx.outside / "created_link.txt"),
                          "'" + createGuest + "' created nothing outside the root");

                const std::string removeGuest = prefix + "/escape/secret.txt";
                t.Equals(fx.fio(fioRemove, removeGuest), -1, "fioRemove('" + removeGuest + "') fails with -1");
                t.IsTrue(std::filesystem::exists(fx.secret), "'" + removeGuest + "' left the outside file in place");
                if (!std::filesystem::exists(fx.secret))
                {
                    std::ofstream(fx.secret, std::ios::binary) << "outside every root";
                }

                std::error_code ec;
                std::filesystem::remove(root / "escape", ec);
            }
        });

        tc.Run("contained paths still translate: in-root '..', ISO versions, a link that stays inside the root", [](TestCase &t)
        {
            PathContainmentFixture fx;
            t.Equals(translatePs2Path("mc0:/dir/../save.dat"), (fx.mcRoot / "save.dat").lexically_normal().string(),
                     "a '..' that stays inside mcRoot is kept");
            t.Equals(translatePs2Path("host0:config.ini"), (fx.hostRoot / "config.ini").lexically_normal().string(),
                     "host0: resolves under hostRoot");
            t.Equals(translatePs2Path("cdrom0:\\DATA\\X.BIN;1"), (fx.cdRoot / "DATA" / "X.BIN").lexically_normal().string(),
                     "cdrom0: strips the ISO version and resolves under cdRoot");
            t.Equals(translatePs2Path("mc0:/SAVEDATA/save.dat"),
                     (fx.mcRoot / "SAVEDATA" / "save.dat").lexically_normal().string(),
                     "mc0: resolves under mcRoot");
            t.Equals(translatePs2Path("/SYSTEM.CNF;1"), (fx.cdRoot / "SYSTEM.CNF").lexically_normal().string(),
                     "a device-less path resolves under cdRoot");

            std::filesystem::create_directories(fx.cdRoot / "real_dir");
            std::ofstream(fx.cdRoot / "real_dir" / "inner.bin", std::ios::binary) << "inside";
            std::string kind;
            if (plantDirectoryLink(fx.cdRoot / "inner_link", fx.cdRoot / "real_dir", kind))
            {
                t.Equals(translatePs2Path("cdrom0:\\inner_link\\inner.bin"),
                         (fx.cdRoot / "inner_link" / "inner.bin").lexically_normal().string(),
                         "a " + kind + " that stays inside cdRoot is still followed");
                const int32_t fd = fx.fio(fioOpen, "cdrom0:\\inner_link\\inner.bin", PS2_FIO_O_RDONLY);
                fx.closeIfOpen(fd);
                t.IsTrue(fd >= 0, "and fioOpen through it succeeds");
            }
        });
    });
}
