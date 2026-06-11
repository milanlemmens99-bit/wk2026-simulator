import streamlit as st
import pandas as pd
import random
import math
import os
from pathlib import Path
from collections import Counter

st.set_page_config(page_title="WK 2026 Analytics Pro", layout="wide")
st.title("🏆 WK 2026 Simulator & Predictor Dashboard")

# =========================================================================
# 0. CONFIGURATIE
# =========================================================================
if 'ingevulde_odds' not in st.session_state:
    st.session_state['ingevulde_odds'] = {}

# =========================================================================
# 1. DATA INLADEN (ROBUUST, ZONDER SPELERSDATA)
# =========================================================================
def bereken_vorm_multiplier(vorm_string):
    if pd.isna(vorm_string) or not isinstance(vorm_string, str): return 1.0
    resultaten = vorm_string.split('-')
    wegingen = [5, 4, 3, 2, 1]
    totale_score = sum(3 if res.upper() == 'W' else (1 if res.upper() == 'G' else 0) * wegingen[i] for i, res in enumerate(resultaten) if i < len(wegingen))
    return round(1.0 + ((totale_score - 22.5) / 225), 3)

@st.cache_data
def laad_data():
    files = os.listdir('.')
    data_file = next((f for f in files if f.startswith("wk_data")), None)
    if data_file is None:
        st.error(f"Geen bestand gevonden dat begint met 'wk_data'. Zorg dat wk_data.csv in de hoofdmap van GitHub staat.")
        return pd.DataFrame()
    try:
        df = pd.read_csv(data_file) if data_file.endswith('.csv') else pd.read_excel(data_file)
        df['Vorm_Multiplier'] = df['Vorm'].apply(bereken_vorm_multiplier)
        return df
    except Exception as e:
        st.error(f"Fout bij laden van {data_file}: {e}")
        return pd.DataFrame()

df_teams = laad_data()
if df_teams.empty: st.stop()

def clean_odd(tekst):
    try: return float(str(tekst).replace(',', '.'))
    except: return 2.0 

# =========================================================================
# 2. LOGICA (TACTIEK & STATS)
# =========================================================================
def bereken_odds_bonus(odd_waarde):
    return (1000 / math.log(float(odd_waarde) + 1)) - 400 if float(odd_waarde) > 0 else 0

def pak_tactische_kracht(team_row, handmatige_odd=None):
    kracht = (team_row['Elo'] * team_row['Vorm_Multiplier'] * 0.4) + (bereken_odds_bonus(handmatige_odd or team_row['Odd']) * 0.4) + (float(team_row['FC26']) * 20 * 0.1) + ((math.log(float(team_row['Marktwaarde']) + 1) * 50 if float(team_row['Marktwaarde']) > 0 else 0) * 0.1) + 400
    if team_row['Land'] in ["VS", "Mexico", "Canada"]: kracht += 40
    return kracht

def bereken_formatie_impact(thuis_formatie, uit_formatie):
    tempo, mod_t, mod_u = 1.0, 1.0, 1.0
    def verwerk(form, is_thuis):
        nonlocal tempo, mod_t, mod_u
        if pd.notna(form):
            p = form.split('-')
            if len(p) >= 3:
                if int(p[0]) >= 5: tempo -= 0.1; mod_u -= 0.15 if is_thuis else mod_t - 0.15
                if int(p[-1]) >= 3: tempo += 0.1; mod_t += 0.1 if is_thuis else mod_u + 0.1
    try: verwerk(thuis_formatie, True); verwerk(uit_formatie, False)
    except: pass
    return tempo, mod_t, mod_u

def bereken_micro_stats(goals_t, goals_u, exp_goals_t, exp_goals_u):
    # Realistische schoten gebaseerd op verwachte doelpuntwaarde (xG) in deze specifieke simulatie
    schot_t = max(goals_t, int(random.gauss(exp_goals_t * 9, 2)))
    schot_u = max(goals_u, int(random.gauss(exp_goals_u * 9, 2)))
    
    # 30-40% van de schoten is ongeveer op doel
    sot_t = max(goals_t, int(schot_t * random.uniform(0.3, 0.45)))
    sot_u = max(goals_u, int(schot_u * random.uniform(0.3, 0.45)))
    
    # Reddingen: Schoten op doel van tegenstander MINUS de doelpunten van tegenstander
    saves_t = max(0, sot_u - goals_u)
    saves_u = max(0, sot_t - goals_t)
    
    return schot_t, sot_t, saves_t, schot_u, sot_u, saves_u

