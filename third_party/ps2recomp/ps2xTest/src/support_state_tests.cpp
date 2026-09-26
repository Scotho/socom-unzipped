// Issue #51: the last per-translation-unit state in Kernel/Stubs/Helpers/Support.h.
//
// Support.h defined the CD group (fourteen variables, g_cdFilesByKey .. g_cdInitialized) and
// g_iopHeapNext in an anonymous namespace, so every translation unit that includes it -- the
// nineteen stub units through Stubs/Common.h, and this file -- compiled its own copy. A file one unit
// registered was invisible to a lookup compiled in another (docs/KNOWN.md section 1, "A header that
// defines its state in an anonymous namespace gives every translation unit its own copy"). Sprint 11
// Task 8b moved four other groups into PS2Runtime-owned structs (runtime_state_tests.cpp); these cases
// hold the same two properties for the groups it left:
//   (a) the stub, compiled in a DIFFERENT translation unit, reached the state of the runtime it was
//       handed -- and a Support.h helper compiled in THIS unit sees that same state; and
//   (b) a second PS2Runtime in the same process saw none of it.
//
// This file includes Stubs/Common.h, and through it Support.h, on purpose: its own compiled copy of
// registerCdFile / findRegisteredCdFileForLbn / readCdSectors is the "other translation unit" of the
// defect class.

#include "MiniTest.h"
#include "Kernel/Stubs/Common.h"
#include "Kernel/Stubs/CD.h"
#include "Kernel/Stubs/Helpers/CdRuntimeState.h"
#include "Kernel/Stubs/SIF.h"
#include "Kernel/Stubs/Helpers/IopHeapRuntimeState.h"

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
    void setRegU32(R5900Context &ctx, int reg, uint32_t value)
    {
        ctx.r[reg] = _mm_set_epi64x(0, static_cast<int64_t>(value));
    }

    void writeGuestString(std::vector<uint8_t> &rdram, uint32_t addr, const std::string &text)
    {
        std::memcpy(rdram.data() + (addr & PS2_RAM_MASK), text.c_str(), text.size() + 1u);
    }

    uint32_t readGuestU32(const std::vector<uint8_t> &rdram, uint32_t addr)
    {
        uint32_t value = 0;
        std::memcpy(&value, rdram.data() + (addr & PS2_RAM_MASK), sizeof(value));
        return value;
    }

    // A CD root of its own with two host files, the process's IoPaths pointed at it for the life of
    // the fixture (and put back after), and no disc image -- so a lookup that misses the registered
    // files has nothing to fall back on.
    struct CdRootFixture
    {
        PS2Runtime::IoPaths saved;
        std::filesystem::path base;
        std::filesystem::path cdRoot;
        std::vector<uint8_t> rdram;
        R5900Context ctx{};

        CdRootFixture() : saved(PS2Runtime::getIoPaths()), rdram(PS2_RAM_SIZE, 0)
        {
            const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
            base = std::filesystem::temp_directory_path() / ("ps2recomp-x51-" + std::to_string(now));
            cdRoot = base / "cdroot";
            std::filesystem::create_directories(cdRoot / "DATA");
            writeFile(cdRoot / "DATA" / "X51A.BIN", 5000u, 0xA0u);   // three sectors
            writeFile(cdRoot / "DATA" / "X51B.BIN", 2048u, 0xB0u);   // one sector

            PS2Runtime::IoPaths paths;
            paths.elfDirectory = cdRoot;
            paths.hostRoot = cdRoot;
            paths.cdRoot = cdRoot;
            paths.mcRoot = base / "mc0";
            paths.cdImage.clear();
            PS2Runtime::setIoPaths(paths);
        }

        ~CdRootFixture()
        {
            PS2Runtime::setIoPaths(saved);
            std::error_code ec;
            std::filesystem::remove_all(base, ec);
        }

        static void writeFile(const std::filesystem::path &path, uint32_t size, uint8_t seed)
        {
            std::ofstream out(path, std::ios::binary);
            for (uint32_t i = 0; i < size; ++i)
            {
                out.put(static_cast<char>(static_cast<uint8_t>(seed + (i / kCdSectorSize))));
            }
        }

        // sceCdSearchFile (Stubs/CD.cpp) on `runtime`: $v0, and the LSN it wrote into the sceCdlFILE.
        int32_t search(PS2Runtime *runtime, const std::string &guestPath, uint32_t &lsnOut)
        {
            constexpr uint32_t kFileAddr = 0x00201000u;
            constexpr uint32_t kPathAddr = 0x00200000u;
            std::memset(rdram.data() + kFileAddr, 0, 32);
            writeGuestString(rdram, kPathAddr, guestPath);
            ctx = R5900Context{};
            setRegU32(ctx, 4, kFileAddr);
            setRegU32(ctx, 5, kPathAddr);
            ps2_stubs::sceCdSearchFile(rdram.data(), &ctx, runtime);
            lsnOut = readGuestU32(rdram, kFileAddr);
            return static_cast<int32_t>(getRegU32(&ctx, 2));
        }

        // sceCdRead (Stubs/CD.cpp) on `runtime`: one sector of `lbn` into kReadBuf; $v0.
        static constexpr uint32_t kReadBuf = 0x00300000u;
        int32_t read(PS2Runtime *runtime, uint32_t lbn)
        {
            std::memset(rdram.data() + kReadBuf, 0x5A, kCdSectorSize);
            ctx = R5900Context{};
            setRegU32(ctx, 4, lbn);
            setRegU32(ctx, 5, 1u);
            setRegU32(ctx, 6, kReadBuf);
            ps2_stubs::sceCdRead(rdram.data(), &ctx, runtime);
            return static_cast<int32_t>(getRegU32(&ctx, 2));
        }
    };
}

