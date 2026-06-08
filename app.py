import streamlit as st
import pandas as pd
import numpy as np

# =====================================================
# CONFIG
# =====================================================
MIN_DECKLE = 2160
MAX_DECKLE = 2200

MIN_PATTERN_MT = 1.5
MAX_PATTERNS = 20

st.set_page_config(page_title="Mill Deckle Planner", layout="wide")

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
# INPUT: DEMAND (REAL PRODUCTION STYLE)
# =====================================================
st.title("🏭 Industrial Mill Planner (Demand Driven)")

st.subheader("📦 Enter Demand (MT per product)")

demand = {}

for item in st.session_state.repository:
    qty = st.number_input(
        f"{item} (MT)",
        min_value=0.0,
        value=0.0,
        step=0.5
    )
    if qty > 0:
        demand[item] = qty

if not demand:
    st.warning("Enter at least one product demand")
    st.stop()

TOTAL_MT = sum(demand.values())

st.info(f"Total required production = {TOTAL_MT:.2f} MT")

selected_items = list(demand.keys())

# =====================================================
# PATTERN GENERATION (PRUNED)
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
    return patterns[:300]

# =====================================================
# MATRIX
# =====================================================
def build_matrix(patterns, demand):
    products = list(demand.keys())
    idx = {p:i for i,p in enumerate(products)}

    A = np.zeros((len(products), len(patterns)))

    for j, pat in enumerate(patterns):
        d = pat["deckle"]
        for w, p in zip(pat["widths"], pat["products"]):
            if p in idx:
                A[idx[p], j] += w / d

    b = np.array([demand[p] for p in products], dtype=float)
    return A, b, products

# =====================================================
# OPTIMIZER (MULTI-PATTERN BALANCED SOLUTION)
# =====================================================
def optimize(A, b, total_mt, max_iter=1200):

    n = A.shape[1]

    x = np.ones(n) * (total_mt / n)
    lr = 0.04

    for _ in range(max_iter):
        Ax = A @ x
        grad = 2 * (A.T @ (Ax - b))

        x = x - lr * grad
        x = np.maximum(x, 0)

        s = x.sum()
        if s == 0:
            x[:] = total_mt / n
        else:
            x = x * (total_mt / s)

    return x

# =====================================================
# ACTUALS
# =====================================================
def compute_actuals(patterns, x, products):
    out = {p: 0.0 for p in products}

    for pat, ton in zip(patterns, x):
        d = pat["deckle"]
        for w, p in zip(pat["widths"], pat["products"]):
            if p in out:
                out[p] += ton * (w / d)

    return out

# =====================================================
# RMSE
# =====================================================
def rmse(actual, target):
    return float(np.sqrt(np.mean([
        (actual[k] - target[k]) ** 2 for k in target
    ])))

# =====================================================
# RUN
# =====================================================
patterns = generate_patterns(tuple(selected_items), st.session_state.repository)

A, b, products = build_matrix(patterns, demand)

x = optimize(A, b, TOTAL_MT)

actual = compute_actuals(patterns, x, products)

error = rmse(actual, demand)

# =====================================================
# FILTER OUTPUT (INDUSTRIAL RULES)
# =====================================================
st.subheader(f"RMSE: {error:.3f}")

final_patterns = []
final_tons = []

for pat, ton in zip(patterns, x):
    if ton >= MIN_PATTERN_MT:
        final_patterns.append(pat)
        final_tons.append(ton)

# enforce max 20 patterns
if len(final_patterns) > MAX_PATTERNS:
    idx = np.argsort(-np.array(final_tons))[:MAX_PATTERNS]
    final_patterns = [final_patterns[i] for i in idx]
    final_tons = [final_tons[i] for i in idx]

# renormalize
if sum(final_tons) > 0:
    final_tons = np.array(final_tons)
    final_tons = final_tons * (TOTAL_MT / final_tons.sum())

# =====================================================
# OUTPUT
# =====================================================
for pat, ton in zip(final_patterns, final_tons):
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
        "Demand": v,
        "Actual": actual.get(k, 0),
        "Diff": actual.get(k, 0) - v
    }
    for k, v in demand.items()
])

st.dataframe(df, use_container_width=True)
