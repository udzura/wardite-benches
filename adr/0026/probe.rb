# frozen_string_literal: true

# Preload in a separate CRuby CLI process. Leave timing runs uninstrumented.
require "wardite"

module FrameCounts
  TOTAL = {acquired: 0, created: 0, copied_slots: 0}

  def acquire(destination)
    previous = created
    frame = super
    TOTAL[:acquired] += 1
    if created > previous
      TOTAL[:created] += 1
      TOTAL[:copied_slots] += frame.registers.size
    end
    frame
  end
end

Wardite::Efflorescence::FramePool.prepend(FrameCounts)
at_exit { warn FrameCounts::TOTAL.map { |name, value| "#{name}=#{value}" }.join(" ") }
