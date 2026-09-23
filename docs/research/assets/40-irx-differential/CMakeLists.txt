cmake_minimum_required(VERSION 3.21)
project(irx_differential LANGUAGES CXX)

# PR #244's ps2xIOP (research/ps2recomp-244 is a worktree of the upstream clone at origin/main = 75d729c).
set(PS2XIOP_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../ps2recomp-244/ps2xIOP" CACHE PATH "PR #244 ps2xIOP source")
add_subdirectory(${PS2XIOP_DIR} ps2xiop)

add_executable(irx_differential harness.cpp)
target_compile_features(irx_differential PRIVATE cxx_std_20)
target_link_libraries(irx_differential PRIVATE ps2x::iop)
