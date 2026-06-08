import streamlit as st
import itertools
import pandas as pd
import numpy as np

# =====================================================================
# CONSTANTS
# =====================================================================
MIN_DECKLE = 2160
MAX_DECKLE = 2200

st.set_page_config(
    page_title="Paper Mill Deckle Optimizer",
    layout="wide",
    page_icon="🧻"
)

# =====================================================================
# SESSION STATE — default inventory
# =====================================================================
if "repository" not in st.session_state:
    st.session_state.repository = {
        "50 ri":          [652, 778, 904],
        "50/46 old":      [645, 770, 895],
        "*60/35 uncle":   [655, 782, 905],
        "65 ri":          [550, 675, 805],
        "65 gi":          [550, 680, 810],
        "*80/48":         [675, 805, 935],
        "80/49":          [700, 835],
        "80/50":          [718, 860],
        "85/50":          [720, 860],
        "100/50":         [595, 735, 880],
        "100/56":         [649, 805],
        "100/55":         [633],
        "60/43":          [630, 750, 875],
        "50/43":          [614, 735, 855],
        "Katori":         [612, 810],
        "100/55 New":     [780, 629],
        "100/55 old":     [785, 633],
        "200/55":         [705, 875],
        "200/55 Papri":   [705, 875],
    }

# =====================================================================
# ROUNDING UTILITY — snap to nearest 0.5 mt, sum preserved
# =====================================================================

def round_to_500kg(tonnages, total_mt, min_pattern_mt):
    if not tonnages:
        return tonnages
    rounded = [round(t * 2) / 2 for t in tonnages]
    floor = round(min_pattern_mt * 2) / 2
    rounded = [max(r, floor) for r in rounded]
    diff = round(total_mt - sum(rounded), 10)
    if abs(diff) > 1e-9:
        max_idx = rounded.index(max(rounded))
        rounded[max_idx] = round((rounded[max_idx] + diff) * 2) / 2
    return rounded


# =====================================================================
# CORE ENGINES
# =====================================================================

def find_valid_patterns(selected_items, repository):
    slots = []
    for item in selected_items:
        for w in repository.get(item, []):
            slots.append((w, item))

    valid = []
    seen  = set()
    L     = len(slots)

    for i in range(L):
        for j in range(i, L):
            for k in range(j, L):
                total = slots[i][0] + slots[j][0] + slots[k][0]
                if not (MIN_DECKLE <= total <= MAX_DECKLE):
                    continue
                triplet = sorted(
                    [(slots[i][0], slots[i][1]),
                     (slots[j][0], slots[j][1]),
                     (slots[k][0], slots[k][1])],
                    key=lambda x: (x[0], x[1])
                )
                key = "|".join(f"{w}:{p}" for w, p in triplet) + f"|{total}"
                if key in seen:
                    continue
                seen.add(key)
                valid.append({
                    "deckle":   total,
                    "widths":   [t[0] for t in triplet],
                    "products": [t[1] for t in triplet],
                })

    valid.sort(key=lambda x: (-x["deckle"], x["widths"][0]))
    return valid


def proportional_tons(patterns, target_weights, total_mt):
    scores = []
    for pat in patterns:
        score = sum(target_weights.get(p, 0.0) for p in pat["products"])
        scores.append(score)
    total_score = sum(scores)
    if total_score == 0:
        return [total_mt / len(patterns)] * len(patterns)
    return [total_mt * s / total_score for s in scores]


def select_max_deckle_patterns(valid_patterns, selected_items, total_mt,
                                target_weights, min_pattern_mt):
    operational = []
    covered = set()
    for pat in valid_patterns:
        new_prods = [p for p in pat["products"] if p not in covered]
        if new_prods or pat["deckle"] == MAX_DECKLE:
            operational.append(pat)
            covered.update(pat["products"])
        if len(covered) >= len(selected_items) and len(operational) >= 2:
            break

    result = operational if operational else (valid_patterns[:1] if valid_patterns else [])

    while len(result) > 1:
        tons = proportional_tons(result, target_weights, total_mt)
        if min(tons) < min_pattern_mt:
            min_idx = tons.index(min(tons))
            result = [p for i, p in enumerate(result) if i != min_idx]
        else:
            break

    return result


def project_simplex(v, total):
    n = len(v)
    u = sorted(v, reverse=True)
    cssv, rho = 0.0, 0
    for i in range(n):
        cssv += u[i]
        if u[i] - (cssv - total) / (i + 1) > 0:
            rho = i
    theta = (sum(u[:rho + 1]) - total) / (rho + 1)
    return [max(0.0, vi - theta) for vi in v]


