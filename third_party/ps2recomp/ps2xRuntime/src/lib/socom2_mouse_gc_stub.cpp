// Non-Apple builds: no GCMouse. socom2MouseFrame falls back to raylib's GetMouseDelta after 2 s.
#include "socom2_mouse.h"

namespace ps2_stubs
{
    bool socom2MouseGcStart(bool) { return false; }
    void socom2MouseGcReport() {}
}
