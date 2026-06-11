import streamlit as st
import pandas as pd
import random
import math
from pathlib import Path
from collections import Counter

st.set_page_config(page_title="WK 2026 Analytics Pro", layout="wide")
st.title("🏆 WK 2026 Simulator & Predictor Dashboard")

BASE_TOTAL_GOALS = 1.9
MIN_GOALS = 0.1

# =========================================================================
# 0. GEHEUGEN (SESSION STATE) INITIALISEREN
# =========================================================================
if 'ingevulde_odds' not in st.session_state:
    st.session_state['ingevulde_odds'] = {}

# =========================================================================
# 1. DATA INLADEN & CODE CONFIGURATIE (INCLUSIEF xG & xGA)
# =========================================================================
def bereken_vorm_multiplier(vorm_string):
    if pd.isna(vorm_string) or not isinstance(vorm_string, str):
        return 1.0
    resultaten = vorm_string.split('-')
    wegingen = [5, 4, 3, 2, 1]
    totale_score = 0
    for i, res in enumerate(resultaten):
        if i < len(wegingen):
            punten = 3 if res.upper() == 'W' else (1 if res.upper() == 'G' else 0)
            totale_score += punten * wegingen[i]
    return round(1.0 + ((totale_score - 22.5) / 225), 3)

@st.cache_data
def laad_data():
    # Lijst alle bestanden in de map
    files = os.listdir('.')
    
    # Zoek naar een bestand dat begint met 'wk_data'
    data_file = next((f for f in files if f.startswith("wk_data")), None)
    
    if data_file is None:
        st.error(f"Geen bestand gevonden dat begint met 'wk_data'. Gevonden bestanden: {files}")
        return pd.DataFrame()
    
    # Laad op basis van extensie
    try:
        if data_file.endswith('.csv'):
            df = pd.read_csv(data_file)
        else:
            df = pd.read_excel(data_file)
            
        # Check kolommen
        required = {"Land", "Poule", "Elo", "Marktwaarde", "Odd", "FC26", "Formatie", "Vorm", "xG last 10", "xGA last 10"}
        if not required.issubset(df.columns):
            st.error(f"Kolommen missen! Gevonden kolommen: {list(df.columns)}")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Fout bij openen van {data_file}: {e}")
        return pd.DataFrame()

df_teams = laad_data()
if df_teams.empty:
    st.stop()

df_teams['Vorm_Multiplier'] = df_teams['Vorm'].apply(bereken_vorm_multiplier)

def clean_odd(tekst):
    try:
        return float(str(tekst).replace(',', '.'))
    except:
        return 2.0 

# =========================================================================
# 2. TACTISCHE BEREKENINGEN & MICRO STATS
# =========================================================================
def bereken_odds_bonus(odd_waarde):
    odd = float(odd_waarde)
    if odd > 0:
        return (1000 / math.log(odd + 1)) - 400
    return 0

def pak_tactische_kracht(team_row, handmatige_odd=None):
    elo_kracht = team_row['Elo'] * team_row['Vorm_Multiplier']
    actuele_odd = handmatige_odd if handmatige_odd is not None else team_row['Odd']
    odds_bonus = bereken_odds_bonus(actuele_odd)
    fc26_kracht = float(team_row['FC26']) * 20
    marktwaarde = float(team_row['Marktwaarde'])
    marktwaarde_bonus = (math.log(marktwaarde + 1) * 50) if marktwaarde > 0 else 0

    super_rating = (elo_kracht * 0.4) + (odds_bonus * 0.4) + (fc26_kracht * 0.1) + (marktwaarde_bonus * 0.1) + 400

    if team_row['Land'] in ["VS", "Mexico", "Canada"]:
        super_rating += 40
    return super_rating

def bereken_formatie_impact(thuis_formatie, uit_formatie):
    wedstrijd_tempo = 1.0 
    thuis_modifier, uit_modifier = 1.0, 1.0
    
    def verwerk_formatie(formatie_str, is_thuis):
        nonlocal wedstrijd_tempo, thuis_modifier, uit_modifier
        if pd.notna(formatie_str) and isinstance(formatie_str, str):
            parts = formatie_str.split('-')
            if len(parts) >= 3:
                if int(parts[0]) >= 5: 
                    wedstrijd_tempo -= 0.1
                    if is_thuis: uit_modifier -= 0.15
                    else: thuis_modifier -= 0.15
                if int(parts[-1]) >= 3: 
                    wedstrijd_tempo += 0.1
                    if is_thuis: thuis_modifier += 0.1
                    else: uit_modifier += 0.1

    try:
        verwerk_formatie(thuis_formatie, True)
        verwerk_formatie(uit_formatie, False)
    except Exception: 
        pass
        
    return wedstrijd_tempo, thuis_modifier, uit_modifier

