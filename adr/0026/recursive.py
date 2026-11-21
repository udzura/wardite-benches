"""Emit a WAT module whose deepest frame executes the large arithmetic body."""

WIDTH = 96


def module():
    steps = "\n".join(f"      local.get $sum i32.const {i} i32.add local.set $sum"
                      for i in range(1, WIDTH + 1))
    return f"""(module
  (func $descend (param $depth i32) (result i32) (local $sum i32)
    local.get $depth
    if (result i32)
      local.get $depth i32.const 1 i32.sub call $descend
      i32.const 1 i32.add
    else
{steps}
      local.get $sum
    end)
  (func (export "run") (param $depth i32) (param $passes i32) (result i32)
    (local $total i32)
    loop $again
      local.get $total local.get $depth call $descend i32.add local.set $total
      local.get $passes i32.const 1 i32.sub local.tee $passes br_if $again
    end
    local.get $total))"""


if __name__ == "__main__":
    print(module())
