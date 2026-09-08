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

    st.title("🏆 Enjin Portfolio 7 Skuad Juara FPL MFF (SOP v6.4 - Actual vs Predicted Tracker)")
    st.caption("Automasi Penuh: Perbandingan Mata Sebenar (Live API) vs Unjuran, Formasi Taktikal & Audit Skuad")

    @st.cache_data(ttl=1800)
    def fetch_fpl_api(endpoint):
        url = f"https://fantasy.premierleague.com/api/{endpoint}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception:
            return None

    @st.cache_data(ttl=120)
    def fetch_fpl_live(gw_id):
        url = f"https://fantasy.premierleague.com/api/event/{gw_id}/live/"
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

    # Tarik data mata sebenar (Live Actual Points)
    live_raw = fetch_fpl_live(gw_id)
    actual_stats = {}
    if live_raw and "elements" in live_raw:
        for item in live_raw["elements"]:
            pid = item["id"]
            stats_dict = item.get("stats", {})
            actual_stats[pid] = {
                "actual_pts": stats_dict.get("total_points", 0),
                "minutes": stats_dict.get("minutes", 0),
                "goals": stats_dict.get("goals_scored", 0),
                "assists": stats_dict.get("assists", 0),
                "clean_sheets": stats_dict.get("clean_sheets", 0),
                "bonus": stats_dict.get("bonus", 0)
            }

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

        try:
            form_val = float(p.get("form", 0) or 0)
        except Exception:
            form_val = 0.0

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
            "element_type": p["element_type"],
            "min": int(p.get("minutes", 0)),
            "xGI": round(xgi, 2),
            "form": form_val,
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
        url = f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds/?apiKey={api_key}®ions=uk,eu&markets=h2h,totals&oddsFormat=decimal"
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
            
            is_giant_home = (m["odds_1"] <= 1.50)
            is_giant_away = (m["odds_2"] <= 1.50)
            btts_extreme = (m["btts_yes"] < 1.65)
            
            underdog = a if is_giant_home else (h if is_giant_away else None)
            match_rules[m["id"]] = {
                "underdog": underdog, 
                "all_attack": btts_extreme,
                "btts_val": m["btts_yes"],
                "over_25_val": m["over_25"]
            }

        def calculate_official_fpl_points(p, m_rule):
            role = p["role"]
            xgi = p["xGI"]
            form = p["form"]
            
            pts_appearance = 2.0 
            goal_multiplier = 6 if role in ["GKP", "DEF"] else (5 if role == "MID" else 4)
            assist_multiplier = 3.0
            
            est_goals = xgi * 0.45
            est_assists = xgi * 0.55
            pts_attacking = (est_goals * goal_multiplier) + (est_assists * assist_multiplier)
            
            fdr = club_fdr.get(p["club"], 3)
            clean_sheet_prob = max(0.05, (6 - fdr) / 5.0)
            
            if m_rule and (m_rule["all_attack"] or m_rule["over_25_val"] < 1.75):
                clean_sheet_prob *= 0.35
                
            pts_clean_sheet = 0.0
            if role in ["GKP", "DEF"]:
                pts_clean_sheet = clean_sheet_prob * 4.0
            elif role == "MID":
                pts_clean_sheet = clean_sheet_prob * 1.0
                
            pts_saves = 1.0 if role == "GKP" else 0.0
            
            sp_bonus = 0.0
            if p.get("is_pk"):
                sp_bonus += 1.5
            if p.get("is_fk") or p.get("is_ck"):
                sp_bonus += 0.5
                
            form_bonus = form * 0.2
            
            total_projected_fpl_pts = pts_appearance + pts_attacking + pts_clean_sheet + pts_saves + sp_bonus + form_bonus
            return round(max(1.0, total_projected_fpl_pts), 2)

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
                if p["role"] in ["GKP", "DEF"] and p["xGI"] < 0.10 and not (p.get("is_fk") or p.get("is_ck")):
                    continue
            
            if r["all_attack"] and p["role"] in ["GKP", "DEF"]:
                if p["role"] == "GKP":
                    pass
                elif p["xGI"] < 0.05 and not (p.get("is_fk") or p.get("is_ck")):
                    continue
                    
            p_data = dict(p)
            p_data["fdr"] = club_fdr.get(p_club, 3)
            p_data["fdr_score"] = calculate_official_fpl_points(p, r)
            eligible_players[p_name] = p_data

        odds_badge = "🟢 Auto-Odds Aktif" if odds_data else "🟡 Odds Asas Digunakan"
        live_badge = "⚡ Data Mata Sebenar Aktif" if actual_stats else "⏳ Menunggu Perlawanan Bermula"
        st.info(f"🟢 **Status ({gw_name}):** Mengunci **{len(matches)} perlawanan** | **{len(eligible_players)} pemain layak** | {odds_badge} | {live_badge}")

        BLUEPRINTS = [
            {"name": "Skuad 1 (4-3-3 Attacking / 4-2-1-3)", "formation": "4-3-3", "xi": {"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3}},
            {"name": "Skuad 2 (3-4-3 Wing-Backs Attack)", "formation": "3-4-3", "xi": {"GKP": 1, "DEF": 3, "MID": 4, "FWD": 3}},
            {"name": "Skuad 3 (4-1-2-3 Heavy Attack)", "formation": "4-3-3", "xi": {"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3}},
            {"name": "Skuad 4 (4-2-3-1 Modern Possession)", "formation": "4-2-3-1", "xi": {"GKP": 1, "DEF": 4, "MID": 5, "FWD": 1}},
            {"name": "Skuad 5 (3-5-2 Midfield Control)", "formation": "3-5-2", "xi": {"GKP": 1, "DEF": 3, "MID": 5, "FWD": 2}},
            {"name": "Skuad 6 (4-5-1 Defensive Solid)", "formation": "4-5-1", "xi": {"GKP": 1, "DEF": 4, "MID": 5, "FWD": 1}},
            {"name": "Skuad 7 (5-4-1 Low Block Counter)", "formation": "5-4-1", "xi": {"GKP": 1, "DEF": 5, "MID": 4, "FWD": 1}}
        ]

        def get_match_id(club):
            for m in matches:
                if m["home"].lower() in club.lower() or m["away"].lower() in club.lower():
                    return m["id"]
            return None

        def get_player_actual(p_id):
            return actual_stats.get(p_id, {"actual_pts": 0, "minutes": 0, "goals": 0, "assists": 0, "clean_sheets": 0, "bonus": 0})

        def build_portfolio():
            global_counts = Counter()
            squads = []
            used_captains = set()
            
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
                    if global_counts[p["name"]] < 3 and p["fdr"] <= 3 and p["role"] in ["MID", "FWD"] and p["name"] not in used_captains
                ]
                
                if cap_candidates:
                    cap = cap_candidates[0]
                else:
                    fallback_cands = [p for p in sorted_pool if p["role"] in ["MID", "FWD"] and p["name"] not in used_captains]
                    cap = fallback_cands[0] if fallback_cands else sorted_pool[0]
                
                used_captains.add(cap["name"])
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
                
                # Unjuran Mata (Predicted Points)
                total_proj_pts = sum([p["fdr_score"] for p in xi]) + cap["fdr_score"]
                
                # Mata Sebenar FPL (Actual Live Points)
                cap_act = get_player_actual(cap["id"])
                vc_act = get_player_actual(vc["id"]) if vc else {"actual_pts": 0