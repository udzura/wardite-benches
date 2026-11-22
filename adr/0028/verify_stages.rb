# frozen_string_literal: true

require "wardite"

e = Wardite::Efflorescence
instance = Wardite.new(path: ARGV.fetch(0), enable_wasi: false)
config = e::Configuration.new(%i[fold cfg dce exit_copy licm compact cse])
ir = e::Optimizer.new(config).optimize(instance.runtime.semantic_ir)
inline = ir.function_at(instance.export_section.exports.fetch("inline").index)
raise "expected an inlined addition" if inline.instructions.any? { |op| op[0] == e::Opcode::CALL }
validator = e::RegisterValidation.new
[e::Passes::ConstantFolding, e::Passes::ControlFlow, e::Passes::DeadCode,
 e::Passes::ExitCopies, e::Passes::LoopInvariants].each do |stage|
  pass = stage.new
  ir.functions.each do |function|
    pass.run(function)
    validator.validate(function, ir, tags: instance.tags)
  end
  if stage == e::Passes::ConstantFolding
    ret = inline.instructions.fetch(0)
    unless inline.instructions.size == 1 && ret[0] == e::Opcode::RETURN && inline.initial_value(ret[1]) == 1
      raise "expected the inlined sum to fold to return 1"
    end
  end
  puts "#{stage.name.split('::').last}: validated #{ir.functions.size} functions"
end
