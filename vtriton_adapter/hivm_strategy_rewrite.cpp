// V3.3.2 Phase-2G: vTriton-style HIVM strategy rewrite bridge.
//
// Purpose
// -------
// This standalone C++ bridge consumes structural_edit_script.json and emits
// optimized.structural.hivm.mlir.  It is an executable engineering boundary
// between the Python strategy searcher and a future vTriton/HivmOpsEditor or
// MLIR PatternRewriter pass.
//
// Phase-2G supported strict edits:
//   1) replace_barrier_all_with_directional_sync
//      Replace explicit PIPE_ALL / barrier_ALL anchors with directional
//      set_flag + wait_flag pairs.
//   2) insert_sync_before_first_vector_op
//      Insert a minimal CV boundary set_flag + wait_flag before vector-stage
//      ops after a cube/fixpipe anchor.
//   3) remove_redundant_gm_roundtrip
//      Detection/precheck only in this standalone bridge; deletion remains
//      deferred until a target MLIR/vTriton alias/dependency checker proves it.
//
// Official MLIR direction followed by the design
// ----------------------------------------------
// MLIR's PatternRewriter/RewriterBase guidance is that real IR mutations in
// rewrite patterns should be coordinated through the rewriter because rewrite
// drivers may track state invalidated by mutation.  Dialect Conversion likewise
// uses an explicit legality model before converting illegal ops.  Therefore this
// standalone bridge remains a STRICT BRIDGE, not the final compiler pass:
//   * it only mutates explicit text anchors with a local legality contract;
//   * it reports every mutation and skipped reason;
//   * the production target remains vTriton/HivmOpsEditor or an MLIR pass using
//     PatternRewriter/RewriterBase and target HIVM dialect verification.
//
// Target CLI:
//   hivm-strategy-rewrite \
//     --input original.hivm.mlir \
//     --edit-script structural_edit_script.json \
//     --output optimized.structural.hivm.mlir \
//     --report structural_rewrite_report.json

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <map>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Change {
  std::string type;
  int line = 0;
  std::string before;
  std::vector<std::string> after;
};

struct RewriteSummary {
  bool success = false;
  bool mutated = false;
  int applied = 0;
  std::vector<Change> changes;
  std::vector<std::string> skipped;
  std::string reason;
  std::map<std::string, int> requestedMaxEditsByType;
  std::map<std::string, int> appliedByType;
};

static bool readFile(const std::string &path, std::string &out) {
  std::ifstream is(path);
  if (!is.good()) return false;
  std::ostringstream ss;
  ss << is.rdbuf();
  out = ss.str();
  return true;
}

static bool writeFile(const std::string &path, const std::string &text) {
  std::ofstream os(path);
  if (!os.good()) return false;
  os << text;
  return os.good();
}

static std::string jsonEscape(const std::string &s) {
  std::string out;
  for (char c : s) {
    switch (c) {
      case '\\': out += "\\\\"; break;
      case '"': out += "\\\""; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) out += " ";
        else out += c;
    }
  }
  return out;
}

static std::vector<std::string> splitLines(const std::string &text) {
  std::vector<std::string> lines;
  std::string cur;
  std::istringstream is(text);
  while (std::getline(is, cur)) lines.push_back(cur);
  return lines;
}

static std::string joinLines(const std::vector<std::string> &lines, bool trailingNewline) {
  std::ostringstream os;
  for (size_t i = 0; i < lines.size(); ++i) {
    if (i) os << '\n';
    os << lines[i];
  }
  if (trailingNewline) os << '\n';
  return os.str();
}

static std::string indentOf(const std::string &line) {
  size_t i = 0;
  while (i < line.size() && std::isspace(static_cast<unsigned char>(line[i]))) ++i;
  return line.substr(0, i);
}

static std::string stripped(const std::string &line) {
  size_t i = line.find_first_not_of(" \t");
  if (i == std::string::npos) return line;
  return line.substr(i);
}

static bool containsBarrierAllAnchor(const std::string &line) {
  return line.find("hivm.hir.barrier") != std::string::npos &&
         line.find("mode") != std::string::npos &&
         line.find("ALL") != std::string::npos;
}

static bool containsPipeAllAnchor(const std::string &line) {
  return line.find("hivm.hir.pipe_barrier[<PIPE_ALL>]") != std::string::npos ||
         line.find("hivm.pipe_barrier[<PIPE_ALL>]") != std::string::npos;
}

static bool isCubeOrFixpipeOp(const std::string &line) {
  return line.find("hivm.hir.mmad") != std::string::npos ||
         line.find("hivm.hir.mmadL1") != std::string::npos ||
         line.find("hivm.hir.fixpipe") != std::string::npos;
}

