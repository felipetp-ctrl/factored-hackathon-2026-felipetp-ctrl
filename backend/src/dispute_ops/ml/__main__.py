"""python -m dispute_ops.ml train [--embeddings] | fraud-audit"""

from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="dispute_ops.ml")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="train, select and export the intent classifier")
    t.add_argument("--version", default="intent-v2", choices=["intent-v1", "intent-v2"])
    t.add_argument("--embeddings", action="store_true", help="also compare multilingual-e5-small embeddings (offline)")
    sub.add_parser("fraud-audit", help="audit the organizer fraud labels on the silver layer")
    sub.add_parser("learnability", help="which outcomes in the organizer data can be predicted at all")
    args = p.parse_args()
    if args.cmd == "train":
        from dispute_ops.ml.train import run
        s = run(version=args.version, with_embeddings=args.embeddings)
        print(f"selected {s['selected']} · threshold {s['threshold']:.2f} · report ml/results/{s['version']}.md")
    elif args.cmd == "learnability":
        from dispute_ops.ml.learnability import run as scan
        print(scan())
    else:
        from dispute_ops.ml.fraud_audit import run as audit
        print(audit())


if __name__ == "__main__":
    main()