# =========================================================================
# 3. SIMULATIE ENGINE
# =========================================================================
def simuleer_doelpunten(lambda_basis, temming=True):
    lambda_basis = max(0.01, min(6.0, lambda_basis)) 
    L, k, p = math.exp(-lambda_basis), 0, 1.0
    while p > L and k < 15: k += 1; p *= random.random()
    goals = k - 1
    if temming and lambda_basis < 3.0: 
        if goals == 3 and random.random() > 0.5: goals = 2
        elif goals >= 4 and random.random() > 0.2: goals = random.randint(1, 2)
    return max(0, goals)

def simuleer_wedstrijd_90min(thuis_team, uit_team, handmatige_odd_thuis=None, handmatige_odd_uit=None):
    # Deze snelle functie wordt gebruikt in de volledige WK toernooi simulator
    kracht_thuis = pak_tactische_kracht(thuis_team, handmatige_odd_thuis)
    kracht_uit = pak_tactische_kracht(uit_team, handmatige_odd_uit)
    elo_diff = (kracht_thuis - kracht_uit) / 400
    winstkans_thuis = 1 / (1 + math.pow(10, -elo_diff))
    
    tempo, mod_t, mod_u = bereken_formatie_impact(thuis_team['Formatie'], uit_team['Formatie'])
    
    xg_t = float(thuis_team.get('xG last 10', 1.3)) if pd.notna(thuis_team.get('xG last 10')) else 1.3
    xga_t = float(thuis_team.get('xGA last 10', 1.0)) if pd.notna(thuis_team.get('xGA last 10')) else 1.0
    xg_u = float(uit_team.get('xG last 10', 1.3)) if pd.notna(uit_team.get('xG last 10')) else 1.3
    xga_u = float(uit_team.get('xGA last 10', 1.0)) if pd.notna(uit_team.get('xGA last 10')) else 1.0

    base_t = ((xg_t + xga_u) / 2) * tempo
    base_u = ((xg_u + xga_t) / 2) * tempo

    lambda_thuis = max(0.1, min(4.0, base_t * (winstkans_thuis * 2) * mod_t))
    lambda_uit = max(0.1, min(4.0, base_u * ((1 - winstkans_thuis) * 2) * mod_u))
    
    return simuleer_doelpunten(lambda_thuis), simuleer_doelpunten(lambda_uit)

def simuleer_knockout_match(thuis, uit):
    g_t, g_u = simuleer_wedstrijd_90min(thuis, uit)
    details = f"{g_t} - {g_u}"
    if g_t == g_u:
        k_t, k_u = pak_tactische_kracht(thuis), pak_tactische_kracht(uit)
        win_prob = 1 / (1 + math.pow(10, -(k_t - k_u)/400))
        winnaar = thuis if random.random() < win_prob else uit
        return winnaar, f"{details} (n.v./w.n.s.)"
    return (thuis, details) if g_t > g_u else (uit, details)

