// Sprint 10 Q4: the caption's colours on Windows 11 (DwmSetWindowAttribute's DWMWA_CAPTION_COLOR / _TEXT_COLOR /
// _BORDER_COLOR, build 22000 and later). dwmapi.dll is loaded by hand: no new link line for the runner, and a
// Windows 10 that lacks the attributes answers E_INVALIDARG, which reads as "not set". Elsewhere: false.
#include <cstdint>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace ps2x_host
{
    bool colourWindowCaption(void *windowHandle, unsigned caption, unsigned text, unsigned border)
    {
#ifdef _WIN32
        HWND window = static_cast<HWND>(windowHandle);
        if (window == nullptr)
            return false;
        HMODULE dwm = LoadLibraryW(L"dwmapi.dll");
        if (dwm == nullptr)
            return false;
        using SetAttrFn = HRESULT(WINAPI *)(HWND, DWORD, LPCVOID, DWORD);
        auto setAttr = reinterpret_cast<SetAttrFn>(reinterpret_cast<void *>(GetProcAddress(dwm, "DwmSetWindowAttribute")));
        if (setAttr == nullptr)
        {
            FreeLibrary(dwm);
            return false;
        }
        constexpr DWORD kBorderColor = 34, kCaptionColor = 35, kTextColor = 36;   // DWMWA_*_COLOR (Windows 11)
        const COLORREF captionRef = caption, textRef = text, borderRef = border;
        const bool ok = SUCCEEDED(setAttr(window, kCaptionColor, &captionRef, sizeof(captionRef)));
        if (ok)
        {
            setAttr(window, kTextColor, &textRef, sizeof(textRef));
            setAttr(window, kBorderColor, &borderRef, sizeof(borderRef));
        }
        // The module stays loaded: dwmapi is a system DLL the process would map anyway, and freeing it under
        // a compositor callback is not worth the saving.
        return ok;
#else
        (void)windowHandle;
        (void)caption;
        (void)text;
        (void)border;
        return false;
#endif
    }
}