# --- NIEUW: Functie voor Schoten & Reddingen ---
def bereken_micro_stats(goals_t, goals_u, xg_t, xg_u):
    # Schoten berekenen (gemiddeld 9 schoten per 1.0 xG)
    verwacht_schoten_t = max(goals_t, int(random.gauss(xg_t * 9, 2)))
    verwacht_schoten_u = max(goals_u, int(random.gauss(xg_u * 9, 2)))
    
    # Schoten op doel (meestal 35% van totaal, minimaal gelijk aan goals)
    sot_t = max(goals_t, int(verwacht_schoten_t * random.uniform(0.3, 0.5)))
    sot_u = max(goals_u, int(verwacht_schoten_u * random.uniform(0.3, 0.5)))
    
    # Reddingen keepers
    saves_keeper_t = max(0, sot_u - goals_u)
    saves_keeper_u = max(0, sot_t - goals_t)
    
    return verwacht_schoten_t, sot_t, saves_keeper_t, verwacht_schoten_u, sot_u, saves_keeper_u


# =========================================================================
# 3. SIMULATIE ENGINE
# =========================================================================
def simuleer_doelpunten(lambda_basis, temming=True):
    lambda_basis = max(0.01, min(6.0, lambda_basis)) 
    L = math.exp(-lambda_basis)
    k = 0; p = 1.0
    while p > L and k < 15:
        k += 1; p *= random.random()
    goals = k - 1
    if temming and lambda_basis < 3.0: 
        if goals == 3 and random.random() > 0.5: goals = 2
        elif goals >= 4 and random.random() > 0.2: goals = random.randint(1, 2)
    return max(0, goals)

def simuleer_wedstrijd_90min(thuis_team, uit_team, handmatige_odd_thuis=None, handmatige_odd_uit=None):
    kracht_thuis = pak_tactische_kracht(thuis_team, handmatige_odd_thuis)
    kracht_uit = pak_tactische_kracht(uit_team, handmatige_odd_uit)
    elo_diff = (kracht_thuis - kracht_uit) / 400
    winstkans_thuis = 1 / (1 + math.pow(10, -elo_diff))
    winstkans_uit = 1 - winstkans_thuis
    
    tempo, mod_thuis, mod_uit = bereken_formatie_impact(thuis_team['Formatie'], uit_team['Formatie'])
    
    xg_t = float(thuis_team.get('xG last 10', 1.3)) if pd.notna(thuis_team.get('xG last 10')) else 1.3
    xga_t = float(thuis_team.get('xGA last 10', 1.0)) if pd.notna(thuis_team.get('xGA last 10')) else 1.0
    xg_u = float(uit_team.get('xG last 10', 1.3)) if pd.notna(uit_team.get('xG last 10')) else 1.3
    xga_u = float(uit_team.get('xGA last 10', 1.0)) if pd.notna(uit_team.get('xGA last 10')) else 1.0

    base_t = ((xg_t + xga_u) / 2) * tempo
    base_u = ((xg_u + xga_t) / 2) * tempo

    lambda_thuis = max(0.1, min(4.0, base_t * (winstkans_thuis * 2) * mod_thuis))
    lambda_uit = max(0.1, min(4.0, base_u * (winstkans_uit * 2) * mod_uit))
    
    return simuleer_doelpunten(lambda_thuis), simuleer_doelpunten(lambda_uit)

def simuleer_knockout_match(thuis, uit):
    g_t, g_u = simuleer_wedstrijd_90min(thuis, uit)
    details = f"{g_t} - {g_u}"
    if g_t == g_u:
        k_t = pak_tactische_kracht(thuis)
        k_u = pak_tactische_kracht(uit)
        win_prob = 1 / (1 + math.pow(10, -(k_t - k_u)/400))
        if random.random() < win_prob:
            return thuis, f"{details} (n.v./w.n.s.)"
        else:
            return uit, f"{details} (n.v./w.n.s.)"
    return (thuis, details) if g_t > g_u else (uit, details)