def run_match_simulation(thuis_row, uit_row, odd1, oddX, odd2, runs=5000):
    # Uitgebreide simulator voor Scorito Helper & Losse Wedstrijd
    tot_impl = (1/odd1) + (1/oddX) + (1/odd2)
    b_prob_t, b_prob_x, b_prob_u = (1/odd1)/tot_impl, (1/oddX)/tot_impl, (1/odd2)/tot_impl

    elo_diff = (pak_tactische_kracht(thuis_row, odd1) - pak_tactische_kracht(uit_row, odd2)) / 400
    db_prob_t = (1 / (1 + math.pow(10, -elo_diff))) * 0.75 
    db_prob_u = (1 - (1 / (1 + math.pow(10, -elo_diff)))) * 0.75
    
    p_t = (b_prob_t * 0.7) + (db_prob_t * 0.3)
    p_x = (b_prob_x * 0.7) + (0.25 * 0.3)
    p_u = (b_prob_u * 0.7) + (db_prob_u * 0.3)
    tot_p = p_t + p_x + p_u
    p_t, p_x, p_u = p_t/tot_p, p_x/tot_p, p_u/tot_p
    
    xg_t = float(thuis_row.get('xG last 10', 1.3)) if pd.notna(thuis_row.get('xG last 10')) else 1.3
    xga_t = float(thuis_row.get('xGA last 10', 1.0)) if pd.notna(thuis_row.get('xGA last 10')) else 1.0
    xg_u = float(uit_row.get('xG last 10', 1.3)) if pd.notna(uit_row.get('xG last 10')) else 1.3
    xga_u = float(uit_row.get('xGA last 10', 1.0)) if pd.notna(uit_row.get('xGA last 10')) else 1.0

    stat_lambda_t, stat_lambda_u = (xg_t + xga_u) / 2, (xg_u + xga_t) / 2
    match_expected_goals = stat_lambda_t + stat_lambda_u

    custom_scores, thuis_wins, draws, uit_wins = Counter(), 0, 0, 0
    tot_shots_t, tot_sot_t, tot_saves_t, tot_shots_u, tot_sot_u, tot_saves_u = 0, 0, 0, 0, 0, 0

    for _ in range(runs):
        random_vlag = random.random()
        tempo, mod_t, mod_u = bereken_formatie_impact(thuis_row['Formatie'], uit_row['Formatie'])
        
        # Base Lambda is de uiteindelijke "xG" voor de specifieke simulatie van de wedstrijd
        base_lambda_t = (((match_expected_goals * (p_t / (p_t + p_u))) * 0.5) + (stat_lambda_t * 0.5)) * mod_t * tempo
        base_lambda_u = (((match_expected_goals * (p_u / (p_t + p_u))) * 0.5) + (stat_lambda_u * 0.5)) * mod_u * tempo

        if odd1 < 1.50: base_lambda_t += (1.50 - odd1) * 2.5
        if odd2 < 1.50: base_lambda_u += (1.50 - odd2) * 2.5
        
        if random_vlag < p_t:
            gt, gu = simuleer_doelpunten(base_lambda_t * 1.2, temming=False), simuleer_doelpunten(base_lambda_u * 0.6, temming=False)
            if gt <= gu: gt = gu + random.choice([1, 1, 2, 2, 3] if odd1 < 1.5 else [1, 1, 2])
            thuis_wins += 1
        elif random_vlag < (p_t + p_x):
            gt = simuleer_doelpunten(max(0.5, (base_lambda_t + base_lambda_u) / 2), temming=False)
            gu = gt; draws += 1
        else:
            gt, gu = simuleer_doelpunten(base_lambda_t * 0.6, temming=False), simuleer_doelpunten(base_lambda_u * 1.2, temming=False)
            if gu <= gt: gu = gt + random.choice([1, 1, 2, 2, 3] if odd2 < 1.5 else [1, 1, 2])
            uit_wins += 1
            
        custom_scores[f"{gt} - {gu}"] += 1
        
        # Micro stats berekenen voor deze exacte uitslag
        shots_t, sot_t, saves_t, shots_u, sot_u, saves_u = bereken_micro_stats(gt, gu, base_lambda_t, base_lambda_u)
        tot_shots_t += shots_t; tot_sot_t += sot_t; tot_saves_t += saves_t
        tot_shots_u += shots_u; tot_sot_u += sot_u; tot_saves_u += saves_u
        
    avg_stats = { 
        "shots_t": round(tot_shots_t/runs, 1), 
        "sot_t": round(tot_sot_t/runs, 1), 
        "saves_t": round(tot_saves_t/runs, 1), 
        "shots_u": round(tot_shots_u/runs, 1), 
        "sot_u": round(tot_sot_u/runs, 1), 
        "saves_u": round(tot_saves_u/runs, 1)
    }
    return custom_scores, thuis_wins, draws, uit_wins, avg_stats

# =========================================================================
# 4. USER INTERFACE & NAVIGATIE
# =========================================================================
fase = st.sidebar.radio("Toernooi Navigatie", ["Database & Teams", "WK Simulator (1 Run)", "Poule Scorito Helper", "Losse Wedstrijd Voorspellen"])

if fase == "Database & Teams":
    st.subheader("📊 Landen & Statistieken")
    st.dataframe(df_teams, use_container_width=True)

