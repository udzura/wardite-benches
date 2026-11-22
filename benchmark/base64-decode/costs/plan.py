"""Find the successful 32-symbol path in the lowered, timed decoder."""
from collections import Counter
from functools import cache


def trace(code, names):
    latches = [(p, code[p+2]) for p in range(0, len(code), 4)
               if names[code[p]] == "BR_IF" and code[p+2] < p and
               sum(names[code[i]] == "I64_BYTE_LOOKUP" for i in range(code[p+2], p, 4)) == 31]
    (last, first), = latches

    @cache
    def paths(pc):
        if pc == last:
            return [pc]
        if not first <= pc < last:
            return []
        op, a, b, _ = code[pc:pc+4]
        name = names[op]
        if name in ("TRAP", "CALL", "RETURN"):
            return []
        if name == "BR":
            targets = [a]
        elif name.startswith("BR_IF"):
            targets = [b, pc + 4]
        else:
            targets = [pc + (16 if name == "I64_BYTE_LOOKUP" else 4)]
        if any(first <= p <= pc for p in targets):
            raise ValueError("unexpected nested backedge")
        tails = [tail for p in targets if (tail := paths(p))]
        if len(tails) > 1:
            raise ValueError("multiple successful iteration paths")
        return [pc] + tails[0] if tails else []

    pcs = paths(first)
    assert len(pcs) == 221 and pcs[-1] == last
    return pcs


def groups(pcs, code, names, width):
    sequence = []
    for i, pc in enumerate(pcs):
        sequence.append(pc)
        size = 16 if names[code[pc]] == "I64_BYTE_LOOKUP" else 4
        if len(sequence) == width or i == len(pcs) - 1 or pcs[i+1] != pc + size:
            yield tuple(sequence)
            sequence = []


def counts(pcs, code, names):
    return dict(Counter(names[code[p]] for p in pcs))
