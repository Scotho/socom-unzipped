cmake_minimum_required(VERSION 3.21)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE AND DEFINED ENV{VITASDK})
    set(PS2X_VITA_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake")
    if(EXISTS "${PS2X_VITA_TOOLCHAIN_FILE}")
        set(CMAKE_TOOLCHAIN_FILE "${PS2X_VITA_TOOLCHAIN_FILE}" CACHE PATH
            "Toolchain file used for cross-compiling" FORCE)
        message(STATUS "Using VitaSDK toolchain from VITASDK: ${CMAKE_TOOLCHAIN_FILE}")
    endif()
endif()

project(PS2RetroX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(PS2X_BUILD_RECOMP "Build ps2xRecomp" ON)
option(PS2X_BUILD_RUNTIME "Build ps2xRuntime" ON)
option(PS2X_BUILD_ANALYZER "Build ps2xAnalyzer" ON)
option(PS2X_BUILD_TEST "Build ps2xTest" ON)
# Sprint 11 Task 17 (R247): ps2xStudio (the upstream ImGui workbench) was deleted -- nobody here built it and it
# carried two fonts we do not ship. There is no PS2X_BUILD_STUDIO option any more.

# Sprint 9 Goal 2: the release configuration's link hygiene. OFF in the developer build (build.sh runtime,
# scripts/build_linux.sh runtime), which must not change; ON only from `build.sh release` /
# `scripts/build_linux.sh release`, in their own build trees. Declared here, before any add_subdirectory,
# so raylib and every library in the tree are compiled into sections too.
option(PS2X_RELEASE_LINK "Release link hygiene: function/data sections, --gc-sections, --as-needed on ELF" OFF)
set(PS2X_LINK_ICF "" CACHE STRING "Identical-code folding at link: empty (off), safe or all")
if(PS2X_RELEASE_LINK AND NOT MSVC)
    add_compile_options(-ffunction-sections -fdata-sections)
    add_link_options(-Wl,--gc-sections)
    if(UNIX AND NOT APPLE)
        # Link only what is called: the runner names libavformat and libswresample (pkg_check_modules) and
        # calls neither, and without this both become DT_NEEDED and drag their closure into the tarball's lib/.
        add_link_options(-Wl,--as-needed)
    endif()
endif()
if(PS2X_LINK_ICF AND NOT MSVC)
    if(UNIX AND NOT APPLE)
        add_link_options(-fuse-ld=lld)      # GNU ld has no --icf
    endif()
    add_link_options(-Wl,--icf=${PS2X_LINK_ICF})
endif()

if(ANDROID)
    message(STATUS "Android target detected, building runtime only")
    set(PS2X_BUILD_RECOMP OFF)
    set(PS2X_BUILD_ANALYZER OFF)
    set(PS2X_BUILD_TEST OFF)
endif()

set(PS2X_IS_ARM_TARGET OFF)
set(PS2X_IS_AARCH64_TARGET OFF)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm64|aarch64|ARM64")
    set(PS2X_IS_ARM_TARGET ON)
    set(PS2X_IS_AARCH64_TARGET ON)
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "^arm|^ARM")
    set(PS2X_IS_ARM_TARGET ON)
endif()

if((CMAKE_C_COMPILER MATCHES "arm-vita-eabi") OR
   (CMAKE_CXX_COMPILER MATCHES "arm-vita-eabi"))
    set(PS2X_IS_ARM_TARGET ON)
endif()

if(PS2X_IS_ARM_TARGET)
    message(STATUS "ARM target detected, fetching sse2neon")

    include(FetchContent)
    FetchContent_Declare(
        sse2neon
        GIT_REPOSITORY https://github.com/DLTcollab/sse2neon.git
        GIT_TAG 92f6de174717aef09033ad21568d5bb9e5470404 # v1.9.1
    )
    FetchContent_MakeAvailable(sse2neon)

    include_directories(${sse2neon_SOURCE_DIR})
    add_compile_definitions(USE_SSE2NEON)

    if(PS2X_IS_AARCH64_TARGET AND APPLE)
        # macOS ARM64 already uses optimal defaults
        message(STATUS "macOS ARM64 - using default compiler flags")
    elseif(PS2X_IS_AARCH64_TARGET AND MSVC)
        # Windows ARM64 - MSVC already uses optimal defaults
        message(STATUS "Windows ARM64 (MSVC) - using default compiler flags")
    elseif(PS2X_IS_AARCH64_TARGET)
        # Linux ARM64 - add NEON flags
        message(STATUS "Non-Apple ARM64 - adding NEON compiler flags")
        add_compile_options(-march=armv8-a+fp+simd)

        # Try to enable crypto and CRC extensions if supported
        include(CheckCXXCompilerFlag)
        check_cxx_compiler_flag("-march=armv8-a+fp+simd+crypto+crc" COMPILER_SUPPORTS_CRYPTO_CRC)
        if(COMPILER_SUPPORTS_CRYPTO_CRC)
            set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -march=armv8-a+fp+simd+crypto+crc")
            message(STATUS "Crypto and CRC extensions enabled")
        else()
            add_compile_options(-march=armv8-a+fp+simd)
        endif()
    endif()
endif()

if(PS2X_BUILD_RECOMP)
    add_subdirectory("ps2xRecomp")
endif()

# Sprint 9 Goal 1: shared by the runner and the launcher; depends on nothing in this tree.
add_subdirectory("ps2xShared")

if(PS2X_BUILD_RUNTIME)
    add_subdirectory("ps2xIOP")
    add_subdirectory("ps2xRuntime")
endif()

if(PS2X_BUILD_RUNTIME AND NOT PS2X_IS_VITA AND NOT PS2X_IS_ANDROID)
    add_subdirectory("ps2xLauncher")
endif()

if(PS2X_BUILD_ANALYZER)
    add_subdirectory("ps2xAnalyzer")
endif()

if(PS2X_BUILD_TEST)
    add_subdirectory("ps2xTest")
endif()