elif fase == "WK Simulator (1 Run)":
    st.header("⚽ Volledige WK 2026 Simulator")
    st.write("Klik op de knop om het toernooi live één keer te doorlopen.")
    
    if st.button("🚀 Start Wereldkampioenschap"):
        poules = df_teams['Poule'].unique()
        standen = {row['Land']: {"Land": row['Land'], "Poule": row['Poule'], "Elo": row['Elo'], "Vorm_Multiplier": row['Vorm_Multiplier'], "Formatie": row['Formatie'], "Odd": row['Odd'], "FC26": row['FC26'], "Marktwaarde": row['Marktwaarde'], "xG last 10": row.get('xG last 10', 1.3), "xGA last 10": row.get('xGA last 10', 1.0), "GS": 0, "W": 0, "G": 0, "V": 0, "DV": 0, "DT": 0, "DS": 0, "Pnt": 0} for _, row in df_teams.iterrows()}
        uitslagen_per_poule = {poule: [] for poule in poules}
        
        fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]

        with st.spinner('Bezig met groepsfase simuleren...'):
            for poule in poules:
                teams = df_teams[df_teams['Poule'] == poule].reset_index(drop=True)
                for t_idx, u_idx, sd in fifa_schema:
                    t, u = teams.iloc[t_idx], teams.iloc[u_idx]
                    gt, gu = simuleer_wedstrijd_90min(standen[t['Land']], standen[u['Land']])
                    uitslagen_per_poule[poule].append(f"Speeldag {sd}: **{t['Land']}** {gt} - {gu} **{u['Land']}**")
                    
                    standen[t['Land']]["GS"] += 1; standen[t['Land']]["DV"] += gt; standen[t['Land']]["DT"] += gu
                    standen[u['Land']]["GS"] += 1; standen[u['Land']]["DV"] += gu; standen[u['Land']]["DT"] += gt
                    if gt > gu:
                        standen[t['Land']]["Pnt"] += 3; standen[t['Land']]["W"] += 1; standen[u['Land']]["V"] += 1
                    elif gu > gt:
                        standen[u['Land']]["Pnt"] += 3; standen[u['Land']]["W"] += 1; standen[t['Land']]["V"] += 1
                    else:
                        standen[t['Land']]["Pnt"] += 1; standen[t['Land']]["G"] += 1
                        standen[u['Land']]["Pnt"] += 1; standen[u['Land']]["G"] += 1

            for l in standen: standen[l]["DS"] = standen[l]["DV"] - standen[l]["DT"]
            df_standen = pd.DataFrame(standen.values())

        st.markdown("## 📊 Groepsfase Uitslagen")
        col1, col2 = st.columns(2)
        p_winnaars, p_runnersup, p_nummers3 = {}, {}, []
        for idx, poule in enumerate(poules):
            p_stand = df_standen[df_standen['Poule'] == poule].sort_values(by=['Pnt', 'DS', 'DV', 'Elo'], ascending=[False, False, False, False]).reset_index(drop=True)
            p_winnaars[poule], p_runnersup[poule] = p_stand.iloc[0], p_stand.iloc[1]
            p_nummers3.append(p_stand.iloc[2])
            with col1 if idx % 2 == 0 else col2:
                st.markdown(f"### ➡️ {poule}")
                with st.expander(f"👁️ Bekijk uitslagen"):
                    for uitslag in uitslagen_per_poule[poule]: st.write(uitslag)
                st.dataframe(p_stand[["Land", "GS", "Pnt", "DV", "DT", "DS"]], hide_index=True)

        st.write("---")
        st.markdown("## ⚖️ Klassement Nummers 3")
        df_3e = pd.DataFrame(p_nummers3).sort_values(by=['Pnt', 'DS', 'DV', 'Elo'], ascending=[False, False, False, False]).reset_index(drop=True)
        df_3e['Status'] = '🔴 Uit'; df_3e.loc[0:7, 'Status'] = '🟢 DOOR'
        st.dataframe(df_3e[["Status", "Poule", "Land", "Pnt", "DS"]], hide_index=True)
        best_3e = list(df_3e.iloc[0:8]['Land'])

        st.write("---")
        st.markdown("## 🛑 Round of 32")
        colA, colB = st.columns(2)
        r32_matches = [
            ("M73", p_runnersup['Poule A'], p_runnersup['Poule B']), ("M74", p_winnaars['Poule E'], standen[best_3e[0]]),
            ("M75", p_winnaars['Poule F'], p_runnersup['Poule C']), ("M76", p_winnaars['Poule C'], p_runnersup['Poule F']),
            ("M77", p_winnaars['Poule I'], standen[best_3e[1]]), ("M78", p_runnersup['Poule E'], p_runnersup['Poule I']),
            ("M79", p_winnaars['Poule A'], standen[best_3e[2]]), ("M80", p_winnaars['Poule L'], standen[best_3e[3]]),
            ("M81", p_winnaars['Poule D'], standen[best_3e[4]]), ("M82", p_winnaars['Poule G'], standen[best_3e[5]]),
            ("M83", p_runnersup['Poule K'], p_runnersup['Poule L']), ("M84", p_winnaars['Poule H'], p_runnersup['Poule J']),
            ("M85", p_winnaars['Poule B'], standen[best_3e[6]]), ("M86", p_winnaars['Poule J'], p_runnersup['Poule H']),
            ("M87", p_winnaars['Poule K'], standen[best_3e[7]]), ("M88", p_runnersup['Poule D'], p_runnersup['Poule G'])
        ]
        w32 = {}
        for idx, (m_id, t1, t2) in enumerate(r32_matches):
            winnaar, uitslag = simuleer_knockout_match(t1, t2)
            w32[m_id] = winnaar
            with colA if idx < 8 else colB: st.write(f"**{m_id}**: {t1['Land']} vs {t2['Land']} ➔ **{winnaar['Land']}** ({uitslag})")

        st.markdown("## ⚡ Achtste Finales")
        r16_matches = [("M89", w32["M74"], w32["M77"]), ("M90", w32["M73"], w32["M75"]), ("M91", w32["M76"], w32["M78"]), ("M92", w32["M79"], w32["M80"]), ("M93", w32["M83"], w32["M84"]), ("M94", w32["M81"], w32["M82"]), ("M95", w32["M86"], w32["M88"]), ("M96", w32["M85"], w32["M87"])]
        w16, cols = {}, st.columns(2)
        for idx, (m_id, t1, t2) in enumerate(r16_matches):
            winnaar, uitslag = simuleer_knockout_match(t1, t2)
            w16[m_id] = winnaar
            with cols[idx % 2]: st.write(f"**{m_id}**: {t1['Land']} vs {t2['Land']} ➔ **{winnaar['Land']}** ({uitslag})")

        st.markdown("## 📐 Kwartfinales")
        q_matches = [("M97", w16["M89"], w16["M90"]), ("M98", w16["M93"], w16["M94"]), ("M99", w16["M91"], w16["M92"]), ("M100", w16["M95"], w16["M96"])]
        wq, cols = {}, st.columns(2)
        for idx, (m_id, t1, t2) in enumerate(q_matches):
            winnaar, uitslag = simuleer_knockout_match(t1, t2)
            wq[m_id] = winnaar
            with cols[idx % 2]: st.write(f"**{m_id}**: {t1['Land']} vs {t2['Land']} ➔ **{winnaar['Land']}** ({uitslag})")

        st.markdown("## 🏟️ Halve Finales")
        col_sf1, col_sf2 = st.columns(2)
        with col_sf1:
            w_sf1, u_sf1 = simuleer_knockout_match(wq["M97"], wq["M98"])
            st.write(f"**M101**: {wq['M97']['Land']} vs {wq['M98']['Land']} ➔ **{w_sf1['Land']}** ({u_sf1})")
        with col_sf2:
            w_sf2, u_sf2 = simuleer_knockout_match(wq["M99"], wq["M100"])
            st.write(f"**M102**: {wq['M99']['Land']} vs {wq['M100']['Land']} ➔ **{w_sf2['Land']}** ({u_sf2})")

        st.write("---"); st.markdown("## 👑 De Finale")
        w_final, u_final = simuleer_knockout_match(w_sf1, w_sf2)
        st.balloons()
        st.title(f"🎉 {w_final['Land']} IS WERELDKAMPIOEN 2026! 🎉")
        st.subheader(f"Finale uitslag: {w_sf1['Land']} {u_final} {w_sf2['Land']}")