# --- DE ULTIEME SCORITO HYBRIDE REKENMACHINE (MET MICRO STATS) ---
def run_match_simulation(thuis_row, uit_row, odd1, oddX, odd2, runs=5000):
    impliciete_kans_thuis = 1 / odd1
    impliciete_kans_gelijk = 1 / oddX
    impliciete_kans_uit = 1 / odd2
    totaal_impliciet = impliciete_kans_thuis + impliciete_kans_gelijk + impliciete_kans_uit
    
    bookie_prob_thuis = impliciete_kans_thuis / totaal_impliciet
    bookie_prob_gelijk = impliciete_kans_gelijk / totaal_impliciet
    bookie_prob_uit = impliciete_kans_uit / totaal_impliciet

    kracht_thuis = pak_tactische_kracht(thuis_row, odd1)
    kracht_uit = pak_tactische_kracht(uit_row, odd2)
    elo_diff = (kracht_thuis - kracht_uit) / 400
    
    db_prob_thuis = (1 / (1 + math.pow(10, -elo_diff))) * 0.75 
    db_prob_uit = (1 - (1 / (1 + math.pow(10, -elo_diff)))) * 0.75
    db_prob_gelijk = 0.25

    prob_thuis = (bookie_prob_thuis * 0.7) + (db_prob_thuis * 0.3)
    prob_gelijk = (bookie_prob_gelijk * 0.7) + (db_prob_gelijk * 0.3)
    prob_uit = (bookie_prob_uit * 0.7) + (db_prob_uit * 0.3)
    
    totaal_hybride = prob_thuis + prob_gelijk + prob_uit
    prob_thuis /= totaal_hybride
    prob_gelijk /= totaal_hybride
    prob_uit /= totaal_hybride
    
    xg_t = float(thuis_row.get('xG last 10', 1.3)) if pd.notna(thuis_row.get('xG last 10')) else 1.3
    xga_t = float(thuis_row.get('xGA last 10', 1.0)) if pd.notna(thuis_row.get('xGA last 10')) else 1.0
    xg_u = float(uit_row.get('xG last 10', 1.3)) if pd.notna(uit_row.get('xG last 10')) else 1.3
    xga_u = float(uit_row.get('xGA last 10', 1.0)) if pd.notna(uit_row.get('xGA last 10')) else 1.0

    stat_lambda_t = (xg_t + xga_u) / 2
    stat_lambda_u = (xg_u + xga_t) / 2
    match_expected_goals = stat_lambda_t + stat_lambda_u

    custom_scores = Counter()
    thuis_wins, uit_wins, draws = 0, 0, 0
    
    # We houden de totalen bij van alle schoten om het gemiddelde te bepalen
    tot_shots_t, tot_sot_t, tot_saves_t = 0, 0, 0
    tot_shots_u, tot_sot_u, tot_saves_u = 0, 0, 0

    for _ in range(runs):
        random_vlag = random.random()
        tempo, mod_thuis, mod_uit = bereken_formatie_impact(thuis_row['Formatie'], uit_row['Formatie'])
        
        base_lambda_t = ((match_expected_goals * (prob_thuis / (prob_thuis + prob_uit))) * 0.5) + (stat_lambda_t * 0.5)
        base_lambda_t = base_lambda_t * mod_thuis * tempo

        base_lambda_u = ((match_expected_goals * (prob_uit / (prob_thuis + prob_uit))) * 0.5) + (stat_lambda_u * 0.5)
        base_lambda_u = base_lambda_u * mod_uit * tempo

        if odd1 < 1.50: base_lambda_t += (1.50 - odd1) * 2.5
        if odd2 < 1.50: base_lambda_u += (1.50 - odd2) * 2.5
        
        if random_vlag < prob_thuis:
            gt = simuleer_doelpunten(base_lambda_t * 1.2, temming=False)
            gu = simuleer_doelpunten(base_lambda_u * 0.6, temming=False)
            if gt <= gu: gt = gu + random.choice([1, 1, 2, 2, 3] if odd1 < 1.5 else [1, 1, 2])
            thuis_wins += 1
        elif random_vlag < (prob_thuis + prob_gelijk):
            gemiddelde_lambda = max(0.5, (base_lambda_t + base_lambda_u) / 2)
            gt = simuleer_doelpunten(gemiddelde_lambda, temming=False)
            gu = gt
            draws += 1
        else:
            gt = simuleer_doelpunten(base_lambda_t * 0.6, temming=False)
            gu = simuleer_doelpunten(base_lambda_u * 1.2, temming=False)
            if gu <= gt: gu = gt + random.choice([1, 1, 2, 2, 3] if odd2 < 1.5 else [1, 1, 2])
            uit_wins += 1
            
        custom_scores[f"{gt} - {gu}"] += 1
        
        # Micro stats updaten per gesimuleerde wedstrijd
        shots_t, sot_t, saves_t, shots_u, sot_u, saves_u = bereken_micro_stats(gt, gu, xg_t, xg_u)
        tot_shots_t += shots_t
        tot_sot_t += sot_t
        tot_saves_t += saves_t
        tot_shots_u += shots_u
        tot_sot_u += sot_u
        tot_saves_u += saves_u
        
    # Bereken de gemiddelden na alle simulaties
    avg_stats = {
        "shots_t": round(tot_shots_t / runs, 1),
        "sot_t": round(tot_sot_t / runs, 1),
        "saves_t": round(tot_saves_t / runs, 1),
        "shots_u": round(tot_shots_u / runs, 1),
        "sot_u": round(tot_sot_u / runs, 1),
        "saves_u": round(tot_saves_u / runs, 1),
    }
        
    return custom_scores, thuis_wins, draws, uit_wins, avg_stats


