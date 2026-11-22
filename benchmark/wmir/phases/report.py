"""Report exclusive mean milliseconds per stage and median process controls."""
import json
from pathlib import Path
from statistics import mean, median
import sys


GROUPS = {
    "process start and CLI": ["before_open", "open"],
    "read Wasm or map and check WMIR directory": ["input"],
    "MIR key (includes source hash only for Wasm)": ["key"],
    "Wasm sections and module checks": ["sections"],
    "read MIR2 file": ["mir_read"],
    "MIR2 payload slice and checksum": ["mir_verify"],
    "MIR function declarations and layout": ["declare"],
    "instance, Store, exports, types": ["instance"],
    "VM linking and WASI setup": ["link"],
    "snapshot identity": ["snap_key"],
    "snapshot file read and header": ["snap_read"],
    "snapshot payload slice": ["snap_slice"],
    "snapshot payload SHA-256": ["snap_hash"],
    "frame and page checks, payload extraction": ["snap_validate"],
    "linear memory grow": ["snap_grow"],
    "restore saved pages": ["snap_copy"],
    "clear other pages": ["snap_zero"],
    "globals and return from restore": ["snap_globals"],
    "rebuild execution frames": ["frames"],
    "MIR functions decoded during restore": ["lazy_snap_validate", "lazy_frames"],
    "MIR functions decoded during guest execution": ["lazy_guest"],
    "guest execution and WASI, exclusive": ["guest"],
    "exit and parent collection": ["after_guest"],
}


def report(data):
    samples = data["samples"]
    modes = ("mir2_snap", "wmir_snap", "mir2", "wmir")
    probes = {mode: [r for r in samples if r["mode"] == mode and r["build"] == "probe"] for mode in modes}
    for group, labels in GROUPS.items():
        print(group, *(f'{mean(sum(r["ns"].get(k, 0) for k in labels) for r in probes[mode])/1e6:.3f}'
                       for mode in modes), sep="\t")
    for mode in modes:
        rows = probes[mode]
        for row in rows:
            if set(row["ns"]) - {k for keys in GROUPS.values() for k in keys}:
                raise ValueError("unreported phase")
        for build in ("release", "probe"):
            walls = [r["wall_ns"]/1e6 for r in samples if r["mode"] == mode and r["build"] == build]
            print(mode, build, "median / mean ms", round(median(walls), 3), round(mean(walls), 3))
        print(mode, "lazy counts", {tuple(sorted(r["lazy_calls"].items())) for r in rows},
              "pages (initial, restored, saved)", {tuple(r["pages"]) for r in rows})


if __name__ == "__main__":
    report(json.loads(Path(sys.argv[1]).read_text()))
