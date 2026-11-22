# frozen_string_literal: true
require "wardite"
require "json"

e = Wardite::Efflorescence
fn = Wardite.new(path: ARGV.fetch(0)).runtime.optimized_ir.functions.find do |body|
  body.instructions.count { |op| op[0] == e::Opcode::I64_BYTE_LOOKUP } == 31
end
abort "expected the instrumented base64 0.22.1 decoder" unless fn
# Fused byte lookups retain all four primitive operands and destinations.
# A temporary read only inside this one fusion doesn't escape the handler.
reads = Hash.new(0)
fn.instructions.each do |op|
  if op[0] == e::Opcode::I64_BYTE_LOOKUP
    op = e::Instruction.new([e::Opcode::I32_ADD_IMM, op[1], op[2], op[3]])
  end
  fn.reads(op).each { |r| reads[r] += 1 }
end
dead = {}
fn.bytecode.each_slice(4).with_index do |(op, *), i|
  next unless op == e::Opcode::I64_BYTE_LOOKUP
  pc = 4 * i
  slots = [1, 5, 9, 13].map { |off| fn.bytecode.fetch(pc + off) }
  dead[pc] = slots.take(3).each_index.select do |j|
    r = slots[j]
    r >= fn.parameter_count + fn.local_count && slots.count(r) == 1 && reads[r] == 1
  end
end
# Reuse Wardite's own definition of slot traffic, including forwarding
# within an already fused four-op byte lookup.
copy = fn.copy
e::Instrumentation.new.instrument_function(copy)
traffic = {}
copy.instructions.each do |op|
  next unless op[0] == e::Opcode::PROFILE
  next if %w[CALL CALL_HOST CALL_INDIRECT].include?(e::Opcode::NAMES[op[1]])
  traffic[op[1]] = [op[2], op[3]]
end
puts JSON.generate(traffic: traffic, code: fn.bytecode, count: fn.register_count, names: e::Opcode::NAMES, dead: dead)