def solve_balanced_lp(all_patterns, target_weights, total_mt,
                       min_pattern_mt, max_iter=8000):
    n = len(all_patterns)
    if n == 0:
        return [], []

    prod_list = list(target_weights.keys())

    frac = []
    for pat in all_patterns:
        d = {}
        for w, p in zip(pat["widths"], pat["products"]):
            d[p] = d.get(p, 0.0) + w / pat["deckle"]
        frac.append(d)

    def get_actuals(x):
        a = {p: 0.0 for p in prod_list}
        for i, fi in enumerate(frac):
            for p, f in fi.items():
                if p in a:
                    a[p] += x[i] * f
        return a

    x = [total_mt / n] * n
    m = [0.0] * n
    v = [0.0] * n
    beta1, beta2, eps, lr = 0.9, 0.999, 1e-8, 0.05

    for it in range(1, max_iter + 1):
        actuals = get_actuals(x)
        grad = [0.0] * n
        for i, fi in enumerate(frac):
            for p, f in fi.items():
                if p in target_weights:
                    grad[i] += 2.0 * (actuals[p] - target_weights.get(p, 0.0)) * f

        m = [beta1 * m[i] + (1 - beta1) * grad[i] for i in range(n)]
        v = [beta2 * v[i] + (1 - beta2) * grad[i] ** 2 for i in range(n)]
        m_hat = [m[i] / (1 - beta1 ** it) for i in range(n)]
        v_hat = [v[i] / (1 - beta2 ** it) for i in range(n)]
        x = [x[i] - lr * m_hat[i] / (v_hat[i] ** 0.5 + eps) for i in range(n)]
        x = project_simplex(x, total_mt)

    noise_floor = total_mt * 0.005
    active_idx = [i for i in range(n) if x[i] >= noise_floor]
    if not active_idx:
        active_idx = [x.index(max(x))]

    tons = [x[i] for i in active_idx]
    s = sum(tons)
    tons = [t * total_mt / s for t in tons]

    changed = True
    while changed and len(active_idx) > 1:
        changed = False
        min_val = min(tons)
        min_pos = tons.index(min_val)
        if min_val < min_pattern_mt:
            surplus    = tons[min_pos]
            remain     = [t for j, t in enumerate(tons) if j != min_pos]
            remain_sum = sum(remain)
            if remain_sum > 0:
                tons = [t + surplus * t / remain_sum for t in remain]
            else:
                tons = [total_mt / len(remain)] * len(remain)
            active_idx = [idx for j, idx in enumerate(active_idx) if j != min_pos]
            changed = True

    final_sum = sum(tons)
    tonnages      = [t * total_mt / final_sum for t in tons]
    used_patterns = [all_patterns[i] for i in active_idx]

    return tonnages, used_patterns


def compute_actuals(patterns, tonnages):
    out = {}
    for pat, ton in zip(patterns, tonnages):
        for w, p in zip(pat["widths"], pat["products"]):
            out[p] = out.get(p, 0.0) + ton * (w / pat["deckle"])
    return out


def rmse(actuals, targets):
    keys = list(targets.keys())
    if not keys:
        return 0.0
    sq = sum((actuals.get(k, 0.0) - targets.get(k, 0.0)) ** 2 for k in keys)
    return (sq / len(keys)) ** 0.5


# =====================================================================
# SIDEBAR
# =====================================================================
st.sidebar.header("📋 Production Parameters")

total_mt = st.sidebar.number_input(
    "Total quantity required (mt):",
    min_value=0.1, value=12.0, step=0.5, format="%.2f"
)

MIN_PATTERN_MT = st.sidebar.select_slider(
    "Minimum tonnage per pattern (mt):",
    options=[1.5, 2.0, 2.5, 3.0],
    value=1.5,
)
st.sidebar.caption(
    f"⚠️ Every active pattern must carry **≥ {MIN_PATTERN_MT} mt**. "
    f"Patterns below this floor are dropped and tonnage redistributed. "
    f"All final pattern quantities are rounded to **500 kg steps** "
    f"(e.g. 2.0, 2.5, 3.0 mt)."
)

st.sidebar.subheader("Select Items for This Run")
selected_items = []
for item in list(st.session_state.repository.keys()):
    widths_str = ", ".join(map(str, st.session_state.repository[item]))
    if st.sidebar.checkbox(item, value=True, help=f"Widths: {widths_str} mm"):
        selected_items.append(item)

st.sidebar.subheader("Target Weights per Item (mt)")
item_quantities = {}
for item in selected_items:
    default = round(total_mt / max(len(selected_items), 1), 2)
    item_quantities[item] = st.sidebar.number_input(
        f"{item}:", min_value=0.0, value=default, step=0.5,
        format="%.2f", key=f"qty_{item}"
    )

if not selected_items:
    st.error("❌ Select at least one item from the sidebar.")
    st.stop()

