import streamlit as st
import itertools
import pandas as pd

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

# 1. Request Total Run Volume
total_material = st.sidebar.number_input(
    "Enter TOTAL quantity required (Metric Tons / mt):", 
    min_value=0.1, 
    value=12.0, 
    step=0.5,
    format="%.2f"
)

# 2. Render Active Inventory Checklist
st.sidebar.subheader("Select Required Items for Current Run")
selected_items = []
for item in list(st.session_state.repository.keys()):
    if st.sidebar.checkbox(item, value=True, help=f"Current Widths: {st.session_state.repository[item]} mm"):
        selected_items.append(item)

# 3. Collect Target Baseline Weights dynamically
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

# =====================================================================
# 3. MAIN AREA: INVENTORY MANAGEMENT DASHBOARD
# =====================================================================
st.title("🧻 Paper Mill Production Deckle Optimization System")
st.markdown("Calculate zero-waste (0 mm trim) 3-reel slitter configurations prioritizing maximum deckle sizes.")

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
# 4. DECKLE SCHEDULING ENGINE
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

valid_patterns.sort(key=lambda x: (-x["deckle"], x["widths"]))

if not valid_patterns:
    st.error("❌ Mathematically impossible to find a zero-waste 3-reel pattern with the chosen sizes within 2160 mm - 2200 mm.")
    st.stop()

operational_patterns = []
retained_products = set()

for pattern in valid_patterns:
    pattern_products = set(pattern["products"])
    if not pattern_products.issubset(retained_products) or pattern["deckle"] == MAX_DECKLE:
        operational_patterns.append(pattern)
        retained_products.update(pattern_products)
    if len(retained_products) == len(selected_items) and len(operational_patterns) >= 2:
        break

if not operational_patterns and valid_patterns:
    operational_patterns = [valid_patterns[0]]

total_patterns = len(operational_patterns)
tonnage_per_pattern = total_material / total_patterns

# Crucial initialization fix for weight calculation tracking
simulated_yields = {item: 0.0 for item in selected_items}

# =====================================================================
# 5. BLUEPRINT WEB DASHBOARD DISPLAY & TEXT FORMATTING
# =====================================================================
st.header(f"📊 Production Blueprint Summary ({total_material:.2f} mt Total Run)")
st.info("💡 The system has optimized configurations to favor the 2200 mm deckle and guarantee 0 mm waste.")

cols = st.columns(total_patterns)
copyable_text_lines = []

for i, pattern in enumerate(operational_patterns):
    w1 = pattern["widths"][0]
    w2 = pattern["widths"][1]
    w3 = pattern["widths"][2]
    
    # Format perfectly: 638+645+917=2200 4.29 mt
    pattern_string = f"{w1}+{w2}+{w3}={pattern['deckle']} {tonnage_per_pattern:.2f} mt"
    copyable_text_lines.append(pattern_string)
    
    with cols[i]:
        st.subheader(f"✂️ Pattern {i+1}: Deckle {pattern['deckle']} mm")
        st.metric(label="Target Batch Allocation", value=f"{tonnage_per_pattern:.2f} mt")
        
        knife_data = []
        for j, (w, prod) in enumerate(zip(pattern["widths"], pattern["products"]), 1):
            weight_fraction = w / pattern["deckle"]
            calculated_mass = tonnage_per_pattern * weight_fraction
            if prod in simulated_yields:
                simulated_yields[prod] += calculated_mass
                
            knife_data.append({
                "Knife Target": f"Position #{j}",
                "Width (mm)": w,
                "Product Allocation": prod,
                "Yield Output (mt)": round(calculated_mass, 2)
            })
            
        st.table(pd.DataFrame(knife_data))

# =====================================================================
# 6. UNIFIED COPYABLE TEXT SECTION
# =====================================================================
st.write("---")
st.header("📋 Copyable Production Text")
st.markdown("Tap the button inside the box below to instantly copy these settings:")

final_copy_block = "\n".join(copyable_text_lines)
st.code(final_copy_block, language="text")

# =====================================================================
# 7. QUANTITY ADVICE COMPARISON VIEW
# =====================================================================
st.write("---")
st.header("⚖️ Quantity Advice Comparison (Target vs Optimized Output)")

comparison_rows = []
for prod in selected_items:
    target = item_quantities.get(prod, 0.0)
    actual = simulated_yields.get(prod, 0.0)
    variance = actual - target
    
    comparison_rows.append({
        "Product Name": prod,
        "Requested (mt)": round(target, 2),
        "Optimized Final Yield (mt)": round(actual, 2),
        "Variance Delta (mt)": f"+{variance:.2f}" if variance >= 0 else f"{variance:.2f}"
    })

df_compare = pd.DataFrame(comparison_rows)
st.dataframe(df_compare, use_container_width=True, hide_index=True)
