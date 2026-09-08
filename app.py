import streamlit as st
import requests
import pandas as pd
from collections import Counter

st.set_page_config(
    page_title="Portfolio Generator FPL v6.4",
    page_icon="⚽",
    layout="wide"
)

# ==========================================
# 1. KESELAMATAN & PENGESAHAN PIN
# ==========================================
CORRECT_PIN = "1994"  # Tukar PIN anda di sini jika perlu

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Kawalan Keselamatan FPL Portfolio")
    pin_input = st.text_input("Masukkan PIN Keselamatan:", type="password")
    if st.button("Masuk"):
        if pin_input == CORRECT_PIN:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("PIN salah. Sila cuba lagi.")
    st.stop()

# ==========================================
# 2. FUNGSI AMBIL DATA (API & CACHE)
# ==========================================
ODDS_API_KEY = "4c5a97480b5a82fa022dd02e"  # Kunci The Odds API anda

@st.cache_data(ttl=3600)
def get_fpl_bootstrap():
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
        return res.json()
    return None

@st.cache_data(ttl=3600)
def get_fpl_fixtures():
    url = "https://fantasy.premierleague.com/api/fixtures/"
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
        return res.json()
    return None

@st.cache_data(ttl=120)
def get_fpl_live(gw):
    url = f"https://fantasy.premierleague.com/api/event/{gw}/live/"
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
        return res.json()
    return None

@st.cache_data(ttl=21600)
def get_odds_data(api_key):
    if not api_key:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={api_key}&regions=uk,eu&markets=h2h,totals"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

# Muat data asas
bootstrap_data = get_fpl_bootstrap()
fixtures_data = get_fpl_fixtures()

if not bootstrap_data or not fixtures_data:
    st.error("Gagal menyambung ke pelayan FPL API. Sila muat semula sebentar lagi.")
    st.stop()

# Kenal pasti Gameweek semasa / akan datang
events = bootstrap_data.get("events", [])
current_gw = next((e["id"] for e in events if e.get("is_next")), None)
if not current_gw:
    current_gw = next((e["id"] for e in events if e.get("is_current")), 1)

# Ambil data mata sebenar (Live)
live_data = get_fpl_live(current_gw)

# Petakan Nama Pasukan
teams_dict = {t["id"]: t["name"] for t in bootstrap_data.get("teams", [])}
team_short_dict = {t["id"]: t["short_name"] for t in bootstrap_data.get("teams", [])}

# Tapis Jadual GW Semasa
gw_fixtures = [f for f in fixtures_data if f.get("event") == current_gw]

# ==========================================
# 3. MENU SISI (SIDEBAR CONTROLS)
# ==========================================
st.sidebar.header(f"⚙️ Tetapan Gameweek {current_gw}")

if st.sidebar.button("🔄 Segarkan Data (Clear Cache)"):
    st.cache_data.clear()
    st.rerun()

# Pilihan Pantas Perlawanan
st.sidebar.subheader("Pilih Perlawanan")
preset_options = ["Semua Perlawanan", "4 Perlawanan Terawal (Game 1-4)", "Pilihan Manual"]
preset = st.sidebar.selectbox("Mod Pilihan Jadual:", preset_options)

fixture_display_list = []
fixture_map = {}
for f in gw_fixtures:
    h_team = teams_dict.get(f["team_h"], f"Team {f['team_h']}")
    a_team = teams_dict.get(f["team_a"], f"Team {f['team_a']}")
    label = f"{h_team} vs {a_team}"
    fixture_display_list.append(label)
    fixture_map[label] = f

if preset == "Semua Perlawanan":
    selected_labels = fixture_display_list
elif preset == "4 Perlawanan Terawal (Game 1-4)":
    selected_labels = fixture_display_list[:4]
else:
    selected_labels = st.sidebar.multiselect("Pilih Perlawanan:", fixture_display_list, default=fixture_display_list[:5])

selected_team_ids = set()
for lbl in selected_labels:
    f_obj = fixture_map[lbl]
    selected_team_ids.add(f_obj["team_h"])
    selected_team_ids.add(f_obj["team_a"])

# Senarai Hitam Pemain
st.sidebar.subheader("🚫 Senarai Hitam (Blacklist)")
blacklist_str = st.sidebar.text_input("Nama pemain (pisahkan dengan koma):", value="Mateta, Caicedo")
blacklist = [name.strip().lower() for name in blacklist_str.split(",") if name.strip()]

# ==========================================
# 4. PEMPROSESAN DATA PEMAIN & PRESTASI
# ==========================================
raw_players = bootstrap_data.get("elements", [])
element_types = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# Dapatkan data odds untuk penapis CS bolos
odds_list = get_odds_data(ODDS_API_KEY)

