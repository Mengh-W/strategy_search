#pragma once
#include <string>
#include <vector>

// Minimal C++ contract mirror for structural_edit_script.json.
// Production integration should replace this with a real JSON parser such as
// llvm::json or nlohmann::json, depending on the local vTriton build policy.
struct HivmStrategyEdit {
  std::string type;
  bool enabled = false;
  int maxEdits = 0;
  std::vector<std::string> requiredGates;
  std::vector<std::string> mutationKinds;
};

struct HivmStrategyEditScript {
  std::string schemaVersion;
  std::string rewriteSafety;
  std::vector<HivmStrategyEdit> edits;
};