# =====================================================================
# TITLE
# =====================================================================
st.title("🧻 Paper Mill Deckle Optimization System")
st.markdown(
    f"**0 mm trim · 3-reel slitter · LP Engine v2.3 · Adam Optimiser · "
    f"≥ {MIN_PATTERN_MT} mt per pattern · Quantities in 500 kg steps**"
)

# =====================================================================
# INVENTORY MANAGER
# =====================================================================
with st.expander("🔧 Manage Inventory & Item Widths", expanded=False):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Option A — Modify or Add Item**")
        options = list(st.session_state.repository.keys()) + ["-- Create New Item --"]
        edit_target = st.selectbox("Select item:", options)

        if edit_target == "-- Create New Item --":
            new_name   = st.text_input("New product name:", placeholder="e.g., 40ml new").strip()
            widths_val = ""
        else:
            new_name   = edit_target
            widths_val = ", ".join(map(str, st.session_state.repository[edit_target]))

        widths_input = st.text_input(
            f"Widths for '{new_name or 'new item'}' (comma-separated mm):",
            value=widths_val, placeholder="e.g., 790, 660, 600"
        )

        if st.button("💾 Save / Add Product"):
            if new_name and widths_input:
                try:
                    parsed = [int(w.strip()) for w in widths_input.split(",") if w.strip()]
                    if parsed:
                        st.session_state.repository[new_name] = parsed
                        st.success(f"✅ Saved '{new_name}': {parsed} mm")
                        st.rerun()
                    else:
                        st.error("Enter valid integer widths.")
                except ValueError:
                    st.error("Widths must be whole numbers.")
            else:
                st.error("Fill in both fields.")

    with col2:
        st.markdown("**Option B — Delete Item**")
        del_target = st.selectbox(
            "Select item to delete:",
            list(st.session_state.repository.keys()),
            key="del_sel"
        )
        if st.button("🗑️ Delete Item", type="primary"):
            del st.session_state.repository[del_target]
            st.success(f"Removed '{del_target}'.")
            st.rerun()

# =====================================================================
# ENGINE — compute both strategies
# =====================================================================
all_patterns = find_valid_patterns(selected_items, st.session_state.repository)

if not all_patterns:
    st.error(
        f"❌ No valid 3-reel zero-waste patterns exist within "
        f"{MIN_DECKLE}–{MAX_DECKLE} mm for the selected items."
    )
    st.stop()

# ── Strategy 1 — Max Deckle ──────
max_patterns   = select_max_deckle_patterns(
    all_patterns, selected_items, total_mt, item_quantities, MIN_PATTERN_MT
)
max_tons_raw   = proportional_tons(max_patterns, item_quantities, total_mt)
max_tons       = round_to_500kg(max_tons_raw, total_mt, MIN_PATTERN_MT)
max_actuals    = compute_actuals(max_patterns, max_tons)
max_rmse       = rmse(max_actuals, item_quantities)

# ── Strategy 2 — Balanced LP ─────────────
with st.spinner("⚙️ Running LP optimiser…"):
    bal_tons_raw, bal_patterns = solve_balanced_lp(
        all_patterns, item_quantities, total_mt, MIN_PATTERN_MT
    )
bal_tons    = round_to_500kg(bal_tons_raw, total_mt, MIN_PATTERN_MT)
bal_actuals = compute_actuals(bal_patterns, bal_tons)
bal_rmse    = rmse(bal_actuals, item_quantities)

# =====================================================================
# MODE SELECTOR
# =====================================================================
st.write("---")
mode = st.radio(
    "**Optimisation Mode:**",
    ["① Maximize Deckle", "② Balanced LP", "Compare Both"],
    index=2,
    horizontal=True
)
show_max = mode in ["① Maximize Deckle", "Compare Both"]
show_bal = mode in ["② Balanced LP", "Compare Both"]

# =====================================================================
# INFO STRIPS
# =====================================================================
if show_bal:
    st.info(
        f"**② Balanced LP:** Evaluates all **{len(all_patterns)}** valid zero-waste patterns "
        f"simultaneously using Adam gradient descent (8,000 iterations). Tonnage minimises "
        f"Σ(actual − target)² per product, then is **snapped to the nearest 500 kg step**. "
        f"Every active pattern carries ≥ {MIN_PATTERN_MT} mt. "
        f"RMSE = root mean square error after rounding; lower = closer to targets."
    )

if show_max:
    st.info(
        f"**① Maximize Deckle:** Selects highest-deckle patterns covering all products. "
        f"Tonnage distributed **proportionally** by target demand, then **rounded to nearest "
        f"500 kg step**. Every pattern carries ≥ {MIN_PATTERN_MT} mt."
    )

