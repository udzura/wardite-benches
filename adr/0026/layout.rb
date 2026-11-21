# frozen_string_literal: true

require "wardite"

include Wardite::Efflorescence
fn = Function.new(0, [:i32], [:i64], 1, local_types: [:f64])
fn.allocate_register(0)                        # 2 unused
answer = fn.allocate_constant(-42, type: :i64) # 3 -> 2
fn.allocate_constant(456)                      # 4 unused
dest = fn.allocate_register(0, type: :i64)     # 5 -> 3, only written
arg = fn.allocate_constant(17)                 # 6 -> 4, side tables only
exn = fn.allocate_register(0, type: :exnref)   # 7 -> 5, catch destination
fn.replace_instructions([
  Instruction.new([Opcode::COPY, dest, answer]),
  Instruction.new([Opcode::RETURN, answer])
])
# Side descriptors can outlive rewritten instructions. Every retained descriptor
# must use the final numbering when it is subsequently serialized or copied.
fn.dynamic_sites << DynamicCallSite.new(0, [arg, arg], [:i32, :i32], [])
fn.memory_sites << MemorySite.new([arg, arg, arg])
fn.throw_sites << ThrowSite.new(0, [arg])
clause = CatchTarget.new(0, [dest], exn, 1, 0)
fn.handlers << HandlerDescriptor.new([clause])

2.times do
  fn.compact_registers!
  raise "types/order" unless fn.register_types == %i[i32 f64 i64 i64 i32 exnref]
  raise "initial values" unless fn.initial_registers == [0, 0, -42, 0, 17, 0]
  raise "constants" unless fn.constant_registers == [2, 4]
  raise "instructions" unless fn.instructions.map(&:operands) == [[Opcode::COPY, 3, 2], [Opcode::RETURN, 2]]
  raise "dynamic" unless fn.dynamic_sites.first.arguments == [4, 4]
  raise "bulk" unless fn.memory_sites.first.sources == [4, 4, 4]
  raise "throw" unless fn.throw_sites.first.payload_registers == [4]
  raise "catch" unless clause.destinations == [3, 5]
end
puts "slot layout and idempotence passed"
