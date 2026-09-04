// SOCOM II: U.S. Navy SEALs (SCUS_972.75, r0001) — game-specific EE overrides.
//
// The retail boot ELF is a loader that (1) looks for the r0004 update on the memory card,
// (2) otherwise loads OVERLAY/REL/DNAS.BIN and uses libdnas2 to decrypt RUN/RAW/APACHE00.ZDB
// into the FTSCore (0x1e7000) and ZSealEtc (0x4c5380) overlays, then (3) jumps to 0x4c53c0.
// Our recompiled image (game/overlays/socom2_game.elf) already contains both overlays in
// plaintext, so the loader's decrypt path is replaced by "success" and the memory-card
// update path by "not found".  See docs/research/05-code-package-and-harness.md.
#include "game_overrides.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"
#include "runtime/ee_scheduler.h"
#include <cstring>
#include <fstream>
#include <vector>

#include <cstdint>
#include <filesystem>
#include <iostream>

namespace
{
    inline void returnTo(R5900Context *ctx, uint32_t value)
    {
        SET_GPR_U32(ctx, 2, value);
        ctx->pc = GPR_U32(ctx, 31);
    }

    // The loader's crt0 zero-fills 0x1d5600..0x686f80 (its own bss, which spans the overlay
    // slots) *after* our ELF loader placed the overlays there.  Restore them from the ELF file.
    bool reloadOverlaySegments(uint8_t *rdram)
    {
        const auto elfPath = PS2Runtime::getIoPaths().elfPath;
        std::ifstream f(elfPath, std::ios::binary);
        if (!f)
            return false;
        std::vector<uint8_t> hdr(52);
        f.read(reinterpret_cast<char *>(hdr.data()), 52);
        uint32_t phoff, phnum;
        std::memcpy(&phoff, hdr.data() + 0x1c, 4);
        uint16_t phnum16;
        std::memcpy(&phnum16, hdr.data() + 0x2c, 2);
        phnum = phnum16;
        int restored = 0;
        for (uint32_t i = 0; i < phnum; ++i)
        {
            uint8_t ph[32];
            f.seekg(phoff + i * 32);
            f.read(reinterpret_cast<char *>(ph), 32);
            uint32_t type, off, vaddr, filesz, memsz;
            std::memcpy(&type, ph + 0, 4);
            std::memcpy(&off, ph + 4, 4);
            std::memcpy(&vaddr, ph + 8, 4);
            std::memcpy(&filesz, ph + 16, 4);
            std::memcpy(&memsz, ph + 20, 4);
            if (type != 1 || vaddr < 0x001e7000u || memsz == 0)
                continue;
            uint8_t *dst = getMemPtr(rdram, vaddr);
            if (!dst)
                continue;
            if (filesz)
            {
                f.seekg(off);
                f.read(reinterpret_cast<char *>(dst), filesz);
            }
            if (memsz > filesz)
                std::memset(dst + filesz, 0, memsz - filesz);
            ++restored;
        }
        std::cout << "[socom2] restored " << restored << " overlay segments from " << elfPath.filename().string() << std::endl;
        return restored > 0;
    }

    // FUN_001c59c0: load DNAS.BIN from disc, decrypt APACHE00.ZDB into both overlay slots and run
    // each overlay's static constructors (loader FUN_00182840(ctor_start, ctor_end, 0, 0)).
    // Here: restore the plaintext overlays and invoke the constructors as guest calls.
    void socom2_LoadGameCodeFromDisc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        std::cout << "[socom2] LoadGameCodeFromDisc -> restoring overlays, running static constructors" << std::endl;
        reloadOverlaySegments(rdram);