elif fase == "Poule Scorito Helper":
    st.header("📋 Poule Scorito Helper")
    
    gekozen_poule = st.selectbox("Selecteer de poule:", df_teams['Poule'].unique())
    teams_poule = df_teams[df_teams['Poule'] == gekozen_poule].reset_index(drop=True)
    fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]
    
    match_inputs = {}
    for t_idx, u_idx, sd in fifa_schema:
        t_naam, u_naam = teams_poule.iloc[t_idx]['Land'], teams_poule.iloc[u_idx]['Land']
        key = f"{sd}_{t_naam}_{u_naam}"
        k1, kX, k2 = f"o1_{key}", f"oX_{key}", f"o2_{key}"
        
        st.write(f"**Speeldag {sd}: {t_naam} vs {u_naam}**")
        c1, c2, c3 = st.columns(3)
        odd_1_txt = c1.text_input(f"Winst {t_naam}", value=str(st.session_state['ingevulde_odds'].get(k1, "2.00")), key=f"txt_{k1}")
        odd_X_txt = c2.text_input("Gelijkspel", value=str(st.session_state['ingevulde_odds'].get(kX, "3.20")), key=f"txt_{kX}")
        odd_2_txt = c3.text_input(f"Winst {u_naam}", value=str(st.session_state['ingevulde_odds'].get(k2, "3.50")), key=f"txt_{k2}")
        
        st.session_state['ingevulde_odds'][k1], st.session_state['ingevulde_odds'][kX], st.session_state['ingevulde_odds'][k2] = odd_1_txt, odd_X_txt, odd_2_txt
        match_inputs[key] = {"t": teams_poule.iloc[t_idx], "u": teams_poule.iloc[u_idx], "odd1": clean_odd(odd_1_txt), "oddX": clean_odd(odd_X_txt), "odd2": clean_odd(odd_2_txt)}
    
    if st.button("🚀 Genereer Scorito tips voor poule"):
        for key, data in match_inputs.items():
            scores, _, _, _, _ = run_match_simulation(data['t'], data['u'], data['odd1'], data['oddX'], data['odd2'], runs=5000)
            score = scores.most_common(1)[0][0]
            st.success(f"**{data['t']['Land']} vs {data['u']['Land']}** 👉 **{score}**")

