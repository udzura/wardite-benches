(module
  (type $unary (func (param i32) (result i32)))
  (memory 1)
  (table 1 funcref)
  (elem (i32.const 0) $rem)
  (tag $error (param i32))
  (func $rem (export "rem") (type $unary)
    i32.const 2345 drop
    i32.const 85 local.get 0 i32.rem_u)
  (func (export "run") (param $divisor i32) (result i32)
    (local $saved exnref)
    ;; A discarded constant before the side-table operands forces renumbering.
    i32.const 1234 drop
    i32.const 17 i32.const 42 i32.const 1 memory.fill
    block $outer (result i32)
      try_table (catch $error $outer)
        block $caught (result i32 exnref)
          try_table (catch_ref $error $caught)
            i32.const 17 i32.load8_u
            local.get $divisor i32.const 0 call_indirect (type $unary)
            i32.add local.get $divisor call $rem i32.add
            throw $error
          end unreachable
        end
        local.set $saved i32.const 44 i32.ne if unreachable end
        local.get $saved throw_ref
      end unreachable
    end))
