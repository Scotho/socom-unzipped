# Sprint 9 Goal 1: what the runner (socom2) and the launcher both need, and nothing either of them owns.
# Plain C++20: no raylib, no GL, no ps2_runtime. The runner links this so that it never links the launcher;
# the launcher's tested core (ps2x_launcher_core) links it PUBLIC, so every existing
# #include "launcher/launcher_config.h" keeps resolving.
add_library(ps2x_shared STATIC
    src/iso9660.cpp
    src/sha256.cpp
    src/launcher_config.cpp
    src/preflight.cpp
    src/exe_dir.cpp
    src/bare_run.cpp
    src/zip_store.cpp
    src/diagnostics.cpp
)
target_include_directories(ps2x_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(ps2x_shared PUBLIC cxx_std_20)
# The Android runner is a SHARED library (ps2xRuntime/CMakeLists.txt:489); objects it absorbs must be PIC.
set_target_properties(ps2x_shared PROPERTIES POSITION_INDEPENDENT_CODE ON)
