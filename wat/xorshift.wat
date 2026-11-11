(module
  (func (export "xorshift") (param $rounds i32) (param $state i32) (result i32)
    (block $done
      (loop $next
        (br_if $done (i32.eqz (local.get $rounds)))

        (local.set $state
          (i32.xor (local.get $state) (i32.shl (local.get $state) (i32.const 13))))
        (local.set $state
          (i32.xor (local.get $state) (i32.shr_u (local.get $state) (i32.const 17))))
        (local.set $state
          (i32.xor (local.get $state) (i32.shl (local.get $state) (i32.const 5))))

        (local.set $rounds (i32.sub (local.get $rounds) (i32.const 1)))
        (br $next)))

    (local.get $state)))
