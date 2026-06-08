import streamlit as st
import pandas as pd
import numpy as np

# =====================================================
# CONFIG
# =====================================================
MIN_DECKLE = 2160
MAX_DECKLE = 2200

TARGET_TOP_PATTERNS = 250  # INDUSTRIAL CONTROL

st.set_page_config(page_title="Industrial Deckle Optimizer", layout="wide")

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
# INDUSTRIAL PATTERN GENERATION (SMART PRUNING)
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

            # early reject (very important speed gain)
            if partial + w2 > MAX_DECKLE:
                break

            for k in range(j, n):
                w3, p3 = slots[k]
                total = partial + w3

                if total > MAX_DECKLE:
                    break

                if total < MIN_DECKLE:
                    continue

                # INDUSTRIAL QUALITY FILTER
                efficiency = total / MAX_DECKLE

                # reject weak patterns (key improvement)
                if efficiency < 0.98:
                    continue

                key = tuple(sorted([(w1,p1),(w2,p2),(w3,p3)])) + (total,)
                if key in seen:
                    continue
                seen.add(key)

                patterns.append({
                    "deckle": total,
                    "widths": [w1, w2, w3],
                    "products": [p1, p2, p3],
                    "eff": efficiency
                })

    # KEEP ONLY BEST PATTERNS (INDUSTRIAL FILTER)
    patterns.sort(key=lambda x: (x["eff"], x["deckle"]), reverse=True)

    return patterns[:TARGET_TOP_PATTERNS]

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
# INDUSTRIAL OPTIMIZER (STABLE PROJECTION)
# =====================================================
def optimize(A, b, total_mt, max_iter=900):
    m, n = A.shape

    # smart initialization (important improvement)
    x = np.ones(n) * (total_mt / n)

    lr = 0.04

    for _ in range(max_iter):
        Ax = A @ x

        # weighted error (industrial stability improvement)
        err = Ax - b
        grad = 2 * (A.T @ err)

        x = x - lr * grad

        # projection (simplex)
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
# UI
# =====================================================
st.title("🏭 Industrial Deckle Optimizer (Production Grade)")

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

st.write("Industrial patterns:", len(patterns))

A, b, products = build_matrix(patterns, targets)

x = optimize(A, b, total_mt)

actual = compute_actuals(patterns, x, products)

error = rmse(actual, targets)

# =====================================================
# OUTPUT
# =====================================================
st.subheader(f"RMSE: {error:.3f}")

for pat, ton in zip(patterns, x):
    if ton > 0.01:
        st.write(
            f"{pat['widths']} → {pat['deckle']} mm | "
            f"{ton:.2f} MT | eff={pat['eff']:.3f}"
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
