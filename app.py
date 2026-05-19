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

st.set_page_config(page_title="guidami", page_icon="🚗", layout="centered")

# ─── Design System CSS ─────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Variables ── */
:root {
    --g-black:   #111111;
    --g-accent:  #C45C00;
    --g-accent2: #E8A87C;
    --g-bg:      #F7F7F5;
    --g-surface: #FFFFFF;
    --g-border:  #E0DDD8;
    --g-text:    #2C2C2C;
    --g-muted:   #8A8580;
    --g-green:   #1A6B3A;
    --g-red:     #C0392B;
    --g-r:       10px;
    --g-shadow:  0 2px 12px rgba(0,0,0,0.07);
}

/* ── Brand header ── */
.g-brand {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 4px 0 22px 0;
}
.g-logo {
    font-size: 1.55rem;
    font-weight: 800;
    color: var(--g-black);
    letter-spacing: -0.04em;
}
.g-logo span { color: var(--g-accent); }
.g-tagline {
    font-size: 0.88rem;
    color: var(--g-muted);
    font-weight: 400;
}

/* ── Progress bar ── */
.g-prog-wrap { margin-bottom: 20px; }
.g-prog-track {
    height: 3px;
    background: var(--g-border);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 7px;
}
.g-prog-fill {
    height: 100%;
    background: var(--g-accent);
    border-radius: 2px;
}
.g-prog-label {
    font-size: 0.72rem;
    color: var(--g-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Riepilogo ── */
.g-recap {
    font-size: 0.82rem;
    color: var(--g-muted);
    margin-bottom: 16px;
    line-height: 1.5;
}

/* ── Divider ── */
.g-div {
    height: 1px;
    background: var(--g-border);
    margin: 0 0 22px 0;
}

/* ── Wizard buttons ── */
div[data-testid="stButton"] > button {
    text-align: left !important;
    padding: 16px 20px !important;
    font-size: 0.94rem !important;
    height: auto !important;
    white-space: pre-wrap !important;
    line-height: 1.5 !important;
    border-radius: var(--g-r) !important;
    border: 1.5px solid var(--g-border) !important;
    background: var(--g-surface) !important;
    color: var(--g-text) !important;
    box-shadow: var(--g-shadow) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
    font-family: inherit !important;
}
div[data-testid="stButton"] > button:hover {
    border-color: var(--g-accent) !important;
    box-shadow: 0 4px 18px rgba(196,92,0,0.13) !important;
    background: #FFF8F4 !important;
}
div[data-testid="stButton"] > button::first-line {
    font-weight: 700 !important;
    color: var(--g-black) !important;
    font-size: 1rem !important;
}

/* ── Result cards ── */
.g-rcard {
    background: var(--g-surface);
    border: 1.5px solid var(--g-border);
    border-radius: 14px;
    padding: 24px 26px 20px;
    margin-bottom: 22px;
    box-shadow: var(--g-shadow);
}
.g-rcard h2 {
    margin: 10px 0 8px 0;
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--g-black);
    line-height: 1.3;
}
.g-badge {
    display: inline-block;
    color: white;
    font-size: 0.69rem;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 999px;
    letter-spacing: 0.07em;
    text-transform: uppercase;
}
.g-why {
    font-size: 0.91rem;
    color: var(--g-text);
    margin: 0 0 16px 0;
    line-height: 1.6;
    font-style: italic;
}
.g-stats {
    display: flex;
    flex-wrap: wrap;
    border: 1.5px solid var(--g-border);
    border-radius: var(--g-r);
    overflow: hidden;
    margin-bottom: 14px;
}
.g-stat {
    flex: 1;
    min-width: 80px;
    padding: 11px 14px;
    border-right: 1px solid var(--g-border);
    text-align: center;
}
.g-stat:last-child { border-right: none; }
.g-stat-val {
    display: block;
    font-size: 0.98rem;
    font-weight: 700;
    color: var(--g-black);
}
.g-stat-lbl {
    display: block;
    font-size: 0.67rem;
    color: var(--g-muted);
    margin-top: 2px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.g-motori {
    font-size: 0.87rem;
    color: var(--g-text);
    background: rgba(196,92,0,0.06);
    border-left: 3px solid var(--g-accent);
    padding: 10px 14px;
    border-radius: 0 var(--g-r) var(--g-r) 0;
    margin-bottom: 14px;
    line-height: 1.55;
}
.g-pro-con { margin-top: 10px; }
.g-pro {
    color: var(--g-green);
    font-size: 0.84rem;
    margin: 4px 0;
}
.g-con {
    color: var(--g-red);
    font-size: 0.84rem;
    margin: 4px 0;
}
details summary {
    cursor: pointer;
    font-size: 0.81rem;
    color: var(--g-muted);
    margin-top: 6px;
    user-select: none;
}
details summary:hover { color: var(--g-black); }

/* ── Exclusion block ── */
.g-excl {
    background: var(--g-bg);
    border: 1.5px solid var(--g-border);
    border-radius: var(--g-r);
    padding: 16px 20px;
    margin-top: 8px;
}
.g-excl h4 {
    margin: 0 0 10px 0;
    font-size: 0.78rem;
    color: var(--g-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}
.g-excl-item {
    font-size: 0.86rem;
    color: var(--g-text);
    margin: 5px 0;
    line-height: 1.45;
}
.g-excl-item strong { color: var(--g-black); }

/* ── Footer ── */
.g-footer {
    margin-top: 36px;
    padding-top: 16px;
    border-top: 1px solid var(--g-border);
    font-size: 0.76rem;
    color: var(--g-muted);
    text-align: center;
    line-height: 1.6;
}

/* ── Warning ── */
.g-warn {
    font-size: 0.82rem;
    color: #a05000;
    margin: 8px 0 0 0;
}
</style>
""", unsafe_allow_html=True)

# ─── Cache catalogo ────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_catalogo():
    return carica_auto()

# ─── Spiegazioni dinamiche (definite qui per evitare dipendenze extra) ──────────

def spiega_motorizzazione(ft, profilo):
    ft = ft.lower()
    ricarica = profilo.ricarica_a_casa
    km       = profilo.km_giorno
    mix_c    = profilo.mix_citta
    mix_a    = profilo.mix_auto
    if ft == "electric":
        if ricarica and mix_c >= 0.55:
            costo_anno = round(km * 365 * 0.15 * 0.25)
            return ("Uso urbano + ricarica a casa: costo energia stimato ~{}€/anno. "
                    "Zero emissioni in città, manutenzione ridotta al minimo.").format(costo_anno)
        if ricarica:
            return ("Con ricarica domestica elimini quasi del tutto il costo del carburante. "
                    "Ideale per chi ha percorsi quotidiani prevedibili.")
        return ("Elettrico senza ricarica a casa: richiede accesso frequente a colonnine "
                "pubbliche nei pressi di casa o del lavoro.")
    if ft == "petrol/electric":
        if ricarica:
            return ("Ibrido plug-in: i tragitti brevi in modalità elettrica, i lunghi col termico. "
                    "Con ricarica domestica è la scelta più versatile per uso misto.")
        return ("Ibrido plug-in senza ricarica: funziona come un termico efficiente, "
                "con il motore benzina sempre disponibile come backup.")
    if ft == "diesel":
        if mix_a >= 0.40 or km > 80:
            return ("Diesel: la motorizzazione più efficiente per chi percorre molti km "
                    "in autostrada o su extraurbano ({} km/giorno medi).").format(km)
        return ("Diesel efficiente nei percorsi misti. Consumi ridotti su lunghi tragitti, "
                "meno vantaggioso nell'uso esclusivamente urbano.")
    if ft == "lpg":
        return ("GPL a ~0,85 €/L: a parità di km percorsi, circa la metà del costo rispetto "
                "alla benzina. Rete distributori capillare in Italia.")
    if ft == "petrol":
        if mix_c >= 0.60:
            return ("Benzina semplice e affidabile per uso prevalentemente urbano. "
                    "Rete distributori ovunque, manutenzione senza sorprese.")
        return ("Benzina affidabile e flessibile per utilizzo misto. "
                "La scelta più diffusa, senza dipendere da infrastrutture specifiche.")
    return "Motorizzazione compatibile con il tuo profilo di utilizzo."


def spiega_scelta(auto, profilo, rank, score=None):
    RANK_INTRO = {1: "La scelta migliore per te", 2: "Ottima alternativa", 3: "Valida opzione"}
    intro = RANK_INTRO.get(rank, "Opzione #{}".format(rank))
    if score is None:
        return "{}: ottimo compromesso tra budget, motorizzazione e dimensioni.".format(intro)
    # Costruisce dizionario punti per categoria (somma)
    cats = set(c for c, _, _ in score.voci)
    punti = {c: sum(p for cc, p, _ in score.voci if cc == c) for c in cats}
    frasi = []
    # Budget
    if punti.get("budget", 0) >= 35 and auto.prezzo:
        pct = round(auto.prezzo / profilo.budget_acquisto_eur * 100)
        frasi.append("usa il {}% del tuo budget".format(pct))
    # Alimentazione
    alim_pts = punti.get("alimentazione", 0)
    FT_IT = {
        "electric": "elettrica", "petrol/electric": "ibrida PHEV",
        "diesel": "diesel", "lpg": "GPL", "petrol": "benzina",
    }
    ft_it = FT_IT.get(auto.alimentazione, auto.alimentazione)
    if alim_pts >= 70:
        frasi.append("motorizzazione {} ideale per il tuo mix di percorsi".format(ft_it))
    elif alim_pts >= 50:
        frasi.append("motorizzazione {} compatibile con le tue abitudini".format(ft_it))
    # Contesto stradale
    if punti.get("contesto_stradale", 0) >= 20:
        if profilo.contesto_stradale == "centro" and auto.lunghezza_mm:
            frasi.append("compatta ({:.2f} m) per centro e ZTL".format(auto.lunghezza_mm / 1000))
        elif profilo.contesto_stradale == "montagna":
            frasi.append("trazione integrale per fondi sdrucciolevoli")
    # Bagagliaio famiglia
    sp_pos = [(c, p, d) for c, p, d in score.voci if c == "spazio" and p > 0]
    if sp_pos and auto.bagagliaio and profilo.n_passeggeri_abituali >= 4:
        frasi.append("bagagliaio da {:.0f} L per tutta la famiglia".format(auto.bagagliaio))
    # Marca
    if punti.get("marca", 0) >= 15:
        frasi.append("brand {} in linea con il tuo profilo".format(auto.marca))
    if not frasi:
        return "{}: il miglior punteggio complessivo tra tutte le auto del catalogo.".format(intro)
    return "{}: ".format(intro) + ", ".join(frasi) + "."

# ─── Dati wizard (formato lista per numerazione automatica) ───────────────────

PROFILI_GUIDA = [
    {
        "titolo": "Quasi tutto in città",
        "descrizione": "Traffico, semafori, parcheggi. Autostrada solo in vacanza.",
        "mix_citta": 0.80, "mix_extra": 0.15, "mix_auto": 0.05,
        "km_giorno": 22, "autonomia_viaggio": 40,
    },
    {
        "titolo": "Città con qualche gita",
        "descrizione": "Quotidiano urbano, ma qualche weekend fuori o commissioni lontane.",
        "mix_citta": 0.60, "mix_extra": 0.25, "mix_auto": 0.15,
        "km_giorno": 32, "autonomia_viaggio": 120,
    },
    {
        "titolo": "Mix equilibrato",
        "descrizione": "Città durante la settimana, extraurbano e autostrada con regolarità.",
        "mix_citta": 0.40, "mix_extra": 0.35, "mix_auto": 0.25,
        "km_giorno": 50, "autonomia_viaggio": 150,
    },
    {
        "titolo": "Pendolare extraurbano",
        "descrizione": "Tragitto casa-lavoro su statali o tangenziali, poco traffico urbano.",
        "mix_citta": 0.20, "mix_extra": 0.55, "mix_auto": 0.25,
        "km_giorno": 65, "autonomia_viaggio": 80,
    },
    {
        "titolo": "Autostrada frequente",
        "descrizione": "Trasferte, clienti, viaggi lunghi. Autostrada più volte a settimana.",
        "mix_citta": 0.15, "mix_extra": 0.25, "mix_auto": 0.60,
        "km_giorno": 95, "autonomia_viaggio": 280,
    },
    {
        "titolo": "Uso saltuario",
        "descrizione": "Meno di 4 volte a settimana, tragitti brevi, nessuna routine fissa.",
        "mix_citta": 0.55, "mix_extra": 0.30, "mix_auto": 0.15,
        "km_giorno": 12, "autonomia_viaggio": 60,
    },
]

PASSEGGERI_OPZIONI = [
    {"titolo": "Solo io",          "n": 1, "label": "Solo io"},
    {"titolo": "Io + 1",           "n": 2, "label": "Io + 1"},
    {"titolo": "Famiglia (3-4)",   "n": 4, "label": "Famiglia"},
    {"titolo": "Spesso in 5",      "n": 5, "label": "Spesso in 5"},
]

RICARICA_OPZIONI = [
    {"titolo": "Sì, ho garage con presa elettrica",  "ricarica": True,  "label": "Garage con presa"},
    {"titolo": "Garage senza presa",                 "ricarica": False, "label": "Garage senza presa"},
    {"titolo": "Parcheggio su strada o pubblico",    "ricarica": False, "label": "Parcheggio pubblico"},
]

BUDGET_OPZIONI = [
    {"titolo": "Fino a 15.000 €",      "budget": 14_000,  "label": "Fino a 15k€"},
    {"titolo": "15.000 – 25.000 €",    "budget": 23_000,  "label": "15–25k€"},
    {"titolo": "25.000 – 40.000 €",    "budget": 37_000,  "label": "25–40k€"},
    {"titolo": "40.000 – 60.000 €",    "budget": 56_000,  "label": "40–60k€"},
    {"titolo": "Oltre 60.000 €",       "budget": 110_000, "label": "Oltre 60k€"},
]

MENTALITA_OPZIONI = [
    {
        "titolo": "Spendo il minimo necessario",
        "descrizione": "L'auto è un mezzo. Voglio spendere poco e risparmiare sulla gestione.",
        "valore": "minimo",
    },
    {
        "titolo": "Miglior rapporto qualità/prezzo",
        "descrizione": "Voglio sfruttare bene il mio budget senza rinunciare a qualità e tecnologia.",
        "valore": "qualita",
    },
    {
        "titolo": "Qualità prima di tutto",
        "descrizione": "Marca, finiture e tecnologia contano. Il budget è una guida, non un limite fisso.",
        "valore": "premium",
    },
]

CONTESTO_STRADALE_OPZIONI = [
    {
        "titolo": "Centro città, ZTL, parcheggi stretti",
        "descrizione": "Traffico intenso, manovre frequenti, spazi ridotti. Le dimensioni contano.",
        "valore": "centro",
    },
    {
        "titolo": "Periferia e circonvallazioni",
        "descrizione": "Strade scorrevoli, parcheggi comodi. Nessun vincolo particolare.",
        "valore": "periferia",
    },
    {
        "titolo": "Strade di montagna o sterrato",
        "descrizione": "Curve, salite, fondi sconnessi o innevati. La trazione fa la differenza.",
        "valore": "montagna",
    },
]

AUTONOMIA_OPZIONI = [
    {
        "titolo": "No, al massimo 80-100 km in una volta",
        "descrizione": "Uso quotidiano locale. Non ho bisogno di grande autonomia.",
        "valore": "corta",
    },
    {
        "titolo": "Qualche volta, tra 100 e 300 km",
        "descrizione": "Ogni tanto faccio tragitti più lunghi, ma non è la norma.",
        "valore": "media",
    },
    {
        "titolo": "Sì, spesso faccio oltre 300 km senza soste",
        "descrizione": "Viaggi frequenti e lunghi. L'autonomia è una priorità.",
        "valore": "lunga",
    },
]

# ─── Session state ─────────────────────────────────────────────────────────────

_DEFAULTS = {
    "step": 1,
    "km_giorno": None, "autonomia_viaggio": None,
    "mix_citta": None, "mix_extra": None, "mix_auto": None,
    "n_passeggeri": None, "ricarica_a_casa": None, "budget": None,
    "neopatentato": False, "contesto": "privato",
    "mentalita": "qualita", "contesto_stradale": "periferia", "autonomia_utente": "media",
    "label_uso": None, "label_passeggeri": None,
    "label_parcheggio": None, "label_budget": None,
    "label_mentalita": None, "label_contesto_str": None,
}

for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _reset():
    for k in list(_DEFAULTS.keys()) + ["chk_neo", "chk_piva"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


def _riepilogo() -> str:
    parts = [
        st.session_state.get("label_uso"),
        st.session_state.get("label_passeggeri"),
        st.session_state.get("label_parcheggio"),
        st.session_state.get("label_budget"),
        st.session_state.get("label_mentalita"),
        st.session_state.get("label_contesto_str"),
    ]
    return " · ".join(p for p in parts if p)


def _avanza(vals: dict, next_step):
    for k, v in vals.items():
        st.session_state[k] = v
    st.session_state.step = next_step
    st.rerun()

# ─── Helper: analisi esclusi ───────────────────────────────────────────────────

def _analizza_esclusi(catalogo, profilo: ProfiloUtente, top_risultati) -> list:
    top_keys = {(r.auto.marca, r.auto.modello, r.auto.alimentazione) for r in top_risultati}
    cnt: Counter = Counter()

    for auto in catalogo:
        if (auto.marca, auto.modello, auto.alimentazione) in top_keys:
            continue
        det = score_auto(auto, profilo)
        if det is None:
            if auto.prezzo and auto.prezzo > 150_000:
                cnt["luxury"] += 1
            elif profilo.neopatentato and auto.rapporto_peso_potenza and auto.rapporto_peso_potenza > 55:
                cnt["neopatentato"] += 1
            elif auto.is_elettrica:
                cnt["ev_no_ricarica"] += 1
        else:
            tol = 1.20 if profilo.mentalita == "premium" else (1.05 if profilo.mentalita == "minimo" else 1.10)
            if auto.prezzo and auto.prezzo > profilo.budget_acquisto_eur * tol:
                cnt["budget"] += 1
            else:
                fuel_pts = sum(p for cat, p, _ in det.voci if cat == "alimentazione")
                if fuel_pts < 25:
                    cnt["alimentazione"] += 1

    LABELS = {
        "luxury":        "Oltre 150.000€: al di fuori del mercato di massa, escluse automaticamente",
        "neopatentato":  "Potenza eccessiva per neopatentati (>55 kW/t): escluse per legge",
        "ev_no_ricarica": "Auto elettriche: senza ricarica domestica non sono pratiche per il tuo utilizzo",
        "budget":        "Prezzo superiore al tuo budget",
        "alimentazione": "Alimentazione poco compatibile con il tuo mix di percorsi",
    }
    return [(LABELS[k], v) for k, v in cnt.most_common(3) if k in LABELS]

# ─── Brand header (sempre visibile) ────────────────────────────────────────────

st.markdown("""
<div class="g-brand">
  <span class="g-logo">guida<span>mi</span></span>
  <span class="g-tagline">trova la tua auto</span>
</div>
""", unsafe_allow_html=True)

step = st.session_state.step

# ─── Progress bar custom (7 passi) ─────────────────────────────────────────────

if step != "results":
    step_num    = step if isinstance(step, int) else 8
    display_step = min(step_num, 7)      # step 8 → mostra "7 di 7"
    pct          = int(display_step / 7 * 100)
    riepilogo_txt = _riepilogo()
    st.markdown(f"""
<div class="g-prog-wrap">
  <div class="g-prog-track"><div class="g-prog-fill" style="width:{pct}%"></div></div>
  <div class="g-prog-label">Passo {display_step} di 7</div>
</div>
{('<div class="g-recap">📋 ' + riepilogo_txt + '</div>') if riepilogo_txt else ''}
<div class="g-div"></div>
""", unsafe_allow_html=True)

# ─── Step 1 — Profilo di guida ─────────────────────────────────────────────────

if step == 1:
    st.subheader("Che tipo di guidatore sei?")
    st.caption("Scegli il profilo che descrive meglio il tuo utilizzo quotidiano")
    for i, p in enumerate(PROFILI_GUIDA):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}\n{p['descrizione']}"
        if st.button(label, use_container_width=True, key=f"s1_p{i}"):
            _avanza({
                "mix_citta":         p["mix_citta"],
                "mix_extra":         p["mix_extra"],
                "mix_auto":          p["mix_auto"],
                "km_giorno":         p["km_giorno"],
                "autonomia_viaggio": p["autonomia_viaggio"],
                "label_uso":         p["titolo"],
            }, 2)

# ─── Step 2 — Passeggeri ──────────────────────────────────────────────────────

elif step == 2:
    st.subheader("Quante persone trasporti di solito?")
    for i, p in enumerate(PASSEGGERI_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}"
        if st.button(label, use_container_width=True, key=f"s2_{i}"):
            _avanza({"n_passeggeri": p["n"], "label_passeggeri": p["label"]}, 3)

# ─── Step 3 — Ricarica ────────────────────────────────────────────────────────

elif step == 3:
    st.subheader("Dove parcheggi la notte?")
    for i, p in enumerate(RICARICA_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}"
        if st.button(label, use_container_width=True, key=f"s3_{i}"):
            _avanza({"ricarica_a_casa": p["ricarica"], "label_parcheggio": p["label"]}, 4)

# ─── Step 4 — Budget (5 fasce) ────────────────────────────────────────────────

elif step == 4:
    st.subheader("Qual è il tuo budget?")
    for i, p in enumerate(BUDGET_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}"
        if st.button(label, use_container_width=True, key=f"s4_{i}"):
            _avanza({"budget": p["budget"], "label_budget": p["label"]}, 5)

# ─── Step 5 — Mentalità acquisto ───────────────────────────────────────────────

elif step == 5:
    st.subheader("Come ragioni sull'acquisto?")
    for i, p in enumerate(MENTALITA_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}\n{p['descrizione']}"
        if st.button(label, use_container_width=True, key=f"s5_m{i}"):
            _avanza({"mentalita": p["valore"], "label_mentalita": p["titolo"]}, 6)

# ─── Step 6 — Contesto stradale ────────────────────────────────────────────────

elif step == 6:
    st.subheader("Dove guidi principalmente?")
    for i, p in enumerate(CONTESTO_STRADALE_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}\n{p['descrizione']}"
        if st.button(label, use_container_width=True, key=f"s6_c{i}"):
            next_step = 7 if st.session_state.ricarica_a_casa else 8
            extra     = {} if st.session_state.ricarica_a_casa else {"autonomia_utente": "media"}
            _avanza({"contesto_stradale": p["valore"],
                     "label_contesto_str": p["titolo"], **extra}, next_step)

# ─── Step 7 — Autonomia (solo se ricarica_a_casa=True) ─────────────────────────

elif step == 7:
    st.subheader("Fai mai viaggi lunghi senza fermarti a ricaricare?")
    st.caption("Influenza il tipo di elettrico consigliato")
    for i, p in enumerate(AUTONOMIA_OPZIONI):
        num   = f"{i + 1:02d}"
        label = f"{num}  {p['titolo']}\n{p['descrizione']}"
        if st.button(label, use_container_width=True, key=f"s7_a{i}"):
            _avanza({"autonomia_utente": p["valore"]}, 8)

# ─── Step 8 — Ultime info ──────────────────────────────────────────────────────

elif step == 8:
    st.subheader("Ultime info")
    st.write("")
    neo  = st.checkbox("Sono neopatentato (patente < 3 anni)", key="chk_neo",
                       value=st.session_state.neopatentato)
    piva = st.checkbox("Uso per lavoro / Partita IVA", key="chk_piva",
                       value=(st.session_state.contesto == "partita_iva"))
    st.write("")
    if st.button("🔍  Trova la mia auto", use_container_width=True, type="primary"):
        st.session_state.neopatentato = neo
        st.session_state.contesto     = "partita_iva" if piva else "privato"
        st.session_state.step         = "results"
        st.rerun()

# ─── Risultati ─────────────────────────────────────────────────────────────────

elif step == "results":
    _required = ["km_giorno", "autonomia_viaggio", "mix_citta", "mix_extra", "mix_auto",
                 "ricarica_a_casa", "budget", "n_passeggeri"]
    if any(st.session_state.get(k) is None for k in _required):
        st.session_state.step = 1
        st.rerun()

    profilo = ProfiloUtente(
        mix_citta             = st.session_state.mix_citta,
        mix_extra             = st.session_state.mix_extra,
        mix_auto              = st.session_state.mix_auto,
        km_giorno             = int(st.session_state.km_giorno),
        autonomia_viaggio     = int(st.session_state.autonomia_viaggio),
        ricarica_a_casa       = st.session_state.ricarica_a_casa,
        budget_acquisto_eur   = st.session_state.budget,
        n_passeggeri_abituali = st.session_state.n_passeggeri,
        neopatentato          = st.session_state.neopatentato,
        contesto              = st.session_state.contesto,
        mentalita             = st.session_state.get("mentalita", "qualita"),
        contesto_stradale     = st.session_state.get("contesto_stradale", "periferia"),
        autonomia_utente      = st.session_state.get("autonomia_utente", "media"),
    )

    with st.spinner("Calcolo raccomandazioni…"):
        catalogo  = get_catalogo()
        risultati = raccomanda(profilo, top_n=3, catalogo=catalogo)

    if not risultati:
        st.error("Nessuna auto trovata con questi criteri. Prova a ricominciare con un budget più alto.")
    else:
        recap = _riepilogo()
        if recap:
            st.markdown(f'<div class="g-recap">📋 {recap}</div>', unsafe_allow_html=True)
        st.write("")

        COLORI    = {1: "#C45C00", 2: "#1A6B3A", 3: "#2563EB"}
        LABEL_RNK = {1: "Prima scelta", 2: "Seconda scelta", 3: "Terza scelta"}
        ETICHETTE = {
            "electric":        "Elettrica",
            "petrol":          "Benzina",
            "diesel":          "Diesel",
            "lpg":             "GPL",
            "ng":              "Metano",
            "petrol/electric": "Ibrida plug-in",
        }

        for r in risultati:
            auto     = r.auto
            score    = r.score
            col      = COLORI.get(r.rank, "#555")
            rank_lbl = LABEL_RNK.get(r.rank, f"#{r.rank}")
            ft_lbl   = ETICHETTE.get(auto.alimentazione, auto.alimentazione.upper())

            # Stats block
            stats_parts = []
            if auto.prezzo:
                stats_parts.append(
                    f'<div class="g-stat">'
                    f'<span class="g-stat-val">{auto.prezzo:,.0f} €</span>'
                    f'<span class="g-stat-lbl">Prezzo base</span></div>')
            if auto.consumo:
                unita = "kWh/100km" if auto.is_elettrica else "l/100km"
                ast   = " *" if auto.consumo_stimato else ""
                stats_parts.append(
                    f'<div class="g-stat">'
                    f'<span class="g-stat-val">{auto.consumo}{ast}</span>'
                    f'<span class="g-stat-lbl">Consumo {unita}</span></div>')
            if auto.bagagliaio:
                stats_parts.append(
                    f'<div class="g-stat">'
                    f'<span class="g-stat-val">{auto.bagagliaio:.0f} L</span>'
                    f'<span class="g-stat-lbl">Bagagliaio</span></div>')
            if auto.lunghezza_mm:
                stats_parts.append(
                    f'<div class="g-stat">'
                    f'<span class="g-stat-val">{auto.lunghezza_mm / 1000:.2f} m</span>'
                    f'<span class="g-stat-lbl">Lunghezza</span></div>')
            stats_html = "".join(stats_parts)

            # Pro / Con items
            pro_html = "".join(
                f'<div class="g-pro">✓ {d}</div>'
                for _, p, d in score.voci if p > 0
            )
            con_html = "".join(
                f'<div class="g-con">✗ {d}</div>'
                for _, p, d in score.voci if p < 0
            )

            # Dynamic explanations
            why_txt    = spiega_scelta(auto, profilo, r.rank, score)
            motori_txt = spiega_motorizzazione(auto.alimentazione, profilo)

            avviso = (
                '<p class="g-warn">⚠ Prezzo non disponibile: verifica sul sito del costruttore.</p>'
                if not auto.prezzo else ""
            )

            st.markdown(f"""
<div class="g-rcard">
  <span class="g-badge" style="background:{col}">{rank_lbl} · {ft_lbl}</span>
  <h2>{auto.marca} {auto.modello}</h2>
  <p class="g-why">{why_txt}</p>
  <div class="g-stats">{stats_html}</div>
  <div class="g-motori">{motori_txt}</div>
  {avviso}
  <details>
    <summary>Dettaglio punteggio ({score.totale:.0f} pt)</summary>
    <div class="g-pro-con">{pro_html}{con_html}</div>
  </details>
</div>
""", unsafe_allow_html=True)

        if any(r.auto.consumo_stimato for r in risultati):
            st.caption("\\* Consumo stimato per categoria — verifica sul configuratore ufficiale.")

        # Sezione esclusioni
        esclusi = _analizza_esclusi(catalogo, profilo, risultati)
        if esclusi:
            items_html = "".join(
                '<div class="g-excl-item">· <strong>{} {}</strong> — {}</div>'.format(
                    v, "modello" if v == 1 else "modelli", m)
                for m, v in esclusi
            )
            st.markdown(f"""
<div class="g-excl">
  <h4>Perché abbiamo escluso le altre</h4>
  {items_html}
</div>
""", unsafe_allow_html=True)

    # Restart button
    st.write("")
    if st.button("↺  Ricomincia dall'inizio", key="restart"):
        _reset()

    # Footer
    st.markdown("""
<div class="g-footer">
  guidami · Database auto 2026 · Prezzi di listino pubblici · Oltre 400 versioni disponibili in Italia<br>
  I risultati sono indicativi — verifica sempre le specifiche sul sito del costruttore o del concessionario.
</div>
""", unsafe_allow_html=True)

# ─── Bottone Indietro (step 2-8) ───────────────────────────────────────────────

if isinstance(step, int) and step > 1:
    st.write("")
    st.write("")
    if st.button("← Indietro", key="back_btn"):
        if step == 8 and not st.session_state.get("ricarica_a_casa", False):
            st.session_state.step = 6
        else:
            st.session_state.step = step - 1
        st.rerun()