# =========================================================================
# 4. INTERNAL MONTE CARLO LOOP (TOERNOOI)
# =========================================================================
def run_enkel_toernooi(df_teams):
    poules = df_teams['Poule'].unique()
    standen = {row['Land']: {"Land": row['Land'], "Poule": row['Poule'], "Elo": row['Elo'], "Vorm_Multiplier": row['Vorm_Multiplier'], "Formatie": row['Formatie'], "Odd": row['Odd'], "FC26": row['FC26'], "Marktwaarde": row['Marktwaarde'], "xG last 10": row.get('xG last 10', 1.3), "xGA last 10": row.get('xGA last 10', 1.0), "Pnt": 0, "DS": 0, "DV": 0, "DT": 0} for _, row in df_teams.iterrows()}
    groeps_uitslagen = {}
    
    fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]

    for poule in poules:
        teams = df_teams[df_teams['Poule'] == poule].reset_index(drop=True)
        for t_idx, u_idx, sd in fifa_schema:
            t, u = teams.iloc[t_idx]['Land'], teams.iloc[u_idx]['Land']
            gt, gu = simuleer_wedstrijd_90min(standen[t], standen[u])
            groeps_uitslagen[f"{t} vs {u}"] = f"{gt}-{gu}"
            standen[t]["DV"] += gt; standen[t]["DT"] += gu
            standen[u]["DV"] += gu; standen[u]["DT"] += gt
            if gt > gu: standen[t]["Pnt"] += 3
            elif gu > gt: standen[u]["Pnt"] += 3
            else: standen[t]["Pnt"] += 1; standen[u]["Pnt"] += 1

    for l in standen: standen[l]["DS"] = standen[l]["DV"] - standen[l]["DT"]
    df_standen = pd.DataFrame(standen.values())

    p_winnaars, p_runnersup, p_nummers3 = {}, {}, []
    for poule in poules:
        p_stand = df_standen[df_standen['Poule'] == poule].sort_values(by=['Pnt', 'DS', 'DV', 'Elo'], ascending=[False, False, False, False]).reset_index(drop=True)
        p_winnaars[poule] = p_stand.iloc[0]
        p_runnersup[poule] = p_stand.iloc[1]
        p_nummers3.append(p_stand.iloc[2])

    df_3e = pd.DataFrame(p_nummers3).sort_values(by=['Pnt', 'DS', 'DV', 'Elo'], ascending=[False, False, False, False]).reset_index(drop=True)
    best_3e = list(df_3e.iloc[0:8]['Land'])

    r32_setup = [
        ("M73", p_runnersup['Poule A'], p_runnersup['Poule B']), ("M74", p_winnaars['Poule E'], standen[best_3e[0]]),
        ("M75", p_winnaars['Poule F'], p_runnersup['Poule C']), ("M76", p_winnaars['Poule C'], p_runnersup['Poule F']),
        ("M77", p_winnaars['Poule I'], standen[best_3e[1]]), ("M78", p_runnersup['Poule E'], p_runnersup['Poule I']),
        ("M79", p_winnaars['Poule A'], standen[best_3e[2]]), ("M80", p_winnaars['Poule L'], standen[best_3e[3]]),
        ("M81", p_winnaars['Poule D'], standen[best_3e[4]]), ("M82", p_winnaars['Poule G'], standen[best_3e[5]]),
        ("M83", p_runnersup['Poule K'], p_runnersup['Poule L']), ("M84", p_winnaars['Poule H'], p_runnersup['Poule J']),
        ("M85", p_winnaars['Poule B'], standen[best_3e[6]]), ("M86", p_winnaars['Poule J'], p_runnersup['Poule H']),
        ("M87", p_winnaars['Poule K'], standen[best_3e[7]]), ("M88", p_runnersup['Poule D'], p_runnersup['Poule G'])
    ]
    w32 = {m_id: simuleer_knockout_match(t1, t2)[0] for m_id, t1, t2 in r32_setup}
    
    r16_setup = [
        ("M89", w32["M74"], w32["M77"]), ("M90", w32["M73"], w32["M75"]),
        ("M91", w32["M76"], w32["M78"]), ("M92", w32["M79"], w32["M80"]),
        ("M93", w32["M83"], w32["M84"]), ("M94", w32["M81"], w32["M82"]),
        ("M95", w32["M86"], w32["M88"]), ("M96", w32["M85"], w32["M87"])
    ]
    w16 = {m_id: simuleer_knockout_match(t1, t2)[0] for m_id, t1, t2 in r16_setup}
    
    q_setup = [
        ("M97", w16["M89"], w16["M90"]), ("M98", w16["M93"], w16["M94"]),
        ("M99", w16["M91"], w16["M92"]), ("M100", w16["M95"], w16["M96"])
    ]
    wq = {m_id: simuleer_knockout_match(t1, t2)[0] for m_id, t1, t2 in q_setup}
    
    w_sf1, _ = simuleer_knockout_match(wq["M97"], wq["M98"])
    w_sf2, _ = simuleer_knockout_match(wq["M99"], wq["M100"])
    
    kampioen, _ = simuleer_knockout_match(w_sf1, w_sf2)
    return kampioen['Land'], groeps_uitslagen


