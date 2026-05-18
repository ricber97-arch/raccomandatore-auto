import streamlit as st
from pathlib import Path
import sys

# Assicura che lo script di scoring sia trovato anche se si lancia da altra dir
sys.path.insert(0, str(Path(__file__).parent))

from raccomandatore_auto import (
    ProfiloUtente,
    Raccomandazione,
    carica_auto,
    raccomanda,
)

# ─── Config pagina ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Trova la tua auto",
    page_icon="🚗",
    layout="centered",
)

# ─── Stile custom ──────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* Card risultato */
.auto-card {
    background: #f8f9fa;
    border-left: 5px solid #1a73e8;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 20px;
}
.auto-card h3 { margin: 0 0 4px 0; font-size: 1.15rem; color: #111; }
.auto-card .badge {
    display: inline-block;
    background: #1a73e8;
    color: white;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 2px 9px;
    border-radius: 999px;
    margin-bottom: 12px;
    letter-spacing: .03em;
    text-transform: uppercase;
}
.stat-row { display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 14px; }
.stat { text-align: center; }
.stat .val { font-size: 1.1rem; font-weight: 700; color: #1a73e8; }
.stat .lbl { font-size: 0.72rem; color: #666; }
.motivi { margin-top: 10px; }
.motivo-pos { color: #1e8e3e; font-size: 0.88rem; margin: 2px 0; }
.motivo-neg { color: #d93025; font-size: 0.88rem; margin: 2px 0; }
.warn { color: #e37400; font-size: 0.82rem; margin-top: 8px; }
</style>
""", unsafe_allow_html=True)

# ─── Catalogo (caricato una volta sola) ────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_catalogo():
    return carica_auto()

# ─── Header ────────────────────────────────────────────────────────────────────

st.title("🚗 Trova la tua auto")
st.caption("Top 50 auto più vendute in Italia nel 2024 — dati EEA reali")

# ─── Form ──────────────────────────────────────────────────────────────────────

with st.form("profilo"):
    st.subheader("Il tuo profilo di guida")

    col1, col2 = st.columns(2)

    with col1:
        km_giorno = st.slider(
            "Km percorsi al giorno",
            min_value=5, max_value=400, value=50, step=5,
            help="Media giornaliera inclusi weekend"
        )
        percorso = st.selectbox(
            "Percorso prevalente",
            options=["città", "misto", "autostrada"],
            index=1,
        )
        n_passeggeri = st.slider(
            "Passeggeri abituali (te incluso)",
            min_value=1, max_value=5, value=2
        )

    with col2:
        budget = st.slider(
            "Budget di acquisto (€)",
            min_value=10_000, max_value=80_000, value=25_000, step=1_000,
            format="€%d",
        )
        contesto = st.selectbox(
            "Contesto d'uso",
            options=["privato", "partita_iva"],
            format_func=lambda x: "Privato" if x == "privato" else "Partita IVA",
        )
        st.write("")  # spacer visivo
        ricarica = st.checkbox("Ho la possibilità di ricaricare a casa", value=True)
        neopatentato = st.checkbox("Sono neopatentato (patente < 3 anni)")

    submitted = st.form_submit_button(
        "🔍 Trova la mia auto",
        use_container_width=True,
        type="primary",
    )

# ─── Risultati ─────────────────────────────────────────────────────────────────

if submitted:
    profilo = ProfiloUtente(
        km_giorno=km_giorno,
        percorso=percorso,
        ricarica_a_casa=ricarica,
        budget_acquisto_eur=budget,
        n_passeggeri_abituali=n_passeggeri,
        neopatentato=neopatentato,
        contesto=contesto,
    )

    with st.spinner("Calcolo raccomandazioni..."):
        catalogo = get_catalogo()
        risultati = raccomanda(profilo, top_n=3, catalogo=catalogo)

    if not risultati:
        st.error(
            "Nessuna auto trovata con i criteri inseriti. "
            "Prova ad aumentare il budget o a modificare le preferenze."
        )
        st.stop()

    st.subheader("Le tue 3 auto consigliate")

    COLORI_FEED = {1: "#1a73e8", 2: "#188038", 3: "#e37400"}
    LABEL_FEED = {1: "Prima scelta", 2: "Seconda scelta", 3: "Terza scelta"}

    ETICHETTE_FT = {
        "electric":       "Elettrica",
        "petrol":         "Benzina",
        "diesel":         "Diesel",
        "lpg":            "GPL",
        "ng":             "Metano",
        "petrol/electric": "Ibrida plug-in (PHEV)",
    }

    for r in risultati:
        auto = r.auto
        score = r.score
        colore = COLORI_FEED.get(r.rank, "#555")
        label_rank = LABEL_FEED.get(r.rank, f"#{r.rank}")
        ft_label = ETICHETTE_FT.get(auto.alimentazione, auto.alimentazione.upper())

        # Costruisce le statistiche da mostrare
        stats_html = ""
        if auto.prezzo:
            stats_html += f'<div class="stat"><div class="val">{auto.prezzo:,.0f} €</div><div class="lbl">Prezzo base</div></div>'
        if auto.consumo:
            stats_html += f'<div class="stat"><div class="val">{auto.consumo} l/100km</div><div class="lbl">Consumo WLTP</div></div>'
        if auto.co2 is not None:
            val_co2 = f"{auto.co2:.0f} g/km" if auto.co2 > 0 else "0 g/km"
            stats_html += f'<div class="stat"><div class="val">{val_co2}</div><div class="lbl">CO₂ WLTP</div></div>'
        if auto.autonomia_elettrica:
            stats_html += f'<div class="stat"><div class="val">{auto.autonomia_elettrica:.0f} km</div><div class="lbl">Autonomia EV</div></div>'
        if auto.bagagliaio:
            stats_html += f'<div class="stat"><div class="val">{auto.bagagliaio:.0f} L</div><div class="lbl">Bagagliaio</div></div>'

        # Costruisce le motivazioni
        motivi_html = ""
        for _, punti, desc in score.voci:
            if punti > 0:
                motivi_html += f'<div class="motivo-pos">✓ {desc}</div>'
            elif punti < 0:
                motivi_html += f'<div class="motivo-neg">✗ {desc}</div>'

        avviso_prezzo = (
            '<p class="warn">⚠ Prezzo non disponibile nel dataset: verifica sul sito del costruttore.</p>'
            if not auto.prezzo else ""
        )

        st.markdown(f"""
<div class="auto-card" style="border-left-color:{colore}">
  <h3>{auto.marca} {auto.modello}</h3>
  <span class="badge" style="background:{colore}">{label_rank} · {ft_label}</span>
  <div class="stat-row">{stats_html}</div>
  {avviso_prezzo}
  <div class="motivi">{motivi_html}</div>
</div>
""", unsafe_allow_html=True)

    st.caption(f"Score interno: {' | '.join(f'{r.auto.marca} {r.auto.modello} {r.score.totale:.1f}pt' for r in risultati)}")

# ─── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption("Fonte dati: EEA Vehicle CO₂ monitoring 2024 · Prezzi di listino pubblici · Top 50 immatricolazioni Italia 2024")