        struct Table { uint32_t begin, end; const char *name; };
        const Table tables[] = {{0x00404d10u, 0x00404f04u, "FTSCore"}, {0x006690e0u, 0x00669120u, "ZSealEtc"}};
        std::vector<GuestInvocation> invocations;
        for (const Table &t : tables)
        {
            int n = 0;
            for (uint32_t p = t.begin; p < t.end; p += 4)
            {
                uint32_t fn;
                std::memcpy(&fn, rdram + (p & PS2_RAM_MASK), 4);
                if (fn == 0 || !runtime->hasFunction(fn))
                {
                    if (fn) std::cout << "[socom2]   ctor " << std::hex << fn << std::dec << " has no recompiled body" << std::endl;
                    continue;
                }
                GuestInvocation inv{};
                inv.kind = GuestInvocationKind::HleCall;
                inv.context = *ctx;
                inv.context.pc = fn;
                SET_GPR_U32(&inv.context, 29, 0u);   // scheduler assigns an invocation stack
                SET_GPR_U32(&inv.context, 31, 0u);   // scheduler supplies the return trampoline
                invocations.push_back(std::move(inv));
                ++n;
            }
            std::cout << "[socom2]   " << t.name << ": " << n << " static constructors queued" << std::endl;
        }

        // resume state of the caller once the constructors have run
        returnTo(ctx, 1);
        if (invocations.empty())
            return;
        EeScheduler &scheduler = runtime->eeScheduler();
        scheduler.bindMainContextForSyscall(*ctx, rdram);
        scheduler.invokeCurrentSequence(std::move(invocations));
    }

    // FUN_001c5b30(port): load the r0004 update from the memory card.  0 = not present.
    void socom2_LoadGameCodeFromMemcard(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        std::cout << "[socom2] LoadGameCodeFromMemcard -> none" << std::endl;
        returnTo(ctx, 0);
    }

    // FUN_00181c90(path, dest): load an MWo3 overlay file (only used for DNAS.BIN).
    void socom2_LoadOverlayFile(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        std::cout << "[socom2] LoadOverlayFile(" << std::hex << GPR_U32(ctx, 4) << ", "
                  << GPR_U32(ctx, 5) << std::dec << ") -> stubbed" << std::endl;
        returnTo(ctx, 1);
    }

    // The engine reads the ISO9660 volume descriptor / directory records itself (sector 16...)
    // and then reads files by LBN, so the disc must be available as a raw image.  Look for an
    // .iso next to the ELF or one directory up; otherwise honour PS2X_CD_IMAGE.
    void configureCdImage()
    {
        PS2Runtime::IoPaths paths = PS2Runtime::getIoPaths();
        if (!paths.cdImage.empty())
            return;
        if (const char *env = std::getenv("PS2X_CD_IMAGE"); env && *env)
        {
            paths.cdImage = env;
        }
        else
        {
            std::error_code ec;
            for (const auto &dir : {paths.elfDirectory, paths.elfDirectory.parent_path()})
            {
                for (const auto &e : std::filesystem::directory_iterator(dir, ec))
                {
                    auto ext = e.path().extension().string();
                    for (auto &c : ext) c = static_cast<char>(std::tolower(c));
                    if (ext == ".iso") { paths.cdImage = e.path(); break; }
                }
                if (!paths.cdImage.empty()) break;
            }
        }
        if (paths.cdImage.empty())
        {
            std::cout << "[socom2] WARNING: no .iso found; raw sector reads will fail" << std::endl;
            return;
        }
        std::cout << "[socom2] CD image: " << paths.cdImage.string() << std::endl;
        PS2Runtime::setIoPaths(paths);
    }

    void applySocom2(PS2Runtime &runtime)
    {
        std::cout << "[socom2] applying SOCOM II overrides" << std::endl;
        {
            // sanity check that the FTSCore data segment is resident: should print the boot path string
            const uint8_t *p = getConstMemPtr(runtime.memory().getRDRAM(), 0x003e5c60u);
            std::string s;
            for (int i = 0; p && i < 24 && p[i]; ++i) s.push_back(static_cast<char>(p[i]));
            std::cout << "[socom2] mem@0x3e5c60 = \"" << s << "\"" << std::endl;
        }
        configureCdImage();
        runtime.replaceFunction(0x001c59c0u, socom2_LoadGameCodeFromDisc);
        runtime.replaceFunction(0x001c5b30u, socom2_LoadGameCodeFromMemcard);
        runtime.replaceFunction(0x00181c90u, socom2_LoadOverlayFile);
        // _InitSys kernel-patch search (FindAddress loop over the BIOS): nothing to find here.
        ps2_game_overrides::bindAddressHandler(runtime, 0x001ac9d8u, "ret0");
    }
}

PS2_REGISTER_GAME_OVERRIDE("socom2-us", "socom2_game.elf", 0x00180008u, 0u, applySocom2)