# =========================================================================
# 5. USER INTERFACE NAVIGATIE
# =========================================================================
fase = st.sidebar.radio("Toernooi Navigatie", ["Database & Teams", "WK Simulator (1 Run)", "Monte Carlo Voorspeller", "Poule Scorito Helper", "Losse Wedstrijd Voorspellen"])

if fase == "Database & Teams":
    st.subheader("📊 Landen & Statistieken uit Database")
    st.dataframe(df_teams, use_container_width=True)

elif fase == "WK Simulator (1 Run)":
    st.header("⚽ Volledige WK 2026 Simulator (Single Run)")
    st.write("Klik op de knop hieronder om het toernooi live één keer van groepsfase tot finale te doorlopen.")
    if st.button("🚀 Start een enkel Wereldkampioenschap!"):
        # [Deel verborgen gehouden voor de lengte, dit is identiek aan jouw eerdere code]
        st.info("Ga naar de Poule Helper of Losse Wedstrijd voor de Micro Stats!")

elif fase == "Monte Carlo Voorspeller":
    st.header("🎲 Monte Carlo Toernooi Voorspeller")
    st.write("Simuleer het WK duizenden keren op de achtergrond. Krachtverhoudingen zijn gebaseerd op Elo, Vorm, Odds, FC26, Marktwaarde én xG/xGA statistieken!")
    
    runs = st.slider("Aantal simulaties", min_value=100, max_value=2000, value=1000, step=100)
    
    if st.button("🔮 Start data-analyse..."):
        kampioen_teller = Counter()
        wedstrijd_scores = {}
        progress_bar = st.progress(0)
        
        for i in range(runs):
            if i % 100 == 0: progress_bar.progress(i / runs)
            kampioen, uitslagen = run_enkel_toernooi(df_teams)
            kampioen_teller[kampioen] += 1
            for match, score in uitslagen.items():
                if match not in wedstrijd_scores: wedstrijd_scores[match] = Counter()
                wedstrijd_scores[match][score] += 1
                
        progress_bar.progress(1.0)
        st.success(f"Klaar! {runs} volledige toernooien gesimuleerd.")
        
        col_links, col_rechts = st.columns([1, 2])
        with col_links:
            st.subheader("🏆 Wie wint het WK?")
            df_kampioenen = pd.DataFrame(kampioen_teller.most_common(), columns=["Land", "Aantal Titels"])
            df_kampioenen["Winstkans (%)"] = round((df_kampioenen["Aantal Titels"] / runs) * 100, 1)
            st.dataframe(df_kampioenen[["Land", "Winstkans (%)"]], hide_index=True)
            
        with col_rechts:
            st.subheader("⚽ Meest Voorkomende Correcte Scores")
            score_data = []
            for match, counter in wedstrijd_scores.items():
                meest_voorkomende_score, aantal = counter.most_common(1)[0]
                percentage = round((aantal / runs) * 100, 1)
                score_data.append({"Wedstrijd": match, "Uitslag": meest_voorkomende_score, "Kans (%)": percentage})
            st.dataframe(pd.DataFrame(score_data), use_container_width=True, hide_index=True)