static bool isVectorOp(const std::string &line) {
  if (line.find("hivm.hir.v") != std::string::npos) return true;
  return line.find("hivm.hir.cast") != std::string::npos ||
         line.find("hivm.hir.exp") != std::string::npos ||
         line.find("hivm.hir.reduce") != std::string::npos;
}

static bool isSetOrWait(const std::string &line) {
  return line.find("hivm.hir.set_flag[") != std::string::npos ||
         line.find("hivm.hir.wait_flag[") != std::string::npos ||
         line.find("hivm.set_flag[") != std::string::npos ||
         line.find("hivm.wait_flag[") != std::string::npos;
}


static std::vector<std::string> extractMemrefVarsWithSpace(const std::string &line,
                                                           const std::string &section,
                                                           const std::string &space) {
  std::vector<std::string> vars;
  size_t sec = line.find(section + "(");
  if (sec == std::string::npos) return vars;
  size_t begin = sec + section.size() + 1;
  size_t end = line.find(")", begin);
  if (end == std::string::npos || end <= begin) return vars;
  std::string body = line.substr(begin, end - begin);
  std::regex item("(%[A-Za-z0-9_.$-]+)\\s*:\\s*memref<[^>]*#hivm\\.address_space<" + space + ">");
  for (std::sregex_iterator it(body.begin(), body.end(), item), e; it != e; ++it) {
    vars.push_back((*it)[1].str());
  }
  return vars;
}

static bool isHivmLoad(const std::string &line) {
  return line.find("hivm.hir.load") != std::string::npos || line.find("hivm.load") != std::string::npos;
}

static bool isHivmStore(const std::string &line) {
  return line.find("hivm.hir.store") != std::string::npos || line.find("hivm.store") != std::string::npos;
}

static bool isComputeLike(const std::string &line) {
  return isCubeOrFixpipeOp(line) || isVectorOp(line) || isHivmStore(line);
}

static std::vector<std::pair<int, int>> findGmRoundtripCandidates(const std::vector<std::string> &lines,
                                                                  int maxEdits,
                                                                  RewriteSummary &summary) {
  const std::string editType = "remove_redundant_gm_roundtrip";
  std::vector<std::pair<int, int>> candidates;
  return candidates;
}


static std::string editWindow(const std::string &script, const std::string &editType, size_t maxLen = 1800) {
  size_t pos = script.find(editType);
  if (pos == std::string::npos) return "";
  size_t objEnd = script.find("}", pos);
  if (objEnd == std::string::npos) return script.substr(pos, std::min(maxLen, script.size() - pos));
  return script.substr(pos, std::min(maxLen, objEnd - pos + 1));
}

static bool scriptEnablesEdit(const std::string &script, const std::string &editType) {
  std::string window = editWindow(script, editType);
  if (window.empty()) return false;
  if (window.find("\"enabled\"") != std::string::npos && window.find("false") != std::string::npos) return false;
  return true;
}

static int parseMaxEditsForEdit(const std::string &script, const std::string &editType, int fallback) {
  size_t pos = script.find(editType);
  if (pos == std::string::npos) return 0;
  size_t maxPos = script.find("\"max_edits\"", pos);
  if (maxPos == std::string::npos || maxPos > pos + 1800) return fallback;
  size_t colon = script.find(":", maxPos);
  if (colon == std::string::npos) return fallback;
  size_t i = colon + 1;
  while (i < script.size() && std::isspace(static_cast<unsigned char>(script[i]))) ++i;
  int value = 0;
  bool any = false;
  while (i < script.size() && std::isdigit(static_cast<unsigned char>(script[i]))) {
    any = true;
    value = value * 10 + (script[i] - '0');
    ++i;
  }
  return any ? value : fallback;
}

static int findMaxEventId(const std::vector<std::string> &lines) {
  int maxEvent = -1;
  const std::string tag = "EVENT_ID";
  for (const auto &line : lines) {
    size_t pos = 0;
    while ((pos = line.find(tag, pos)) != std::string::npos) {
      size_t i = pos + tag.size();
      int value = 0;
      bool any = false;
      while (i < line.size() && std::isdigit(static_cast<unsigned char>(line[i]))) {
        any = true;
        value = value * 10 + (line[i] - '0');
        ++i;
      }
      if (any) maxEvent = std::max(maxEvent, value);
      pos = i;
    }
  }
  return maxEvent;
}

static void addChange(RewriteSummary &summary, Change ch) {
  ++summary.applied;
  ++summary.appliedByType[ch.type];
  summary.changes.push_back(ch);
}

