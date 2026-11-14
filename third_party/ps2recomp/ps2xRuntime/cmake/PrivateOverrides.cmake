# Sprint 19 task E1 (research/89 Q2): PS2X_PRIVATE_OVERRIDES_DIR, function bodies kept out of the public tree.
#
# A rewritten function body is decompiled game code, so it never lives in this repository (R355). It lives in a
# directory of its own, outside the tree, and this hook adds every *.cpp there to the runner. Such a file registers
# itself the way game_overrides_socom2.cpp does (PS2_REGISTER_GAME_OVERRIDE, a static object), so it must be
# compiled into the executable: in the static library ps2_runtime the linker would drop the unreferenced object
# and its registration with it. Hence ps2EntryRunner, and only it.
#
# Set it with -DPS2X_PRIVATE_OVERRIDES_DIR=<dir>, or with the environment variable of the same name at configure
# time (scripts/build_linux.sh passes no -D of its own). Unset or empty: nothing is added and nothing changes.
# A directory that does not exist, holds no .cpp file, or lies inside this repository is a configure error.
# The files are kept out of the unity batches, so one file's statics never meet another's.

set(PS2X_PRIVATE_OVERRIDES_DIR "" CACHE PATH
    "Directory outside the repository whose *.cpp files join ps2EntryRunner (private function overrides); empty = none")

function(ps2x_add_private_overrides target)
    set(dir "${PS2X_PRIVATE_OVERRIDES_DIR}")
    if(dir STREQUAL "" AND DEFINED ENV{PS2X_PRIVATE_OVERRIDES_DIR})
        set(dir "$ENV{PS2X_PRIVATE_OVERRIDES_DIR}")
    endif()
    if(dir STREQUAL "")
        return()
    endif()
    get_filename_component(dir "${dir}" REALPATH)
    if(NOT IS_DIRECTORY "${dir}")
        message(FATAL_ERROR "PS2X_PRIVATE_OVERRIDES_DIR='${dir}' is not a directory")
    endif()
    # This file is <repo>/third_party/ps2recomp/ps2xRuntime/cmake/PrivateOverrides.cmake.
    get_filename_component(repo "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../../.." REALPATH)
    string(FIND "${dir}/" "${repo}/" inside)
    if(inside EQUAL 0)
        message(FATAL_ERROR "PS2X_PRIVATE_OVERRIDES_DIR='${dir}' is inside the public tree (${repo}): "
                            "function bodies stay outside the repository")
    endif()
    file(GLOB sources CONFIGURE_DEPENDS "${dir}/*.cpp")
    if(NOT sources)
        message(FATAL_ERROR "PS2X_PRIVATE_OVERRIDES_DIR='${dir}' holds no .cpp file")
    endif()
    list(SORT sources)
    target_sources(${target} PRIVATE ${sources})
    set_source_files_properties(${sources} PROPERTIES SKIP_UNITY_BUILD_INCLUSION TRUE)
    list(LENGTH sources count)
    message(STATUS "PS2X_PRIVATE_OVERRIDES_DIR: ${count} source(s) from ${dir} added to ${target}")
endfunction()
