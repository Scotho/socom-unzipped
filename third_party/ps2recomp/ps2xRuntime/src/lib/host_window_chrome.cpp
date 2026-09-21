// Sprint 10 Q4: the launcher's icon and palette on the game window's own chrome. raylib half; the dwmapi half is
// host_window_chrome_win32.cpp, because windows.h and raylib.h do not share a translation unit (CloseWindow,
// ShowCursor, Rectangle, DrawText collide -- the launcher keeps the same split in win32_glue.cpp).
#include "runtime/host_window_chrome.h"

#include "ps2x/app_icon_embedded.h"
#include "ps2x/host_window.h"

#include "raylib.h"

#include <iostream>

namespace ps2x_host
{
    // The Windows half (host_window_chrome_win32.cpp): true when the caption took the colours.
    bool colourWindowCaption(void *windowHandle, unsigned caption, unsigned text, unsigned border);

    void applyHostWindowChrome()
    {
        bool icon = false;
        Image image = LoadImageFromMemory(".png", kImage_SocomUnzippedIcon, kImage_SocomUnzippedIcon_len);
        if (image.data != nullptr)
        {
            // raylib's SetWindowIcon takes only R8G8B8A8; the embedded PNG is exported that way, and a build
            // that changes the artwork must keep it so (or this line converts it).
            if (image.format != PIXELFORMAT_UNCOMPRESSED_R8G8B8A8)
                ImageFormat(&image, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
            SetWindowIcon(image);
            UnloadImage(image);
            icon = true;
        }
        using namespace ps2x::host_window;
        const bool caption = colourWindowCaption(GetWindowHandle(), colorref(kCaption), colorref(kCaptionText), colorref(kBorder));
        std::cout << "[window] chrome: icon " << (icon ? "set" : "NOT set (the embedded PNG would not decode)")
                  << ", caption colours " << (caption ? "set" : "not on this system (Windows 11 only)") << std::endl;
    }
}