elif fase == "Losse Wedstrijd Voorspellen":
    st.header("🎯 Custom Match Predictor (Met Realistische Micro Stats)")
    poules = df_teams['Poule'].unique()
    opties, wedstrijd_mapping = [], {}
    fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]

    for poule in poules:
        teams = df_teams[df_teams['Poule'] == poule].reset_index(drop=True)
        for t_idx, u_idx, sd in fifa_schema:
            t_naam, u_naam = teams.iloc[t_idx]['Land'], teams.iloc[u_idx]['Land']
            titel = f"{poule} | Speeldag {sd}: {t_naam} vs. {u_naam}"
            opties.append(titel)
            wedstrijd_mapping[titel] = {"thuis_row": teams.iloc[t_idx], "uit_row": teams.iloc[u_idx], "thuis_naam": t_naam, "uit_naam": u_naam}

    gekozen = st.selectbox("🔮 Kies wedstrijd:", opties)
    match_data = wedstrijd_mapping[gekozen]
    t_row, u_row, t_naam, u_naam = match_data["thuis_row"], match_data["uit_row"], match_data["thuis_naam"], match_data["uit_naam"]

    col1, col2, col3 = st.columns(3)
    o1 = clean_odd(col1.text_input(f"Winst {t_naam} (1)", value="2.00"))
    oX = clean_odd(col2.text_input("Gelijkspel (X)", value="3.00"))
    o2 = clean_odd(col3.text_input(f"Winst {u_naam} (2)", value="3.00"))

    if st.button("📊 Bereken Score & Stats"):
        custom_scores, t_wins, draws, u_wins, avg_stats = run_match_simulation(t_row, u_row, o1, oX, o2, runs=5000)
        
        st.write("")
        st.subheader("🔮 Meest Waarschijnlijke Uitslag")
        top_score = custom_scores.most_common(1)[0][0]
        st.success(f"### 👉 Uitslag: {top_score}")

        st.write("---")
        st.subheader("📈 Verwachte Wedstrijdstatistieken")
        c_t, c_m, c_u = st.columns([2, 1, 2])
        
        with c_t:
            st.markdown(f"#### 👕 {t_naam}")
            st.write(f"🥅 Schoten: **{avg_stats['shots_t']}**")
            st.write(f"🎯 Op Doel: **{avg_stats['sot_t']}**")
            st.write(f"🧤 Reddingen: **{avg_stats['saves_t']}**")
            
        with c_m:
            st.write("")
            
        with c_u:
            st.markdown(f"#### 👕 {u_naam}")
            st.write(f"🥅 Schoten: **{avg_stats['shots_u']}**")
            st.write(f"🎯 Op Doel: **{avg_stats['sot_u']}**")
            st.write(f"🧤 Reddingen: **{avg_stats['saves_u']}**")