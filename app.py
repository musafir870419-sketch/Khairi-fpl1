import streamlit as st
import pandas as pd
from collections import Counter
import urllib.request
import json

st.set_page_config(page_title="Sistem Portfolio FPL MFF", layout="wide")

# ==========================================================
# 0. KESELAMATAN: SOROKKAN MENU & FOOTER STREAMLIT
# ==========================================================
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stAppDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)

# ==========================================================
# KESELAMATAN: PENGESAHAN PIN
# ==========================================================
PIN_RAHSIA = "870419"

if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False

if not st.session_state["auth_ok"]:
    st.title("🔒 Akses Terhad")
    st.info("Sistem Analisis Strategi FPL MFF (Akses Peribadi)")
    
    user_pin = st.text_input("Masukkan PIN Keselamatan:", type="password")
    if st.button("Buka Kunci Sistem", type="primary"):
        if user_pin == PIN_RAHSIA:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("PIN Tidak Sah!")
else:
    # ==========================================================
    # KANDUNGAN UTAMA SISTEM (HANYA DIBUKA JIKA PIN BETUL)
    # ==========================================================
    ODDS_API_KEY = "4c5a97480b5a82fa022dd02e9833d8e7"

    st.title("🏆 Enjin Portfolio 7 Skuad Juara FPL MFF (SOP v5.7)")
    st.caption("Automasi Penuh: Kawalan PIN, Custom Match Selector, Live API, Auto-FDR & Auto-Odds")

    @st.cache_data(ttl=1800)
    def fetch_fpl_api(endpoint):
        url = f"https://fantasy.premierleague.com/api/{endpoint}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception:
            return None

    fpl_raw = fetch_fpl_api("bootstrap-static/")
    if not fpl_raw:
        st.error("Gagal menyambung ke FPL API. Sila segarkan pelayar.")
        st.stop()

    next_event = next((e for e in fpl_raw["events"] if e.get("is_next")), None)
    if not next_event:
        next_event = next((e for e in fpl_raw["events"] if e.get("is_current")), fpl_raw["events"][0])

    gw_id = next_event["id"]
    gw_name = next_event["name"]

    fixtures_raw = fetch_fpl_api(f"fixtures/?event={gw_id}")
    if not fixtures_raw:
        st.error("Gagal menarik data perlawanan.")
        st.stop()

    team_map = {t["id"]: t["name"] for t in fpl_raw["teams"]}
    role_map = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

    all_players = {}
    for p in fpl_raw["elements"]:
        chance = p.get("chance_of_playing_next_round")
        status = p.get("status")
        if chance == 0 or status in ['i', 's', 'u']:
            continue
            
        try:
            xgi = float(p.get("expected_goal_involvements", 0) or 0)
        except Exception:
            xgi = 0.0

        sp_tags = []
        if p.get("penalties_order") == 1:
            sp_tags.append("🎯 PK")
        elif p.get("penalties_order") == 2:
            sp_tags.append("PK-2")

        if p.get("direct_freekicks_order") == 1:
            sp_tags.append("⚡ FK")

        if p.get("corners_and_indirect_freekicks_order") == 1:
            sp_tags.append("🚩 CK")

        sp_label = ", ".join(sp_tags) if sp_tags else "-"

        all_players[p["web_name"]] = {
            "id": p["id"],
            "name": p["web_name"],
            "full_name": f"{p['first_name']} {p['second_name']}",
            "club": team_map.get(p["team"], "Unknown"),
            "role": role_map.get(p["element_type"], "MID"),
            "min": int(p.get("minutes", 0)),
            "xGI": round(xgi, 2),
            "set_piece": sp_label,
            "is_pk": p.get("penalties_order") == 1,
            "is_fk": p.get("direct_freekicks_order") == 1,
            "is_ck": p.get("corners_and_indirect_freekicks_order") == 1,
            "price": f"£{p.get('now_cost', 0) / 10:.1f}m"
        }

    @st.cache_data(ttl=21600)
    def fetch_live_odds(api_key):
        if not api_key:
            return []
        url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={api_key}&regions=uk,eu&markets=h2h,totals&oddsFormat=decimal"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception:
            return []

    odds_data = fetch_live_odds(ODDS_API_KEY)

    def normalize_team(name):
        n = name.lower().replace("fc", "").replace("afc", "").replace("&", "and").strip()
        aliases = {
            "man city": "manchester city",
            "man utd": "manchester united",
            "spurs": "tottenham hotspur",
            "tottenham": "tottenham hotspur",
            "wolves": "wolverhampton wanderers",
            "nott'm forest": "nottingham forest",
            "west ham": "west ham united",
            "newcastle": "newcastle united",
            "brighton": "brighton and hove albion",
            "leicester": "leicester city",
            "ipswich": "ipswich town"
        }
        for k, v in aliases.items():
            if k in n:
                return v
        return n

    def get_market_odds(home_name, away_name):
        h_norm = normalize_team(home_name)
        a_norm = normalize_team(away_name)
        
        for ev in odds_data:
            ev_h = normalize_team(ev.get("home_team", ""))
            ev_a = normalize_team(ev.get("away_team", ""))
            if (h_norm in ev_h or ev_h in h_norm) and (a_norm in ev_a or ev_a in a_norm):
                bookmakers = ev.get("bookmakers", [])
                if bookmakers:
                    bm = bookmakers[0]
                    o1, ox, o2, o25 = 2.00, 3.40, 3.20, 1.85
                    for m in bm.get("markets", []):
                        if m["key"] == "h2h":
                            for out in m["outcomes"]:
                                if out["name"] == ev["home_team"]: o1 = out["price"]
                                elif out["name"] == ev["away_team"]: o2 = out["price"]
                                else: ox = out["price"]
                        elif m["key"] == "totals":
                            for out in m["outcomes"]:
                                if out["name"].lower() == "over" and out.get("point") == 2.5:
                                    o25 = out["price"]
                    return o1, ox, o2, o25
        return 2.00, 3.40, 3.20, 1.85

    st.sidebar.header(f"📅 {gw_name} (Pilihan Perlawanan)")

    fixture_options = []
    for idx, f in enumerate(fixtures_raw):
        h = team_map.get(f["team_h"], f"Team {f['team_h']}")
        a = team_map.get(f["team_a"], f"Team {f['team_a']}")
        fixture_options.append(f"M{idx+1}: {h} vs {a}")

    preset_mode = st.sidebar.selectbox(
        "Pilihan Mod Pantas:",
        [
            "4 Perlawanan Terawal (Game 1-4)",
            "4 Perlawanan Terakhir",
            "Semua 10 Perlawanan",
            "Pilih Bebas / Kustom (Tanda Sendiri)"
        ]
    )

    if preset_mode == "4 Perlawanan Terawal (Game 1-4)":
        default_sel = fixture_options[:4]
    elif preset_mode == "4 Perlawanan Terakhir":
        default_sel = fixture_options[-4:]
    elif preset_mode == "Semua 10 Perlawanan":
        default_sel = fixture_options
    else:
        default_sel = fixture_options[1:5] if len(fixture_options) >= 5 else fixture_options[:4]

    selected_labels = st.sidebar.multiselect(
        "Senarai Perlawanan:",
        options=fixture_options,
        default=default_sel,
        key=f"sel_{preset_mode}"
    )

    if not selected_labels:
        st.warning("⚠️ Sila pilih sekurang-kurangnya 1 perlawanan di menu sisi.")
    else:
        selected_indices = [fixture_options.index(lbl) for lbl in selected_labels]
        selected_indices.sort()

        matches = []
        for idx in selected_indices:
            f = fixtures_raw[idx]
            h_team = team_map.get(f["team_h"], f"Team {f['team_h']}")
            a_team = team_map.get(f["team_a"], f"Team {f['team_a']}")
            auto_fdr_h = f.get("team_h_difficulty", 3)
            auto_fdr_a = f.get("team_a_difficulty", 3)
            
            live_o1, live_ox, live_o2, live_o25 = get_market_odds(h_team, a_team)
            
            with st.sidebar.expander(f"M{idx+1}: {h_team} vs {a_team}", expanded=False):
                st.markdown(f"**FDR Rasmi:** {h_team} (`{auto_fdr_h}`) vs {a_team} (`{auto_fdr_a}`)")
                c1, c2, c3 = st.columns(3)
                o1 = c1.number_input(f"1 ({h_team[:3]})", value=float(live_o1), step=0.05, key=f"o1_{idx}")
                ox = c2.number_input("X", value=float(live_ox), step=0.05, key=f"ox_{idx}")
                o2 = c3.number_input(f"2 ({a_team[:3]})", value=float(live_o2), step=0.05, key=f"o2_{idx}")
                
                cb1, cb2 = st.columns(2)
                btts_y = cb1.number_input("BTTS Ya", value=1.75, step=0.05, key=f"by_{idx}")
                o25 = cb2.number_input("Over 2.5", value=float(live_o25), step=0.05, key=f"o25_{idx}")
                
                matches.append({
                    "id": f"M{idx+1}", "home": h_team, "away": a_team,
                    "odds_1": o1, "odds_x": ox, "odds_2": o2,
                    "btts_yes": btts_y, "over_25": o25,
                    "fdr_h": auto_fdr_h, "fdr_a": auto_fdr_a
                })

        st.sidebar.header("2. Senarai Hitam Tambahan")
        blacklist_input = st.sidebar.text_area("Pemain Ditolak (Nama Web FPL)", "Mateta, Caicedo, Philogene")
        blacklist = [name.strip().lower() for name in blacklist_input.split(",") if name.strip()]

        club_fdr = {}
        match_rules = {}

        for m in matches:
            h, a = m["home"], m["away"]
            club_fdr[h] = m["fdr_h"]
            club_fdr[a] = m["fdr_a"]
            
            is_giant_home = (m["odds_1"] <= 1.60)
            is_giant_away = (m["odds_2"] <= 1.60)
            btts_extreme = (m["btts_yes"] < 1.60)
            
            underdog = a if is_giant_home else (h if is_giant_away else None)
            match_rules[m["id"]] = {"underdog": underdog, "all_attack": btts_extreme}

        def calculate_fdr_score(p):
            fdr = club_fdr.get(p["club"], 3)
            fdr_multiplier = (6 - fdr) / 3.0
            
            if p["role"] in ["DEF", "GKP"] and fdr >= 4:
                fdr_multiplier *= 0.5
                
            base_score = p["xGI"] * fdr_multiplier
            
            sp_bonus = 0.0
            if p.get("is_pk"):
                sp_bonus += 0.35
            if p.get("is_fk"):
                sp_bonus += 0.10
            if p.get("is_ck"):
                sp_bonus += 0.10
                
            return round(base_score + sp_bonus, 3)

        eligible_players = {}
        for p_name, p in all_players.items():
            if any(b in p_name.lower() or b in p["full_name"].lower() for b in blacklist):
                continue
                
            p_club = p["club"]
            m_info = next((m for m in matches if m["home"].lower() in p_club.lower() or m["away"].lower() in p_club.lower()), None)
            
            if not m_info:
                continue
                
            r = match_rules[m_info["id"]]
            if r["underdog"] and r["underdog"].lower() in p_club.lower():
                continue
            if r["all_attack"] and p["role"] in ["GKP", "DEF"]:
                continue
                    
            p_data = dict(p)
            p_data["fdr"] = club_fdr.get(p_club, 3)
            p_data["fdr_score"] = calculate_fdr_score(p)
            eligible_players[p_name] = p_data

        odds_badge = "🟢 Auto-Odds Aktif" if odds_data else "🟡 Odds Asas Digunakan"
        st.info(f"🟢 **Status ({gw_name}):** Mengunci **{len(matches)} perlawanan** | **{len(eligible_players)} pemain layak** | {odds_badge}")

        BLUEPRINTS = [
            {"name": "Skuad 1 (5-3-2)", "formation": "5-3-2", "xi": {"GKP": 1, "DEF": 5, "MID": 3, "FWD": 2}},
            {"name": "Skuad 2 (4-4-2)", "formation": "4-4-2", "xi": {"GKP": 1, "DEF": 4, "MID": 4, "FWD": 2}},
            {"name": "Skuad 3 (4-5-1)", "formation": "4-5-1", "xi": {"GKP": 1, "DEF": 4, "MID": 5, "FWD": 1}},
            {"name": "Skuad 4 (3-4-3)", "formation": "3-4-3", "xi": {"GKP": 1, "DEF": 3, "MID": 4, "FWD": 3}},
            {"name": "Skuad 5 (3-5-2)", "formation": "3-5-2", "xi": {"GKP": 1, "DEF": 3, "MID": 5, "FWD": 2}},
            {"name": "Skuad 6 (4-3-3)", "formation": "4-3-3", "xi": {"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3}},
            {"name": "Skuad 7 (5-4-1)", "formation": "5-4-1", "xi": {"GKP": 1, "DEF": 5, "MID": 4, "FWD": 1}}
        ]

        def get_match_id(club):
            for m in matches:
                if m["home"].lower() in club.lower() or m["away"].lower() in club.lower():
                    return m["id"]
            return None

        def build_portfolio():
            global_counts = Counter()
            squads = []
            
            sorted_pool = sorted(
                eligible_players.values(),
                key=lambda x: (x["fdr"] <= 2, x["min"] >= 60, x["fdr_score"]),
                reverse=True
            )
            
            for bp in BLUEPRINTS:
                selected = []
                club_counts = Counter()
                role_counts = Counter()
                limits = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
                
                cap_candidates = [
                    p for p in sorted_pool 
                    if global_counts[p["name"]] < 3 and p["fdr"] <= 3 and p["role"] in ["MID", "FWD"]
                ]
                cap = cap_candidates[0] if cap_candidates else sorted_pool[0]
                selected.append(cap)
                club_counts[cap["club"]] += 1
                role_counts[cap["role"]] += 1
                
                for p in sorted_pool:
                    if len(selected) == 15:
                        break
                    if p["name"] in [x["name"] for x in selected]:
                        continue
                    if global_counts[p["name"]] >= 3:
                        continue
                    if club_counts[p["club"]] >= 3:
                        continue
                    if role_counts[p["role"]] >= limits[p["role"]]:
                        continue
                        
                    selected.append(p)
                    club_counts[p["club"]] += 1
                    role_counts[p["role"]] += 1
                    
                cap_m = get_match_id(cap["club"])
                vc_cands = [p for p in selected if get_match_id(p["club"]) != cap_m and p["name"] != cap["name"]]
                vc = max(vc_cands, key=lambda x: x["fdr_score"]) if vc_cands else (selected[1] if len(selected) > 1 else cap)
                
                xi_roles = dict(bp["xi"])
                xi = []
                bench = []
                
                for priority_p in [cap, vc]:
                    if priority_p:
                        r = priority_p["role"]
                        if xi_roles.get(r, 0) > 0 and priority_p not in xi:
                            xi.append(priority_p)
                            xi_roles[r] -= 1
                            
                rem = [p for p in selected if p not in xi]
                rem.sort(key=lambda x: x["fdr_score"], reverse=True)
                
                for p in rem:
                    r = p["role"]
                    if xi_roles.get(r, 0) > 0:
                        xi.append(p)
                        xi_roles[r] -= 1
                    else:
                        bench.append(p)
                        
                bench_g = [p for p in bench if p["role"] == "GKP"]
                bench_out = sorted([p for p in bench if p["role"] != "GKP"], key=lambda x: x["fdr_score"], reverse=True)
                
                for p in selected:
                    global_counts[p["name"]] += 1
                    
                squads.append({
                    "name": bp["name"],
                    "formation": bp["formation"],
                    "C": cap["name"] if cap else "-",
                    "VC": vc["name"] if vc else "-",
                    "xi": xi,
                    "bench": bench_g + bench_out,
                    "clubs": dict(club_counts)
                })
                
            return squads, global_counts

        if st.button("🚀 Jana Portfolio 7 Skuad Juara Sekarang", type="primary"):
            if len(eligible_players) < 15:
                st.error("Pemain layak tidak mencukupi untuk membentuk skuad. Pilih sekurang-kurangnya 3-4 perlawanan.")
            else:
                squads, exp_counts = build_portfolio()
                st.subheader("📋 Rumusan Portfolio 7 Skuad Lengkap")
                tabs = st.tabs([s["name"] for s in squads])
                
                for i, tab in enumerate(tabs):
                    sq = squads[i]
                    with tab:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Formasi", sq["formation"])
                        c2.write(f"**Kapten [C]:** :green[{sq['C']}] | **VC:** :blue[{sq['VC']}]")
                        c3.write(f"**Disiplin Kelab:** {sq['clubs']}")
                        
                        c_xi, c_bench = st.columns([3, 2])
                        with c_xi:
                            st.markdown("#### ⚽ Kesebelasan Utama (XI)")
                            st.dataframe(pd.DataFrame([{
                                "Pos": p["role"],
                                "Pemain": p["name"],
                                "Kelab": p["club"],
                                "Set Piece": p["set_piece"],
                                "Harga": p["price"],
                                "FDR": p["fdr"],
                                "xGI": p["xGI"],
                                "Skor Akhir": p["fdr_score"]
                            } for p in sq["xi"]]), use_container_width=True, hide_index=True)
                            
                        with c_bench:
                            st.markdown("#### 🪑 Bangku Simpanan")
                            st.dataframe(pd.DataFrame([{
                                "Turutan": f"Sub {idx}" if idx > 0 else "Sub GKP",
                                "Pos": p["role"],
                                "Pemain": p["name"],
                                "Kelab": p["club"],
                                "Set Piece": p["set_piece"],
                                "FDR": p["fdr"],
                                "xGI": p["xGI"]
                            } for idx, p in enumerate(sq["bench"])]), use_container_width=True, hide_index=True)

                st.markdown("---")
                st.subheader("📊 Audit Siling Monopoli Aset (Maksimum 3 Kemunculan / ≤ 43%)")
                st.dataframe(pd.DataFrame([
                    {"Pemain": p, "Kemunculan": f"{cnt}/7 Skuad", "Pendedahan": f"{round(cnt/7*100, 1)}%", "Status": "PATUH" if cnt <= 3 else "LEBIH HAD"}
                    for p, cnt in exp_counts.most_common()
                ]), use_container_width=True, hide_index=True)