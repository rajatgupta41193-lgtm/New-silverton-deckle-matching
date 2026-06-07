import streamlit as st
import itertools
import pandas as pd
import numpy as np
from scipy.optimize import minimize

# Set page configurations
st.set_page_config(page_title="Paper Mill Trim Optimizer", layout="wide", page_icon="🧻")

# =====================================================================
# 1. INITIAL SESSION STATE FOR DYNAMIC ITEMS
# =====================================================================
if "repository" not in st.session_state:
    st.session_state.repository = {
        "210 ml": [790, 600],
        "80/46 ml": [915, 790, 660],
        "60/46 ml": [917, 790, 660],
        "80/50 ml": [860, 718, 580],
        "50/46 new": [890, 764, 638]
    }

MIN_DECKLE = 2160
MAX_DECKLE = 2200

# =====================================================================
# 2. WEB APPLICATION SIDEBAR & USER RUN SETTINGS
# =====================================================================
st.sidebar.header("📋 Production Parameters")

total_material = st.sidebar.number_input(
    "Enter TOTAL quantity required (Metric Tons / mt):", 
    min_value=0.1, 
    value=12.0, 
    step=0.5,
    format="%.2f"
)

st.sidebar.subheader("Select Required Items for Current Run")
selected_items = []
for item in list(st.session_state.repository.keys()):
    if st.sidebar.checkbox(item, value=True, help=f"Current Widths: {st.session_state.repository[item]} mm"):
        selected_items.append(item)

st.sidebar.subheader("Target Weights per Item (mt)")
item_quantities = {}
for item in selected_items:
    default_val = round(total_material / max(len(selected_items), 1), 2)
    item_quantities[item] = st.sidebar.number_input(
        f"Target weight for {item}:", 
        min_value=0.0, 
        value=default_val, 
        step=0.5,
        format="%.2f",
        key=f"qty_{item}"
    )

if not selected_items:
    st.error("❌ Please select at least one item from the sidebar checklist to begin configuration.")
    st.stop()

# Strategy Selector Switch
st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Optimization Plan Option")
strategy_option = st.sidebar.radio(
    "Choose your priority strategy:",
    options=[
        "Option 1: Maximize Deckle (Strict Max 15% Quantity Shift)", 
        "Option 2: Balanced Strategy"
    ]
)

# =====================================================================
# 3. MAIN AREA: INVENTORY MANAGEMENT DASHBOARD
# =====================================================================
st.title("🧻 Paper Mill Production Deckle Optimization System")
st.markdown("Calculate zero-waste (0 mm trim) 3-reel slitter configurations with intelligent quantity balancing.")

with st.expander("🔧 MANAGE INVENTORY & CHANGE ITEM WIDTHS", expanded=False):
    st.subheader("Modify Widths of Existing Items or Create New Ones")
    col_manage_1, col_manage_2 = st.columns(2)
    
    with col_manage_1:
        st.markdown("**Option A: Modify or Add Item**")
        item_to_edit = st.selectbox(
            "Select an Item to change/create:", 
            options=list(st.session_state.repository.keys()) + ["-- Create New Item --"]
        )
        
        if item_to_edit == "-- Create New Item --":
            target_item_name = st.text_input("Enter New Product Name:", placeholder="e.g., 40ml new").strip()
            current_widths_str = ""
        else:
            target_item_name = item_to_edit
            current_widths_str = ", ".join(map(str, st.session_state.repository[item_to_edit]))
            
        widths_input = st.text_input(
            f"Enter width values for '{target_item_name}' (separate with commas):", 
            value=current_widths_str,
            placeholder="e.g., 790, 660, 600"
        )
        
        if st.button("💾 Save Changes / Add Product"):
            if target_item_name and widths_input:
                try:
                    parsed_widths = [int(w.strip()) for w in widths_input.split(",") if w.strip()]
                    if parsed_widths:
                        st.session_state.repository[target_item_name] = parsed_widths
                        st.success(f"Successfully updated '{target_item_name}' to {parsed_widths} mm!")
                        st.rerun()
                    else:
                        st.error("Please provide valid number widths.")
                except ValueError:
                    st.error("Widths must be whole numbers separated by commas.")
            else:
                st.error("Please complete both fields.")
                
    with col_manage_2:
        st.markdown("**Option B: Delete Item From List**")
        item_to_delete = st.selectbox("Select an item to completely remove:", options=list(st.session_state.repository.keys()))
        if st.button("🗑️ Delete Selected Item", type="primary"):
            if item_to_delete in st.session_state.repository:
                del st.session_state.repository[item_to_delete]
                st.success(f"Removed '{item_to_delete}' from system.")
                st.rerun()

