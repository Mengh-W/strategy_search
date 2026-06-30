cmake_minimum_required(VERSION 3.16)
project(vtriton_a1_microbench)
include(GNUInstallDirs)

set(RUN_MODE "npu" CACHE STRING "cpu/sim/npu")
set(SOC_VERSION "Ascend910B1" CACHE STRING "system on chip type")
set(ASCEND_CANN_PACKAGE_PATH "/usr/local/Ascend/ascend-toolkit/8.2.RC1.alpha003"
    CACHE STRING "ASCEND CANN package installation directory"
)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type Release/Debug" FORCE)
endif()
if(CMAKE_INSTALL_PREFIX STREQUAL /usr/local)
    set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_LIST_DIR}/out" CACHE STRING "path for install()" FORCE)
endif()

file(GLOB CCE_KERNEL_FILES ${CMAKE_CURRENT_SOURCE_DIR}/*.cce)
set(GENERATED_KERNEL_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated_kernels)
file(MAKE_DIRECTORY ${GENERATED_KERNEL_DIR})
configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/vt_microbench_common.h
    ${GENERATED_KERNEL_DIR}/vt_microbench_common.h
    COPYONLY
)
foreach(CCE_KERNEL_FILE ${CCE_KERNEL_FILES})
    get_filename_component(KERNEL_STEM ${CCE_KERNEL_FILE} NAME_WE)
    set(GENERATED_KERNEL_FILE ${GENERATED_KERNEL_DIR}/${KERNEL_STEM}.cpp)
    configure_file(${CCE_KERNEL_FILE} ${GENERATED_KERNEL_FILE} COPYONLY)
    list(APPEND KERNEL_FILES ${GENERATED_KERNEL_FILE})
endforeach()

if(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/aarch64-linux/tikcpp/ascendc_kernel_cmake)
    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/aarch64-linux/tikcpp/ascendc_kernel_cmake)
elseif(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/x86_64-linux/tikcpp/ascendc_kernel_cmake)
    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/x86_64-linux/tikcpp/ascendc_kernel_cmake)
elseif(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/tools/tikcpp/ascendc_kernel_cmake)
    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/tools/tikcpp/ascendc_kernel_cmake)
elseif(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/compiler/tikcpp/ascendc_kernel_cmake)
    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/compiler/tikcpp/ascendc_kernel_cmake)
else()
    message(FATAL_ERROR "ascendc_kernel_cmake does not exist")
endif()
include(${ASCENDC_CMAKE_DIR}/ascendc.cmake)

ascendc_library(ascendc_kernels_${RUN_MODE} SHARED ${KERNEL_FILES})

add_executable(vt_a1_bench_launcher ${CMAKE_CURRENT_SOURCE_DIR}/bench_launcher.cpp)
set_target_properties(vt_a1_bench_launcher PROPERTIES
    BUILD_RPATH "$ORIGIN/lib;$ORIGIN/lib64"
    INSTALL_RPATH "$ORIGIN/../lib64;$ORIGIN/../lib"
)

target_compile_options(vt_a1_bench_launcher PRIVATE
    -O2 -std=c++17 -D_GLIBCXX_USE_CXX11_ABI=0 -Wall -Werror
)

set(ASCEND_RUNTIME_LIB_DIRS
    ${ASCEND_CANN_PACKAGE_PATH}/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/fwkacllib/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/runtime/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/compiler/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/atc/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/aarch64-linux/lib64
)

target_link_directories(vt_a1_bench_launcher PRIVATE ${ASCEND_RUNTIME_LIB_DIRS})
foreach(ASCEND_RUNTIME_LIB_DIR ${ASCEND_RUNTIME_LIB_DIRS})
    target_link_options(vt_a1_bench_launcher PRIVATE
        "LINKER:-rpath-link,${ASCEND_RUNTIME_LIB_DIR}"
    )
endforeach()

target_link_libraries(vt_a1_bench_launcher PRIVATE
    $<BUILD_INTERFACE:$<$<OR:$<STREQUAL:${RUN_MODE},npu>,$<STREQUAL:${RUN_MODE},sim>>:host_intf_pub>>
    ascendc_kernels_${RUN_MODE}
    ascendcl
    ascendcl_impl
    tiling_api
    register
    platform
    ascendalog
    ascend_protobuf
    ge_common
    ge_common_base
    ge_executor
    davinci_executor
    hybrid_executor
    gert
    runtime
    runtime_common
    dl
)

install(TARGETS vt_a1_bench_launcher
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
