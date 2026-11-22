(module
  (import "wasi_snapshot_preview1" "fd_write" (func $write (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 2)
  ;; The second initial page will be zero at the checkpoint.
  (data (i32.const 65536) "A")
  (func (export "_start")
    (i32.store8 (i32.const 65536) (i32.const 0))
    (drop (memory.grow (i32.const 2)))
    ;; The first new page stays zero. The second new page must restore 'Z'.
    (i32.store8 (i32.const 196608) (i32.const 90))
    (drop (call $write (i32.const 1) (i32.const 0) (i32.const 0) (i32.const 16)))
    (call $exit (i32.or
      (i32.or (i32.load8_u (i32.const 65536)) (i32.load8_u (i32.const 131072)))
      (i32.ne (i32.load8_u (i32.const 196608)) (i32.const 90))))))