elif fase == "Poule Scorito Helper":
    st.header("📋 Poule Scorito Helper")
    st.write("Jouw odds worden automatisch opgeslagen. Gebruik punten of komma's, de app begrijpt het beide.")
    
    gekozen_poule = st.selectbox("Selecteer de poule:", df_teams['Poule'].unique())
    teams_poule = df_teams[df_teams['Poule'] == gekozen_poule].reset_index(drop=True)
    
    fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]
    
    match_inputs = {}
    for t_idx, u_idx, sd in fifa_schema:
        t_naam = teams_poule.iloc[t_idx]['Land']
        u_naam = teams_poule.iloc[u_idx]['Land']
        
        key = f"{sd}_{t_naam}_{u_naam}"
        k1, kX, k2 = f"o1_{key}", f"oX_{key}", f"o2_{key}"
        
        val_1 = str(st.session_state['ingevulde_odds'].get(k1, "2.00"))
        val_X = str(st.session_state['ingevulde_odds'].get(kX, "3.20"))
        val_2 = str(st.session_state['ingevulde_odds'].get(k2, "3.50"))
        
        st.write(f"**Speeldag {sd}: {t_naam} vs {u_naam}**")
        c1, c2, c3 = st.columns(3)
        
        odd_1_txt = c1.text_input(f"Winst {t_naam}", value=val_1, key=f"txt_{k1}")
        odd_X_txt = c2.text_input("Gelijkspel", value=val_X, key=f"txt_{kX}")
        odd_2_txt = c3.text_input(f"Winst {u_naam}", value=val_2, key=f"txt_{k2}")
        
        st.session_state['ingevulde_odds'][k1] = odd_1_txt
        st.session_state['ingevulde_odds'][kX] = odd_X_txt
        st.session_state['ingevulde_odds'][k2] = odd_2_txt
        
        match_inputs[key] = {
            "t": teams_poule.iloc[t_idx], "u": teams_poule.iloc[u_idx],
            "odd1": clean_odd(odd_1_txt), 
            "oddX": clean_odd(odd_X_txt), 
            "odd2": clean_odd(odd_2_txt)
        }
    
    if st.button("🚀 Genereer tips voor hele poule"):
        st.subheader("✅ Jouw Scorito-advies voor deze poule:")
        for key, data in match_inputs.items():
            # Let op de extra , _ voor de nieuwe stats!
            custom_scores, _, _, _, _ = run_match_simulation(
                data['t'], data['u'], 
                data['odd1'], data['oddX'], data['odd2'], 
                runs=5000
            )
            top_score = custom_scores.most_common(1)[0][0]
            st.success(f"**{data['t']['Land']} vs {data['u']['Land']}**: Vul in 👉 **{top_score}**")