# =====================================================================
# HELPER: render one strategy
# =====================================================================
def render_strategy(patterns, tonnages, strategy_label, rmse_val):
    rmse_color = "🟢" if rmse_val < 0.3 else ("🟡" if rmse_val < 1.0 else "🔴")
    st.markdown(
        f"**{strategy_label}** &nbsp; {rmse_color} RMSE: `{rmse_val:.3f}`",
        unsafe_allow_html=True
    )

    copy_lines = []
    for i, (pat, ton) in enumerate(zip(patterns, tonnages)):
        w0, w1, w2 = pat["widths"]
        deckle     = pat["deckle"]
        tag        = "🔴 MAX" if deckle == MAX_DECKLE else "🔵 OK"
        ton_display = f"{int(ton * 1000)} kg  ({ton:.1f} mt)"

        st.markdown(
            f"**Pattern {i+1}:** `{w0}+{w1}+{w2}={deckle} mm` {tag} — "
            f"**`{ton_display}`**"
        )

        rows = []
        for pos, (w, prod) in enumerate(zip(pat["widths"], pat["products"]), 1):
            yield_mt = ton * (w / deckle)
            rows.append({
                "Knife Position": f"#{pos}",
                "Width (mm)":     w,
                "Product":        prod,
                "Yield (mt)":     round(yield_mt, 3),
            })
        st.table(pd.DataFrame(rows))
        copy_lines.append(f"{w0}+{w1}+{w2}={deckle}  {ton:.1f} mt  ({int(ton*1000)} kg)")

    return "\n".join(copy_lines)


# =====================================================================
# RESULTS
# =====================================================================
st.write("---")
st.header("📊 Production Blueprint")

if show_max and show_bal:
    col_max, col_bal = st.columns(2)
    with col_max:
        st.subheader("① Maximize Deckle")
        max_copy = render_strategy(max_patterns, max_tons, "Max Deckle Strategy", max_rmse)
    with col_bal:
        st.subheader("② Balanced LP")
        bal_copy = render_strategy(bal_patterns, bal_tons, "Balanced LP Strategy", bal_rmse)

elif show_max:
    st.subheader("① Maximize Deckle")
    max_copy = render_strategy(max_patterns, max_tons, "Max Deckle Strategy", max_rmse)
    bal_copy = ""

else:
    st.subheader("② Balanced LP")
    bal_copy = render_strategy(bal_patterns, bal_tons, "Balanced LP Strategy", bal_rmse)
    max_copy = ""

# =====================================================================
# COPYABLE TEXT
# =====================================================================
st.write("---")
st.header("📋 Copyable Production Text")

if show_max and max_copy:
    st.markdown("**① Max Deckle**")
    st.code(max_copy, language="text")

if show_bal and bal_copy:
    st.markdown("**② Balanced LP**")
    st.code(bal_copy, language="text")

# =====================================================================
# COMPARISON TABLE
# =====================================================================
st.write("---")
st.header("⚖️ Quantity Advice — Target vs Optimised Output")

rows = []
for prod in selected_items:
    tgt  = item_quantities.get(prod, 0.0)
    row  = {"Product": prod, "Target (mt)": round(tgt, 2)}

    if show_max:
        m_yield = round(max_actuals.get(prod, 0.0), 3)
        m_var   = round(m_yield - tgt, 3)
        row["① Yield (mt)"]    = m_yield
        row["① Variance (mt)"] = f"+{m_var}" if m_var >= 0 else str(m_var)

    if show_bal:
        b_yield = round(bal_actuals.get(prod, 0.0), 3)
        b_var   = round(b_yield - tgt, 3)
        row["② Yield (mt)"]    = b_yield
        row["② Variance (mt)"] = f"+{b_var}" if b_var >= 0 else str(b_var)

    rows.append(row)

total_row = {"Product": "TOTAL", "Target (mt)": round(sum(item_quantities.values()), 2)}
if show_max:
    total_row["① Yield (mt)"]    = round(sum(max_actuals.values()), 3)
    total_row["① Variance (mt)"] = f"RMSE {max_rmse:.3f}"
if show_bal:
    total_row["② Yield (mt)"]    = round(sum(bal_actuals.values()), 3)
    total_row["② Variance (mt)"] = f"RMSE {bal_rmse:.3f}"

rows.append(total_row)

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

# =====================================================================
# FOOTER
# =====================================================================
st.write("---")
st.caption(
    f"Deckle range: {MIN_DECKLE}–{MAX_DECKLE} mm · "
    f"Min pattern tonnage: {MIN_PATTERN_MT} mt · "
    f"Quantity denomination: 500 kg steps · "
    f"Total valid patterns found: {len(all_patterns)} · "
    f"LP patterns evaluated: {len(all_patterns)}"
)
