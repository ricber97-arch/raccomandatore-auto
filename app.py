import streamlit as st
from pathlib import Path
from collections import Counter
import sys

sys.path.insert(0, str(Path(__file__).parent))

from raccomandatore_auto import (
    ProfiloUtente,
    carica_auto,
    raccomanda,
    score_auto,
)

# ─── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trova la tua auto", page_icon="🚗", layout="centered")

st.markdown("""
<style>
/* ── Bottoni wizard ── */
div[data-testid="stButton"] > button {
    text-align: left !important;
    padding: 14px 20px !important;
    font-size: 1rem !important;
    height: auto !important;
    white-space: normal !important;
    line-height: 1.4 !important;
}
/* ── Card risultato ── */
.auto-card {
    background: #f8f9fa;
    border-left: 5px solid #1a73e8;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 20px;
}
.auto-card h3 { margin: 0 0 4px 0; font-size: 1.15rem; color: #111; }
.badge {
    display: inline-block;
    color: white;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 999px;
    margin-bottom: 10px;
    letter-spacing: .03em;
    text-transform: uppercase;
}
.spiegazione {
    font-size: 0.93rem;
    color: #333;
    margin: 0 0 14px 0;
    padding-left: 10px;
    border-left: 3px solid #e0e0e0;
    font-style: italic;
}
.stat-row { display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 14px; }
.stat { text-align: center; }
.stat .val { font-size: 1.05rem; font-weight: 700; color: #1a73e8; }
.stat .lbl { font-size: 0.72rem; color: #666; }
.motivi { margin-top: 4px; }
.motivo-pos { color: #1e8e3e; font-size: 0.85rem; margin: 2px 0; }
.motivo-neg { color: #d93025; font-size: 0.85rem; margin: 2px 0; }
.warn { color: #e37400; font-size: 0.82rem; margin-top: 8px; }
details summary {
    cursor: pointer; font-size: 0.82rem; color: #777; margin-top: 8px;
    user-select: none;
}
details summary:hover { color: #333; }
</style>
""", unsafe_allow_html=True)

# ─── Cache catalogo ────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_catalogo():
    return carica_auto()

# ─── Fix 4: mapping uso → mix percorso ────────────────────────────────────────

MAPPING_USO = {
    "Tragitto casa-lavoro in città":  {"mix_citta": 0.75, "mix_extra": 0.15, "mix_auto": 0.10, "km_giorno": 25,  "autonomia_viaggio": 30},
    "Viaggi frequenti fuori città":   {"mix_citta": 0.15, "mix_extra": 0.30, "mix_auto": 0.55, "km_giorno": 80,  "autonomia_viaggio": 250},
    "Uso misto quotidiano":           {"mix_citta": 0.40, "mix_extra": 0.35, "mix_auto": 0.25, "km_giorno": 50,  "autonomia_viaggio": 100},
    "Uso occasionale / weekend":      {"mix_citta": 0.50, "mix_extra": 0.30, "mix_auto": 0.20, "km_giorno": 15,  "autonomia_viaggio": 150},
}

# ─── Session state ─────────────────────────────────────────────────────────────

