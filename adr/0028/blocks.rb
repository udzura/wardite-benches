# frozen_string_literal: true
require "wardite"
require "json"

module BlockProfile
  E = Wardite::Efflorescence
  ROWS = []
  def instrument_function(fn)
    leaders = E::Analysis.new(fn).leaders
    rewrite = E::Rewrite.new(fn)
    fn.instructions.each_with_index do |insn, pc|
      rewrite.mark(pc)
      if leaders[pc] == 1
        id = ROWS.size
        ROWS << [fn.index, pc, 0]
        rewrite.emit(E::Instruction.new([E::Opcode::PROFILE, id, 0, 0]))
      end
      rewrite.emit(insn)
    end
    rewrite.finish
  end
end
module BlockCounts
  def record(id, _r, _w)
    BlockProfile::ROWS.fetch(id)[2] += 1
  end
  def report = "blocks=#{BlockProfile::ROWS.size}"
  def opcode_report = ""
end
BlockProfile::E::Instrumentation.prepend(BlockProfile)
BlockProfile::E::Metrics.prepend(BlockCounts)
at_exit { File.write(ENV.fetch("BLOCK_PROFILE"), JSON.generate(BlockProfile::ROWS.sort_by { |row| -row.last }.first(30))) }
