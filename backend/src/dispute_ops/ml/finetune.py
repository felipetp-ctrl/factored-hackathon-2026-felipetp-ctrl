"""Fine-tuned transformer vs the deployed TF-IDF model, on the same training data and the same held-out sets.

multilingual-e5-small (118M parameters) with a sequence-classification head, fine-tuned on the augmented intent
corpus (the data intent-v2 is trained on). Offline comparison only: the API instance cannot hold PyTorch.

    uv run --group ml --group ml-embeddings python -m dispute_ops.ml finetune
"""

from __future__ import annotations

import json
import time

import numpy as np

from dispute_ops.language.intent_model import LABELS, IntentModel
from dispute_ops.ml import corpus as C
from dispute_ops.ml.augment import augment

BASE = "intfloat/multilingual-e5-small"
SEED = 42
RESULTS = C.REPO / "ml" / "results"


def heldout_sets() -> dict[str, list[tuple[str, str]]]:
    from dispute_ops.ml.independent import load_independent
    gold, _ = C.drop_near_duplicates(load_independent(), [e.text for e in C.load_corpus()])
    v3 = []
    for line in (C.REPO / "eval" / "results" / "test-v3-subagent" / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["system"] == "rules_only" and r.get("expected_reason_code") and r["category"] != "adversarial":
            msgs = [t for role, t in r["transcript"] if role == "customer"]
            k = next((i for i, t in enumerate(r["nlu_turns"]) if t.get("reason_code")), len(msgs) - 1)
            v3.append((" ".join(msgs[: k + 1]), r["expected_reason_code"]))
    return {"independent (525)": [(e.text, e.label) for e in gold], "test-v3 reasons (23)": v3,
            "test-v2 run 3 reasons (23)": [(e.text, e.label) for e in C.heldout_reason_v2(C.TEST_V2_RUN3)]}


def run(epochs: int = 3) -> str:
    import mlflow
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.manual_seed(SEED)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    base, _ = C.drop_near_duplicates(C.load_corpus(), C.eval_messages())
    data, _ = augment(base, 2)
    lab = {l: i for i, l in enumerate(LABELS)}
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=len(LABELS)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=0.01)
    x, y = [f"query: {e.text}" for e in data], np.array([lab[e.label] for e in data])
    rng = np.random.default_rng(SEED)
    started = time.perf_counter()
    model.train()
    for _ in range(epochs):
        order = rng.permutation(len(x))
        for i in range(0, len(x), 32):
            idx = order[i:i + 32]
            batch = tok([x[j] for j in idx], padding=True, truncation=True, max_length=96, return_tensors="pt").to(device)
            loss = model(**batch, labels=torch.tensor(y[idx], device=device)).loss
            loss.backward()
            opt.step()
            opt.zero_grad()
    train_s = time.perf_counter() - started
    model.eval().to("cpu")

    def predict(texts):
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                b = tok([f"query: {t}" for t in texts[i:i + 64]], padding=True, truncation=True, max_length=96, return_tensors="pt")
                out += [LABELS[k] for k in model(**b).logits.argmax(-1).tolist()]
        return out

    tfidf = IntentModel.load()
    rows = []
    for name, items in heldout_sets().items():
        texts, gold = [t for t, _ in items], [y for _, y in items]
        t0 = time.perf_counter()
        ft = predict(texts)
        ft_ms = (time.perf_counter() - t0) * 1000 / len(texts)
        t0 = time.perf_counter()
        tf = [tfidf.predict(t).label for t in texts]
        tf_ms = (time.perf_counter() - t0) * 1000 / len(texts)
        rows.append({"set": name, "n": len(items), "finetuned": sum(p == g for p, g in zip(ft, gold)),
                     "tfidf": sum(p == g for p, g in zip(tf, gold)), "finetuned_ms": ft_ms, "tfidf_ms": tf_ms})
    params = sum(p.numel() for p in model.parameters())

    (C.REPO / "mlruns").mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{C.REPO / 'mlruns' / 'mlflow.db'}")
    mlflow.set_experiment("intent-classifier")
    with mlflow.start_run(run_name=f"finetune {BASE}"):
        mlflow.log_params({"base": BASE, "epochs": epochs, "lr": 5e-5, "batch": 32, "train_examples": len(x), "device": device})
        mlflow.log_metrics({"train_seconds": train_s, "parameters": params,
                            **{f"acc_{r['set'].split()[0]}_{r['set'].split()[1] if len(r['set'].split()) > 2 else ''}".strip("_"):
                               r["finetuned"] / r["n"] for r in rows}})
    lines = [
        "# Fine-tuned transformer vs deployed TF-IDF (`intent-v2`)", "",
        f"> Offline. `{BASE}` ({params / 1e6:.0f}M parameters) + classification head, fine-tuned {epochs} epochs on the "
        f"same {len(x):,} augmented training examples as intent-v2 ({train_s / 60:.1f} min on {device}). "
        "Scored on the held-out sets without any tuning on them.", "",
        "| Held-out set | n | Fine-tuned e5-small | TF-IDF + LR (intent-v2) | ms/message fine-tuned (CPU) | ms/message TF-IDF |",
        "|---|---|---|---|---|---|",
        *[f"| {r['set']} | {r['n']} | {r['finetuned']}/{r['n']} ({r['finetuned'] / r['n']:.1%}) | {r['tfidf']}/{r['n']} "
          f"({r['tfidf'] / r['n']:.1%}) | {r['finetuned_ms']:.1f} | {r['tfidf_ms']:.2f} |" for r in rows], "",
        "Deployment needs PyTorch and ~470 MB of weights; the API instance has 512 MB of RAM. The decision rule in "
        "ADR-019 applies: deploy the transformer only if it is clearly better on held-out data.", ""]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "finetune-e5-small.md").write_text("\n".join(lines))
    (RESULTS / "finetune-e5-small.json").write_text(json.dumps({"rows": rows, "params": params, "train_seconds": train_s}, indent=2))
    return "\n".join(lines)