def calculate_player_metrics(p):
    team_id = p["team"]
    pos = element_types.get(p["element_type"], "MID")
    
    # Nilai Asas Prestasi
    xgi = float(p.get("expected_goal_involvements", 0.0) or 0.0)
    form = float(p.get("form", 0.0) or 0.0)
    
    # Nilai Tugasan Bola Mati
    set_piece_bonus = 0.0
    if p.get("penalties_order") == 1:
        set_piece_bonus += 1.5
    if p.get("corners_and_indirect_freekicks_order") in [1, 2]:
        set_piece_bonus += 0.5
    if p.get("direct_freekicks_order") in [1, 2]:
        set_piece_bonus += 0.5
        
    # Unjuran Skor Kesukaran & Pertahanan
    pred_score = (form * 1.2) + (xgi * 4.5) + set_piece_bonus
    
    if pos in ["GKP", "DEF"]:
        # Asas Clean Sheet jika bermain
        pred_score += 4.0
        # Potongan 65% jika perlawanan dijangka ada lambakan gol
        if len(odds_list) > 0:
            pred_score *= 0.65
            
    return round(pred_score, 1)

eligible_players = []
for p in raw_players:
    # Tapis pasukan yang dipilih
    if p["team"] not in selected_team_ids:
        continue
    # Tapis kecederaan kritikal
    if p.get("chance_of_playing_next_round") is not None and p["chance_of_playing_next_round"] < 50:
        continue
    # Tapis senarai hitam
    web_name = p.get("web_name", "").lower()
    full_name = f"{p.get('first_name', '')} {p.get('second_name', '')}".lower()
    if any(b in web_name or b in full_name for b in blacklist):
        continue
        
    p_copy = dict(p)
    p_copy["pos"] = element_types.get(p["element_type"], "MID")
    p_copy["club"] = teams_dict.get(p["team"], "Unknown")
    p_copy["score"] = calculate_player_metrics(p)
    eligible_players.append(p_copy)

# ==========================================
# 5. FUNGSI PENJEJAK MATA SEBENAR (LIVE)
# ==========================================
def get_player_actual(p_id):
    if not live_data:
        return {"minutes": 0, "actual_pts": 0}
    elements_live = live_data.get("elements", [])
    matched = next((el for el in elements_live if el["id"] == p_id), None)
    if matched:
        stats = matched.get("stats", {})
        return {
            "minutes": stats.get("minutes", 0),
            "actual_pts": stats.get("total_points", 0)
        }
    return {"minutes": 0, "actual_pts": 0}

# ==========================================
# 6. ENJIN GENERATOR PORTFOLIO (7 SKUAD)
# ==========================================
FORMATIONS = [
    {"def": 3, "mid": 4, "fwd": 3, "name": "3-4-3 (Serangan Berbisa)"},
    {"def": 3, "mid": 5, "fwd": 2, "name": "3-5-2 (Dominasi Tengah)"},
    {"def": 4, "mid": 4, "fwd": 2, "name": "4-4-2 (Seimbang Standard)"},
    {"def": 4, "mid": 3, "fwd": 3, "name": "4-3-3 (Triniti Sayap)"},
    {"def": 5, "mid": 3, "fwd": 2, "name": "5-3-2 (Kubu Kebal)"},
    {"def": 5, "mid": 4, "fwd": 1, "name": "5-4-1 (Pertahanan Padat)"},
    {"def": 3, "mid": 4, "fwd": 3, "name": "3-4-3 (Differensial Berani)"}
]

st.title("🏆 Generator Portfolio FPL - 7 Skuad Dinamik")
st.write(f"🟢 **Status:** Mengunci {len(selected_labels)} perlawanan ({len(eligible_players)} pemain layak melepasi tapisan).")

if len(eligible_players) < 25:
    st.warning("⚠️ Kolam pemain terlalu kecil. Sila pilih sekurang-kurangnya 4 hingga 5 perlawanan di menu sisi.")
    st.stop()

# Kiraan kekerapan pemain (had siling <= 43% / maks 3 kemunculan)
usage_tracker = Counter()
used_captains = set()
squads_generated = []

