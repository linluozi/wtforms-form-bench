"""Measure WTForms form lifecycle cost: construction vs validation.

Realistic workload: profile/account forms with 8/20/48 fields built from the
same field+validator patterns used by production signup forms (StringField,
IntegerField, SelectField, BooleanField; DataRequired/Length/Regexp/
NumberRange/Optional).  No randomness: the corpus is deterministic, seed=0.

Usage: python bench.py --src <path-to-src> --impl base|opt --out <json>
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


class MultiDict(dict):
    def getlist(self, key):
        v = self.get(key)
        if v is None:
            return []
        return v if isinstance(v, list) else [v]


def run_case(forms, n, valid, warmup, samples):
    Form = forms.make_form(n)
    payload = forms.payload_for(Form, valid)
    rows = []
    for i in range(warmup + samples):
        formdata = MultiDict(payload)
        t0 = time.perf_counter()
        form = Form(formdata)
        t1 = time.perf_counter()
        ok = form.validate()
        t2 = time.perf_counter()
        if i >= warmup:
            rows.append({
                "sample": i - warmup,
                "construct_s": t1 - t0,
                "validate_s": t2 - t1,
                "total_s": t2 - t0,
                "valid_result": ok,
                "formdata_entries": len(payload),
            })
    return rows


def med(rows, key):
    return statistics.median(r[key] for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--impl", required=True, choices=["base", "opt"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-dir", default=os.path.join(HERE, "raw"))
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--samples", type=int, default=7)
    args = ap.parse_args()

    sys.path.insert(0, args.src)
    sys.path.insert(0, HERE)
    import wtforms
    import forms

    import platform
    print("wtforms from", wtforms.__file__)
    summary = {
        "impl": args.impl,
        "wtforms_file": wtforms.__file__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "seed": 0,
        "warmup": args.warmup,
        "samples": args.samples,
        "cases": {},
    }
    os.makedirs(args.raw_dir, exist_ok=True)
    for n in (8, 20, 48):
        for valid in (True, False):
            key = "%d_%s" % (n, "valid" if valid else "invalid")
            rows = run_case(forms, n, valid, args.warmup, args.samples)
            for r in rows:
                fn = "%s-%s-%d.json" % (args.impl, key, r["sample"])
                with open(os.path.join(args.raw_dir, fn), "w") as fh:
                    json.dump({"case": key, "n_fields": n, "valid_payload": valid, **r}, fh)
            c = [r["construct_s"] for r in rows]
            v = [r["validate_s"] for r in rows]
            t = [r["total_s"] for r in rows]
            def rsd(xs):
                m = statistics.median(xs)
                return statistics.pstdev(xs) / m if m else 0.0
            summary["cases"][key] = {
                "n_fields": n,
                "valid_payload": valid,
                "construct_median_ms": med(rows, "construct_s") * 1e3,
                "validate_median_ms": med(rows, "validate_s") * 1e3,
                "total_median_ms": med(rows, "total_s") * 1e3,
                "total_p25_ms": statistics.quantiles(t, n=4)[0] * 1e3,
                "total_p75_ms": statistics.quantiles(t, n=4)[2] * 1e3,
                "validate_share_pct": med(rows, "validate_s") / med(rows, "total_s") * 100,
                "total_rsd_pct": rsd(t) * 100,
            }
            print(key, json.dumps(summary["cases"][key]))
    with open(args.out, "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