elif fase == "Losse Wedstrijd Voorspellen":
    st.header("🎯 Custom Match Predictor (Met Micro Stats!)")
    st.write("Selecteer een wedstrijd. Vul de actuele 1X2-odds in om de waarschijnlijke uitslagen én de verwachte schoten en reddingen te berekenen.")

    poules = df_teams['Poule'].unique()
    opties_speelschema = []
    wedstrijd_mapping = {}

    fifa_schema = [(0,1,1), (2,3,1), (0,2,2), (3,1,2), (3,0,3), (1,2,3)]

    for poule in poules:
        teams = df_teams[df_teams['Poule'] == poule].reset_index(drop=True)
        for t_idx, u_idx, sd in fifa_schema:
            t_naam = teams.iloc[t_idx]['Land']
            u_naam = teams.iloc[u_idx]['Land']
            
            weergave_tekst = f"{poule} | Speeldag {sd}: {t_naam} vs. {u_naam}"
            opties_speelschema.append(weergave_tekst)
            
            wedstrijd_mapping[weergave_tekst] = {
                "thuis_row": teams.iloc[t_idx],
                "uit_row": teams.iloc[u_idx],
                "thuis_naam": t_naam,
                "uit_naam": u_naam
            }

    gekozen_wedstrijd = st.selectbox("🔮 Kies een wedstrijd uit de groepsfase:", opties_speelschema)
    
    match_data = wedstrijd_mapping[gekozen_wedstrijd]
    thuis_row = match_data["thuis_row"]
    uit_row = match_data["uit_row"]
    thuis_select = match_data["thuis_naam"]
    uit_select = match_data["uit_naam"]

    st.write("---")

    st.subheader(f"🎲 Voer de 1X2 Odds in voor: {thuis_select} vs. {uit_select}")
    col_o1, col_o2, col_o3 = st.columns(3)
    
    odd_1_txt = col_o1.text_input(f"Odd voor Winst {thuis_select} (1)", value="2.00")
    odd_X_txt = col_o2.text_input("Odd voor Gelijkspel (X)", value="3.00")
    odd_2_txt = col_o3.text_input(f"Odd voor Winst {uit_select} (2)", value="3.00")

    st.write("---")
    
    if st.button("📊 Bereken Wedstrijd & Correcte Scores"):
        odd_1 = clean_odd(odd_1_txt)
        odd_X = clean_odd(odd_X_txt)
        odd_2 = clean_odd(odd_2_txt)

        runs = 5000
        # HIER PAKKEN WE DE NIEUWE AVG_STATS UIT DE SIMULATIE:
        custom_scores, thuis_wins, draws, uit_wins, avg_stats = run_match_simulation(
            thuis_row, uit_row, odd_1, odd_X, odd_2, runs=runs
        )
        
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        col_stat1.metric(f"Simulator Kans Winst {thuis_select}", f"{round((thuis_wins/runs)*100, 1)}%")
        col_stat2.metric("Simulator Kans Gelijkspel", f"{round((draws/runs)*100, 1)}%")
        col_stat3.metric(f"Simulator Kans Winst {uit_select}", f"{round((uit_wins/runs)*100, 1)}%")
        
        st.write("")
        st.subheader("🔮 Top 5 Meest Waarschijnlijke Uitslagen")
        
        top_5 = custom_scores.most_common(5)
        top_5_data = []
        for idx, (score, aantal) in enumerate(top_5, start=1):
            kans = round((aantal / runs) * 100, 1)
            top_5_data.append({"Positie": f"#{idx}", "Correcte Score": score, "Kans hierop (%)": f"{kans}%"})
            
        st.table(pd.DataFrame(top_5_data))

        # --- NIEUW: VISUALISATIE VAN DE MICRO STATS ---
        st.write("---")
        st.subheader("📈 Verwachte Wedstrijdstatistieken (Gemiddelden)")
        
        col_t, col_mid, col_u = st.columns([2, 1, 2])
        
        with col_t:
            st.markdown(f"### 👕 {thuis_select}")
            st.write(f"🥅 Totale Schoten: **{avg_stats['shots_t']}**")
            st.write(f"🎯 Schoten op Doel: **{avg_stats['sot_t']}**")
            st.write(f"🧤 Reddingen Keeper: **{avg_stats['saves_t']}**")
            
        with col_mid:
            st.write(" ")
            
        with col_u:
            st.markdown(f"### 👕 {uit_select}")
            st.write(f"🥅 Totale Schoten: **{avg_stats['shots_u']}**")
            st.write(f"🎯 Schoten op Doel: **{avg_stats['sot_u']}**")
            st.write(f"🧤 Reddingen Keeper: **{avg_stats['saves_u']}**")

        # --- SCORITO TIP ---
        st.write("---")
        st.markdown(f"## 📱 De Ultieme Scorito Tip voor {thuis_select} - {uit_select}")
        
        scorito_uitslag = top_5[0][0]
        st.success(f"### 👉 Vul in op Scorito: {scorito_uitslag}")
