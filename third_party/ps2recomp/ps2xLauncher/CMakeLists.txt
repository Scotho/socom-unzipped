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
add_executable(socom_unzipped_launcher WIN32 src/main.cpp src/win32_glue.cpp)
target_link_libraries(socom_unzipped_launcher PRIVATE ps2x_launcher_core raylib)
if(WIN32)
    target_link_libraries(socom_unzipped_launcher PRIVATE comdlg32 shell32)
endif()
target_compile_features(socom_unzipped_launcher PRIVATE cxx_std_20)
