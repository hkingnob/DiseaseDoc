import yaml
import math

with open("content.yaml", "r") as f:
    content = yaml.safe_load(f)

SYMPTOMS = {s["id"]: s["label"] for s in content["symptoms"]}
DISEASES = {d["id"]: d["label"] for d in content["differentials"]}
LIKELIHOODS = content["likelihoods"]

WEIGHTS = {"H": 2, "M": 1, "L": 0}

def score(symptom_ids):
    scores = {dx: 0 for dx in DISEASES}
    rationale = {dx: [] for dx in DISEASES}

    for s in symptom_ids:
        if s in LIKELIHOODS:
            for dx, val in LIKELIHOODS[s].items():
                scores[dx] += WEIGHTS.get(val, 0)
                rationale[dx].append(f"{SYMPTOMS[s]} suggests {DISEASES[dx]} ({val})")

    results = []
    for dx, sc in scores.items():
        if sc == 0:
            continue
        p = 1 / (1 + math.exp(-(1.0 * sc - 1.5)))  # logistic
        p = min(p, 0.80)
        results.append({
            "dx_id": dx,
            "label": DISEASES[dx],
            "confidence": round(p, 2),
            "rationale": rationale[dx]
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:3]