for i, fmt in enumerate(FORMATIONS):
    squad_xi = []
    
    # Urutkan kolam mengikut unjuran tertinggi dan tapis had pendedahan
    avail = [p for p in eligible_players if usage_tracker[p["id"]] < 3]
    avail.sort(key=lambda x: x["score"], reverse=True)
    
    gkp_pool = [p for p in avail if p["pos"] == "GKP"]
    def_pool = [p for p in avail if p["pos"] == "DEF"]
    mid_pool = [p for p in avail if p["pos"] == "MID"]
    fwd_pool = [p for p in avail if p["pos"] == "FWD"]
    
    # Pilih Barisan Utama mengikut Formasi
    selected_gkp = gkp_pool[:1]
    selected_def = def_pool[:fmt["def"]]
    selected_mid = mid_pool[:fmt["mid"]]
    selected_fwd = fwd_pool[:fmt["fwd"]]
    
    squad_xi = selected_gkp + selected_def + selected_mid + selected_fwd
    
    # Pilih Kapten Berbeza (Wajib MID/FWD)
    att_candidates = [p for p in squad_xi if p["pos"] in ["MID", "FWD"]]
    att_candidates.sort(key=lambda x: x["score"], reverse=True)
    
    capt = None
    for cand in att_candidates:
        if cand["id"] not in used_captains:
            capt = cand
            used_captains.add(cand["id"])
            break
    if not capt and att_candidates:
        capt = att_candidates[0]
        
    # Pilih Naib Kapten
    vc_candidates = [p for p in att_candidates if p["id"] != (capt["id"] if capt else -1)]
    vc = vc_candidates[0] if vc_candidates else (squad_xi[1] if len(squad_xi) > 1 else squad_xi[0])
    
    # Rekodkan penggunaan pemain
    for p in squad_xi:
        usage_tracker[p["id"]] += 1
        
    # Pilih Bangku Simpanan (1 GKP, Baki DEF/MID/FWD)
    bench = []
    b_gkp = [p for p in gkp_pool if p not in squad_xi]
    if b_gkp: bench.append(b_gkp[0])
    b_others = [p for p in avail if p not in squad_xi and p not in bench]
    bench.extend(b_others[:3])
    
    # Kiraan Mata Langsung Sebenar (Actual Points)
    total_actual = 0
    total_pred = 0
    
    c_act = get_player_actual(capt["id"]) if capt else {"actual_pts": 0, "minutes": 0}
    vc_act = get_player_actual(vc["id"]) if vc else {"actual_pts": 0}  # Baris 475 yang telah dibaiki
    
    for p in squad_xi:
        act_info = get_player_actual(p["id"])
        total_pred += p["score"]
        
        # Logik Kapten / VC
        if capt and p["id"] == capt["id"]:
            if c_act.get("minutes", 0) > 0:
                total_actual += act_info["actual_pts"] * 2
            else:
                total_actual += act_info["actual_pts"]
                if vc and p["id"] == vc["id"]:
                    total_actual += vc_act.get("actual_pts", 0)
        else:
            total_actual += act_info["actual_pts"]

    squads_generated.append({
        "index": i + 1,
        "name": f"Skuad #{i+1} ({fmt['name']})",
        "xi": squad_xi,
        "bench": bench,
        "capt": capt,
        "vc": vc,
        "total_pred": round(total_pred, 1),
        "total_actual": total_actual
    })

# ==========================================
# 7. PAPARAN KEPUTUSAN & PAPAN MARKAH
# ==========================================
st.subheader("📊 Papan Kedudukan Langsung 7 Skuad")
leaderboard_data = []
for sq in squads_generated:
    leaderboard_data.append({
        "Skuad": sq["name"],
        "Kapten": sq["capt"]["web_name"] if sq["capt"] else "-",
        "Naib Kapten": sq["vc"]["web_name"] if sq["vc"] else "-",
        "Unjuran Mata": sq["total_pred"],
        "Mata Sebenar (Live)": sq["total_actual"]
    })

df_leaderboard = pd.DataFrame(leaderboard_data)
df_leaderboard = df_leaderboard.sort_values(by="Mata Sebenar (Live)", ascending=False).reset_index(drop=True)
st.dataframe(df_leaderboard, use_container_width=True)

st.write("---")

# Paparan Terperinci Mengikut Tab
tabs = st.tabs([f"Skuad #{sq['index']}" for sq in squads_generated])

for idx, sq in enumerate(squads_generated):
    with tabs[idx]:
        col_info1, col_info2, col_info3 = st.columns(3)
        col_info1.metric("Formasi", sq["name"].split("(")[-1].replace(")", ""))
        col_info2.metric("Unjuran Mata", sq["total_pred"])
        col_info3.metric("Mata Sebenar (Live)", sq["total_actual"])
        
        st.markdown(f"**Kapten (C):** `{sq['capt']['web_name'] if sq['capt'] else '-'}` | **Naib Kapten (VC):** `{sq['vc']['web_name'] if sq['vc'] else '-'}`")
        
        st.write("#### ⚽ Kesebelasan Utama (XI)")
        xi_rows = []
        for p in sq["xi"]:
            act = get_player_actual(p["id"])
            p_name = p["web_name"]
            if sq["capt"] and p["id"] == sq["capt"]["id"]:
                p_name += " (C)"
            elif sq["vc"] and p["id"] == sq["vc"]["id"]:
                p_name += " (VC)"
                
            xi_rows.append({
                "Pos": p["pos"],
                "Pemain": p_name,
                "Kelab": p["club"],
                "Minit": act["minutes"],
                "Unjuran": p["score"],
                "Mata Sebenar": act["actual_pts"]
            })
        st.dataframe(pd.DataFrame(xi_rows), use_container_width=True)
        
        if sq["bench"]:
            st.write("#### 🪑 Bangku Simpanan")
            bench_rows = []
            for p in sq["bench"]:
                act = get_player_actual(p["id"])
                bench_rows.append({
                    "Pos": p["pos"],
                    "Pemain": p["web_name"],
                    "Kelab": p["club"],
                    "Minit": act["minutes"],
                    "Mata Sebenar": act["actual_pts"]
                })
            st.dataframe(pd.DataFrame(bench_rows), use_container_width=True)
