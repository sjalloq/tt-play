#!/usr/bin/env python3
"""Experiment 1 (host, no torch): real vLLM kv-cache-groups layout vs the harness.

The integer logic of the three real vLLM functions is transcribed VERBATIM from
the pinned clone src/vllm @ 5eb61e8:

  * unify_kv_cache_spec_page_size          (kv_cache_utils.py:905)
  * _get_kv_cache_groups_uniform_page_size (kv_cache_utils.py:950)
  * get_kv_cache_config_from_groups        (kv_cache_utils.py:1070, general case)

page_size_bytes for both Sliding/Full reduces to 2*block_size*kv*head*dtype
(FullAttentionSpec uses head_size+head_size_v == 2*head_size), confirmed from
kv_cache_interface.py:80 / :181. The constant cancels in every ratio, so the
integer transcription is exact — importing the real module (which needs torch,
container-only) would yield identical numbers.

The harness model is transcribed from
models/demos/gemma4/tests/vllm_harness.py:214-240.
"""
import json
from pathlib import Path

CONFIGS = Path(__file__).resolve().parents[2] / "third_party/tt-metal/models/demos/gemma4/configs"
BS = 64           # requested cache_config.block_size (serving arg)
MAXLEN = 4096     # --max-model-len
DTYPE_BYTES = 2   # bf16


