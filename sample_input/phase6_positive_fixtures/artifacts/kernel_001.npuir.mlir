func.func @sparse_flash_attention_prefill_kernel_cvpipe_mix_aic(%arg0: i64 {hacc.arg_type = #hacc.arg_type<ffts_base_address>}, %arg1: memref<?xi8, #hivm.address_space<gm>> {hacc.arg_type = #hacc.arg_type<sync_block_lock>}, %arg2: memref<?xi8, #hivm.address_space<gm>> {hacc.arg_type = #hacc.arg_type<workspace>}, %arg3: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg4: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg5: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg6: memref<?xi32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg7: memref<?xf32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 1 : i32}, %arg8: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg9: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg10: memref<?xf32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg11: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 2 : i32}, %arg12: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 2 : i32}, %arg13: i32 {tt.divisibility = 16 : i32}, %arg14: i32 {tt.divisibility = 16 : i32}, %arg15: i32 {tt.divisibility = 16 : i32}, %arg16: i32 {tt.divisibility = 16 : i32}, %arg17: i32 {tt.divisibility = 16 : i32}, %arg18: i32 {tt.divisibility = 16 : i32}, %arg19: i32 {tt.divisibility = 16 : i32}, %arg20: i32 {tt.divisibility = 16 : i32}, %arg21: i32 {tt.divisibility = 16 : i32}, %arg22: i32 {tt.divisibility = 16 : i32}, %arg23: i32 {tt.divisibility = 16 : i32}, %arg24: i32 {tt.divisibility = 16 : i32}, %arg25: i32 {tt.divisibility = 16 : i32}, %arg26: i32 {tt.divisibility = 16 : i32}, %arg27: i32 {tt.divisibility = 16 : i32}, %arg28: i32 {tt.divisibility = 16 : i32}, %arg29: i32 {tt.divisibility = 16 : i32}, %arg30: i32 {tt.divisibility = 16 : i32}, %arg31: i32 {tt.divisibility = 16 : i32}, %arg32: i32 {tt.divisibility = 16 : i32}, %arg33: i32 {tt.divisibility = 16 : i32}, %arg34: i32 {tt.divisibility = 16 : i32}, %arg35: i32 {tt.divisibility = 16 : i32}, %arg36: f32, %arg37: i32, %arg38: i32, %arg39: i32, %arg40: i32, %arg41: i32, %arg42: i32, %arg43: i32, %arg44: i32) attributes {SyncBlockLockArgIdx = 0 : i64, WorkspaceArgIdx = 1 : i64, func_dyn_memref_args = dense<[false, true, true, true, true, true, true, true, true, true, true, true, true, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false]> : vector<45xi1>, hacc.entry, hacc.function_kind = #hacc.function_kind<DEVICE>, hivm.func_core_type = #hivm.func_core_type<AIC>, hivm.part_of_mix, hivm.storage_aligned, parallel_mode = "simd"} {
  %c3_i64 = arith.constant 3 : i64
  %c2_i64 = arith.constant 2 : i64
  %c1_i64 = arith.constant 1 : i64
  %c1_i64_0 = arith.constant 1 : i64
  %c-1_i64 = arith.constant -1 : i64
  %c1_i64_1 = arith.constant 1 : i64
  %c-1_i64_2 = arith.constant -1 : i64
  %c1_i64_3 = arith.constant 1 : i64
  %c-1_i64_4 = arith.constant -1 : i64
  %c8192_i64 = arith.constant 8192 : i64
  %c335872_i64 = arith.constant 335872 : i64
  %c165888_i64 = arith.constant 165888 : i64
  %c319488_i64 = arith.constant 319488 : i64
  %c149504_i64 = arith.constant 149504 : i64
  %c188416_i64 = arith.constant 188416 : i64
  %c18432_i64 = arith.constant 18432 : i64
  %c186368_i64 = arith.constant 186368 : i64
  %c16384_i64 = arith.constant 16384 : i64
  %c169984_i64 = arith.constant 169984 : i64
  %c0_i64 = arith.constant 0 : i64
  %c8_i32 = arith.constant 8 : i32
  %c0_i32 = arith.constant 0 : i32
  %c128_i32 = arith.constant 128 : i32
  %c512 = arith.constant 512 : index
  %true = arith.constant true
  %false = arith.constant false
  %c1_i32 = arith.constant 1 : i32
  %c16 = arith.constant 16 : index
  %c128 = arith.constant 128 : index
  %c64 = arith.constant 64 : index
  hivm.hir.set_ffts_base_addr %arg0
  hivm.hir.set_mask_norm
  %0 = arith.muli %arg42, %arg43 : i32
  %1 = arith.muli %0, %arg44 : i32
  annotation.mark %1 {logical_block_num} : i32
  %2 = hivm.hir.get_block_idx -> i64
  %3 = arith.trunci %2 : i64 to i32
  %4 = arith.muli %arg44, %arg43 : i32
  %5 = arith.divsi %3, %4 : i32
  %6 = arith.remsi %5, %arg42 : i32
  %7 = arith.muli %6, %arg41 : i32
  %8 = arith.addi %6, %c1_i32 : i32
  %9 = arith.muli %8, %arg41 : i32
  %10 = arith.minsi %arg37, %9 : i32
  %11 = arith.muli %6, %arg32 : i32
  %12 = arith.muli %6, %arg34 : i32
  %13 = arith.index_cast %11 : i32 to index
  %14 = arith.index_cast %arg33 : i32 to index
  %reinterpret_cast = memref.reinterpret_cast %arg11 to offset: [%13], sizes: [16, 128], strides: [%14, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x128xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
  %15 = arith.index_cast %12 : i32 to index
  %16 = arith.index_cast %arg35 : i32 to index
  %reinterpret_cast_5 = memref.reinterpret_cast %arg12 to offset: [%15], sizes: [16, 512], strides: [%16, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
  hivm.hir.sync_block_set[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 2
  %17 = arith.index_cast %arg15 : i32 to index
  %18 = arith.index_cast %arg26 : i32 to index
  %19 = arith.index_cast %arg29 : i32 to index
  %20 = arith.index_cast %2 : i64 to index
  %21 = affine.apply affine_map<()[s0] -> (s0 * 8192)>()[%20]
  %view = memref.view %arg2[%21][] : memref<?xi8, #hivm.address_space<gm>> to memref<16x128xf32, #hivm.address_space<gm>>
  hivm.hir.set_flag[<PIPE_M>, <PIPE_MTE1>, <EVENT_ID0>]
  hivm.hir.set_flag[<PIPE_M>, <PIPE_MTE1>, <EVENT_ID1>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID0>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID1>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID2>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID3>]
  hivm.hir.set_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID0>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID4>]
  hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID5>]
  hivm.hir.set_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID1>]
  scf.for %arg45 = %7 to %10 step %c1_i32  : i32 {
    %22 = arith.index_cast %arg45 : i32 to index
    %23 = arith.index_cast %7 : i32 to index
    %24 = arith.index_cast %10 : i32 to index
    %25 = arith.index_cast %c1_i32 : i32 to index
    %26 = affine.apply affine_map<()[s0, s1, s2] -> (((s0 - s1) floordiv s2) mod 2)>()[%22, %23, %25]
    %27 = arith.index_cast %26 : index to i1
    %c0_i64_6 = arith.constant 0 : i64
    %c1_i64_7 = arith.constant 1 : i64
    %28 = arith.select %27, %c0_i64_6, %c1_i64_7 : i64
    %29 = hivm.hir.pointer_cast(%c16384_i64, %c186368_i64) : memref<4x1x16x16xbf16, #hivm.address_space<cbuf>>
    annotation.mark %29 {hivm.multi_buffer = 2 : i32} : memref<4x1x16x16xbf16, #hivm.address_space<cbuf>>
    %30 = hivm.hir.pointer_cast(%c0_i64, %c169984_i64) : memref<32x1x16x16xbf16, #hivm.address_space<cbuf>>
    annotation.mark %30 {hivm.multi_buffer = 2 : i32} : memref<32x1x16x16xbf16, #hivm.address_space<cbuf>>
    %31 = arith.muli %arg45, %arg13 : i32
    %32 = arith.muli %arg45, %arg24 : i32
    %33 = arith.muli %arg45, %arg27 : i32
    %34 = arith.index_cast %31 : i32 to index
    %reinterpret_cast_8 = memref.reinterpret_cast %arg3 to offset: [%34], sizes: [16, 512], strides: [%17, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
    %cast = memref.cast %30 : memref<32x1x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>
    hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, %28]
    hivm.hir.pipe_barrier[<PIPE_MTE2>]
    hivm.hir.nd2nz {dst_continuous} ins(%reinterpret_cast_8 : memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%cast : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
    %35 = affine.apply affine_map<()[s0] -> (s0 + 512)>()[%34]
    %reinterpret_cast_9 = memref.reinterpret_cast %arg3 to offset: [%35], sizes: [16, 64], strides: [%17, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x64xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
    %cast_10 = memref.cast %29 : memref<4x1x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>
    hivm.hir.nd2nz {dst_continuous} ins(%reinterpret_cast_9 : memref<16x64xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%cast_10 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
    hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE1>, <EVENT_ID0>]
    %36 = arith.index_cast %32 : i32 to index
    %37 = arith.index_cast %33 : i32 to index
    hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_MTE1>, <EVENT_ID0>]
    scf.for %arg46 = %c0_i32 to %c8_i32 step %c1_i32  : i32 {
      %38 = arith.index_cast %arg46 : i32 to index
      %39 = arith.index_cast %c0_i32 : i32 to index
      %40 = arith.index_cast %c8_i32 : i32 to index
      %41 = arith.index_cast %c1_i32 : i32 to index
      %42 = arith.index_cast %arg45 : i32 to index
      %43 = arith.index_cast %7 : i32 to index
      %44 = arith.index_cast %10 : i32 to index
      %45 = arith.index_cast %c1_i32 : i32 to index
      %46 = affine.apply affine_map<()[s0, s1, s2, s3, s4, s5, s6] -> (((s0 - s1) floordiv s3 + ((s4 - s5) floordiv s6) * ((-s1 + s2 + s3 - 1) floordiv s3)) mod 2)>()[%38, %39, %40, %41, %42, %43, %45]
      %47 = arith.index_cast %46 : index to i1
      %c4_i64 = arith.constant 4 : i64
      %c5_i64 = arith.constant 5 : i64
      %48 = arith.select %47, %c4_i64, %c5_i64 : i64
      %c2_i64_11 = arith.constant 2 : i64
      %c3_i64_12 = arith.constant 3 : i64
      %49 = arith.select %47, %c2_i64_11, %c3_i64_12 : i64
      %50 = arith.index_cast %arg46 : i32 to index
      %51 = arith.index_cast %c0_i32 : i32 to index
      %52 = arith.index_cast %c8_i32 : i32 to index
      %53 = arith.index_cast %c1_i32 : i32 to index
      %54 = arith.index_cast %arg45 : i32 to index
      %55 = arith.index_cast %7 : i32 to index
      %56 = arith.index_cast %10 : i32 to index
      %57 = arith.index_cast %c1_i32 : i32 to index
      %58 = affine.apply affine_map<()[s0, s1, s2, s3, s4, s5, s6] -> ((s0 - s1) floordiv s3 + ((s4 - s5) floordiv s6) * ((-s1 + s2 + s3 - 1) floordiv s3))>()[%50, %51, %52, %53, %54, %55, %57]
      %59 = arith.index_cast %58 : index to i64
      %c0_i64_13 = arith.constant 0 : i64
      %60 = arith.index_cast %arg46 : i32 to index
      %61 = arith.index_cast %c0_i32 : i32 to index
      %62 = arith.index_cast %c8_i32 : i32 to index
      %63 = arith.index_cast %c1_i32 : i32 to index
      %64 = arith.index_cast %arg45 : i32 to index
      %65 = arith.index_cast %7 : i32 to index
      %66 = arith.index_cast %10 : i32 to index
      %67 = arith.index_cast %c1_i32 : i32 to index
      %68 = affine.apply affine_map<()[s0, s1, s2, s3, s4, s5, s6] -> ((s0 - s1) floordiv s3 + ((s4 - s5) floordiv s6) * ((-s1 + s2 + s3 - 1) floordiv s3))>()[%60, %61, %62, %63, %64, %65, %67]
      %69 = arith.index_cast %68 : index to i64
      %c0_i64_14 = arith.constant 0 : i64
      %70 = arith.index_cast %arg46 : i32 to index
      %71 = arith.index_cast %c0_i32 : i32 to index
      %72 = arith.index_cast %c8_i32 : i32 to index
      %73 = arith.index_cast %c1_i32 : i32 to index
      %74 = arith.index_cast %arg45 : i32 to index
      %75 = arith.index_cast %7 : i32 to index
      %76 = arith.index_cast %10 : i32 to index
      %77 = arith.index_cast %c1_i32 : i32 to index
      %78 = affine.apply affine_map<()[s0, s1, s2, s3, s4, s5, s6] -> ((s0 - s1) floordiv s3 + ((s4 - s5) floordiv s6) * ((-s1 + s2 + s3 - 1) floordiv s3))>()[%70, %71, %72, %73, %74, %75, %77]
      %79 = arith.index_cast %78 : index to i64
      %c0_i64_15 = arith.constant 0 : i64
      %80 = hivm.hir.pointer_cast(%c149504_i64, %c319488_i64) : memref<4x8x16x16xbf16, #hivm.address_space<cbuf>>
      annotation.mark %80 {hivm.multi_buffer = 2 : i32} : memref<4x8x16x16xbf16, #hivm.address_space<cbuf>>
      %81 = hivm.hir.pointer_cast(%c165888_i64, %c335872_i64) : memref<8x1x16x16xbf16, #hivm.address_space<cbuf>>
      annotation.mark %81 {hivm.multi_buffer = 2 : i32} : memref<8x1x16x16xbf16, #hivm.address_space<cbuf>>
      %82 = hivm.hir.pointer_cast(%c18432_i64, %c188416_i64) : memref<32x8x16x16xbf16, #hivm.address_space<cbuf>>
      annotation.mark %82 {hivm.multi_buffer = 2 : i32} : memref<32x8x16x16xbf16, #hivm.address_space<cbuf>>
      %83 = arith.muli %arg46, %c128_i32 : i32
      %84 = arith.index_cast %83 : i32 to index
      %85 = affine.apply affine_map<()[s0, s1, s2] -> (s0 + s1 * s2)>()[%36, %84, %18]
      %reinterpret_cast_16 = memref.reinterpret_cast %arg8 to offset: [%85], sizes: [128, 512], strides: [%18, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<128x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
      %cast_17 = memref.cast %82 : memref<32x8x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>
      hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, %49]
      hivm.hir.nd2nz {dst_continuous} ins(%reinterpret_cast_16 : memref<128x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%cast_17 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE1>, <EVENT_ID1>]
      %86 = hivm.hir.pointer_cast(%c0_i64) : memref<8x1x16x16xf32, #hivm.address_space<cc>>
      %cast_18 = memref.cast %86 : memref<8x1x16x16xf32, #hivm.address_space<cc>> to memref<?x?x?x?xf32, #hivm.address_space<cc>>
      hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID0>]
      hivm.hir.mmadL1 {b_transpose} ins(%cast, %cast_17, %true, %c16, %c512, %c128 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, i1, index, index, index) outs(%cast_18 : memref<?x?x?x?xf32, #hivm.address_space<cc>>) sync_related_args(%c-1_i64_4, %c1_i64, %c-1_i64_4, %c-1_i64_4, %79, %c0_i64_15, %c1_i64_3 : i64, i64, i64, i64, i64, i64, i64)
      %87 = affine.apply affine_map<()[s0, s1, s2] -> (s0 + s1 * s2)>()[%37, %84, %19]
      %reinterpret_cast_19 = memref.reinterpret_cast %arg9 to offset: [%87], sizes: [128, 64], strides: [%19, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<128x64xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
      %cast_20 = memref.cast %80 : memref<4x8x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>
      hivm.hir.nd2nz {dst_continuous} ins(%reinterpret_cast_19 : memref<128x64xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%cast_20 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE1>, <EVENT_ID2>]
      hivm.hir.mmadL1 {b_transpose, fixpipe_already_inserted = true} ins(%cast_10, %cast_20, %false, %c16, %c64, %c128 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, i1, index, index, index) outs(%cast_18 : memref<?x?x?x?xf32, #hivm.address_space<cc>>) sync_related_args(%c-1_i64_2, %c2_i64, %c-1_i64_2, %c-1_i64_2, %69, %c0_i64_14, %c1_i64_1 : i64, i64, i64, i64, i64, i64, i64)
      hivm.hir.set_flag[<PIPE_M>, <PIPE_FIX>, <EVENT_ID0>]
      hivm.hir.sync_block_wait[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 0
      hivm.hir.wait_flag[<PIPE_M>, <PIPE_FIX>, <EVENT_ID0>]
      hivm.hir.fixpipe {enable_nz2nd} ins(%cast_18 : memref<?x?x?x?xf32, #hivm.address_space<cc>>) outs(%view : memref<16x128xf32, #hivm.address_space<gm>>)
      hivm.hir.set_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID0>]
      annotation.mark %view : memref<16x128xf32, #hivm.address_space<gm>>
      hivm.hir.sync_block_set[<CUBE>, <PIPE_FIX>, <PIPE_S>] flag = 1
      %cast_21 = memref.cast %81 : memref<8x1x16x16xbf16, #hivm.address_space<cbuf>> to memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>
      hivm.hir.sync_block_wait[<CUBE>, <PIPE_MTE3>, <PIPE_S>] flag = 1
      hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, %48]
      hivm.hir.nd2nz {dst_continuous} ins(%reinterpret_cast : memref<16x128xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%cast_21 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>) init_out_buffer = false
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_MTE1>, <EVENT_ID3>]
      hivm.hir.sync_block_set[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 2
      %88 = hivm.hir.pointer_cast(%c8192_i64) : memref<32x1x16x16xf32, #hivm.address_space<cc>>
      %cast_22 = memref.cast %88 : memref<32x1x16x16xf32, #hivm.address_space<cc>> to memref<?x?x?x?xf32, #hivm.address_space<cc>>
      hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID1>]
      hivm.hir.mmadL1 {fixpipe_already_inserted = true} ins(%cast_21, %cast_17, %true, %c16, %c128, %c512 : memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, memref<?x?x?x?xbf16, #hivm.address_space<cbuf>>, i1, index, index, index) outs(%cast_22 : memref<?x?x?x?xf32, #hivm.address_space<cc>>) sync_related_args(%c3_i64, %c-1_i64, %48, %49, %59, %c0_i64_13, %c1_i64_0 : i64, i64, i64, i64, i64, i64, i64)
      hivm.hir.set_flag[<PIPE_M>, <PIPE_FIX>, <EVENT_ID1>]
      hivm.hir.sync_block_wait[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 3
      hivm.hir.wait_flag[<PIPE_M>, <PIPE_FIX>, <EVENT_ID1>]
      hivm.hir.fixpipe {enable_nz2nd, pre_quant = #hivm.fixpipe_pre_quant_mode<F322BF16>} ins(%cast_22 : memref<?x?x?x?xf32, #hivm.address_space<cc>>) outs(%reinterpret_cast_5 : memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>)
      hivm.hir.set_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID1>]
      hivm.hir.sync_block_set[<CUBE>, <PIPE_FIX>, <PIPE_S>] flag = 1
    }
    hivm.hir.set_flag[<PIPE_MTE1>, <PIPE_MTE2>, %28]
  }
  hivm.hir.wait_flag[<PIPE_M>, <PIPE_MTE1>, <EVENT_ID0>]
  hivm.hir.wait_flag[<PIPE_M>, <PIPE_MTE1>, <EVENT_ID1>]
  hivm.hir.pipe_barrier[<PIPE_ALL>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID0>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID1>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID2>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID3>]
  hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID0>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID4>]
  hivm.hir.wait_flag[<PIPE_MTE1>, <PIPE_MTE2>, <EVENT_ID5>]
  hivm.hir.wait_flag[<PIPE_FIX>, <PIPE_M>, <EVENT_ID1>]
  hivm.hir.sync_block_wait[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 0
  hivm.hir.sync_block_wait[<CUBE>, <PIPE_MTE2>, <PIPE_S>] flag = 3
  return
}

// -----// IR Dump After InjectSync (hivm-inject-sync) //----- //
func.func @sparse_flash_attention_prefill_kernel_cvpipe_mix_aiv(%arg0: i64 {hacc.arg_type = #hacc.arg_type<ffts_base_address>}, %arg1: memref<?xi8, #hivm.address_space<gm>> {hacc.arg_type = #hacc.arg_type<sync_block_lock>}, %arg2: memref<?xi8, #hivm.address_space<gm>> {hacc.arg_type = #hacc.arg_type<workspace>}, %arg3: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg4: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg5: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg6: memref<?xi32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg7: memref<?xf32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 1 : i32}, %arg8: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg9: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 0 : i32}, %arg10: memref<?xf32, #hivm.address_space<gm>> {tt.divisibility = 16 : i32}, %arg11: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 2 : i32}, %arg12: memref<?xbf16, #hivm.address_space<gm>> {tt.divisibility = 16 : i32, tt.tensor_kind = 2 : i32}, %arg13: i32 {tt.divisibility = 16 : i32}, %arg14: i32 {tt.divisibility = 16 : i32}, %arg15: i32 {tt.divisibility = 16 : i32}, %arg16: i32 {tt.divisibility = 16 : i32}, %arg17: i32 {tt.divisibility = 16 : i32}, %arg18: i32 {tt.divisibility = 16 : i32}, %arg19: i32 {tt.divisibility = 16 : i32}, %arg20: i32 {tt.divisibility = 16 : i32}, %arg21: i32 {tt.divisibility = 16 : i32}, %arg22: i32 {tt.divisibility = 16 : i32}, %arg23: i32 {tt.divisibility = 16 : i32}, %arg24: i32 {tt.divisibility = 16 : i32}, %arg25: i32 {tt.divisibility = 16 : i32}, %arg26: i32 {tt.divisibility = 16 : i32}, %arg27: i32 {tt.divisibility = 16 : i32}, %arg28: i32 {tt.divisibility = 16 : i32}, %arg29: i32 {tt.divisibility = 16 : i32}, %arg30: i32 {tt.divisibility = 16 : i32}, %arg31: i32 {tt.divisibility = 16 : i32}, %arg32: i32 {tt.divisibility = 16 : i32}, %arg33: i32 {tt.divisibility = 16 : i32}, %arg34: i32 {tt.divisibility = 16 : i32}, %arg35: i32 {tt.divisibility = 16 : i32}, %arg36: f32, %arg37: i32, %arg38: i32, %arg39: i32, %arg40: i32, %arg41: i32, %arg42: i32, %arg43: i32, %arg44: i32) attributes {SyncBlockLockArgIdx = 0 : i64, WorkspaceArgIdx = 1 : i64, func_dyn_memref_args = dense<[false, true, true, true, true, true, true, true, true, true, true, true, true, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false, false]> : vector<45xi1>, hacc.entry, hacc.function_kind = #hacc.function_kind<DEVICE>, hivm.func_core_type = #hivm.func_core_type<AIV>, hivm.part_of_mix, hivm.storage_aligned, parallel_mode = "simd"} {
  %c128 = arith.constant 128 : index
  %c125376_i64 = arith.constant 125376 : i64
  %c124864_i64 = arith.constant 124864 : i64
  %c92096_i64 = arith.constant 92096 : i64
  %c75712_i64 = arith.constant 75712 : i64
  %c75200_i64 = arith.constant 75200 : i64
  %c74688_i64 = arith.constant 74688 : i64
  %c74560_i64 = arith.constant 74560 : i64
  %c74528_i64 = arith.constant 74528 : i64
  %c74464_i64 = arith.constant 74464 : i64
  %c74432_i64 = arith.constant 74432 : i64
  %c70336_i64 = arith.constant 70336 : i64
  %c70272_i64 = arith.constant 70272 : i64
  %c69760_i64 = arith.constant 69760 : i64
  %c65664_i64 = arith.constant 65664 : i64
  %c65600_i64 = arith.constant 65600 : i64
  %c65568_i64 = arith.constant 65568 : i64
  %c57376_i64 = arith.constant 57376 : i64
  %c53280_i64 = arith.constant 53280 : i64
  %c53184_i64 = arith.constant 53184 : i64
  %c52928_i64 = arith.constant 52928 : i64
  %c52672_i64 = arith.constant 52672 : i64
  %c52416_i64 = arith.constant 52416 : i64
  %c51392_i64 = arith.constant 51392 : i64
  %c43200_i64 = arith.constant 43200 : i64
  %c42688_i64 = arith.constant 42688 : i64
  %c74624_i64 = arith.constant 74624 : i64
  %c42624_i64 = arith.constant 42624 : i64
  %c158144_i64 = arith.constant 158144 : i64
  %c41600_i64 = arith.constant 41600 : i64
  %c41088_i64 = arith.constant 41088 : i64
  %c32896_i64 = arith.constant 32896 : i64
  %c128_i64 = arith.constant 128 : i64
  %c64_i64 = arith.constant 64 : i64
  %c0_i64 = arith.constant 0 : i64
  %cst = arith.constant 0xFF800000 : f32
  %cst_0 = arith.constant 0.000000e+00 : f32
  %c8_i32 = arith.constant 8 : i32
  %c0_i32 = arith.constant 0 : i32
  %c128_i32 = arith.constant 128 : i32
  %c1 = arith.constant 1 : index
  %c0 = arith.constant 0 : index
  %c1024_i64 = arith.constant 1024 : i64
  %cst_1 = arith.constant 0.000000e+00 : f16
  %c1_i32 = arith.constant 1 : i32
  hivm.hir.set_ffts_base_addr %arg0
  hivm.hir.set_mask_norm
  %0 = arith.muli %arg42, %arg43 : i32
  %1 = arith.muli %0, %arg44 : i32
  annotation.mark %1 {logical_block_num} : i32
  %2 = hivm.hir.get_block_idx -> i64
  %3 = arith.trunci %2 : i64 to i32
  %4 = arith.muli %arg44, %arg43 : i32
  %5 = arith.divsi %3, %4 : i32
  %6 = arith.remsi %5, %arg42 : i32
  %7 = hivm.hir.pointer_cast(%c0_i64) : memref<16xf32, #hivm.address_space<ub>>
  hivm.hir.set_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID0>]
  hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID0>]
  hivm.hir.set_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID1>]
  hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID1>]
  hivm.hir.vbrc ins(%cst : f32) outs(%7 : memref<16xf32, #hivm.address_space<ub>>)
  %8 = hivm.hir.pointer_cast(%c64_i64) : memref<16xf32, #hivm.address_space<ub>>
  hivm.hir.vbrc ins(%cst_0 : f32) outs(%8 : memref<16xf32, #hivm.address_space<ub>>)
  %9 = hivm.hir.pointer_cast(%c128_i64) : memref<16x512xf32, #hivm.address_space<ub>>
  %collapse_shape = memref.collapse_shape %9 [[0, 1]] : memref<16x512xf32, #hivm.address_space<ub>> into memref<8192xf32, #hivm.address_space<ub>>
  hivm.hir.vbrc ins(%cst_0 : f32) outs(%collapse_shape : memref<8192xf32, #hivm.address_space<ub>>)
  %10 = hivm.hir.pointer_cast(%c32896_i64) : memref<16x128xf32, #hivm.address_space<ub>>
  %collapse_shape_2 = memref.collapse_shape %10 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
  hivm.hir.vbrc ins(%cst : f32) outs(%collapse_shape_2 : memref<2048xf32, #hivm.address_space<ub>>)
  %11 = arith.muli %6, %arg41 : i32
  %12 = arith.addi %6, %c1_i32 : i32
  %13 = arith.muli %12, %arg41 : i32
  %14 = arith.minsi %arg37, %13 : i32
  %15 = arith.muli %6, %arg32 : i32
  %16 = arith.muli %6, %arg34 : i32
  %17 = hivm.hir.pointer_cast(%c41088_i64) : memref<128xi32, #hivm.address_space<ub>>
  hivm.hir.varange offset[%c0] strides[%c1] outs(%17 : memref<128xi32, #hivm.address_space<ub>>)
  %18 = arith.index_cast %15 : i32 to index
  %19 = arith.index_cast %arg33 : i32 to index
  %reinterpret_cast = memref.reinterpret_cast %arg11 to offset: [%18], sizes: [16, 128], strides: [%19, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x128xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
  %20 = arith.index_cast %16 : i32 to index
  %21 = arith.index_cast %arg35 : i32 to index
  %reinterpret_cast_3 = memref.reinterpret_cast %arg12 to offset: [%20], sizes: [16, 512], strides: [%21, 1] : memref<?xbf16, #hivm.address_space<gm>> to memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
  hivm.hir.sync_block_set[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 0
  hivm.hir.sync_block_set[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 3
  %22 = arith.index_cast %2 : i64 to index
  %23 = affine.apply affine_map<()[s0] -> (s0 * 8192)>()[%22]
  %view = memref.view %arg2[%23][] : memref<?xi8, #hivm.address_space<gm>> to memref<16x128xf32, #hivm.address_space<gm>>
  %24 = hivm.hir.pointer_cast(%c41600_i64) : memref<128xi64, #hivm.address_space<ub>>
  hivm.hir.vbrc ins(%c1024_i64 : i64) outs(%24 : memref<128xi64, #hivm.address_space<ub>>)
  %25 = hivm.hir.get_sub_block_idx -> i64
  %26 = arith.index_cast %25 : i64 to index
  %27 = arith.cmpi eq, %26, %c0 : index
  %28 = arith.index_cast %arg23 : i32 to index
  scf.for %arg45 = %11 to %14 step %c1_i32  : i32 {
    %29 = arith.muli %arg45, %arg22 : i32
    %30 = hivm.hir.pointer_cast(%c158144_i64) : memref<16x512xf32, #hivm.address_space<ub>>
    %collapse_shape_4 = memref.collapse_shape %30 [[0, 1]] : memref<16x512xf32, #hivm.address_space<ub>> into memref<8192xf32, #hivm.address_space<ub>>
    hivm.hir.pipe_barrier[<PIPE_V>]
    hivm.hir.wait_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID0>]
    hivm.hir.copy ins(%collapse_shape : memref<8192xf32, #hivm.address_space<ub>>) outs(%collapse_shape_4 : memref<8192xf32, #hivm.address_space<ub>>)
    %31 = hivm.hir.pointer_cast(%c42624_i64) : memref<16xf32, #hivm.address_space<ub>>
    hivm.hir.copy ins(%7 : memref<16xf32, #hivm.address_space<ub>>) outs(%31 : memref<16xf32, #hivm.address_space<ub>>)
    %32 = hivm.hir.pointer_cast(%c74624_i64) : memref<16xf32, #hivm.address_space<ub>>
    hivm.hir.copy ins(%8 : memref<16xf32, #hivm.address_space<ub>>) outs(%32 : memref<16xf32, #hivm.address_space<ub>>)
    %33:3 = scf.for %arg46 = %c0_i32 to %c8_i32 step %c1_i32 iter_args(%arg47 = %30, %arg48 = %31, %arg49 = %32) -> (memref<16x512xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>)  : i32 {
      %35 = arith.muli %arg46, %c128_i32 : i32
      %36 = hivm.hir.pointer_cast(%c42688_i64) : memref<128xi32, #hivm.address_space<ub>>
      hivm.hir.vadd ins(%17, %35 : memref<128xi32, #hivm.address_space<ub>>, i32) outs(%36 : memref<128xi32, #hivm.address_space<ub>>)
      hivm.hir.sync_block_wait[<VECTOR>, <PIPE_FIX>, <PIPE_S>] flag = 1
      %37 = hivm.hir.pointer_cast(%c43200_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %collapse_shape_6 = memref.collapse_shape %view [[0, 1]] : memref<16x128xf32, #hivm.address_space<gm>> into memref<2048xf32, #hivm.address_space<gm>>
      %collapse_shape_7 = memref.collapse_shape %37 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID0>]
      hivm.hir.load ins(%collapse_shape_6 : memref<2048xf32, #hivm.address_space<gm>>) outs(%collapse_shape_7 : memref<2048xf32, #hivm.address_space<ub>>) init_out_buffer = false may_implicit_transpose_with_last_axis = false
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, <EVENT_ID0>]
      hivm.hir.sync_block_set[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 0
      %38 = hivm.hir.pointer_cast(%c43200_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %collapse_shape_8 = memref.collapse_shape %38 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, <EVENT_ID0>]
      hivm.hir.vmul ins(%collapse_shape_7, %arg36 : memref<2048xf32, #hivm.address_space<ub>>, f32) outs(%collapse_shape_8 : memref<2048xf32, #hivm.address_space<ub>>)
      %39 = hivm.hir.pointer_cast(%c51392_i64) : memref<128xi64, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcast ins(%36 : memref<128xi32, #hivm.address_space<ub>>) outs(%39 : memref<128xi64, #hivm.address_space<ub>>)
      hivm.hir.set_flag[<PIPE_V>, <PIPE_S>, <EVENT_ID0>]
      %40 = hivm.hir.pointer_cast(%c52416_i64) : memref<128xi1, #hivm.address_space<ub>>
      %41 = hivm.hir.pointer_cast(%c51392_i64) : memref<128xi8, #hivm.address_space<ub>>
      hivm.hir.wait_flag[<PIPE_V>, <PIPE_S>, <EVENT_ID0>]
      scf.for %arg50 = %c0 to %c128 step %c1 {
        %79 = memref.load %39[%arg50] : memref<128xi64, #hivm.address_space<ub>>
        %80 = memref.load %24[%arg50] : memref<128xi64, #hivm.address_space<ub>>
        %81 = arith.cmpi slt, %79, %80 : i64
        %82 = arith.extui %81 : i1 to i8
        memref.store %82, %41[%arg50] : memref<128xi8, #hivm.address_space<ub>>
      }
      hivm.hir.set_flag[<PIPE_S>, <PIPE_V>, <EVENT_ID0>]
      %42 = hivm.hir.pointer_cast(%c52416_i64) : memref<128xf16, #hivm.address_space<ub>>
      hivm.hir.wait_flag[<PIPE_S>, <PIPE_V>, <EVENT_ID0>]
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcast ins(%41 : memref<128xi8, #hivm.address_space<ub>>) outs(%42 : memref<128xf16, #hivm.address_space<ub>>)
      %43 = hivm.hir.pointer_cast(%c52672_i64) : memref<128xf16, #hivm.address_space<ub>>
      hivm.hir.vbrc ins(%cst_1 : f16) outs(%43 : memref<128xf16, #hivm.address_space<ub>>)
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcmp ins(%42, %43 : memref<128xf16, #hivm.address_space<ub>>, memref<128xf16, #hivm.address_space<ub>>) outs(%40 : memref<128xi1, #hivm.address_space<ub>>) compare_mode = <ne>
      %44 = hivm.hir.pointer_cast(%c52928_i64) : memref<128xf16, #hivm.address_space<ub>>
      %45 = hivm.hir.pointer_cast(%c53184_i64) : memref<48xf16, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcast ins(%40 : memref<128xi1, #hivm.address_space<ub>>) outs(%44 : memref<128xf16, #hivm.address_space<ub>>) temp_buffer(%45 : memref<48xf16, #hivm.address_space<ub>>) round_mode = <trunc>
      %expand_shape = memref.expand_shape %44 [[0, 1]] output_shape [1, 128] : memref<128xf16, #hivm.address_space<ub>> into memref<1x128xf16, #hivm.address_space<ub>>
      %46 = hivm.hir.pointer_cast(%c53280_i64) : memref<16x128xf16, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vbrc ins(%expand_shape : memref<1x128xf16, #hivm.address_space<ub>>) outs(%46 : memref<16x128xf16, #hivm.address_space<ub>>) broadcast_dims = [0]
      %47 = hivm.hir.pointer_cast(%c53280_i64) : memref<16x128xi1, #hivm.address_space<ub>>
      %collapse_shape_9 = memref.collapse_shape %46 [[0, 1]] : memref<16x128xf16, #hivm.address_space<ub>> into memref<2048xf16, #hivm.address_space<ub>>
      %collapse_shape_10 = memref.collapse_shape %47 [[0, 1]] : memref<16x128xi1, #hivm.address_space<ub>> into memref<2048xi1, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcmp ins(%collapse_shape_9, %cst_1 : memref<2048xf16, #hivm.address_space<ub>>, f16) outs(%collapse_shape_10 : memref<2048xi1, #hivm.address_space<ub>>)
      %48 = hivm.hir.pointer_cast(%c53280_i64) : memref<16x128xi1, #hivm.address_space<ub>>
      %collapse_shape_11 = memref.collapse_shape %48 [[0, 1]] : memref<16x128xi1, #hivm.address_space<ub>> into memref<2048xi1, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vnot ins(%collapse_shape_10 : memref<2048xi1, #hivm.address_space<ub>>) outs(%collapse_shape_11 : memref<2048xi1, #hivm.address_space<ub>>)
      %49 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %collapse_shape_12 = memref.collapse_shape %49 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      %50 = hivm.hir.pointer_cast(%c65568_i64) : memref<8xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.wait_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID1>]
      hivm.hir.vsel ins(%collapse_shape_11, %collapse_shape_8, %collapse_shape_2 : memref<2048xi1, #hivm.address_space<ub>>, memref<2048xf32, #hivm.address_space<ub>>, memref<2048xf32, #hivm.address_space<ub>>) outs(%collapse_shape_12 : memref<2048xf32, #hivm.address_space<ub>>) temp_buffer(%50 : memref<8xf32, #hivm.address_space<ub>>)
      hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID0>]
      %51 = hivm.hir.pointer_cast(%c65600_i64) : memref<16x1xf32, #hivm.address_space<ub>>
      %52 = hivm.hir.pointer_cast(%c65664_i64) : memref<1024xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vreduce <max> ins(%49 : memref<16x128xf32, #hivm.address_space<ub>>) outs(%51 : memref<16x1xf32, #hivm.address_space<ub>>) temp_buffer(%52 : memref<1024xf32, #hivm.address_space<ub>>) reduce_dims = [1]
      %collapse_shape_13 = memref.collapse_shape %51 [[0, 1]] : memref<16x1xf32, #hivm.address_space<ub>> into memref<16xf32, #hivm.address_space<ub>>
      %53 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %54 = hivm.hir.pointer_cast(%c69760_i64) : memref<128xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vsub ins(%49, %51 : memref<16x128xf32, #hivm.address_space<ub>>, memref<16x1xf32, #hivm.address_space<ub>>) outs(%53 : memref<16x128xf32, #hivm.address_space<ub>>) temp_buffer(%54 : memref<128xf32, #hivm.address_space<ub>>) broadcast = [1]
      %55 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %collapse_shape_14 = memref.collapse_shape %53 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      %collapse_shape_15 = memref.collapse_shape %55 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vexp ins(%collapse_shape_14 : memref<2048xf32, #hivm.address_space<ub>>) outs(%collapse_shape_15 : memref<2048xf32, #hivm.address_space<ub>>)
      %56 = hivm.hir.pointer_cast(%c70272_i64) : memref<16x1xf32, #hivm.address_space<ub>>
      %57 = hivm.hir.pointer_cast(%c70336_i64) : memref<1024xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vreduce <sum> ins(%55 : memref<16x128xf32, #hivm.address_space<ub>>) outs(%56 : memref<16x1xf32, #hivm.address_space<ub>>) temp_buffer(%57 : memref<1024xf32, #hivm.address_space<ub>>) reduce_dims = [1]
      %collapse_shape_16 = memref.collapse_shape %56 [[0, 1]] : memref<16x1xf32, #hivm.address_space<ub>> into memref<16xf32, #hivm.address_space<ub>>
      %58 = hivm.hir.pointer_cast(%c74432_i64) : memref<16xi1, #hivm.address_space<ub>>
      hivm.hir.vcmp ins(%arg48, %collapse_shape_13 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%58 : memref<16xi1, #hivm.address_space<ub>>) compare_mode = <gt>
      %59 = hivm.hir.pointer_cast(%c74464_i64) : memref<16xf32, #hivm.address_space<ub>>
      %60 = hivm.hir.pointer_cast(%c74528_i64) : memref<8xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vsel ins(%58, %arg48, %collapse_shape_13 : memref<16xi1, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%59 : memref<16xf32, #hivm.address_space<ub>>) temp_buffer(%60 : memref<8xf32, #hivm.address_space<ub>>)
      %61 = hivm.hir.pointer_cast(%c74560_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vsub ins(%arg48, %59 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%61 : memref<16xf32, #hivm.address_space<ub>>)
      %62 = hivm.hir.pointer_cast(%c74560_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vexp ins(%61 : memref<16xf32, #hivm.address_space<ub>>) outs(%62 : memref<16xf32, #hivm.address_space<ub>>)
      %63 = hivm.hir.pointer_cast(%c65600_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.vsub ins(%collapse_shape_13, %59 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%63 : memref<16xf32, #hivm.address_space<ub>>)
      %64 = hivm.hir.pointer_cast(%c65600_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vexp ins(%63 : memref<16xf32, #hivm.address_space<ub>>) outs(%64 : memref<16xf32, #hivm.address_space<ub>>)
      %65 = hivm.hir.pointer_cast(%c74560_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.vmul ins(%62, %arg49 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%65 : memref<16xf32, #hivm.address_space<ub>>)
      %66 = hivm.hir.pointer_cast(%c70272_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vmul ins(%64, %collapse_shape_16 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%66 : memref<16xf32, #hivm.address_space<ub>>)
      %67 = hivm.hir.pointer_cast(%c74624_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vadd ins(%65, %66 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%67 : memref<16xf32, #hivm.address_space<ub>>)
      %68 = hivm.hir.pointer_cast(%c74560_i64) : memref<16xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vdiv ins(%65, %67 : memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>) outs(%68 : memref<16xf32, #hivm.address_space<ub>>)
      %expand_shape_17 = memref.expand_shape %64 [[0, 1]] output_shape [16, 1] : memref<16xf32, #hivm.address_space<ub>> into memref<16x1xf32, #hivm.address_space<ub>>
      %69 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %70 = hivm.hir.pointer_cast(%c74688_i64) : memref<128xf32, #hivm.address_space<ub>>
      hivm.hir.vmul ins(%expand_shape_17, %55 : memref<16x1xf32, #hivm.address_space<ub>>, memref<16x128xf32, #hivm.address_space<ub>>) outs(%69 : memref<16x128xf32, #hivm.address_space<ub>>) temp_buffer(%70 : memref<128xf32, #hivm.address_space<ub>>) broadcast = [1]
      %expand_shape_18 = memref.expand_shape %67 [[0, 1]] output_shape [16, 1] : memref<16xf32, #hivm.address_space<ub>> into memref<16x1xf32, #hivm.address_space<ub>>
      %71 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xf32, #hivm.address_space<ub>>
      %72 = hivm.hir.pointer_cast(%c75200_i64) : memref<128xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vdiv ins(%69, %expand_shape_18 : memref<16x128xf32, #hivm.address_space<ub>>, memref<16x1xf32, #hivm.address_space<ub>>) outs(%71 : memref<16x128xf32, #hivm.address_space<ub>>) temp_buffer(%72 : memref<128xf32, #hivm.address_space<ub>>) broadcast = [1]
      %73 = hivm.hir.pointer_cast(%c57376_i64) : memref<16x128xbf16, #hivm.address_space<ub>>
      %collapse_shape_19 = memref.collapse_shape %71 [[0, 1]] : memref<16x128xf32, #hivm.address_space<ub>> into memref<2048xf32, #hivm.address_space<ub>>
      %collapse_shape_20 = memref.collapse_shape %73 [[0, 1]] : memref<16x128xbf16, #hivm.address_space<ub>> into memref<2048xbf16, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vcast ins(%collapse_shape_19 : memref<2048xf32, #hivm.address_space<ub>>) outs(%collapse_shape_20 : memref<2048xbf16, #hivm.address_space<ub>>)
      hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, <EVENT_ID0>]
      hivm.hir.sync_block_wait[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 2
      hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, <EVENT_ID0>]
      scf.if %27 {
        hivm.hir.store ins(%73 : memref<16x128xbf16, #hivm.address_space<ub>>) outs(%reinterpret_cast : memref<16x128xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>)
      } {limit_sub_block_id0}
      hivm.hir.set_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID1>]
      hivm.hir.sync_block_set[<VECTOR>, <PIPE_MTE3>, <PIPE_S>] flag = 1
      %74 = hivm.hir.pointer_cast(%c75712_i64) : memref<16x512xbf16, #hivm.address_space<ub>>
      hivm.hir.sync_block_wait[<VECTOR>, <PIPE_FIX>, <PIPE_S>] flag = 1
      hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID1>]
      hivm.hir.load ins(%reinterpret_cast_3 : memref<16x512xbf16, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>) outs(%74 : memref<16x512xbf16, #hivm.address_space<ub>>) init_out_buffer = false may_implicit_transpose_with_last_axis = false
      hivm.hir.set_flag[<PIPE_MTE2>, <PIPE_V>, <EVENT_ID1>]
      hivm.hir.sync_block_set[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 3
      %expand_shape_21 = memref.expand_shape %68 [[0, 1]] output_shape [16, 1] : memref<16xf32, #hivm.address_space<ub>> into memref<16x1xf32, #hivm.address_space<ub>>
      %75 = hivm.hir.pointer_cast(%c92096_i64) : memref<16x512xf32, #hivm.address_space<ub>>
      %76 = hivm.hir.pointer_cast(%c124864_i64) : memref<128xf32, #hivm.address_space<ub>>
      hivm.hir.vmul ins(%arg47, %expand_shape_21 : memref<16x512xf32, #hivm.address_space<ub>>, memref<16x1xf32, #hivm.address_space<ub>>) outs(%75 : memref<16x512xf32, #hivm.address_space<ub>>) temp_buffer(%76 : memref<128xf32, #hivm.address_space<ub>>) broadcast = [1]
      %77 = hivm.hir.pointer_cast(%c125376_i64) : memref<16x512xf32, #hivm.address_space<ub>>
      %collapse_shape_22 = memref.collapse_shape %74 [[0, 1]] : memref<16x512xbf16, #hivm.address_space<ub>> into memref<8192xbf16, #hivm.address_space<ub>>
      %collapse_shape_23 = memref.collapse_shape %77 [[0, 1]] : memref<16x512xf32, #hivm.address_space<ub>> into memref<8192xf32, #hivm.address_space<ub>>
      hivm.hir.wait_flag[<PIPE_MTE2>, <PIPE_V>, <EVENT_ID1>]
      hivm.hir.vcast ins(%collapse_shape_22 : memref<8192xbf16, #hivm.address_space<ub>>) outs(%collapse_shape_23 : memref<8192xf32, #hivm.address_space<ub>>)
      hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID1>]
      %78 = hivm.hir.pointer_cast(%c158144_i64) : memref<16x512xf32, #hivm.address_space<ub>>
      %collapse_shape_24 = memref.collapse_shape %75 [[0, 1]] : memref<16x512xf32, #hivm.address_space<ub>> into memref<8192xf32, #hivm.address_space<ub>>
      %collapse_shape_25 = memref.collapse_shape %78 [[0, 1]] : memref<16x512xf32, #hivm.address_space<ub>> into memref<8192xf32, #hivm.address_space<ub>>
      hivm.hir.pipe_barrier[<PIPE_V>]
      hivm.hir.vadd ins(%collapse_shape_24, %collapse_shape_23 : memref<8192xf32, #hivm.address_space<ub>>, memref<8192xf32, #hivm.address_space<ub>>) outs(%collapse_shape_25 : memref<8192xf32, #hivm.address_space<ub>>)
      hivm.hir.copy ins(%59 : memref<16xf32, #hivm.address_space<ub>>) outs(%arg48 : memref<16xf32, #hivm.address_space<ub>>)
      scf.yield %78, %arg48, %67 : memref<16x512xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>, memref<16xf32, #hivm.address_space<ub>>
    }
    hivm.hir.set_flag[<PIPE_V>, <PIPE_MTE3>, <EVENT_ID1>]
    %34 = arith.index_cast %29 : i32 to index
    %reinterpret_cast_5 = memref.reinterpret_cast %arg7 to offset: [%34], sizes: [16, 512], strides: [%28, 1] : memref<?xf32, #hivm.address_space<gm>> to memref<16x512xf32, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>
    hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE3>, <EVENT_ID1>]
    scf.if %27 {
      hivm.hir.store ins(%33#0 : memref<16x512xf32, #hivm.address_space<ub>>) outs(%reinterpret_cast_5 : memref<16x512xf32, strided<[?, 1], offset: ?>, #hivm.address_space<gm>>)
    } {limit_sub_block_id0}
    hivm.hir.set_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID0>]
  }
  hivm.hir.pipe_barrier[<PIPE_ALL>]
  hivm.hir.wait_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID0>]
  hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID0>]
  hivm.hir.wait_flag[<PIPE_MTE3>, <PIPE_V>, <EVENT_ID1>]
  hivm.hir.wait_flag[<PIPE_V>, <PIPE_MTE2>, <EVENT_ID1>]
  hivm.hir.sync_block_wait[<VECTOR>, <PIPE_MTE2>, <PIPE_S>] flag = 2
  return
}

