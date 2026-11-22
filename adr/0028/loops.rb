# frozen_string_literal: true

# Run the real LICM selection on a copy. Count the original executions and the
# preheader entries that would replace them, leaving the workload MIR intact.
require "wardite"
require "json"

module LoopCensus
  E = Wardite::Efflorescence
  SITES = []
  GROUPS = {}
  class << self
    attr_accessor :positions, :previous, :pending, :groups
  end
end

module TracePlacement
  def mark(pc)
    if LoopCensus.positions
      unless LoopCensus.pending.empty?
        LoopCensus.groups[pc] = LoopCensus.pending
        LoopCensus.pending = []
      end
      LoopCensus.previous = pc
    end
    super
  end

  def emit(insn)
    if LoopCensus.positions
      original = LoopCensus.positions.fetch(insn.object_id)
      LoopCensus.pending << original unless original == LoopCensus.previous
    end
    super
  end
end

module SelectInvariants
  def run(function)
    copy = function.copy
    LoopCensus.positions = copy.instructions.each_with_index.to_h { |op, pc| [op.object_id, pc] }
    LoopCensus.previous = -1
    LoopCensus.pending = []
    LoopCensus.groups = {}
    super(copy)
    LoopCensus::GROUPS[function.index] = LoopCensus.groups
  ensure
    LoopCensus.positions = nil
  end
end

module CountPlacement
  include LoopCensus
  def instrument_function(function)
    groups = GROUPS.fetch(function.index)
    return if groups.empty?
    preheaders = {}
    body = {}
    groups.each do |first, candidates|
      preheaders[first] = SITES.size
      SITES << [function.index, first, first, "entry", 0]
      candidates.each do |pc|
        body[pc] = SITES.size
        SITES << [function.index, first, pc, E::Opcode::NAMES.fetch(function.instructions.fetch(pc)[0]), 0]
      end
    end
    rewrite = E::Rewrite.new(function)
    function.instructions.each_with_index do |insn, pc|
      if (id = preheaders[pc])
        rewrite.emit(E::Instruction.new([E::Opcode::PROFILE, id, 0, 0]))
      end
      rewrite.mark(pc)
      if (id = body[pc])
        rewrite.emit(E::Instruction.new([E::Opcode::PROFILE, id, 0, 0]))
      end
      rewrite.emit(insn)
    end
    rewrite.finish
  end
end

module LoopCounts
  def record(id, _r, _w)
    LoopCensus::SITES.fetch(id)[4] += 1
  end
  def report = "candidate_sites=#{LoopCensus::SITES.size}"
  def opcode_report = ""
end

LoopCensus::E::Passes::LoopInvariants.prepend(SelectInvariants)
LoopCensus::E::Rewrite.prepend(TracePlacement)
LoopCensus::E::Instrumentation.prepend(CountPlacement)
LoopCensus::E::Metrics.prepend(LoopCounts)
at_exit { File.write(ENV.fetch("LOOP_CENSUS"), JSON.generate(LoopCensus::SITES)) }
