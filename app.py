    # ==========================================================
    # 1. TARIK SEMUA JADUAL & KIRA PURATA FDR 5 GAME AKAN DATANG
    # ==========================================================
    @st.cache_data(ttl=3600)
    def fetch_5gw_fdr(current_gw_id):
        all_fixtures = fetch_fpl_api("fixtures/")
        if not all_fixtures:
            return {}
        
        target_gws = list(range(current_gw_id, current_gw_id + 5))
        team_fdr_collector = {t_id: [] for t_id in range(1, 21)}
        
        for f in all_fixtures:
            if f.get("event") in target_gws:
                h = f["team_h"]
                a = f["team_a"]
                if h in team_fdr_collector:
                    team_fdr_collector[h].append(f["team_h_difficulty"])
                if a in team_fdr_collector:
                    team_fdr_collector[a].append(f["team_a_difficulty"])
                    
        # Kira purata FDR (Skor rendah = jadual mudah/hijau)
        avg_fdr_map = {}
        for t_id, diffs in team_fdr_collector.items():
            avg_fdr_map[t_id] = round(sum(diffs) / len(diffs), 2) if diffs else 3.0
            
        return avg_fdr_map

    team_5gw_fdr = fetch_5gw_fdr(gw_id)

    # ==========================================================
    # 2. PROSES PEMAIN & METRIK SERANGAN (GOL + ASSIST)
    # ==========================================================
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
            xg = float(p.get("expected_goals", 0) or 0)
            xa = float(p.get("expected_assists", 0) or 0)
        except Exception:
            xgi, xg, xa = 0.0, 0.0, 0.0

        try:
            form_val = float(p.get("form", 0) or 0)
        except Exception:
            form_val = 0.0

        # Set piece tagging
        is_pk = p.get("penalties_order") == 1
        is_fk = p.get("direct_freekicks_order") == 1
        is_ck = p.get("corners_and_indirect_freekicks_order") == 1

        sp_tags = []
        if is_pk: sp_tags.append("🎯 PK")
        if is_fk: sp_tags.append("⚡ FK")
        if is_ck: sp_tags.append("🚩 CK")
        sp_label = ", ".join(sp_tags) if sp_tags else "-"

        # Saringan Metrik Serangan: 
        # Untuk DEF & MID, singkirkan pemain yang tiada sumbangan serangan langsung
        # kecuali GK atau pertahanan dengan xGI / Set-Piece aktif
        has_attacking_output = (xgi >= 0.10) or is_pk or is_fk or is_ck or (p["element_type"] == 4)

        all_players[p["web_name"]] = {
            "id": p["id"],
            "name": p["web_name"],
            "full_name": f"{p['first_name']} {p['second_name']}",
            "club": team_map.get(p["team"], "Unknown"),
            "club_id": p["team"],
            "role": role_map.get(p["element_type"], "MID"),
            "element_type": p["element_type"],
            "min": int(p.get("minutes", 0)),
            "xGI": round(xgi, 2),
            "xG": round(xg, 2),
            "xA": round(xa, 2),
            "form": form_val,
            "has_attack_threat": has_attacking_output,
            "set_piece": sp_label,
            "is_pk": is_pk,
            "is_fk": is_fk,
            "is_ck": is_ck,
            "price": f"£{p.get('now_cost', 0) / 10:.1f}m",
            "fdr_5gw": team_5gw_fdr.get(p["team"], 3.0)
        }

    # ==========================================================
    # 3. KUNCI 10 PERLAWANAN GAMEWEEK
    # ==========================================================
    st.sidebar.header(f"📅 {gw_name} (10 Perlawanan)")

    fixture_options = []
    for idx, f in enumerate(fixtures_raw):
        h = team_map.get(f["team_h"], f"Team {f['team_h']}")
        a = team_map.get(f["team_a"], f"Team {f['team_a']}")
        fixture_options.append(f"M{idx+1}: {h} vs {a}")

    # Tetapkan secara lalai kepada SEMUA 10 Perlawanan
    selected_labels = st.sidebar.multiselect(
        "Pilihan Perlawanan:",
        options=fixture_options,
        default=fixture_options, # Kunci 10 perlawanan terus
        key="sel_all_10"
    )

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
            st.caption(f"FDR GW ini: {h_team} ({auto_fdr_h}) | {a_team} ({auto_fdr_a})")
            st.caption(f"Purata FDR 5-GW: {h_team} ({team_5gw_fdr.get(f['team_h'], 3.0)}) | {a_team} ({team_5gw_fdr.get(f['team_a'], 3.0)})")
            
            c1, c2, c3 = st.columns(3)
            o1 = c1.number_input(f"1", value=float(live_o1), step=0.05, key=f"o1_{idx}")
            ox = c2.number_input("X", value=float(live_ox), step=0.05, key=f"ox_{idx}")
            o2 = c3.number_input(f"2", value=float(live_o2), step=0.05, key=f"o2_{idx}")
            
            cb1, cb2 = st.columns(2)
            btts_y = cb1.number_input("BTTS Ya", value=1.75, step=0.05, key=f"by_{idx}")
            o25 = cb2.number_input("Over 2.5", value=float(live_o25), step=0.05, key=f"o25_{idx}")
            
            matches.append({
                "id": f"M{idx+1}", "home": h_team, "away": a_team,
                "odds_1": o1, "odds_x": ox, "odds_2": o2,
                "btts_yes": btts_y, "over_25": o25,
                "fdr_h": auto_fdr_h, "fdr_a": auto_fdr_a
            })

    # ==========================================================
    # 4. PENGIRAAN MATA UNJURAN (xG, xA & FDR 5-GW BOOST)
    # ==========================================================
    def calculate_official_fpl_points(p, m_rule):
        role = p["role"]
        xg = p["xG"]
        xa = p["xA"]
        form = p["form"]
        
        pts_appearance = 2.0 
        goal_pts = 6 if role in ["GKP", "DEF"] else (5 if role == "MID" else 4)
        assist_pts = 3.0
        
        # Pengiraan mata serangan tepat berdasarkan metrik xG dan xA
        pts_attacking = (xg * goal_pts) + (xa * assist_pts)
        
        # FDR minggu semasa
        fdr_gw = club_fdr.get(p["club"], 3)
        clean_sheet_prob = max(0.05, (6 - fdr_gw) / 5.0)
        
        if m_rule and (m_rule["all_attack"] or m_rule["over_25_val"] < 1.75):
            clean_sheet_prob *= 0.35
            
        pts_clean_sheet = 0.0
        if role in ["GKP", "DEF"]:
            pts_clean_sheet = clean_sheet_prob * 4.0
        elif role == "MID":
            pts_clean_sheet = clean_sheet_prob * 1.0
            
        pts_saves = 1.0 if role == "GKP" else 0.0
        
        # Bonus Set-piece & Penalti
        sp_bonus = 0.0
        if p.get("is_pk"): sp_bonus += 1.5
        if p.get("is_fk") or p.get("is_ck"): sp_bonus += 0.5
            
        form_bonus = form * 0.2
        
        # BONUS/PENALTI JADUAL 5-GW:
        # Jika purata FDR 5 game <= 2.6 (Sangat Mudah), tambah ganjaran portfolio
        fdr_5gw = p.get("fdr_5gw", 3.0)
        fixture_multiplier = 1.0
        if fdr_5gw <= 2.5:
            fixture_multiplier = 1.20   # Boost 20% untuk jadual 'sea of green'
        elif fdr_5gw <= 2.8:
            fixture_multiplier = 1.10   # Boost 10%
        elif fdr_5gw >= 3.6:
            fixture_multiplier = 0.90   # Tolak 10% jika 5 perlawanan berturut-turut sukar
        
        base_score = pts_appearance + pts_attacking + pts_clean_sheet + pts_saves + sp_bonus + form_bonus
        final_projected = base_score * fixture_multiplier
        
        return round(max(1.0, final_projected), 2)

    # ==========================================================
    # 5. TAPISAN PEMAIN LAYAK (HANYA DENGAN ANCAMAN SERANGAN)
    # ==========================================================
    eligible_players = {}
    for p_name, p in all_players.items():
        if any(b in p_name.lower() or b in p["full_name"].lower() for b in blacklist):
            continue
            
        p_club = p["club"]
        m_info = next((m for m in matches if m["home"].lower() in p_club.lower() or m["away"].lower() in p_club.lower()), None)
        
        if not m_info:
            continue
            
        r = match_rules[m_info["id"]]
        
        # SYARAT KHAS: Singkirkan pemain luar yang langsung tiada metrik serangan
        # (Kecualikan penjaga gol)
        if p["role"] != "GKP" and not p["has_attack_threat"]:
            continue
            
        p_data = dict(p)
        p_data["fdr"] = club_fdr.get(p_club, 3)
        p_data["fdr_score"] = calculate_official_fpl_points(p, r)
        eligible_players[p_name] = p_data

    # SUSUNAN POOL: Utamakan FDR 5-GW yang mudah dan skor serangan tinggi
    sorted_pool = sorted(
        eligible_players.values(),
        key=lambda x: (x["fdr_5gw"] <= 2.8, x["fdr"] <= 2, x["min"] >= 60, x["fdr_score"]),
        reverse=True
    )