_DEFAULTS = {
    "step": 1,
    "km_giorno": None, "autonomia_viaggio": None,
    "mix_citta": None, "mix_extra": None, "mix_auto": None,
    "n_passeggeri": None, "ricarica_a_casa": None, "budget": None,
    "neopatentato": False, "contesto": "privato",
    "label_uso": None, "label_passeggeri": None,
    "label_parcheggio": None, "label_budget": None,
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _reset():
    for k in list(_DEFAULTS.keys()) + ["chk_neo", "chk_piva",
            "s1_citta", "s1_extra", "s1_auto", "s1_prev_c", "s1_prev_e", "s1_prev_a"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


def _riepilogo() -> str:
    parts = [
        st.session_state.get("label_uso"),
        st.session_state.get("label_passeggeri"),
        st.session_state.get("label_parcheggio"),
        st.session_state.get("label_budget"),
    ]
    return " · ".join(p for p in parts if p)


def _avanza(vals: dict, next_step):
    for k, v in vals.items():
        st.session_state[k] = v
    st.session_state.step = next_step
    st.rerun()

# ─── Helper: spiegazione dinamica ─────────────────────────────────────────────

def _spiegazione(auto, profilo: ProfiloUtente) -> str:
    km = profilo.km_giorno
    uso_city    = profilo.mix_citta >= 0.60
    uso_highway = profilo.mix_auto  >= 0.50
    if auto.is_elettrica:
        if uso_city and km <= 40:
            costo = km * 365 / 100 * 18 * 0.25
            return (f"Con {km:.0f} km/giorno in città il costo energia stimato è ~{costo:.0f}€/anno "
                    f"— meno di un pieno al mese di benzina.")
        return "Ideale per uso urbano con ricarica domestica: zero emissioni e costi di esercizio bassi."
    if auto.is_phev:
        if profilo.ricarica_a_casa:
            return ("I tragitti brevi in modalità elettrica, il resto col termico. "
                    "Con ricarica domestica è la scelta più versatile per uso misto.")
        return "Flessibile anche senza ricarica: il motore termico è sempre disponibile come backup."
    if auto.is_full_hybrid:
        return ("L'ibrido si ricarica da solo in frenata — nessuna presa necessaria, "
                "consumi ridotti specialmente nel traffico urbano.")
    if auto.is_diesel:
        if uso_highway or km > 100:
            consumo = f"{auto.consumo} l/100km" if auto.consumo else "ridotti"
            return (f"Diesel efficiente per le tue percorrenze elevate: {consumo} "
                    f"tra i più bassi tra le termiche su lunghi tragitti.")
        return f"Consumi contenuti ({auto.consumo} l/100km) per chi percorre molti km su tratti misti."
    if auto.is_lpg:
        return "GPL a ~0,80€/L: a parità di km percorsi, si spende circa la metà rispetto alla benzina."
    if auto.is_ng:
        return "Metano, il carburante più economico: ideale per chi fa tanti km in città o in pianura."
    return "Benzina affidabile e flessibile, adatta al tuo profilo di utilizzo quotidiano."

# ─── Helper: analisi esclusi ───────────────────────────────────────────────────

def _analizza_esclusi(catalogo, profilo: ProfiloUtente, top_risultati) -> list:
    top_keys = {(r.auto.marca, r.auto.modello, r.auto.alimentazione) for r in top_risultati}
    cnt: Counter = Counter()

    for auto in catalogo:
        if (auto.marca, auto.modello, auto.alimentazione) in top_keys:
            continue
        det = score_auto(auto, profilo)
        if det is None:
            if profilo.neopatentato and auto.rapporto_peso_potenza and auto.rapporto_peso_potenza > 55:
                cnt["neopatentato"] += 1
            elif auto.is_elettrica:
                cnt["ev_no_ricarica"] += 1
        else:
            # Con il nuovo budget_score, fuori budget = score 0 E prezzo > budget*1.10
            if auto.prezzo and auto.prezzo > profilo.budget_acquisto_eur * 1.10:
                cnt["budget"] += 1
            else:
                fuel_pts = sum(p for cat, p, _ in det.voci if cat == "alimentazione")
                if fuel_pts < 25:
                    cnt["alimentazione"] += 1

    LABELS = {
        "neopatentato":  "Potenza eccessiva per neopatentati (>55 kW/t): escluse per legge",
        "ev_no_ricarica":"Auto elettriche: senza ricarica domestica non sono pratiche per il tuo utilizzo",
        "budget":        "Prezzo superiore al tuo budget (>10% oltre)",
        "alimentazione": "Alimentazione poco compatibile con il tuo mix di percorsi",
    }
    return [(LABELS[k], v) for k, v in cnt.most_common(3) if k in LABELS]

# ─── Layout ────────────────────────────────────────────────────────────────────

st.title("🚗 Trova la tua auto")
st.caption("Top 50 auto più vendute in Italia nel 2024 — dati EEA reali")

step = st.session_state.step

if step != "results":
    step_num = step if isinstance(step, int) else 5
    st.progress(step_num / 5, text=f"Step {step_num} di 5")
    riepilogo_txt = _riepilogo()
    if riepilogo_txt:
        st.caption(f"📋 {riepilogo_txt}")
    st.markdown("---")

# ─── Step 1 ────────────────────────────────────────────────────────────────────

if step == 1:
    for k, v in [("s1_citta", 50), ("s1_extra", 30), ("s1_auto", 20),
                 ("s1_prev_c", 50), ("s1_prev_e", 30), ("s1_prev_a", 20)]:
        if k not in st.session_state:
            st.session_state[k] = v

    st.subheader("Come usi l'auto di solito?")
    st.caption("Distribuisci il tuo utilizzo tipico — i valori si adattano automaticamente")

    c = st.slider("🏙️ Città e traffico urbano",    0, 100, step=5, format="%d%%", key="s1_citta")
    e = st.slider("🛣️ Extraurbano e strade statali", 0, 100, step=5, format="%d%%", key="s1_extra")
    a = st.slider("🚗 Autostrada",                  0, 100, step=5, format="%d%%", key="s1_auto")

    prev_c = st.session_state.s1_prev_c
    prev_e = st.session_state.s1_prev_e
    prev_a = st.session_state.s1_prev_a

    def _spread(new_val, o1_prev, o2_prev):
        remaining = 100 - new_val
        total_prev = o1_prev + o2_prev
        if total_prev > 0:
            r1 = int(round(o1_prev / total_prev * remaining / 5)) * 5
            r1 = max(0, min(remaining, r1))
        else:
            r1 = (remaining // 10) * 5
        return r1, remaining - r1

    changed = False
    if c != prev_c:
        new_e, new_a = _spread(c, prev_e, prev_a)
        st.session_state.s1_extra, st.session_state.s1_auto = new_e, new_a
        changed = True
    elif e != prev_e:
        new_c, new_a = _spread(e, prev_c, prev_a)
        st.session_state.s1_citta, st.session_state.s1_auto = new_c, new_a
        changed = True
    elif a != prev_a:
        new_c, new_e = _spread(a, prev_c, prev_e)
        st.session_state.s1_citta, st.session_state.s1_extra = new_c, new_e
        changed = True

    if changed:
        st.session_state.s1_prev_c = st.session_state.s1_citta
        st.session_state.s1_prev_e = st.session_state.s1_extra
        st.session_state.s1_prev_a = st.session_state.s1_auto
        st.rerun()

    totale = c + e + a
    if totale == 100:
        st.success(f"Totale: {totale}%  ✓")
    else:
        st.error(f"Totale: {totale}% — deve essere esattamente 100%")

    mix_c, mix_e, mix_a = c / 100, e / 100, a / 100
    km_calc = round(mix_c * 20 + mix_e * 60 + mix_a * 120)
    autonomia_calc = 250 if mix_a >= 0.40 else 120 if mix_e >= 0.40 else 50

    st.caption(f"Stima km/giorno: ~{km_calc} km")
    st.write("")
    if st.button("Avanti →", use_container_width=True, type="primary", disabled=(totale != 100)):
        _avanza({
            "mix_citta": mix_c, "mix_extra": mix_e, "mix_auto": mix_a,
            "km_giorno": km_calc, "autonomia_viaggio": autonomia_calc,
            "label_uso": f"Città {c}% · Extra {e}% · Auto {a}%",
        }, 2)

# ─── Step 2 ────────────────────────────────────────────────────────────────────

elif step == 2:
    st.subheader("Quante persone trasporti di solito?")
    OPZIONI = [
        ("🧍  Solo io",           1, "Solo io"),
        ("👫  Io + 1",            2, "Io + 1"),
        ("👨‍👩‍👧  Famiglia (3-4)",  4, "Famiglia"),
        ("🚐  Spesso in 5",       5, "Spesso in 5"),
    ]
    for i, (lbl, n, display) in enumerate(OPZIONI):
        if st.button(lbl, use_container_width=True, key=f"s2_{i}"):
            _avanza(dict(n_passeggeri=n, label_passeggeri=display), 3)

# ─── Step 3 ────────────────────────────────────────────────────────────────────

elif step == 3:
    st.subheader("Dove parcheggi la notte?")
    OPZIONI = [
        ("🔌  Garage con presa elettrica",   True,  "Garage con presa"),
        ("🏠  Garage senza presa",           False, "Garage senza presa"),
        ("🅿️  Strada o parcheggio pubblico", False, "Parcheggio pubblico"),
    ]
    for i, (lbl, ricarica, display) in enumerate(OPZIONI):
        if st.button(lbl, use_container_width=True, key=f"s3_{i}"):
            _avanza(dict(ricarica_a_casa=ricarica, label_parcheggio=display), 4)

# ─── Step 4 ────────────────────────────────────────────────────────────────────

elif step == 4:
    st.subheader("Qual è il tuo budget?")
    OPZIONI = [
        ("💶  Fino a 15.000€",    14_000, "Fino a 15k€"),
        ("💶  15.000 – 25.000€",  23_000, "15–25k€"),
        ("💶  25.000 – 40.000€",  37_000, "25–40k€"),
        ("💶  Oltre 40.000€",     50_000, "Oltre 40k€"),
    ]
    for i, (lbl, budget, display) in enumerate(OPZIONI):
        if st.button(lbl, use_container_width=True, key=f"s4_{i}"):
            _avanza(dict(budget=budget, label_budget=display), 5)

# ─── Step 5 ────────────────────────────────────────────────────────────────────

elif step == 5:
    st.subheader("Ultime info")
    st.write("")
    neo  = st.checkbox("Sono neopatentato (patente < 3 anni)", key="chk_neo",
                       value=st.session_state.neopatentato)
    piva = st.checkbox("Uso per lavoro / Partita IVA", key="chk_piva",
                       value=(st.session_state.contesto == "partita_iva"))
    st.write("")
    if st.button("🔍 Trova la mia auto", use_container_width=True, type="primary"):
        st.session_state.neopatentato = neo
        st.session_state.contesto = "partita_iva" if piva else "privato"
        st.session_state.step = "results"
        st.rerun()

# ─── Risultati ─────────────────────────────────────────────────────────────────

elif step == "results":
    _required = ["km_giorno", "mix_citta", "mix_extra", "mix_auto",
                 "ricarica_a_casa", "budget", "n_passeggeri"]
    if any(st.session_state.get(k) is None for k in _required):
        st.session_state.step = 1
        st.rerun()

    profilo = ProfiloUtente(
        km_giorno             = st.session_state.km_giorno,
        mix_citta             = st.session_state.mix_citta,
        mix_extra             = st.session_state.mix_extra,
        mix_auto              = st.session_state.mix_auto,
        ricarica_a_casa       = st.session_state.ricarica_a_casa,
        budget_acquisto_eur   = st.session_state.budget,
        n_passeggeri_abituali = st.session_state.n_passeggeri,
        neopatentato          = st.session_state.neopatentato,
        contesto              = st.session_state.contesto,
    )

    with st.spinner("Calcolo raccomandazioni..."):
        catalogo  = get_catalogo()
        risultati = raccomanda(profilo, top_n=3, catalogo=catalogo)

    if not risultati:
        st.error("Nessuna auto trovata con questi criteri. Prova a ricominciare con un budget più alto.")
    else:
        st.subheader("Le tue 3 auto consigliate")
        st.caption(f"📋 {_riepilogo()}")
        st.write("")

        COLORI    = {1: "#1a73e8", 2: "#188038", 3: "#e37400"}
        LABEL_RNK = {1: "Prima scelta", 2: "Seconda scelta", 3: "Terza scelta"}
        ETICHETTE = {
            "electric":        "Elettrica",
            "petrol":          "Benzina",
            "diesel":          "Diesel",
            "lpg":             "GPL",
            "ng":              "Metano",
            "petrol/electric": "Ibrida plug-in (PHEV)",
        }

        for r in risultati:
            auto  = r.auto
            score = r.score
            col      = COLORI.get(r.rank, "#555")
            rank_lbl = LABEL_RNK.get(r.rank, f"#{r.rank}")
            ft_lbl   = ETICHETTE.get(auto.alimentazione, auto.alimentazione.upper())

            stats_html = ""
            if auto.prezzo:
                stats_html += f'<div class="stat"><div class="val">{auto.prezzo:,.0f} €</div><div class="lbl">Prezzo base</div></div>'
            if auto.consumo:
                stats_html += f'<div class="stat"><div class="val">{auto.consumo} l/100km</div><div class="lbl">Consumo WLTP</div></div>'
            if auto.co2 is not None:
                co2_val = f"{auto.co2:.0f} g/km" if auto.co2 > 0 else "0 g/km"
                stats_html += f'<div class="stat"><div class="val">{co2_val}</div><div class="lbl">CO₂ WLTP</div></div>'
            if auto.autonomia_elettrica:
                stats_html += f'<div class="stat"><div class="val">{auto.autonomia_elettrica:.0f} km</div><div class="lbl">Autonomia EV</div></div>'
            if auto.bagagliaio:
                stats_html += f'<div class="stat"><div class="val">{auto.bagagliaio:.0f} L</div><div class="lbl">Bagagliaio</div></div>'

            motivi_html = "".join(
                f'<div class="motivo-pos">✓ {d}</div>' if p > 0 else
                f'<div class="motivo-neg">✗ {d}</div>'
                for _, p, d in score.voci if p != 0
            )

            avviso = (
                '<p class="warn">⚠ Prezzo non disponibile: verifica sul sito del costruttore.</p>'
                if not auto.prezzo else ""
            )

            st.markdown(f"""
<div class="auto-card" style="border-left-color:{col}">
  <h3>{auto.marca} {auto.modello}</h3>
  <span class="badge" style="background:{col}">{rank_lbl} · {ft_lbl}</span>
  <p class="spiegazione">{_spiegazione(auto, profilo)}</p>
  <div class="stat-row">{stats_html}</div>
  {avviso}
  <details>
    <summary>Dettaglio punteggio ({score.totale:.0f} pt)</summary>
    <div class="motivi">{motivi_html}</div>
  </details>
</div>
""", unsafe_allow_html=True)

        esclusi = _analizza_esclusi(catalogo, profilo, risultati)
        if esclusi:
            st.markdown("---")
            st.subheader("Perché abbiamo escluso le altre")
            for motivo, count in esclusi:
                st.markdown(f"- **{count} model{'lo' if count == 1 else 'li'}** — {motivo}")

    st.write("")
    if st.button("↺ Ricomincia", key="restart"):
        _reset()

# ─── Bottone Indietro (step 2-5) ───────────────────────────────────────────────

if isinstance(step, int) and step > 1:
    st.write("")
    st.write("")
    if st.button("← Indietro", key="back_btn"):
        st.session_state.step = step - 1
        st.rerun()

# ─── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption("Fonte dati: EEA Vehicle CO₂ monitoring 2024 · Prezzi di listino pubblici · Top 50 immatricolazioni Italia 2024")
