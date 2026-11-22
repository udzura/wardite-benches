"""Generate a benchmark-only Wardite interpreter from the pinned Spinel C."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from instrument import build as build_guest
from plan import counts, groups, trace

# Slot fetches in generated C contain a redundant temporary GC root and
# the full Ruby Array#fetch bounds/error machinery. Frame.registers itself
# stays rooted by execute_flat. Match only the register array, not bytecode.
FETCH = re.compile(r'\(\{ sp_IntArray \*(?P<array>_t\d+) = lv_registers; '
                   r'SP_GC_ROOT\((?P=array)\); sp_int _t\d+ = (?P<index>sp_oint_arg\(lv_[abc]\)); '
                   r'sp_int [^\n]*?sp_oint_nil\(\)\); \}\)')


def register_path(body, roots_only):
    if roots_only:
        return re.sub(r'(sp_IntArray \*(_t\d+) = lv_registers;) SP_GC_ROOT\(\2\);', r'\1', body)
    body = FETCH.sub(lambda m: 'bench_reg_fetch(lv_registers, ' + m['index'] + ')', body)
    # Some fetch indices are themselves instruction-fetch statement
    # expressions. Leave those exact checked expressions in place.
    body = re.sub(r'(sp_IntArray \*(_t\d+) = lv_registers;) SP_GC_ROOT\(\2\);', r'\1', body)
    for before, after in [('oget', 'read'), ('set', 'write'), ('set_nilable', 'copy')]:
        body = body.replace(f'sp_IntArray_{before}(lv_registers,', f'bench_reg_{after}(lv_registers,')
    return body


# Replace checked operand fetches only in the supplementary experiment.
# Offsets remain runtime reads of the identical flat MIR word array.
WORD = re.compile(r'\(\{ sp_IntArray \*_t\d+ = lv_instructions; sp_int _t\d+ = '
                  r'(?P<index>sp_int_add\(lv_pc, \d+LL\)|lv_pc); sp_int [^\n]*?sp_oint_nil\(\)\); \}\)')


def word_path(body):
    return WORD.sub(lambda m: 'bench_operand(lv_instructions, '+m['index']+')', body)


def native_handler(vm, op, name, fixed, dead):
    match = re.search(rf'^    case {op}LL:\n    \{{\n(.*?)      break;\n    \}}', vm, re.M | re.S)
    if not match or 'case ' in match[1]:
        raise ValueError(f"unexpected Spinel handler {name}")
    body = match[1]
    if 'W' in fixed and name == 'I64_BYTE_LOOKUP':
        stores = [line for line in body.splitlines(True)
                  if line.lstrip().startswith('sp_IntArray_set(lv_registers,')]
        if len(stores) != 4 or len(dead) != 31 or any(mask != [0, 2] for mask in dead.values()):
            raise ValueError("unexpected def-use pattern for the 31 fused lookups")
        body = body.replace(stores[0], '').replace(stores[2], '')
    if 'R' in fixed or fixed == 'roots':
        body = register_path(body, fixed == 'roots')
    if 'P' in fixed:
        body = word_path(body)
    if 'A' in fixed:
        body = body.replace('sp_I64Arithmetic_s_flat_shl(', 'bench_shl(')
        body = body.replace('sp_I64Arithmetic_s_flat_shr_u(', 'bench_shr(')
    if 'M' in fixed:
        body = body.replace('sp_StoreAccess_load8_u(', 'bench_load(&bench_view, ')
        body = body.replace('sp_StoreAccess_store(', 'bench_store(&bench_view, ')
    return body


def tagged_case(tag, ops, handlers, advance, fetch_a):
    lines = [f'case {tag}LL: {{', 'BENCH_COUNT_ONE(tags);']
    for i, op in enumerate(ops):
        if i:
            # Retain the ordinary PC advance, safepoint and operand fetch.
            # Prevent clang from passing frame/memory results across handlers.
            lines.extend([advance, '__asm__ __volatile__("" : "+r"(lv_pc) : : "memory");',
                          'if (SP_UNLIKELY(SP_SAFEPOINT_POLL())) sp_safepoint();', fetch_a])
        lines.extend(['BENCH_COUNT_ONE(ops);', f'lv_opcode = sp_oint_of({op});',
                      '{', handlers[op], '}'])
    lines.append('break; }')
    return '\n'.join(lines)


def generate(source, mir, residual=False):
    start = source.index('static sp_oint sp_VM_execute_flat(', source.index('static sp_oint sp_VM_execute_flat(') + 1)
    vm = source[start:source.index('\n}', start) + 2]
    original_size = len(vm)
    clean = re.sub(r'^#line .*\n', '', vm, flags=re.M)
    fetch_a = re.search(r'^    (lv_a = \(\{.*)$', clean, re.M)[1]
    switch = 'switch (_o11.nil ? 117LL : _t11) {'
    code, names = mir['code'], mir['names']
    pcs = trace(code, names)
    advance = next(line.strip() for line in reversed(clean.splitlines())
                   if line.startswith("    lv_pc = (sp_int_add") and "cst_WIDTH" in line)
    patterns = {}
    outputs = []
    cases = []

    # Each setting selects tagged handlers in the same native binary. Only
    # the 221 instruction sites of the successful loop are eligible.
    configs = [('base', (1, 6)), ('R', (1, 6)), ('M', (1, 6)), ('RM', (1, 6)),
               ('roots', (1,)), ('W', (1,)), ('RMW', (1, 6))]
    if residual:
        configs = [('base', (1,)), ('P', (1,)), ('A', (1,)), ('RMW', (6,)),
                   ('RMWP', (6,)), ('RMWA', (6,)), ('RMWPA', (6,))]
    for fixed, widths in configs:
        handlers = {op: native_handler(clean, op, names[op], fixed, mir['dead']) for op in {code[p] for p in pcs}}
        operand_a = word_path(fetch_a) if 'P' in fixed else fetch_a
        for width in widths:
            name = ('D' if width > 1 else '') + (fixed if fixed != 'base' else '')
            changes = []
            for group in groups(pcs, code, names, width):
                ops = tuple(code[p] for p in group)
                key = (fixed, ops)
                if key not in patterns:
                    tag = 300 + len(patterns)
                    patterns[key] = tag
                    cases.append(tagged_case(tag, ops, handlers, advance, operand_a))
                changes.append(f'lv_code->data[lv_code->start+{group[0]}]={patterns[key]};')
            outputs.append('if (!strcmp(mode, "'+(name or 'base')+'")) {\n'+'\n'.join(changes)+'\n}')
    # Capture the exact code before installing any tags, including side exits.
    # Tags never renumber any PC. Branches and traps keep their original path.
    code_array = ','.join(map(str, code))
    install = f'''
    static const sp_int expected[] = {{{code_array}}};
    if (lv_code && lv_code->len == {len(code)} &&
        !memcmp(lv_code->data + lv_code->start, expected, sizeof(expected))) {{
        const char *mode = getenv("WARDITE_BENCH_MODE");
        if (mode) {{ {chr(10).join(outputs)} }}
        if (mode && getenv("WARDITE_BENCH_AUDIT"))
            fprintf(stderr, "matched decode MIR: %s\\n", mode);
    }}
'''
    # In a tagged single handler the operand 'a' is fetched by the normal
    # dispatch prologue. Other operands use the original generated expressions.
    vm = vm.replace('  while (1) {', '#ifdef BENCH_COUNT\n    static int counted;\n    if (!counted++) atexit(bench_report_counts);\n#endif\n  while (1) {', 1)
    vm = vm.replace('  while (1) {', '  bench_view_t bench_view = {0};\n  while (1) {', 1)
    vm = vm.replace(switch, 'if (_t11 < 300) bench_view.data = NULL;\n    ' + switch + '\n' + '\n'.join(cases), 1)
    source = source[:start] + (HERE / 'access.h').read_text() + '\n' + vm + source[start+original_size:]
    anchor = re.compile(r'(static inline sp_PtrArray \* sp_Function_install_code\([^\n]*\) \{\n)')
    source, n = anchor.subn(lambda m: m[0] + install, source)
    assert n == 1
    traffic = [mir['traffic'][str(code[p])] for p in pcs]
    return source, dict(pcs=pcs, ops=counts(pcs, code, names),
                        register_reads=sum(r for r, _ in traffic), register_writes=sum(w for _, w in traffic),
                        groups=[list(g) for g in groups(pcs, code, names, 6)])


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    wardite = args.source.resolve()
    build_guest(args.wasm, out)
    mir = json.loads(subprocess.check_output(['ruby', '-Ilib', HERE/'dump.rb', out/'bulk.wasm'], cwd=wardite))
    spinel = ['spinel', '-I', 'lib', '--strict-require', '-O2']
    with (out/'spinel.log').open('w') as log:
        subprocess.run([*spinel, '-c', 'exe/wardite', '--force', '-o', out/'wardite.c'],
                       cwd=wardite, stdout=log, stderr=log, check=True)
        ingredients = subprocess.check_output([*spinel, '--print-build', 'exe/wardite'], cwd=wardite,
                                              stderr=log, text=True)
    flags = []
    for line in ingredients.splitlines():
        key, value = line.split(' ', 1)
        if key == 'include':
            flags.append('-I' + value)
        elif key in ('define', 'link', 'runtime', 'lib', 'cflag'):
            flags.append(value)
        elif key != 'source':
            raise ValueError(f"unknown build ingredient {key}")
    source = (out/'wardite.c').read_text()
    c, plan = generate(source, mir, args.residual)
    path = out/'experiment.c'
    path.write_text(c)
    subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-w', path, *flags,
                    '-o', out/'experiment'], check=True)
    if args.audit:
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-O2', '-w', '-DBENCH_COUNT', path, *flags,
                        '-o', out/'audit'], check=True)
    (out/'plan.json').write_text(json.dumps(plan)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--residual', action='store_true', help='build operand/shift sensitivity controls')
    p.add_argument('--audit', action='store_true', help='also build a separate counter executable')
    p.add_argument('source', type=Path)
    p.add_argument('wasm', type=Path)
    p.add_argument('out', type=Path)
    main(p.parse_args())