static std::vector<std::string> rewriteBarrierAllToDirectionalSync(
    const std::vector<std::string> &lines, const std::string &scriptText,
    RewriteSummary &summary, int &nextEventId) {
  const std::string editType = "replace_barrier_all_with_directional_sync";
  int maxEdits = parseMaxEditsForEdit(scriptText, editType, 4);
  summary.requestedMaxEditsByType[editType] = maxEdits;
  if (!scriptEnablesEdit(scriptText, editType)) {
    summary.skipped.push_back(editType + ": edit not enabled or not present");
    return lines;
  }
  if (maxEdits <= 0) {
    summary.skipped.push_back(editType + ": max_edits <= 0");
    return lines;
  }

  std::vector<std::string> out;
  int appliedForEdit = 0;
  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string &line = lines[i];
    if (appliedForEdit < maxEdits && (containsBarrierAllAnchor(line) || containsPipeAllAnchor(line))) {
      std::string indent = indentOf(line);
      std::string set = "hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID" + std::to_string(nextEventId) + ">]";
      std::string wait = "hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_M>, <EVENT_ID" + std::to_string(nextEventId) + ">]";
      out.push_back(indent + "// [hivm-strategy-rewrite Phase-2G] replaced explicit PIPE_ALL/barrier_ALL with directional set/wait; original: " + stripped(line));
      out.push_back(indent + set);
      out.push_back(indent + wait);
      Change ch;
      ch.type = editType;
      ch.line = static_cast<int>(i + 1);
      ch.before = line;
      ch.after = {set, wait};
      addChange(summary, ch);
      ++appliedForEdit;
      ++nextEventId;
    } else {
      out.push_back(line);
    }
  }
  if (appliedForEdit == 0) summary.skipped.push_back(editType + ": no explicit PIPE_ALL/barrier_ALL anchor found");
  return out;
}

static std::vector<std::string> insertSyncBeforeFirstVectorOp(
    const std::vector<std::string> &lines, const std::string &scriptText,
    RewriteSummary &summary, int &nextEventId) {
  const std::string editType = "insert_sync_before_first_vector_op";
  int maxEdits = parseMaxEditsForEdit(scriptText, editType, 1);
  summary.requestedMaxEditsByType[editType] = maxEdits;
  if (!scriptEnablesEdit(scriptText, editType)) {
    summary.skipped.push_back(editType + ": edit not enabled or not present");
    return lines;
  }
  if (maxEdits <= 0) {
    summary.skipped.push_back(editType + ": max_edits <= 0");
    return lines;
  }

  std::vector<std::string> out;
  bool seenCubeOrFixpipe = false;
  int appliedForEdit = 0;
  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string &line = lines[i];
    if (isCubeOrFixpipeOp(line)) seenCubeOrFixpipe = true;
    bool vectorAnchor = seenCubeOrFixpipe && isVectorOp(line);
    bool immediatePrevSync = !out.empty() && isSetOrWait(out.back());
    if (vectorAnchor && appliedForEdit < maxEdits && !immediatePrevSync) {
      std::string indent = indentOf(line);
      std::string set = "hivm.hir.set_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID" + std::to_string(nextEventId) + ">]";
      std::string wait = "hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_V>, <EVENT_ID" + std::to_string(nextEventId) + ">]";
      out.push_back(indent + "// [hivm-strategy-rewrite Phase-2G] inserted CV directional sync before vector stage");
      out.push_back(indent + set);
      out.push_back(indent + wait);
      Change ch;
      ch.type = editType;
      ch.line = static_cast<int>(i + 1);
      ch.before = line;
      ch.after = {set, wait, line};
      addChange(summary, ch);
      ++appliedForEdit;
      ++nextEventId;
    }
    out.push_back(line);
  }
  if (appliedForEdit == 0) summary.skipped.push_back(editType + ": no vector anchor after cube/fixpipe or already synchronized");
  return out;
}


