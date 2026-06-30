@echo off
setlocal EnableExtensions
set ROOT_DIR=%~dp0..
set IR_PATH=%~1
if "%IR_PATH%"=="" set IR_PATH=%ROOT_DIR%\sample_input\original_repo_samples\chunk_kda_kernel_clean.npuir.mlir
set PLAN_PATH=%~2
if "%PLAN_PATH%"=="" set PLAN_PATH=%ROOT_DIR%\artifacts\latest_smoke_run\selected_plan.json
set OUT_DIR=%~3
if "%OUT_DIR%"=="" set OUT_DIR=%ROOT_DIR%\artifacts\v51_cvpipeline_true_rewrite
set MAX_MB_CANDIDATES=%~4
if "%MAX_MB_CANDIDATES%"=="" set MAX_MB_CANDIDATES=80
set MAX_MB_ACTIONS=%~5
if "%MAX_MB_ACTIONS%"=="" set MAX_MB_ACTIONS=3
set MAX_CV_WINDOWS=%~6
if "%MAX_CV_WINDOWS%"=="" set MAX_CV_WINDOWS=50
set MAX_CV_ACTIONS=%~7
if "%MAX_CV_ACTIONS%"=="" set MAX_CV_ACTIONS=2
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"
set MB_OUT=%OUT_DIR%\01_multibuffer_true_rewrite
set CV_OUT=%OUT_DIR%\02_cvpipeline_true_rewrite
python "%ROOT_DIR%\tools\run_multibuffer_true_rewrite.py" ^
  --ir "%IR_PATH%" ^
  --selected-plan "%PLAN_PATH%" ^
  --output-dir "%MB_OUT%" ^
  --max-candidates %MAX_MB_CANDIDATES% ^
  --max-actions %MAX_MB_ACTIONS%
python "%ROOT_DIR%\tools\run_cvpipeline_true_rewrite.py" ^
  --ir "%MB_OUT%\optimized.multibuffer_rewritten.hivm.mlir" ^
  --selected-plan "%PLAN_PATH%" ^
  --output-dir "%CV_OUT%" ^
  --max-windows %MAX_CV_WINDOWS% ^
  --max-actions %MAX_CV_ACTIONS%
python -c "import json,pathlib; out=pathlib.Path(r'%OUT_DIR%'); mb=json.loads((out/'01_multibuffer_true_rewrite'/'multibuffer_true_rewrite_summary.json').read_text(encoding='utf-8')); cv=json.loads((out/'02_cvpipeline_true_rewrite'/'cvpipeline_true_rewrite_summary.json').read_text(encoding='utf-8')); s={'schema_version':'hivm_v51_cvpipeline_true_rewrite_closure_summary_v1','version':'V5.1-cvpipeline-restricted-true-rewrite','multibuffer_mutation_performed':mb.get('mutation_performed'),'multibuffer_rewritten_action_count':mb.get('rewritten_action_count'),'cvpipeline_mutation_performed':cv.get('mutation_performed'),'cvpipeline_rewritten_action_count':cv.get('rewritten_action_count'),'cvpipeline_passed_portable_validation':cv.get('passed_portable_validation'),'semantic_mutation_performed':bool(mb.get('semantic_mutation_performed') and cv.get('semantic_mutation_performed')),'production_rewrite_claim_allowed':False,'claim_boundary':'V5.1 portable restricted true rewrite; real HivmOpsEditor verifier/DES/msprof still required'}; (out/'v51_cvpipeline_true_rewrite_closure_summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(s,ensure_ascii=False,indent=2))"
endlocal
