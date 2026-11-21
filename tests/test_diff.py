"""Differential test: pristine WTForms vs patched Field.validate.

Both implementations are imported in *separate* subprocesses (same module name),
each emits one line per case: <case_sha256> <result_sha256>.  The driver requires
>=1000 sha256-deduplicated independent samples and 0 byte differences.

Usage:
  python tests/test_diff.py --base-src /tmp/basewt/src --opt-src /tmp/cand-wtforms/src
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(os.path.dirname(HERE), "benchmark")
VALUES = [
    "", " ", "Ada", "ada_99", "Bad Name!", "a" * 300, "日本語の名前", "Ω≈ç√",
    "ada@example.com", "-1", "0", "30", "999999", "x", "  padded  ", "ünïcode",
    "10.5", "true", "False", "49 30 1234", "\t", "line\nbreak", "emoji🙂", None,
]


def build_cases(n_cases, seed=4321):
    sys.path.insert(0, BENCH)
    import forms
    rng = random.Random(seed)
    seen = set()
    cases = []
    while len(cases) < n_cases:
        n = rng.randint(6, 26)
        Form = forms.make_form(n)
        payload = forms.payload_for(Form, rng.random() < 0.4)
        for _ in range(rng.randint(1, 6)):
            name = rng.choice(list(payload))
            payload[name] = rng.choice(VALUES)
        canonical = json.dumps({"n": n, "p": payload}, sort_keys=True, ensure_ascii=False)
        key = hashlib.sha256(canonical.encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        cases.append({"key": key, "n": n, "payload": payload})
    return cases


def emit(cases, src):
    sys.path.insert(0, src)
    sys.path.insert(0, BENCH)
    import wtforms  # noqa: F401
    import forms

    class MD(dict):
        def getlist(self, k):
            v = self.get(k)
            return [] if v is None else (v if isinstance(v, list) else [v])

    cache = {}
    for case in cases:
        Form = cache.setdefault(case["n"], forms.make_form(case["n"]))
        form = Form(MD(case["payload"]))
        ok = form.validate()
        state = {
            "ok": ok,
            "form_errors": {k: list(v) for k, v in form.errors.items()},
            "fields": {
                name: [repr(f.data), repr(f.raw_data), list(f.errors), list(f.process_errors)]
                for name, f in form._fields.items()
            },
        }
        blob = json.dumps(state, sort_keys=True, ensure_ascii=False)
        print(case["key"], hashlib.sha256(blob.encode()).hexdigest())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-src")
    ap.add_argument("--opt-src")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--src", default=None)
    ap.add_argument("--cases", type=int, default=1200)
    ap.add_argument("--seed", type=int, default=4321)
    args = ap.parse_args()
    cases = build_cases(args.cases, args.seed)
    if args.emit:
        emit(cases, args.src)
        return
    outs = {}
    for label, src in (("base", args.base_src), ("opt", args.opt_src)):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--emit", "--src", src,
             "--cases", str(args.cases), "--seed", str(args.seed)],
            capture_output=True, text=True, env=env, check=True,
        )
        outs[label] = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(outs["base"]) == len(cases) == len(outs["opt"]), "line count mismatch"
    mismatch = sum(a != b for a, b in zip(outs["base"], outs["opt"]))
    print(f"independent samples (sha256-deduplicated inputs): {len(cases)}")
    print(f"mismatches: {mismatch}")
    print(f"byte-identical: {mismatch == 0}")
    sys.exit(1 if mismatch else 0)


if __name__ == "__main__":
    main()
