(module
  (memory 1)
  (tag $tag (param i32))
  (func $add (param i32 i32) (result i32)
    local.get 0 local.get 1 i32.add)
  (func (export "inline") (result i32)
    i32.const -1 i32.const 2 call $add)
  (func (export "width") (result i32)
    i64.const 0x7fffffffffffffff i64.const 1 i64.add
    i64.const 65 i64.shr_u i32.wrap_i64
    i32.const 0xfffffffe i32.const 0xffffffff i32.mul i32.xor)
  (func (export "signed") (result i32)
    i64.const -1 i64.const 1 i64.lt_s
    i32.const -1 i32.const 1 i32.lt_u i32.add)
  (func (export "join") (param i32) (result i32) (local i32)
    i32.const 7 local.set 1
    local.get 0 if i32.const 9 local.set 1 end
    local.get 1 i32.const 1 i32.add)
  (func (export "condition") (result i32)
    i32.const 2 i32.const 3 i32.lt_u
    if (result i32) i32.const 7 else unreachable end)
  (func (export "caught") (result i32)
    block $catch (result i32)
      try_table (catch $tag $catch)
        i32.const 73 throw $tag
      end unreachable
    end)
  (func (export "loop") (param $n i32) (param $x i32) (result i32)
    (local $sum i32)
    i32.const 9 local.set $sum
    block $done
      loop $back
        local.get $n i32.eqz br_if $done
        local.get $sum local.get $x i32.const 5 i32.and i32.add local.set $sum
        local.get $n i32.const 1 i32.sub local.set $n br $back
      end
    end local.get $sum)
  (func (export "dead") (param i32) (result i32)
    local.get 0 i32.const 1 i32.add i32.const 3 i32.mul drop
    i32.const 5)
  (func (export "edge") (param i32 i32 i32) (param $rounds i32) (result i32) (local $index i32)
    i32.const 1 local.get 0 i32.store8
    i32.const 2 local.get 1 i32.store8
    i32.const 3 local.get 2 i32.store8
    block $exit
      local.get $rounds i32.eqz br_if $exit
      loop $again
      i32.const 3 local.set $index i32.const 1 i64.load8_u i64.const 255 i64.eq br_if $exit
      i32.const 7 local.set $index i32.const 2 i64.load8_u i64.const 255 i64.eq br_if $exit
      i32.const 9 local.set $index i32.const 3 i64.load8_u i64.const 255 i64.eq br_if $exit
      i32.const 13 local.set $index
      local.get $rounds i32.const 1 i32.sub local.tee $rounds br_if $again
      end
    end local.get $index)
  (func (export "trap") (param $addr i32) (param $divisor i32)
    i32.const 0 i32.const 11 i32.store8
    local.get $addr i32.load drop
    i32.const 0 i32.const 22 i32.store8
    i32.const 1 local.get $divisor i32.div_u drop
    i32.const 0 i32.const 33 i32.store8)
  (func (export "byte") (result i32) i32.const 0 i32.load8_u))
