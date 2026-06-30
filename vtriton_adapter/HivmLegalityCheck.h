#pragma once
#include <string>

// Target legality checks for the production vTriton/HivmOpsEditor backend.
// These are declarations by design: they document what must be proven before
// applying each edit.  Python Phase-2B only performs local prechecks.
struct HivmLegalityResult {
  bool passed = false;
  std::string reason;
};

class HivmLegalityCheck {
public:
  // Production signatures should take MLIR Operation* / Value / Region anchors.
  HivmLegalityResult canReplaceBarrierAllWithDirectionalSync(void *barrierOp);
  HivmLegalityResult canInsertCvBoundarySync(void *producerOp, void *consumerOp);
  HivmLegalityResult canHoistLoopInvariantLoad(void *loopOp, void *loadOp, void *convertOp);
  HivmLegalityResult canRemoveRedundantGmRoundtrip(void *loadOp, void *storeOp);
};
