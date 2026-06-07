import streamlit as st
import itertools
import pandas as pd

# Set page configurations for mobile responsiveness and wide desktop screens
st.set_page_config(page_title="Paper Mill Trim Optimizer", layout="wide", page_icon="🧻")

# =====================================================================
# 1. INITIAL SESSION STATE FOR DYNAMIC ITEMS (Preset Inventory Repository)
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

# Input for overall run tonnage requirement
total_material = st.sidebar.number_input(
    "Enter TOTAL quantity required (Metric Tons / mt):", 
    min_value=0.1, 
    value=12.0, 
    step=0.5,
    format="%.2f"
)

# Render checkbox catalog of active manufacturing choices
st.sidebar.subheader("Select Required Items for Current Run")
selected_items = []
for item in list(st.session_state.repository.keys()):
    if st.sidebar.checkbox(item, value=True, help=f"Current Widths: {st.session_state.repository[item]} mm"):
        selected_items.append(item)

# Render target quantity input logs per size item
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

# Radio Strategy Selector Switch
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
# 3. MAIN DISPLAY AREA: INVENTORY CONFIGURATION DASHBOARD
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
# 4. ROBUST PURE PYTHON COMBINATORIAL OPTIMIZATION ENGINE
# =====================================================================
master_list = []
for item in selected_items:
    if item in st.session_state.repository:
        for w in st.session_state.repository[item]:
            master_list.append({"width": w, "product": item})

valid_patterns = []
seen_combinations = set()

# Process potential combos using exact 3-reel slitting thresholds
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

# Sort descending to favor the maximum machine limits
valid_patterns.sort(key=lambda x: (-x["deckle"], x["widths"]))

operational_patterns = []
retained_products = set()
for pattern in valid_patterns:
    pattern_products = set(pattern["products"])
    if not pattern_products.issubset(retained_products) or pattern["deckle"] == MAX_DECKLE:
        operational_patterns.append(pattern)
        retained_products.update(pattern_products)

if len(operational_patterns) < 4:
    for pattern in valid_patterns:
        if pattern not in operational_patterns:
            operational_patterns.append(pattern)
        if len(operational_patterns) >= 4:
            break

num_pats = len(operational_patterns)

# Calculate yields for a set of weights vector
def compute_yields(weights_list):
    yields = {item: 0.0 for item in selected_items}
    for idx, pattern in enumerate(operational_patterns):
        w_pat = weights_list[idx]
        for width, prod in zip(pattern["widths"], pattern["products"]):
            if prod in yields:
                yields[prod] += w_pat * (width / pattern["deckle"])
    return yields

best_weights = None

if "Option 1" in strategy_option:
    # --- STRATEGY 1: MAXIMIZE DECKLE SIZE WHILE HOLDING QUANTITY SHIFTS INSIDE ±15% ---
    best_score = float('-inf')
    for steps in itertools.product(range(0, 21), repeat=num_pats):
        s_sum = sum(steps)
        if s_sum == 0:
            continue
        test_w = [(s / s_sum) * total_material for s in steps]
        sim_y = compute_yields(test_w)
        
        valid_allocation = True
        for item in selected_items:
            req = item_quantities[item]
            if req > 0:
                deviation = abs(sim_y[item] - req) / req
                if deviation > 0.15:
                    valid_allocation = False
                    break
        
        if valid_allocation:
            score = sum(test_w[i] * operational_patterns[i]["deckle"] for i in range(num_pats))
            if score > best_score:
                best_score = score
                best_weights = test_w

    # Fallback protocol if constraints are too mathematically rigid for user inputs
    if best_weights is None:
        best_score = float('-inf')
        for steps in itertools.product(range(0, 21), repeat=num_pats):
            s_sum = sum(steps)
            if s_sum == 0:
                continue
            test_w = [(s / s_sum) * total_material for s in steps]
            sim_y = compute_yields(test_w)
            
            max_dev = max(abs(sim_y[item] - item_quantities[item]) / max(item_quantities[item], 0.1) for item in selected_items)
            score = sum(test_w[i] * operational_patterns[i]["deckle"] for i in range(num_pats)) - (max_dev * 10000)
            if score > best_score:
                best_score = score
                best_weights = test_w
