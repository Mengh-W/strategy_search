# Prefill-A5 S0-S9 Cost Model Benchmark Report
## 1. 定位
这组数据来自同一个 sparse prefill kernel 的 S0-S9 优化历史。它适合做多策略 latency trend / ranking sanity test；由于缺少每个阶段的 op_summary，它不能做 AIC/AIV/MTE/scalar/vector 分项校准。
## 2. 校准方式
- S0 measured cycles: `10730000.00`
- S0 raw predicted cycles: `2439390.20`
- Global anchor scale: `4.3986`
- Raw-project 模式：只用 S0 做量纲 anchor，不使用 S1-S9 的真实 gain。
- Hybrid 模式：对当前 StrategyConfig 表达不充分的事件加入经验 prior，对部分可表达事件用半权重。
- Stage-prior 模式：使用 S0-S9 提取出的 stage gain priors，属于 fitted benchmark 上界，不代表泛化。

## 3. Ranking metrics
| Predictor | Spearman | Kendall | Top1 hit | Top3 recall | Best regret | MAPE |
|---|---:|---:|---:|---:|---:|---:|
| raw_project_anchor_scaled | 0.9630 | 1.0000 | False | 0.6667 | 0.1405 | 0.0853 |
| hybrid_calibrated | 1.0000 | 1.0000 | True | 1.0000 | 0.0000 | 0.1187 |
| stage_prior_calibrated | 1.0000 | 1.0000 | True | 1.0000 | 0.0000 | 0.0000 |

## 4. Stage rows
| Stage | latency_us | raw_anchor_cycles | hybrid_cycles | stage_prior_cycles |
|---|---:|---:|---:|---:|
| S0 | 5800.0 | 10730000.0 | 10730000.0 | 10730000.0 |
| S1 | 5392.0 | 10730000.0 | 9975200.0 | 9975200.0 |
| S2 | 4356.0 | 8355505.2 | 6981738.8 | 8058600.0 |
| S3 | 4337.0 | 8323158.2 | 6939526.0 | 8023450.0 |
| S4 | 4294.0 | 8323158.2 | 6870722.8 | 7943900.0 |
| S5 | 4235.0 | 8199043.8 | 6721607.9 | 7834750.0 |
| S6 | 4075.0 | 7872099.0 | 6330494.1 | 7538750.0 |
| S7 | 3580.0 | 7872099.0 | 5561513.8 | 6623000.0 |
| S8 | 3589.0 | 7872099.0 | 5575495.3 | 6639650.0 |
| S9 | 3573.0 | 7872099.0 | 5550639.4 | 6610050.0 |

## 5. Learned stage gain priors
| Event | Evidence | latency multiplier | speedup |
|---|---|---:|---:|
| block_v_512_eliminate_v_loop | S0->S1 | 0.9297 | 1.0757 |
| block_sbs_256_multibuffer_false | S1->S2 | 0.8079 | 1.2378 |
| mixed_cv_disabled | S2->S3 | 0.9956 | 1.0044 |
| workspace_sv_bf16 | S3->S4 | 0.9901 | 1.0100 |
| hivm_auto_cv_balance | S4->S5 | 0.9863 | 1.0139 |
| tile_mix_cube4_vec1 | S5->S6 | 0.9622 | 1.0393 |
| shared_kv_nope_ssa_rewrite | S6->S7 | 0.8785 | 1.1383 |
| hoist_q_loads_rewrite | S7->S8 | 1.0025 | 0.9975 |
| compiler_code_motion | S8->S9 | 0.9955 | 1.0045 |

## 6. 结论
这份文件已经被用于两类事情：第一，测试当前 analytical cost model 在 S0-S9 多策略标签上的排序表现；第二，抽取 stage gain priors，用于校准 BLOCK_V、BLOCK_SBS/multibuffer、CV 配置、tile_mix 和 IR rewrite/code motion 的相对收益。由于缺少每个阶段的 msprof component profile，分项硬件效率校准仍然需要每阶段 op_summary。