def cdiv(a, b):
    return -(-a // b)


def load_layer_types(variant):
    d = json.loads((CONFIGS / variant / "config.json").read_text())
    t = d.get("text_config", d)
    return list(t["layer_types"]), t


def page_size(block_size, kv, hd):
    # AttentionSpec.real_page_size_bytes (==FullAttentionSpec's, head_size_v=head_size)
    return 2 * block_size * kv * hd * DTYPE_BYTES


# ── REAL vLLM ────────────────────────────────────────────────────────────────
def real_layout(layer_types, cfg):
    skv, shd = int(cfg["num_key_value_heads"]), int(cfg["head_dim"])
    fkv = int(cfg.get("num_global_key_value_heads") or skv)
    fhd = int(cfg.get("global_head_dim") or shd)

    # per-layer spec (block_size, kv, hd, type-tag) at requested BS
    spec = {}
    for i, lt in enumerate(layer_types):
        if lt == "sliding_attention":
            spec[f"L{i}"] = [BS, skv, shd, "sw"]
        else:
            spec[f"L{i}"] = [BS, fkv, fhd, "full"]

    # unify_kv_cache_spec_page_size: bump smaller-page specs' block_size
    ps = {name: page_size(s[0], s[1], s[2]) for name, s in spec.items()}
    max_ps = max(ps.values())
    for name, s in spec.items():
        if ps[name] != max_ps:
            assert max_ps % ps[name] == 0, "non-divisible page sizes"
            s[0] *= max_ps // ps[name]   # new block_size

    # _get_kv_cache_groups_uniform_page_size: group by spec identity, then split
    # each type into equal-size subgroups (group_size = min, or max if <1.25x).
    same_type = {}
    for name, s in spec.items():
        same_type.setdefault(tuple(s), []).append(name)
    lens = [len(v) for v in same_type.values()]
    min_n, max_n = min(lens), max(lens)
    group_size = max_n if max_n < min_n * 1.25 else min_n
    grouped = []
    for layers in same_type.values():
        num_groups = cdiv(len(layers), group_size)
        for i in range(num_groups):
            grouped.append(layers[i::num_groups])

    # get_kv_cache_config_from_groups (general case): group_size physical tensors,
    # tensor i shared by the i-th layer of every group.
    g_size = max(len(g) for g in grouped)
    tensors = []
    for i in range(g_size):
        tensors.append([g[i] for g in grouped if i < len(g)])

    # block-table width per group = cdiv(max_model_len, that group's block_size)
    group_info = []
    for g in grouped:
        s = spec[g[0]]
        group_info.append({"type": s[3], "block_size": s[0],
                           "width": cdiv(MAXLEN, s[0]), "n_layers": len(g)})

    # HMA buffer allocation (allocate_vllm_kv_cache_per_layer): one physical
    # buffer per tensor, allocated at the FIRST sharer in layer-index order,
    # and reused for every other sharer. shape = (kv_heads, block_size, head_dim).
    def shp(name):
        bs, kv, hd, _ = spec[name]
        return (kv, bs, hd)
    hma = []
    for ti, sharers in enumerate(tensors):
        by_idx = sorted(sharers, key=lambda n: int(n[1:]))   # layer-index order
        alloc_shape = shp(by_idx[0])                          # first sharer wins
        needed = {n: shp(n) for n in by_idx}
        wrong = {n: s for n, s in needed.items() if s != alloc_shape}
        kv_clash = len({s[0] for s in needed.values()}) > 1   # differing num_kv_heads
        hma.append({"tensor": ti, "alloc_shape": alloc_shape, "first": by_idx[0],
                    "wrong": wrong, "kv_clash": kv_clash})

    return {"n_groups": len(grouped), "n_tensors": g_size,
            "tensors": tensors, "groups": group_info, "spec": spec, "hma": hma}


# ── HARNESS model (vllm_harness.py:214-240) ──────────────────────────────────
def harness_layout(layer_types, cfg):
    skv, shd = int(cfg["num_key_value_heads"]), int(cfg["head_dim"])
    fkv = int(cfg.get("num_global_key_value_heads") or skv)
    fhd = int(cfg.get("global_head_dim") or shd)
    su, fu = BS * skv * shd, BS * fkv * fhd
    if su >= fu:
        sbs, fbs = BS, BS * (su // fu)
    else:
        sbs, fbs = BS * (fu // su), BS

    groups_in_order = []
    for lt in layer_types:
        if lt not in groups_in_order:
            groups_in_order.append(lt)
    members = {lt: [f"L{i}" for i, t in enumerate(layer_types) if t == lt]
               for lt in groups_in_order}

    # one group per attention type; group_size = max(|group|) physical tensors
    grouped = [members[lt] for lt in groups_in_order]
    g_size = max(len(g) for g in grouped)
    tensors = []
    for i in range(g_size):
        tensors.append([g[i] for g in grouped if i < len(g)])

    bs_for = {"sliding_attention": sbs, "full_attention": fbs}
    group_info = [{"type": lt, "block_size": bs_for[lt],
                   "width": cdiv(MAXLEN, bs_for[lt]), "n_layers": len(members[lt])}
                  for lt in groups_in_order]
    return {"n_groups": len(grouped), "n_tensors": g_size,
            "tensors": tensors, "groups": group_info}


def summarize(name, L):
    print(f"  {name}: {L['n_groups']} groups, {L['n_tensors']} physical tensors")
    for g in L["groups"]:
        print(f"      group type={g['type']:18} block_size={g['block_size']:4} "
              f"width={g['width']:3} n_layers={g['n_layers']}")
    print(f"      tensor[0] shared_by={L['tensors'][0]}")


for variant in ["gemma-4-E2B-it", "gemma-4-12B-it"]:
    layer_types, cfg = load_layer_types(variant)
    n_sw = layer_types.count("sliding_attention")
    n_full = layer_types.count("full_attention")
    print(f"\n=== {variant}  ({len(layer_types)} layers: {n_sw} sliding + {n_full} full) ===")
    real = real_layout(layer_types, cfg)
    harn = harness_layout(layer_types, cfg)
    summarize("REAL vLLM", real)
    summarize("HARNESS  ", harn)
    same_groups = real["n_groups"] == harn["n_groups"]
    same_tensors = real["n_tensors"] == harn["n_tensors"]
    same_sharing = real["tensors"] == harn["tensors"]
    verdict = "MATCH" if (same_groups and same_tensors and same_sharing) else "*** DIVERGES ***"
    print(f"  -> groups {real['n_groups']} vs {harn['n_groups']} | "
          f"tensors {real['n_tensors']} vs {harn['n_tensors']} | "
          f"tensor-sharing {'same' if same_sharing else 'DIFFERENT'}  => {verdict}")

    # HMA shape-collapse: does any physical buffer mix layers of different shape?
    print("  HMA buffer allocation (real vLLM sharing, shape=(kv_heads,block_size,head_dim)):")
    bad = [h for h in real["hma"] if h["wrong"]]
    for h in real["hma"][:2] + ([] if len(real["hma"]) <= 2 else [real["hma"][-1]]):
        clash = "  <-- num_kv_heads CLASH" if h["kv_clash"] else ""
        print(f"      tensor[{h['tensor']}] allocated at {h['alloc_shape']} (from {h['first']}); "
              f"{len(h['wrong'])} sharer(s) need a different shape{clash}")
        for n, s in list(h["wrong"].items())[:2]:
            print(f"          {n} actually needs {s}  -> reads buffer with WRONG layout")
    n_clash = sum(1 for h in real["hma"] if h["kv_clash"])
    print(f"  => {len(bad)}/{real['n_tensors']} buffers mix differing shapes; "
          f"{n_clash} have a num_kv_heads clash "
          f"({'BUG: full layers read mis-shaped KV' if n_clash else 'recoverable via block_size_override'})")
