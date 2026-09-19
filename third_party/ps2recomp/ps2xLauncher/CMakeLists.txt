# SOCOM Unzipped launcher (Task 8b): the window that owns the game's configuration and starts socom2.exe.
# ps2x_launcher_core holds the logic the tests cover (ISO 9660 lookup, SHA-256, config.json, the environment);
# the raylib window is socom_unzipped_launcher.
add_library(ps2x_launcher_core STATIC
    src/iso9660.cpp
    src/sha256.cpp
    src/launcher_config.cpp
)
target_include_directories(ps2x_launcher_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(ps2x_launcher_core PUBLIC cxx_std_20)

# The window. WIN32 keeps the console away; the runner's raylib target is available here (ps2xRuntime fetched it).
# Sprint 8 Task 1: the WIN32 keyword exists only on Windows, so it is passed through a variable that is empty
# elsewhere; the same win32glue interface is implemented by src/posix_glue.cpp on Unix.
if(WIN32)
    set(PS2X_LAUNCHER_EXE_TYPE WIN32)
else()
    set(PS2X_LAUNCHER_EXE_TYPE "")
endif()
add_executable(socom_unzipped_launcher ${PS2X_LAUNCHER_EXE_TYPE} src/main.cpp src/win32_glue.cpp src/mic_devices.cpp)
if(UNIX)
    target_sources(socom_unzipped_launcher PRIVATE src/posix_glue.cpp)
endif()
target_link_libraries(socom_unzipped_launcher PRIVATE ps2x_launcher_core raylib)
# Sprint 7 Task 9a: miniaudio ships inside raylib's own sources and is already compiled into libraylib
# (raudio.c:178), so mic_devices.cpp needs only its declarations: it includes the header WITHOUT
# MINIAUDIO_IMPLEMENTATION.
target_include_directories(socom_unzipped_launcher PRIVATE $<TARGET_PROPERTY:raylib,SOURCE_DIR>/external)
if(WIN32)
    target_link_libraries(socom_unzipped_launcher PRIVATE comdlg32 shell32)
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
