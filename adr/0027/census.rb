# frozen_string_literal: true

# Run under CRuby with --mir-profile and CSE disabled. Add one counter at the
# entry of each candidate block, leaving the existing fused instructions intact.
require "wardite"
require "json"

module CandidateCensus
  E = Wardite::Efflorescence
  OP = E::Opcode
  COMMUTATIVE = %w[I32_ADD I32_MUL I32_AND I32_OR I32_XOR I32_EQ I32_NE I64_ADD I64_MUL I64_AND I64_OR I64_XOR I64_EQ I64_NE].freeze
  BLOCKS = []

  def instrument_function(function)
    leaders = E::Analysis.new(function).leaders
    starts = leaders.each_index.select { |pc| leaders[pc] == 1 }
    rewrite = E::Rewrite.new(function)
    (starts << function.instructions.size).each_cons(2) do |start, limit|
      values = Hash.new { |_, slot| -1 - slot }
      expressions = {}
      holders = Hash.new(0)
      duplicates = Hash.new(0)
      (start...limit).each do |pc|
        insn = function.instructions.fetch(pc)
        op = insn[0]
        # Expand the head for static inspection, counting the block only once.
        op = OP::SEQUENCE_HEADS.fetch(op - OP::I32_TABLE_STORE8) if op >= OP::I32_TABLE_STORE8
        dest = OP.destination(insn)
        next if dest < 0
        number = pc
        if op == OP::COPY
          number = values[insn[2]]
        elsif (OP::I32_ADD..OP::I32_EQZ).cover?(op) || (OP::I32_ADD_IMM..OP::I32_SHR_U_IMM).cover?(op) ||
              (OP::I32_EQ..OP::I32_POPCNT).cover?(op) || (OP::I32_AND..OP::I32_EXTEND16_S).cover?(op) ||
              (OP::I64_EQZ..OP::I64_MUL).cover?(op)
          key = insn.operands.dup
          key[0] = op
          key[1] = 0
          OP.read_positions(insn).each { |pos| key[pos] = values[insn[pos]] }
          key[2], key[3] = key[3], key[2] if COMMUTATIVE.include?(OP::NAMES[op]) && key[2] > key[3]
          if (previous = expressions[key]) && holders[previous].positive?
            duplicates[OP::NAMES.fetch(op)] += 1
            number = previous
          end
          expressions[key] = number
        end
        holders[values[dest]] -= 1
        values[dest] = number
        holders[number] += 1
      end
      (start...limit).each do |pc|
        rewrite.mark(pc)
        if pc == start && !duplicates.empty?
          id = BLOCKS.size
          BLOCKS << { function: function.index, start: start, duplicates: duplicates, entries: 0 }
          rewrite.emit(E::Instruction.new([OP::PROFILE, id, 0, 0]))
        end
        rewrite.emit(function.instructions.fetch(pc))
      end
    end
    rewrite.finish
  end
end

module BlockCounters
  def report
    "candidate_blocks=#{CandidateCensus::BLOCKS.size}"
  end

  def opcode_report
    counts = Hash.new(0)
    CandidateCensus::BLOCKS.each do |block|
      block[:duplicates].each { |op, n| counts[op] += n * block[:entries] }
    end
    counts.map { |op, n| "weighted #{op} #{n}" }.join("\n")
  end

  def record(id, _reads, _writes)
    CandidateCensus::BLOCKS.fetch(id)[:entries] += 1
  end
end
CandidateCensus::E::Instrumentation.prepend(CandidateCensus)
CandidateCensus::E::Metrics.prepend(BlockCounters)
at_exit { File.write(ENV.fetch("CSE_CENSUS"), JSON.generate(CandidateCensus::BLOCKS)) }
