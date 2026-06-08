import streamlit as st
import itertools
import numpy as np
import pandas as pd

# =========================
# CONFIG
# =========================
MIN_DECKLE = 2160
MAX_DECKLE = 2200
MAX_PATTERNS = 20
MIN_PATTERN_MT = 1.5

st.set_page_config(page_title="Mill Pattern Planner", layout="wide")

# =========================
# INVENTORY
# =========================
if "repo" not in st.session_state:
    st.session_state.repo = {
        "50/46 new": [638, 764, 890],
        "80/46": [660, 790, 915],
        "60/46": [660, 790, 917],
        "50/46 old": [645, 770, 895],
        "65 ri": [550, 675, 805],
    }

# =========================
# INPUTS
# =========================
st.title("🏭 Paper Mill 3-Reel Pattern Planner")

TOTAL_MT = st.sidebar.number_input("Total MT required", 1.0, 500.0, 30.0)

st.sidebar.subheader("Demand per item")

demand = {}
for item in st.session_state.repo:
    qty = st.sidebar.number_input(item, 0.0, 100.0, 0.0, step=0.5)
    if qty > 0:
        demand[item] = qty

if not demand:
    st.stop()

# =========================
# STEP 1: GENERATE VALID PATTERNS
# =========================
def generate_patterns(demand, repo):
    slots = []
    for p in demand:
        for w in repo[p]:
            slots.append((w, p))

    patterns = []
    seen = set()

    for i, j, k in itertools.combinations_with_replacement(range(len(slots)), 3):
        w1, p1 = slots[i]
        w2, p2 = slots[j]
        w3, p3 = slots[k]

        total = w1 + w2 + w3

        if total < MIN_DECKLE or total > MAX_DECKLE:
            continue

        key = tuple(sorted([w1, w2, w3]))
        if key in seen:
            continue
        seen.add(key)

        patterns.append({
            "widths": [w1, w2, w3],
            "products": [p1, p2, p3],
            "deckle": total
        })

    return patterns

patterns = generate_patterns(demand, st.session_state.repo)

if not patterns:
    st.error("No valid patterns found")
    st.stop()

# =========================
# STEP 2: SCORE PATTERNS
# =========================
def score_pattern(pat):
    return sum(demand.get(p, 0) for p in pat["products"])

patterns.sort(key=score_pattern, reverse=True)
patterns = patterns[:200]

# =========================
# STEP 3: SELECT TOP PATTERNS (MAX 20)
# =========================
patterns = patterns[:MAX_PATTERNS]

# =========================
# STEP 4: ALLOCATE TONNAGE
# =========================
scores = np.array([score_pattern(p) for p in patterns], dtype=float)

if scores.sum() == 0:
    tons = np.ones(len(patterns)) * (TOTAL_MT / len(patterns))
else:
    tons = TOTAL_MT * scores / scores.sum()

# enforce minimum MT
for i in range(len(tons)):
    if tons[i] < MIN_PATTERN_MT:
        diff = MIN_PATTERN_MT - tons[i]
        tons[i] = MIN_PATTERN_MT
        for j in range(len(tons)):
            if j != i:
                tons[j] -= diff / (len(tons)-1)

# renormalize
tons = np.maximum(tons, 0)
tons = TOTAL_MT * tons / tons.sum()

# =========================
# STEP 5: ACTUAL OUTPUT
# =========================
def compute_actuals(patterns, tons):
    out = {}
    for pat, t in zip(patterns, tons):
        for w, p in zip(pat["widths"], pat["products"]):
            out[p] = out.get(p, 0) + t * (w / pat["deckle"])
    return out

actuals = compute_actuals(patterns, tons)

# =========================
# OUTPUT
# =========================
st.header("📊 Pattern Plan")

for i, (pat, t) in enumerate(zip(patterns, tons), 1):
    st.write(f"""
**Pattern {i}:**
{pat['widths']} → {pat['deckle']} mm  
➡ {t:.2f} MT
""")

st.header("📦 Summary")

df = pd.DataFrame([
    {
        "Product": k,
        "Demand": v,
        "Actual": actuals.get(k, 0),
        "Deviation": actuals.get(k, 0) - v
    }
    for k, v in demand.items()
])

df.loc[len(df)] = ["TOTAL", TOTAL_MT, sum(actuals.values()), sum(actuals.values()) - TOTAL_MT]

st.dataframe(df, use_container_width=True)
