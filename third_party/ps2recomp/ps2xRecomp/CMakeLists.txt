cmake_minimum_required(VERSION 3.20)

project(PS2Recomp VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

include(FetchContent)

FetchContent_Declare(
    elfio
    GIT_REPOSITORY https://github.com/serge1/ELFIO.git
    GIT_TAG 8ae6cec5d60495822ecd57d736f66149da9b1830 # Release_3.12
)
FetchContent_MakeAvailable(elfio)

FetchContent_Declare(
    toml11
    GIT_REPOSITORY https://github.com/ToruNiina/toml11.git
    GIT_TAG be08ba2be2a964edcdb3d3e3ea8d100abc26f286 # v4.4.0
)
FetchContent_MakeAvailable(toml11)

FetchContent_Declare(
    fmt
    GIT_REPOSITORY https://github.com/fmtlib/fmt.git
    GIT_TAG 407c905e45ad75fc29bf0f9bb7c5c2fd3475976f # 12.1.0
)
FetchContent_MakeAvailable(fmt)
 
FetchContent_Declare(
    libdwarf
    GIT_REPOSITORY https://github.com/davea42/libdwarf-code.git
    GIT_TAG 2e088b983562860f497b4fd789a3e61524eb857c # v2.2.0 (the annotated tag's commit)
)

set(BUILD_DWARFDUMP    OFF CACHE BOOL "" FORCE)
set(BUILD_DWARFEXAMPLE OFF CACHE BOOL "" FORCE)
set(BUILD_DWARFGEN     OFF CACHE BOOL "" FORCE)

set(BUILD_SHARED   OFF CACHE BOOL "" FORCE)
set(BUILD_NON_SHARED ON CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(libdwarf)

set(LIBDWARF_INCLUDE_DIR "${libdwarf_SOURCE_DIR}/src/lib/libdwarf")

FetchContent_Declare(
    rabbitizer
    GIT_REPOSITORY https://github.com/Decompollaborate/rabbitizer.git
    GIT_TAG d5804fa488474830a47fbf9f3693048ec1e45589 # 1.14.3
)
FetchContent_MakeAvailable(rabbitizer)

if (NOT TARGET rabbitizer)
    file(GLOB_RECURSE RABBITIZER_SOURCES CONFIGURE_DEPENDS
        "${rabbitizer_SOURCE_DIR}/src/analysis/*.c"
        "${rabbitizer_SOURCE_DIR}/src/common/*.c"
        "${rabbitizer_SOURCE_DIR}/src/instructions/*.c"
        "${rabbitizer_SOURCE_DIR}/src/instructions/*/*.c"
    )

    add_library(rabbitizer STATIC ${RABBITIZER_SOURCES})

    target_include_directories(rabbitizer PUBLIC
        "${rabbitizer_SOURCE_DIR}/include"
        "${rabbitizer_SOURCE_DIR}/tables"
        "${rabbitizer_SOURCE_DIR}/tables/tables"
    )
endif()

file(GLOB_RECURSE PS2RECOMP_LIB_SOURCES CONFIGURE_DEPENDS
    src/lib/*.cpp
)

file(GLOB_RECURSE PS2RECOMP_HEADERS CONFIGURE_DEPENDS
    include/*.h
    include/*.hpp
)

add_library(ps2_recomp_lib STATIC ${PS2RECOMP_LIB_SOURCES} ${PS2RECOMP_HEADERS})

target_compile_definitions(ps2_recomp_lib
PUBLIC
    LIBDWARF_STATIC
PRIVATE
    LIBDWARF_STATIC
)

target_include_directories(ps2_recomp_lib
PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${elfio_SOURCE_DIR}
    ${LIBDWARF_INCLUDE_DIR}

PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../ps2xRuntime/include
)

target_link_libraries(ps2_recomp_lib
PUBLIC
    fmt::fmt
    toml11::toml11 
    dwarf
    rabbitizer
)

file(GLOB_RECURSE PS2RECOMP_EXE_SOURCES CONFIGURE_DEPENDS
    src/runner/*.cpp
)

add_executable(ps2_recomp ${PS2RECOMP_EXE_SOURCES})

target_link_libraries(ps2_recomp
PRIVATE
    ps2_recomp_lib
)

install(TARGETS ps2_recomp ps2_recomp_lib
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

install(DIRECTORY include/
    DESTINATION include
)

include("${CMAKE_SOURCE_DIR}/ps2xRuntime/cmake/ReleaseMode.cmake")

if(CMAKE_BUILD_TYPE STREQUAL "Release" OR CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
    EnableFastReleaseMode(ps2_recomp_lib)
    EnableFastReleaseMode(ps2_recomp)
endif()