# =====================================================================
# 4. DECKLE SCHEDULING & DYNAMIC OPTIMIZATION ENGINE
# =====================================================================
master_list = []
for item in selected_items:
    if item in st.session_state.repository:
        for w in st.session_state.repository[item]:
            master_list.append({"width": w, "product": item})

valid_patterns = []
seen_combinations = set()

for combo in itertools.combinations_with_replacement(master_list, 3):
    widths_sorted = tuple(sorted([item["width"] for item in combo]))
    products_sorted = tuple(sorted([item["product"] for item in combo]))
    total_width = sum(widths_sorted)

    if MIN_DECKLE <= total_width <= MAX_DECKLE:
        pattern_id = (total_width, widths_sorted, products_sorted)
        if pattern_id not in seen_combinations:
            seen_combinations.add(pattern_id)
            valid_patterns.append({
                "deckle": total_width,
                "widths": widths_sorted,
                "products": products_sorted
            })

if not valid_patterns:
    st.error("❌ Mathematically impossible to find a zero-waste 3-reel pattern with the chosen sizes within 2160 mm - 2200 mm.")
    st.stop()

valid_patterns.sort(key=lambda x: (-x["deckle"], x["widths"]))
operational_patterns = []
retained_products = set()

for pattern in valid_patterns:
    pattern_products = set(pattern["products"])
    if not pattern_products.issubset(retained_products) or pattern["deckle"] == MAX_DECKLE:
        operational_patterns.append(pattern)
        retained_products.update(pattern_products)

if len(operational_patterns) < 5:
    for pattern in valid_patterns:
        if pattern not in operational_patterns:
            operational_patterns.append(pattern)
        if len(operational_patterns) >= 6:
            break

num_pats = len(operational_patterns)
target_vector = np.array([item_quantities[item] for item in selected_items])

def get_yields_for_weights(w):
    yields = np.zeros(len(selected_items))
    for i, pattern in enumerate(operational_patterns):
        for width, prod in zip(pattern["widths"], pattern["products"]):
            if prod in selected_items:
                idx = selected_items.index(prod)
                yields[idx] += w[i] * (width / pattern["deckle"])
    return yields

constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - total_material}]
bounds = [(0.0, total_material) for _ in range(num_pats)]
initial_guess = [total_material / num_pats] * num_pats

if "Option 1" in strategy_option:
    def objective_opt1(w):
        return -1 * np.sum([w[i] * operational_patterns[i]["deckle"] for i in range(num_pats)])
    
    def quantity_lower_bound_constraint(w):
        return get_yields_for_weights(w) - (0.85 * target_vector)
    def quantity_upper_bound_constraint(w):
        return (1.15 * target_vector) - get_yields_for_weights(w)
        
    constraints.append({'type': 'ineq', 'fun': quantity_lower_bound_constraint})
    constraints.append({'type': 'ineq', 'fun': quantity_upper_bound_constraint})
    
    res = minimize(objective_opt1, initial_guess, bounds=bounds, constraints=constraints)
    raw_weights = res.x if res.success else initial_guess
else:
    def objective_opt2(w):
        calculated_yields = get_yields_for_weights(w)
        return np.sum((calculated_yields - target_vector) ** 2)
        
    res = minimize(objective_opt2, initial_guess, bounds=bounds, constraints=constraints)
    raw_weights = res.x if res.success else initial_guess

pattern_weights = [max(0.0, round(float(wt), 2)) for wt in raw_weights]

filtered_patterns = []
filtered_weights = []
for pat, wt in zip(operational_patterns, pattern_weights):
    if wt > 0.05:
        filtered_patterns.append(pat)
        filtered_weights.append(wt)

if filtered_patterns:
    operational_patterns = filtered_patterns
    pattern_weights = filtered_weights
else:
    operational_patterns = operational_patterns[:2]
    pattern_weights = [total_material / 2] * 2

simulated_yields = {item: 0.0 for item in selected_items}

# =====================================================================
# 5. BLUEPRINT WEB DASHBOARD DISPLAY & TEXT FORMATTING
# =====================================================================
st.header(f"📊 Production Blueprint Summary ({total_material:.2f} mt Total Run)")
if "Option 1" in strategy_option:
    st.info("🎯 Strategy: Option 1 Active. Maximizing deckle width while keeping item volumes within ±15% of targets.")
else:
    st.success("🎯 Strategy: Option 2 Active. Running custom weights per pattern to match your targets exactly.")

cols = st.columns(len(operational_patterns))
copyable_text_lines = []

for i, (pattern, p_weight) in enumerate(zip(operational_patterns, pattern_weights)):
    # FIX: Extract precise index values cleanly
    w1 = pattern["widths"][0]
    w2 = pattern["widths"][1]
    w3 = pattern["widths"][2]
    
