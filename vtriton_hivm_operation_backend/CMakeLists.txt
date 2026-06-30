# Phase-6E generated vTriton HivmOpsEditor-backed backend adapter.
# Intended location: <vTriton>/tools/hivm-operation-backend.
# This follows the existing vTriton tools/CMakeLists.txt pattern for hivm-crud.

if(NOT TRITONSIM_HAS_BISHENGIR_HIVM)
  message(WARNING "hivm-operation-backend requires TRITONSIM_HAS_BISHENGIR_HIVM; target will not be built")
  return()
endif()

add_llvm_executable(hivm-operation-backend
  hivm_operation_backend.cpp
)

target_link_libraries(hivm-operation-backend
  PRIVATE
  AscendModelTransforms
  AscendModelIR
  ${TRITONSIM_BISHENGIR_HIVM_LIBS}
  MLIRIR
  MLIRParser
  MLIRSupport
  MLIRFuncDialect
  MLIRSCFDialect
  MLIRArithDialect
  MLIRMemRefDialect
  MLIRTensorDialect
  MLIRBufferizationDialect
  LLVMSupport
)

target_include_directories(hivm-operation-backend
  PRIVATE
  ${PROJECT_SOURCE_DIR}/include
  ${PROJECT_BINARY_DIR}/include
  ${TRITONSIM_BISHENGIR_INCLUDE_DIRS}
)

mlir_check_all_link_libraries(hivm-operation-backend)
install(TARGETS hivm-operation-backend RUNTIME DESTINATION bin)
