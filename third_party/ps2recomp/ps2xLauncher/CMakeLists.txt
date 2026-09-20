# SOCOM Unzipped launcher (Task 8b): the window that owns the game's configuration and starts socom2.exe.
# ps2x_launcher_core holds the launcher's pure UI logic (focus, pad geometry); the ISO 9660 lookup, SHA-256,
# config.json and the environment live in ps2x_shared (Sprint 9 Goal 1), which it links PUBLIC.
# The raylib window is socom_unzipped_launcher.
# Sprint 8 Goal 9: src/ui/focus.cpp joins it -- the page layout, the focus model and the launch-blocked
# reasons are pure (no raylib), and launcher_tests.cpp asserts on the very rects the pages draw.
add_library(ps2x_launcher_core STATIC
    src/ui/focus.cpp
    src/ui/pad_geometry.cpp
    # Sprint 9 Goal 9 (P3): the pad-to-intent gate. Pure, and in the core so the tests can hold a stick
    # down for five simulated seconds and prove the launcher reads nothing while the game has the pad.
    src/ui/pad_input.cpp
)
target_include_directories(ps2x_launcher_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/src        # "ui/focus.h", "ui/theme.h", "ui/pad_render.h", "ui/glyphs.h"
)
target_compile_features(ps2x_launcher_core PUBLIC cxx_std_20)
# Sprint 9 Goal 1: iso9660, sha256 and launcher_config moved to ps2x_shared (the runner reads config.json too).
target_link_libraries(ps2x_launcher_core PUBLIC ps2x_shared)

# The window. WIN32 keeps the console away; the runner's raylib target is available here (ps2xRuntime fetched it).
# Sprint 8 Task 1: the WIN32 keyword exists only on Windows, so it is passed through a variable that is empty
# elsewhere; the same win32glue interface is implemented by src/posix_glue.cpp on Unix.
if(WIN32)
    set(PS2X_LAUNCHER_EXE_TYPE WIN32)
else()
    set(PS2X_LAUNCHER_EXE_TYPE "")
endif()
add_executable(socom_unzipped_launcher ${PS2X_LAUNCHER_EXE_TYPE}
    src/main.cpp
    src/win32_glue.cpp
    src/mic_devices.cpp
    # Sprint 8 Goal 9: the redesigned UI. focus.cpp is in ps2x_launcher_core above (it is pure and tested).
    src/ui/fonts.cpp
    src/ui/widgets.cpp
    src/ui/glyphs.cpp
    src/ui/pad_render.cpp
    src/ui/page_play.cpp
    src/ui/page_disc.cpp
    src/ui/page_video.cpp
    src/ui/page_audio.cpp
    src/ui/page_controller.cpp
    src/ui/page_microphone.cpp
    src/ui/page_online.cpp
    src/ui/page_report.cpp
    src/ui/page_about.cpp
)
if(UNIX)
    target_sources(socom_unzipped_launcher PRIVATE src/posix_glue.cpp)
endif()
target_link_libraries(socom_unzipped_launcher PRIVATE ps2x_launcher_core raylib)
# Sprint 7 Task 9a: miniaudio ships inside raylib's own sources and is already compiled into libraylib
# (raudio.c:178), so mic_devices.cpp needs only its declarations: it includes the header WITHOUT
# MINIAUDIO_IMPLEMENTATION.
target_include_directories(socom_unzipped_launcher PRIVATE $<TARGET_PROPERTY:raylib,SOURCE_DIR>/external)
if(WIN32)
    # winhttp: Sprint 9 Goal 8's bug report and status line (win32glue::httpRequest). Windows only -- the POSIX
    # glue starts curl instead, so the Linux build links nothing new.
    target_link_libraries(socom_unzipped_launcher PRIVATE comdlg32 shell32 winhttp)
endif()
if(UNIX AND NOT APPLE)
    # The portable folder keeps its non-system .so files in lib/ next to the binary.
    set_target_properties(socom_unzipped_launcher PROPERTIES
        BUILD_RPATH "\$ORIGIN/lib"
        INSTALL_RPATH "\$ORIGIN/lib"
    )
    # F5: DT_RPATH rather than the default DT_RUNPATH -- a RUNPATH is not inherited by this
    # binary's dependencies, so lib/*.so could not find each other on a host without them.
    target_link_options(socom_unzipped_launcher PRIVATE "-Wl,--disable-new-dtags")
endif()
target_compile_features(socom_unzipped_launcher PRIVATE cxx_std_20)