static void precheckGmRoundtripCandidates(const std::vector<std::string> &lines,
                                          const std::string &scriptText,
                                          RewriteSummary &summary) {
  const std::string editType = "remove_redundant_gm_roundtrip";
  int maxEdits = parseMaxEditsForEdit(scriptText, editType, 1);
  summary.requestedMaxEditsByType[editType] = maxEdits;
  if (!scriptEnablesEdit(scriptText, editType)) {
    summary.skipped.push_back(editType + ": edit not enabled or not present");
    return;
  }
  if (maxEdits <= 0) {
    summary.skipped.push_back(editType + ": max_edits <= 0");
    return;
  }
  int detected = 0;
  for (size_t i = 0; i < lines.size() && detected < maxEdits; ++i) {
    const std::string &storeLine = lines[i];
    if (!isHivmStore(storeLine)) continue;
    std::vector<std::string> gmOuts = extractMemrefVarsWithSpace(storeLine, "outs", "gm");
    if (gmOuts.empty()) continue;
    for (size_t j = i + 1; j < std::min(lines.size(), i + static_cast<size_t>(8)); ++j) {
      const std::string &loadLine = lines[j];
      if (stripped(loadLine).rfind("//", 0) == 0 || stripped(loadLine).empty()) continue;
      if (isComputeLike(loadLine) && !isHivmLoad(loadLine)) break;
      if (!isHivmLoad(loadLine)) continue;
      std::vector<std::string> gmIns = extractMemrefVarsWithSpace(loadLine, "ins", "gm");
      bool same = false;
      std::string sameVar;
      for (const auto &a : gmOuts) for (const auto &b : gmIns) if (a == b) { same = true; sameVar = a; }
      if (same) {
        summary.skipped.push_back(editType + ": candidate store line " + std::to_string(i + 1) +
                                  " -> load line " + std::to_string(j + 1) +
                                  " on " + sameVar + " detected, deletion deferred until target alias/dependency proof");
        ++detected;
      }
      break;
    }
  }
  if (detected == 0) summary.skipped.push_back(editType + ": no conservative same-GM store->load candidate found");
}

static RewriteSummary applyStrictBridgeRewrites(const std::string &inputText, const std::string &scriptText, std::string &outputText) {
  RewriteSummary summary;
  bool trailingNewline = !inputText.empty() && inputText.back() == '\n';
  std::vector<std::string> lines = splitLines(inputText);
  int nextEventId = findMaxEventId(lines) + 1;
  if (nextEventId < 0) nextEventId = 0;

  lines = rewriteBarrierAllToDirectionalSync(lines, scriptText, summary, nextEventId);
  lines = insertSyncBeforeFirstVectorOp(lines, scriptText, summary, nextEventId);
  precheckGmRoundtripCandidates(lines, scriptText, summary);

  outputText = joinLines(lines, trailingNewline);
  summary.success = true;
  summary.mutated = summary.applied > 0;
  summary.reason = summary.mutated
      ? "applied standalone strict C++ bridge rewrites"
      : "no enabled explicit structural rewrite anchors found";
  if (!summary.mutated) summary.skipped.push_back(summary.reason);
  return summary;
}

static void writeMapInt(std::ofstream &os, const std::map<std::string, int> &m, int indentSpaces) {
  std::string ind(indentSpaces, ' ');
  os << "{\n";
  size_t idx = 0;
  for (const auto &kv : m) {
    os << ind << "  \"" << jsonEscape(kv.first) << "\": " << kv.second;
    if (++idx < m.size()) os << ",";
    os << "\n";
  }
  os << ind << "}";
}

static void writeReport(const std::string &path, const RewriteSummary &summary,
                        const std::string &inputPath, const std::string &editPath,
                        const std::string &outputPath) {
  if (path.empty()) return;
  std::ofstream os(path);
  os << "{\n";
  os << "  \"schema_version\": \"hivm_strategy_rewrite_cpp_bridge_phase2g_v1\",\n";
  os << "  \"success\": " << (summary.success ? "true" : "false") << ",\n";
  os << "  \"backend_mode\": \"standalone_cpp_strict_bridge\",\n";
  os << "  \"bridge_phase\": \"Phase-2G\",\n";
  os << "  \"supported_edits\": [\"replace_barrier_all_with_directional_sync\", \"insert_sync_before_first_vector_op\", \"remove_redundant_gm_roundtrip\"],\n";
  os << "  \"production_target\": \"vTriton/HivmOpsEditor or MLIR PatternRewriter/RewriterBase pass\",\n";
  os << "  \"reason\": \"" << jsonEscape(summary.reason) << "\",\n";
  os << "  \"input\": \"" << jsonEscape(inputPath) << "\",\n";
  os << "  \"edit_script\": \"" << jsonEscape(editPath) << "\",\n";
  os << "  \"output\": \"" << jsonEscape(outputPath) << "\",\n";
  os << "  \"requested_max_edits_by_type\": ";
  writeMapInt(os, summary.requestedMaxEditsByType, 2);
  os << ",\n";
  os << "  \"applied_changes\": " << summary.applied << ",\n";
  os << "  \"change_counts\": ";
  writeMapInt(os, summary.appliedByType, 2);
  os << ",\n";
  os << "  \"mutated_ir\": " << (summary.mutated ? "true" : "false") << ",\n";
  os << "  \"official_rewrite_boundary\": [\n";
  os << "    \"This bridge is buildable without MLIR/vTriton and is intended as a Phase-2G executable boundary.\",\n";
  os << "    \"Production mutation must move to HivmOpsEditor or PatternRewriter/RewriterBase APIs with target dialect verification.\",\n";
  os << "    \"Run tritonsim-hivm / target compiler parser after using this output.\"\n";
  os << "  ],\n";
  os << "  \"changes\": [\n";
  for (size_t i = 0; i < summary.changes.size(); ++i) {
    const Change &ch = summary.changes[i];
    os << "    {\"type\": \"" << jsonEscape(ch.type) << "\", \"line\": " << ch.line
       << ", \"before\": \"" << jsonEscape(ch.before) << "\", \"after\": [";
    for (size_t j = 0; j < ch.after.size(); ++j) {
      if (j) os << ", ";
      os << "\"" << jsonEscape(ch.after[j]) << "\"";
    }
    os << "]}" << (i + 1 == summary.changes.size() ? "" : ",") << "\n";
  }
  os << "  ],\n";
  os << "  \"skipped\": [";
  for (size_t i = 0; i < summary.skipped.size(); ++i) {
    if (i) os << ", ";
    os << "\"" << jsonEscape(summary.skipped[i]) << "\"";
  }
  os << "]\n";
  os << "}\n";
}

} // namespace