void register_support_state_tests()
{
    MiniTest::Case("Support.h's CD group and IOP heap cursor belong to the runtime (issue #51)", [](TestCase &tc)
    {
        tc.Run("Stubs/CD.cpp's sceCdSearchFile registers the file with the runtime it was handed, and a second runtime sees none of it", [](TestCase &t)
        {
            CdRootFixture fx;
            PS2Runtime first;
            PS2Runtime second;

            uint32_t lsn = 0;
            t.Equals(fx.search(&first, "\\DATA\\X51A.BIN;1", lsn), 1,
                     "sceCdSearchFile should find the host file under the fixture's CD root");
            t.Equals(lsn, ps2_stubs::kCdPseudoLbnStart,
                     "a fresh runtime numbers its own registrations from kCdPseudoLbnStart; a higher "
                     "LSN means Stubs/CD.cpp numbered this file in state some other caller had "
                     "already used (docs/KNOWN.md section 1, issue #51)");

            const ps2_stubs::CdRuntimeState &mine = first.cdRuntimeState();
            t.Equals(static_cast<uint32_t>(mine.filesByKey.size()), 1u,
                     "the registration should be in the CD state of the runtime the stub was called "
                     "with; 0 means Stubs/CD.cpp wrote state that is not this runtime's");
            t.Equals(mine.nextPseudoLbn, ps2_stubs::kCdPseudoLbnStart + 3u + 1u,
                     "and that runtime's next pseudo LBN should be past the file's three sectors");
            t.Equals(mine.streamingLbn, lsn,
                     "sceCdSearchFile parks that runtime's stream cursor on the file");

            const ps2_stubs::CdRuntimeState &theirs = second.cdRuntimeState();
            t.Equals(static_cast<uint32_t>(theirs.filesByKey.size()), 0u,
                     "a second runtime in the same process must not see the first one's registration");
            t.Equals(theirs.nextPseudoLbn, ps2_stubs::kCdPseudoLbnStart,
                     "nor its pseudo-LBN cursor");
            t.Equals(theirs.streamingLbn, 0u, "nor its stream cursor");

            // The debug panel's reader (Stubs/CD.cpp's getCdDebugSnapshot) answers per runtime too.
            t.Equals(static_cast<uint32_t>(ps2_stubs::getCdDebugSnapshot(&first).files.size()), 1u,
                     "getCdDebugSnapshot(runtime) lists the runtime's registration");
            t.Equals(static_cast<uint32_t>(ps2_stubs::getCdDebugSnapshot(&second).files.size()), 0u,
                     "and nothing for a runtime that registered nothing");
        });

        tc.Run("a file one translation unit registers is found by a lookup compiled in another, both ways", [](TestCase &t)
        {
            CdRootFixture fx;
            PS2Runtime first;
            PS2Runtime second;

            // Stubs/CD.cpp registers; this unit's own copy of Support.h's helpers looks it up.
            uint32_t lsn = 0;
            t.Equals(fx.search(&first, "\\DATA\\X51A.BIN;1", lsn), 1,
                     "sceCdSearchFile should find the host file under the fixture's CD root");
            CdFileEntry found{};
            t.IsTrue(findRegisteredCdFileForLbn(first.cdRuntimeState(), lsn + 2u, found),
                     "findRegisteredCdFileForLbn compiled in THIS translation unit should find the file "
                     "Stubs/CD.cpp registered -- the defect class: under the anonymous namespace this "
                     "unit had its own empty g_cdFilesByKey");
            t.Equals(found.baseLbn, lsn, "and it should be the same registration");
            std::vector<uint8_t> sector(kCdSectorSize, 0u);
            t.IsTrue(readCdSectors(first.cdRuntimeState(), lsn + 1u, 1u, sector.data(), sector.size()),
                     "readCdSectors compiled here should read the second sector of that file");
            t.Equals(static_cast<uint32_t>(sector[0]), 0xA1u, "with the file's own bytes");

            // This unit registers; Stubs/CD.cpp's sceCdRead reads it.
            CdFileEntry mine{};
            t.IsTrue(registerCdFile(first.cdRuntimeState(), "\\DATA\\X51B.BIN;1", mine),
                     "registerCdFile compiled here should register the second host file");
            t.Equals(fx.read(&first, mine.baseLbn), 1,
                     "sceCdRead in Stubs/CD.cpp should read the LBN this unit registered with the same "
                     "runtime; 0 means it looked in state that is not that runtime's");
            t.Equals(static_cast<uint32_t>(fx.rdram[CdRootFixture::kReadBuf]), 0xB0u,
                     "and it should have copied that file's bytes");
            t.Equals(fx.read(&second, mine.baseLbn), 0,
                     "a second runtime registered nothing and has no disc image, so the same LBN "
                     "does not resolve there");
        });

        tc.Run("PS2Runtime::resetStubRuntimeState clears the CD group", [](TestCase &t)
        {
            PS2Runtime runtime;
            ps2_stubs::CdRuntimeState &cd = runtime.cdRuntimeState();
            cd.filesByKey["data/x51a.bin"] = CdFileEntry{};
            cd.nextPseudoLbn = ps2_stubs::kCdPseudoLbnStart + 10u;
            cd.leafIndexBuilt = true;
            cd.lastError = -1;
            cd.mode = 5u;
            cd.streamingLbn = 0x1234u;
            cd.streamingEndLbn = 0x2000u;
            cd.initialized = true;

            runtime.resetStubRuntimeState();

            t.Equals(static_cast<uint32_t>(cd.filesByKey.size()), 0u,
                     "a new run starts with no registered CD files; a survivor means "
                     "CdRuntimeState::reset() never ran");
            t.Equals(cd.nextPseudoLbn, ps2_stubs::kCdPseudoLbnStart, "and numbers them from the start");
            t.IsFalse(cd.leafIndexBuilt, "and rebuilds the leaf index");
            t.Equals(cd.lastError, 0, "with no error pending");
            t.Equals(cd.mode, 0u, "no sceCdMmode");
            t.Equals(cd.streamingLbn, 0u, "the stream cursor at 0");
            t.Equals(cd.streamingEndLbn, 0xFFFFFFFFu, "with no end");
            t.IsFalse(cd.initialized, "and sceCdInit not yet called");
        });

        tc.Run("Stubs/SIF.cpp's sceSifAllocIopHeap moves the heap cursor of the runtime it was handed, and only that one", [](TestCase &t)
        {
            PS2Runtime first;
            PS2Runtime second;

            R5900Context ctx{};
            setRegU32(ctx, 4, 0x100u);
            ps2_stubs::sceSifAllocIopHeap(nullptr, &ctx, &first);
            const uint32_t block = getRegU32(&ctx, 2);
            t.IsTrue(block >= ps2_stubs::kIopHeapBase && block + 0x100u <= ps2_stubs::kIopHeapLimit,
                     "sceSifAllocIopHeap should hand out a block inside the IOP heap window");

            // g_iopHeapNext is written by Stubs/SIF.cpp and read by nobody there; this unit reads the
            // runtime's copy, which is the only way it is observable at all.
            t.Equals(first.iopHeapRuntimeState().next, block + 0x100u,
                     "the heap cursor of the runtime the stub was called with should sit at the end of "
                     "the block; the heap base means Stubs/SIF.cpp moved a cursor that is not this "
                     "runtime's (docs/KNOWN.md section 1, issue #51)");
            t.Equals(second.iopHeapRuntimeState().next, ps2_stubs::kIopHeapBase,
                     "a second runtime in the same process must keep its own cursor at the heap base");

            first.resetStubRuntimeState();
            t.Equals(first.iopHeapRuntimeState().next, ps2_stubs::kIopHeapBase,
                     "resetStubRuntimeState (run() calls it) puts the cursor back at the heap base");

            setRegU32(ctx, 4, block);
            ps2_stubs::sceSifFreeIopHeap(nullptr, &ctx, &first);
            t.Equals(static_cast<int32_t>(getRegU32(&ctx, 2)), 0,
                     "and the block frees (the block map is SIF.cpp's own and not this test's subject)");
        });
    });
}