else:
    # --- STRATEGY 2: BALANCED STRATEGY (MINIMIZE QUANTITY DEVIATION SHIFTS) ---
    best_score = float('inf')
    for steps in itertools.product(range(0, 21), repeat=num_pats):
        s_sum = sum(steps)
        if s_sum == 0:
            continue
        test_w = [(s / s_sum) * total_material for s in steps]
        sim_y = compute_yields(test_w)
        
        score = sum((sim_y[item] - item_quantities[item])**2 for item in selected_items)
        if score < best_score:
            best_score = score
            best_weights = test_w

if best_weights is None:
    best_weights = [total_material / num_pats] * num_patspattern_weights = [round(w, 2) for w in best_weights]Exclude idle patterns that carry near-zero allocation targetsfiltered_patterns = []filtered_weights = []for pat, wt in zip(operational_patterns, pattern_weights):if wt > 0.02:filtered_patterns.append(pat)filtered_weights.append(wt)if filtered_patterns:operational_patterns = filtered_patternspattern_weights = filtered_weightselse:operational_patterns = operational_patterns[:1]pattern_weights = [total_material]simulated_yields = {item: 0.0 for item in selected_items}=====================================================================5. BLUEPRINT WEB DASHBOARD DISPLAY & TEXT FORMATTING=====================================================================st.header(f"📊 Production Blueprint Summary ({total_material:.2f} mt Total Run)")if "Option 1" in strategy_option:st.info("🎯 Strategy: Option 1 Active. Maximizing deckle width while holding item volumes as close to ±15% as mathematically possible.")else:st.success("🎯 Strategy: Option 2 Active. Running custom weights per pattern to match your targets exactly.")cols = st.columns(len(operational_patterns))copyable_text_lines = []for i, (pattern, p_weight) in enumerate(zip(operational_patterns, pattern_weights)):# Safe index positioning extraction to clean up equation linesw1 = pattern["widths"][0]w2 = pattern["widths"][1]w3 = pattern["widths"][2]# Generate requested clean copy frame: 638+645+917=2200 4.29 mtpattern_string = f"{w1}+{w2}+{w3}={pattern['deckle']} {p_weight:.2f} mt"copyable_text_lines.append(pattern_string)with cols[i]:st.subheader(f"✂️ Pattern {i+1}: Deckle {pattern['deckle']} mm")st.metric(label="Target Batch Allocation", value=f"{p_weight:.2f} mt")knife_data = []for j, (w, prod) in enumerate(zip(pattern["widths"], pattern["products"]), 1):weight_fraction = w / pattern["deckle"]calculated_mass = p_weight * weight_fractionif prod in simulated_yields:simulated_yields[prod] += calculated_massknife_data.append({"Knife Target": f"Position #{j}","Width (mm)": w,"Product Allocation": prod,"Yield Output (mt)": round(calculated_mass, 2)})st.table(pd.DataFrame(knife_data))=====================================================================6. UNIFIED COPYABLE TEXT SECTION=====================================================================st.write("---")st.header("📋 Copyable Production Text")st.markdown("Tap the button inside the box below to instantly copy these settings:")final_copy_block = "\n".join(copyable_text_lines)st.code(final_copy_block, language="text")=====================================================================7. QUANTITY ADVICE COMPARISON VIEW=====================================================================st.write("---")st.header("⚖️ Quantity Advice Comparison (Target vs Optimized Output)")comparison_rows = []for prod in selected_items:target = item_quantities.get(prod, 0.0)actual = simulated_yields.get(prod, 0.0)variance = actual - targetcomparison_rows.append({"Product Name": prod,"Requested (mt)": round(target, 2),"Optimized Final Yield (mt)": round(actual, 2),"Variance Delta (mt)": f"+{variance:.2f}" if variance >= 0 else f"{variance:.2f}"})df_compare = pd.DataFrame(comparison_rows)st.dataframe(df_compare, use_container_width=True, hide_index=True)