static void printCapabilities() {
  std::cout << "{\n";
  std::cout << "  \"schema_version\": \"hivm_strategy_rewrite_capabilities_v1\",\n";
  std::cout << "  \"backend_mode\": \"standalone_cpp_strict_bridge\",\n";
  std::cout << "  \"bridge_phase\": \"Phase-2G\",\n";
  std::cout << "  \"interface_version\": \"hivm-strategy-rewrite-cli-v1\",\n";
  std::cout << "  \"supports_print_capabilities\": true,\n";
  std::cout << "  \"supported_edits\": [\"replace_barrier_all_with_directional_sync\", \"insert_sync_before_first_vector_op\", \"remove_redundant_gm_roundtrip\"],\n";
  std::cout << "  \"mutation_edits\": [\"replace_barrier_all_with_directional_sync\", \"insert_sync_before_first_vector_op\"],\n";
  std::cout << "  \"precheck_only_edits\": [\"remove_redundant_gm_roundtrip\"],\n";
  std::cout << "  \"required_cli\": \"--input --edit-script --output --report\",\n";
  std::cout << "  \"production_target\": \"vTriton/HivmOpsEditor or MLIR PatternRewriter/RewriterBase pass\"\n";
  std::cout << "}\n";
}

int main(int argc, char **argv) {
  for (int i = 1; i < argc; ++i) {
    std::string key(argv[i]);
    if (key == "--print-capabilities" || key == "--capabilities") {
      printCapabilities();
      return 0;
    }
  }
  std::string input, editScript, output, report;
  for (int i = 1; i < argc; ++i) {
    std::string key(argv[i]);
    if (i + 1 >= argc) break;
    std::string val(argv[i + 1]);
    if (key == "--input") { input = val; ++i; }
    else if (key == "--edit-script") { editScript = val; ++i; }
    else if (key == "--output") { output = val; ++i; }
    else if (key == "--report") { report = val; ++i; }
  }

  if (input.empty() || editScript.empty() || output.empty() || report.empty()) {
    std::cerr << "usage: hivm-strategy-rewrite --input in.mlir --edit-script structural_edit_script.json --output out.mlir --report report.json\n";
    return 2;
  }

  std::string inputText, scriptText, outputText;
  if (!readFile(input, inputText)) {
    RewriteSummary s; s.success = false; s.reason = "input file not found or unreadable";
    writeReport(report, s, input, editScript, output);
    return 2;
  }
  if (!readFile(editScript, scriptText)) {
    RewriteSummary s; s.success = false; s.reason = "edit script not found or unreadable";
    writeReport(report, s, input, editScript, output);
    return 2;
  }

  RewriteSummary summary = applyStrictBridgeRewrites(inputText, scriptText, outputText);
  if (!writeFile(output, outputText)) {
    summary.success = false;
    summary.reason = "failed to write output file";
    writeReport(report, summary, input, editScript, output);
    return 2;
  }
  writeReport(report, summary, input, editScript, output);
  std::cerr << "hivm-strategy-rewrite Phase-2G bridge: " << summary.reason
            << ", changes=" << summary.applied << "\n";
  return summary.success ? 0 : 2;
}
