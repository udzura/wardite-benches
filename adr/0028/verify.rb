# frozen_string_literal: true
# rbs_inline: enabled
require "wardite"

path, cache, mode, phase = ARGV
passes = %i[fold cfg dce exit_copy licm]
enabled = mode == "none" ? [] : (mode == "all" ? passes : mode.split("+").map(&:to_sym))
instance = File.open(path, "rb") do |file|
  Wardite::BinaryLoader.load_from_buffer(file, enable_wasi: false,
    enabled_optimizations: enabled, disabled_optimizations: passes - enabled,
    mir_cache: phase == "lazy" ? nil : cache)
end
vm = instance.runtime
raise "wrong runtime" unless vm.is_a?(Wardite::Efflorescence::VM)
raise "wrong cache phase #{phase}" unless vm.mir_cache_hit == (phase == "hit")

module Check
  # @rbs vm: Wardite::Efflorescence::VM
  # @rbs name: Symbol
  # @rbs args: Array[Object]
  # @rbs expected: Integer
  # @rbs return: void
  def self.value(vm, name, args, expected)
    actual = vm.call_unboxed(name, args)
    raise "#{name} #{args.inspect}: #{actual} != #{expected}" unless actual == expected
  end
end
Check.value(vm, :inline, [], 1)
Check.value(vm, :width, [], 2)
Check.value(vm, :signed, [], 1)
Check.value(vm, :join, [0], 8)
Check.value(vm, :join, [1], 10)
Check.value(vm, :condition, [], 7)
Check.value(vm, :caught, [], 73)
Check.value(vm, :dead, [71], 5)
[0, 1, 100].each { |n| Check.value(vm, :loop, [n, 5], 9 + n*5) }
Check.value(vm, :edge, [255, 0, 0, 1], 3)
Check.value(vm, :edge, [0, 255, 0, 1], 7)
Check.value(vm, :edge, [0, 0, 255, 1], 9)
Check.value(vm, :edge, [0, 0, 0, 8], 13)
[65536, 0].each do |addr|
  begin
    vm.call_unboxed(:trap, [addr, 0])
    raise "missing trap"
  rescue Wardite::EvalError => error
    expected = addr == 0 ? "integer divide by zero" : "out of bounds memory access"
    raise "wrong trap: #{error.message}" unless error.message.include?(expected)
  end
  Check.value(vm, :byte, [], addr == 0 ? 22 : 11)
end
puts "#{mode} #{phase}: ok"
