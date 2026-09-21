// Sprint 10 Goal 9 (research/38): the on-screen keyboard prefill -- the pure half.
//
// The game's login screen opens its two keyboards through the UI action "GetTextInput", whose one C++ handler
// is FUN_0038d770(msg, ctx). `msg` is the action's parsed 0xAC-byte argument block; the handler hands the
// keyboard a fixed initial-text buffer at 0x49ec70 that nothing in the game ever writes, which is why every
// keyboard opens empty. The runtime wraps that handler (game_overrides_socom2.cpp, installOskPrefill): it reads
// the block, decides which field this keyboard edits, and writes the buffer's whole image BEFORE the original
// runs -- the launcher's string for a login field, zeros for any other keyboard -- so the keyboard opens already
// typed with the cursor at the end and ENTER applies it exactly as typed text (R180: prefilled, never
// submitted). Nothing is written after the original: a recompiled guest call can leave through an EE scheduler
// checkpoint and resume later (the third driven login: `[ret-unwound] OskActivate pc=0x3766a0`), so host code
// placed after the call runs before the game has finished with the buffer -- the first version blanked it
// there and every keyboard opened empty. The buffer is read by this handler alone, so what one open leaves is
// simply overwritten by the next. Everything decidable on plain values is decided here, so the suite can say
// what the game will be handed without a launch.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

namespace socom2_osk
{
    // The handler and the buffer (guest addresses, r0001 FTSCore; research/38's table).
    constexpr uint32_t kOskOpenAddr = 0x0038D770u;        // FUN_0038d770: the GetTextInput action handler
    // The UI action table does not point at the handler: it points at a one-instruction thunk (0x2808d0,
    // `j func_38D770`) that the recompiler emits as a DIRECT C++ call, so a replacement at the handler's own
    // address is never reached from the table. The first two driven logins proved it (prefill armed, 0 of 5 in
    // the field): the wrap is installed at every entry the game dispatches through.
    constexpr uint32_t kOskOpenThunkAddr = 0x002808D0u;   // thunk_FUN_0038d770: what the action table calls
    constexpr uint32_t kOskOpenEntries[] = {kOskOpenThunkAddr, kOskOpenAddr};
    constexpr uint32_t kOskTextBufferAddr = 0x0049EC70u;  // the keyboard's initial text, bss, never written by the game
    constexpr std::size_t kOskTextBufferBytes = 0x48;     // room to the next global the game writes (0x49ecb8)

    // The argument block FUN_00395f40 builds from the script's parameters.
    constexpr std::size_t kArgBlockBytes = 0xAC;
    constexpr std::size_t kArgPurposeOffset = 0x10;       // char[0x40]: the Purpose message key, copied verbatim
    constexpr std::size_t kArgPurposeBytes = 0x40;
    constexpr std::size_t kArgSkbNameOffset = 0x58;       // char[0x20]: SkbName, the keyboard spec to use
    constexpr std::size_t kArgSkbNameBytes = 0x20;
    constexpr std::size_t kArgMaxBytesOffset = 0x98;      // int32 MaxBytes (0 = unlimited)
    constexpr std::size_t kArgMaxCharsOffset = 0x9C;      // int32 MaxChars (0 = unlimited)

    // What tells the two login keyboards apart (the UiVar id at +0x8 is a per-screen index and cannot).
    constexpr const char *kPersonaNamePurpose = "_455_EnterPlayerName_MSG";   // "Enter Player Name"
    constexpr const char *kPasswordPurpose = "_604_EnterPassword_MSG";        // "Enter Player Password"
    constexpr const char *kLoginKeyboard = "CREATEPLAYERNAME";                // both login keyboards; the LAN name uses MPPLAYERNAME

    enum class Field { PersonaName, Password, Other };

    inline Field fieldFor(const char *purpose, const char *skbName)
    {
        if (purpose == nullptr || skbName == nullptr || std::strcmp(skbName, kLoginKeyboard) != 0)
            return Field::Other;
        if (std::strcmp(purpose, kPersonaNamePurpose) == 0)
            return Field::PersonaName;
        if (std::strcmp(purpose, kPasswordPurpose) == 0)
            return Field::Password;
        return Field::Other;
    }

    // For the log line: which field, by name (the text itself is never logged).
    inline const char *fieldLabel(Field field)
    {
        if (field == Field::PersonaName)
            return "persona name";
        if (field == Field::Password)
            return "the password";
        return "another field";
    }

    struct Request
    {
        std::string purpose;
        std::string skbName;
        int32_t maxBytes = 0;
        int32_t maxChars = 0;
        Field field = Field::Other;
    };

    // The four fields the override reads, and nothing else. A string field is cut at its own width: a block
    // with no terminator (corrupt, or not a GetTextInput block at all) is never read past it.
    inline Request readRequest(const uint8_t *block)
    {
        Request r;
        if (block == nullptr)
            return r;
        auto field = [&](std::size_t offset, std::size_t width) {
            const char *p = reinterpret_cast<const char *>(block + offset);
            std::size_t n = 0;
            while (n < width && p[n] != '\0')
                ++n;
            return std::string(p, n);
        };
        r.purpose = field(kArgPurposeOffset, kArgPurposeBytes);
        r.skbName = field(kArgSkbNameOffset, kArgSkbNameBytes);
        std::memcpy(&r.maxBytes, block + kArgMaxBytesOffset, sizeof(r.maxBytes));
        std::memcpy(&r.maxChars, block + kArgMaxCharsOffset, sizeof(r.maxChars));
        r.field = fieldFor(r.purpose.c_str(), r.skbName.c_str());
        return r;
    }

    // The tightest of the live MaxChars and MaxBytes (0 or a garbage negative = unlimited) and the buffer's own
    // room less its terminator. The strings are ASCII, so characters are bytes.
    inline std::size_t capFor(int32_t maxChars, int32_t maxBytes, std::size_t bufferBytes)
    {
        std::size_t cap = bufferBytes > 0 ? bufferBytes - 1 : 0;
        if (maxChars > 0 && static_cast<std::size_t>(maxChars) < cap)
            cap = static_cast<std::size_t>(maxChars);
        if (maxBytes > 0 && static_cast<std::size_t>(maxBytes) < cap)
            cap = static_cast<std::size_t>(maxBytes);
        return cap;
    }

    // The string the keyboard opens with: the field's own variable, cut to what its buffer holds (cap counts
    // characters, the terminator is the buffer's own). Empty means "write nothing": the keyboard opens as the
    // console's does. Pure; the wrapper reads the environment and calls this.
    inline std::string prefillFor(Field field, const char *nameEnv, const char *passEnv, std::size_t cap)
    {
        const char *src = field == Field::PersonaName ? nameEnv : (field == Field::Password ? passEnv : nullptr);
        if (src == nullptr || *src == '\0' || cap == 0)
            return std::string();
        std::string out(src);
        if (out.size() > cap)
            out.resize(cap);
        return out;
    }

    // The buffer's image for this open: the text (cut to what the buffer holds with its terminator) followed
    // by zeros to the buffer's end, so nothing of the previous open survives; an empty text is all zeros.
    // Written before the original runs and never touched after it (see the header comment).
    inline void writeBuffer(uint8_t *buf, std::size_t bufferBytes, const std::string &text)
    {
        if (buf == nullptr || bufferBytes == 0)
            return;
        const std::size_t n = text.size() < bufferBytes - 1 ? text.size() : bufferBytes - 1;
        if (n > 0)
            std::memcpy(buf, text.data(), n);
        std::memset(buf + n, 0, bufferBytes - n);
    }
}
