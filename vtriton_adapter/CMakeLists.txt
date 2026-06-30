# Phase-2D vTriton adapter bridge.
#
# The default target is a standalone strict bridge that consumes the same
# structural_edit_script.json used by the Python pipeline and implements two
# executable structural rewrites:
#   1. explicit barrier_ALL/PIPE_ALL -> directional set_flag/wait_flag
#   2. insert CV boundary sync before the first vector op after cube/fixpipe
#
# Production target: move this logic into the local vTriton/LLVM/MLIR checkout
# and replace the standalone text anchor bridge with HivmOpsEditor or MLIR
# PatternRewriter/RewriterBase operation-level mutation and HIVM dialect parser
# verification.
cmake_minimum_required(VERSION 3.16)
project(hivm_strategy_rewrite_phase2d CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(hivm-strategy-rewrite hivm_strategy_rewrite.cpp)
