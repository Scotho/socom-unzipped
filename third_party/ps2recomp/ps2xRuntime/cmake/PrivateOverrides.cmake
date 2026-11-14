# Sprint 19 task E1 (research/89 Q2): PS2X_PRIVATE_OVERRIDES_DIR, function bodies kept out of the public tree.
#
# A rewritten function body is decompiled game code, so it never lives in this repository (R355). It lives in a
# directory of its own, outside the tree, and this hook adds every *.cpp there to the runner. Such a file registers
# itself the way game_overrides_socom2.cpp does (PS2_REGISTER_GAME_OVERRIDE, a static object), so it must be
# compiled into the executable: in the static library ps2_runtime the linker would drop the unreferenced object
# and its registration with it. Hence ps2EntryRunner, and only it.
#
# Set it with -DPS2X_PRIVATE_OVERRIDES_DIR=<dir> and nothing else: the environment is never read here (R375 review),
# so a cached value cannot be beaten or dropped by a shell's variable unseen. The runtime steps of build.sh,
# scripts/build_linux.sh and scripts/build_macos.sh pass the environment variable of that name as the -D (unset
# clears it); every release step refuses a set one. Unset or empty: nothing is added and nothing changes.
# A directory that does not exist, holds no .cpp file, or lies inside this repository or a linked worktree of it
# (the same git common dir; a separate clone has its own and is not caught) is a configure error.
# The files are kept out of the unity batches, so one file's statics never meet another's.

set(PS2X_PRIVATE_OVERRIDES_DIR "" CACHE PATH
    "Directory outside the repository whose *.cpp files join ps2EntryRunner (private function overrides); empty = none")

# The git common dir of <dir>, REALPATH-normalised (lower case on Windows), in <out>; empty when <dir> is in no
# repository or git is absent. GIT_DIR and friends are cleared: inside a git hook they would answer for every path.
function(_ps2x_git_common_dir dir out)
    set(${out} "" PARENT_SCOPE)
    find_program(PS2X_GIT_EXECUTABLE git)
    if(NOT PS2X_GIT_EXECUTABLE)
        return()
    endif()
    execute_process(COMMAND "${CMAKE_COMMAND}" -E env --unset=GIT_DIR --unset=GIT_WORK_TREE --unset=GIT_COMMON_DIR
                            --unset=GIT_INDEX_FILE "${PS2X_GIT_EXECUTABLE}" -C "${dir}" rev-parse --git-common-dir
                    RESULT_VARIABLE rc OUTPUT_VARIABLE common OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    if(NOT rc EQUAL 0 OR common STREQUAL "")
        return()
    endif()
    get_filename_component(common "${common}" REALPATH BASE_DIR "${dir}")   # it may be relative to <dir>
    if(WIN32)
        string(TOLOWER "${common}" common)
    endif()
    set(${out} "${common}" PARENT_SCOPE)
endfunction()

function(ps2x_add_private_overrides target)
    set(dir "${PS2X_PRIVATE_OVERRIDES_DIR}")
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
    _ps2x_git_common_dir("${repo}" repo_common)
    _ps2x_git_common_dir("${dir}" dir_common)
    if(NOT repo_common STREQUAL "" AND repo_common STREQUAL dir_common)
        message(FATAL_ERROR "PS2X_PRIVATE_OVERRIDES_DIR='${dir}' is inside a checkout of the public repository "
                            "(git common dir ${repo_common}): function bodies stay outside the repository")
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
