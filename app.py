import streamlit as st
import pandas as pd
import numpy as np

# =====================================================
# CONFIG
# =====================================================
MIN_DECKLE = 2160
MAX_DECKLE = 2200

MIN_PATTERN_MT = 1.5
MIN_REEL_MT = 0.4
MAX_REEL_MT = 0.6

MAX_PATTERNS = 20

st.set_page_config(page_title="Mill Scheduler Pro", layout="wide")

# =====================================================
# INVENTORY
# =====================================================
if "repository" not in st.session_state:
    st.session_state.repository = {
        "50 ri": [652, 778, 904],
        "50/46 old": [645, 770, 895],
        "*60/35 uncle": [655, 782, 905],
        "65 ri": [550, 675, 805],
        "65 gi": [550, 680, 810],
        "*80/48": [675, 805, 935],
        "80/49": [700, 835],
        "80/50": [718, 860],
        "80/46": [660, 790, 915],
        "60/46": [660, 790, 917],
        "50/46 new": [638, 764, 890],
        "100/50": [595, 735, 880],
        "60/43": [630, 750, 875],
        "50/43": [614, 735, 855],
        "200/55": [705, 875],
    }

# =====================================================
# PATTERN GENERATION (INDUSTRIAL FILTERED)
# =====================================================
@st.cache_data(show_spinner=False)
def generate_patterns(selected_items, repo):
    slots = []
    for item in selected_items:
        for w in repo[item]:
            slots.append((w, item))

    slots.sort()

    patterns = []
    seen = set()

    n = len(slots)

    for i in range(n):
        w1, p1 = slots[i]

        for j in range(i, n):
            w2, p2 = slots[j]
            partial = w1 + w2

            if partial + w2 > MAX_DECKLE:
                break

            for k in range(j, n):
                w3, p3 = slots[k]
                total = partial + w3

                if total > MAX_DECKLE:
                    break

                if total < MIN_DECKLE:
                    continue

                # =================================================
                # HARD CONSTRAINT 1: minimum pattern size
                # =================================================
                if (total / MAX_DECKLE) < 0.85:
                    continue

                key = tuple(sorted([(w1,p1),(w2,p2),(w3,p3)])) + (total,)
                if key in seen:
                    continue
                seen.add(key)

                patterns.append({
                    "deckle": total,
                    "widths": [w1, w2, w3],
                    "products": [p1, p2, p3]
                })

    patterns.sort(key=lambda x: x["deckle"], reverse=True)

    return patterns[:200]   # pre-limit before optimization

# =====================================================
# MATRIX
# =====================================================
def build_matrix(patterns, targets):
    products = list(targets.keys())
    idx = {p:i for i,p in enumerate(products)}

    A = np.zeros((len(products), len(patterns)))

    for j, pat in enumerate(patterns):
        d = pat["deckle"]
        for w, p in zip(pat["widths"], pat["products"]):
            if p in idx:
                A[idx[p], j] += w / d

    b = np.array([targets[p] for p in products], dtype=float)
    return A, b, products

# =====================================================
# INDUSTRIAL OPTIMIZER
# =====================================================
def optimize(A, b, total_mt):
    m, n = A.shape

    x = np.ones(n) * (total_mt / n)
    lr = 0.04

    for _ in range(800):
        Ax = A @ x
        grad = 2 * (A.T @ (Ax - b))

        x = x - lr * grad
        x = np.maximum(x, 0)

        s = x.sum()
        x = x * (total_mt / s if s > 0 else 1)

    return x

# =====================================================
# POST PROCESSING (HARD BUSINESS RULES)
# =====================================================
def enforce_constraints(patterns, x):
    result = []

    for pat, ton in zip(patterns, x):
        if ton < MIN_PATTERN_MT:
            continue

        # enforce reel constraint 0.4–0.6 MT per width contribution
        reel_ok = True

        per_reel = []
        for w in pat["widths"]:
            share = ton * (w / pat["deckle"])
            per_reel.append(share)

        if any(s < MIN_REEL_MT or s > MAX_REEL_MT for s in per_reel):
            reel_ok = False

        if reel_ok:
            result.append((pat, ton))

    # limit to top 20 patterns
    result = sorted(result, key=lambda x: x[1], reverse=True)[:MAX_PATTERNS]

    return result

# =====================================================
# ACTUALS
# =====================================================
def compute_actuals(selected):
    out = {}
    for pat, ton in selected:
        d = pat["deckle"]
        for w, p in zip(pat["widths"], pat["products"]):
            out[p] = out.get(p, 0) + ton * (w / d)
    return out

# =====================================================
# RMSE
# =====================================================
def rmse(actual, target):
    return float(np.sqrt(np.mean([
        (actual[k] - target[k])**2 for k in target
    ])))

# =====================================================
# UI
# =====================================================
st.title("🏭 Industrial Mill Scheduler (Constraint Engine)")

total_mt = st.sidebar.number_input("Total MT", 1.0, 500.0, 30.0)

selected = []
for item in st.session_state.repository:
    if st.sidebar.checkbox(item, value=True):
        selected.append(item)

if not selected:
    st.stop()

targets = {}
for item in selected:
    targets[item] = st.sidebar.number_input(
        item, 0.0, total_mt, total_mt / len(selected)
    )

# =====================================================
# RUN
# =====================================================
patterns = generate_patterns(tuple(selected), st.session_state.repository)

A, b, products = build_matrix(patterns, targets)

x = optimize(A, b, total_mt)

final_selected = enforce_constraints(patterns, x)

actual = compute_actuals(final_selected)

error = rmse(actual, targets)

# =====================================================
# OUTPUT
# =====================================================
st.subheader(f"RMSE: {error:.3f}")
st.write(f"Final patterns used: {len(final_selected)} (max {MAX_PATTERNS})")

for pat, ton in final_selected:
    st.write(
        f"{pat['widths']} → {pat['deckle']} mm | "
        f"{ton:.2f} MT"
    )

# =====================================================
# TABLE
# =====================================================
df = pd.DataFrame([
    {
        "Product": k,
        "Target": v,
        "Actual": actual.get(k, 0),
        "Diff": actual.get(k, 0) - v
    }
    for k, v in targets.items()
])

st.dataframe(df, use_container_width=True)
