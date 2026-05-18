"""
Raccomandatore auto - Top 50 Italia 2024
Dati EEA reali + prezzi di listino
"""

from __future__ import annotations
import csv
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

CSV_PATH = Path(__file__).parent / "auto_top50_con_prezzi.csv"
if not CSV_PATH.exists():
    CSV_PATH = Path.home() / "Downloads" / "auto_top50_con_prezzi.csv"


# ─── Strutture dati ────────────────────────────────────────────────────────────

@dataclass
class ProfiloUtente:
    km_giorno: float
    mix_citta: float          # frequenza uso urbano  (0.0–1.0, somma con gli altri = 1.0)
    mix_extra: float          # frequenza extraurbano
    mix_auto: float           # frequenza autostrada
    ricarica_a_casa: bool
    budget_acquisto_eur: float
    n_passeggeri_abituali: int   # 1-5
    neopatentato: bool
    contesto: str            # "privato" | "partita_iva"


@dataclass
class Auto:
    marca: str
    modello: str
    alimentazione: str
    prezzo: Optional[float]
    consumo: Optional[float]      # l/100km
    co2: Optional[float]          # g/km WLTP
    potenza_kw: Optional[float]
    peso_kg: Optional[float]
    autonomia_elettrica: Optional[float]  # km
    bagagliaio: Optional[float]   # litri
    immatricolazioni: int

    @property
    def nome(self) -> str:
        return f"{self.marca} {self.modello} ({self.alimentazione.upper()})"

    @property
    def rapporto_peso_potenza(self) -> Optional[float]:
        """kW per tonnellata"""
        if self.potenza_kw and self.peso_kg:
            return self.potenza_kw / (self.peso_kg / 1000)
        return None

    @property
    def is_elettrica(self) -> bool:
        return self.alimentazione == "electric"

    @property
    def is_phev(self) -> bool:
        return self.alimentazione == "petrol/electric"

    @property
    def is_diesel(self) -> bool:
        return self.alimentazione == "diesel"

    @property
    def is_lpg(self) -> bool:
        return self.alimentazione == "lpg"

    @property
    def is_ng(self) -> bool:
        return self.alimentazione == "ng"

    @property
    def is_full_hybrid(self) -> bool:
        """Ibrido full (HEV) classificato come petrol con CO2 < 100 g/km (es. Toyota Yaris)"""
        return (
            self.alimentazione == "petrol"
            and self.co2 is not None
            and self.co2 < 100
        )

    @property
    def is_mild_petrol(self) -> bool:
        return self.alimentazione == "petrol" and not self.is_full_hybrid


# ─── Caricamento dati ──────────────────────────────────────────────────────────

def _float(val: str) -> Optional[float]:
    v = val.strip()
    return float(v) if v else None


def carica_auto(path: Path = CSV_PATH) -> list[Auto]:
    auto_list = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                auto_list.append(Auto(
                    marca=row["Mk"].strip(),
                    modello=row["Cn"].strip(),
                    alimentazione=row["Ft"].strip(),
                    prezzo=_float(row["prezzo_listino_base_eur"]),
                    consumo=_float(row["consumo_medio_l100km"]),
                    co2=_float(row["co2_wltp_medio"]),
                    potenza_kw=_float(row["potenza_media_kw"]),
                    peso_kg=_float(row["peso_medio_kg"]),
                    autonomia_elettrica=_float(row["autonomia_elettrica_media_km"]),
                    bagagliaio=_float(row["bagagliaio_litri"]),
                    immatricolazioni=int(row["immatricolazioni"] or 0),
                ))
            except (ValueError, KeyError):
                continue
    return auto_list


# ─── Logica di scoring ─────────────────────────────────────────────────────────

@dataclass
class DettaglioScore:
    totale: float
    voci: list[tuple[str, float, str]]   # (categoria, punti, descrizione)

    def positivi(self):
        return [(c, p, d) for c, p, d in self.voci if p > 0]

    def negativi(self):
        return [(c, p, d) for c, p, d in self.voci if p < 0]


# ── Fix 1: budget score ────────────────────────────────────────────────────────

def budget_score(prezzo: Optional[float], budget: float) -> int:
    """Premia chi usa il budget in modo intelligente (70-100% = sweet spot).
    Penalizza chi è molto sotto (spreca potenziale) o fuori budget."""
    if prezzo is None:
        return 0
    ratio = prezzo / budget
    if ratio < 0.40:    return 0    # troppo sotto budget
    if ratio < 0.55:    return 10
    if ratio < 0.70:    return 20
    if ratio < 0.85:    return 35
    if ratio <= 1.0:    return 45   # sweet spot — usa bene il budget
    if ratio <= 1.10:   return 20   # tolleranza 10%
    return 0


def _budget_desc(prezzo: float, budget: float, score: int) -> str:
    ratio = prezzo / budget
    if score == 0:
        if ratio < 0.40:
            return f"prezzo {prezzo:,.0f}€ molto sotto budget (potenziale inespresso)"
        return f"prezzo {prezzo:,.0f}€ fuori budget (+{(ratio - 1):.0%})"
    if ratio <= 1.0:
        return f"prezzo {prezzo:,.0f}€ ({ratio:.0%} del budget utilizzato)"
    return f"prezzo {prezzo:,.0f}€ — appena sopra budget (+{(ratio - 1):.0%}, tollerato)"


# ── Fix 2: peso motorizzazione con mix percorso ────────────────────────────────

PESI_PER_SCENARIO: dict[str, tuple[int, int, int]] = {
    # chiave → (punteggio_città, punteggio_extraurbano, punteggio_autostrada) 0-100
    "electric":        (100, 60, 20),
    "petrol/electric": (90,  85, 65),
    "full_hybrid":     (88,  72, 50),   # HEV: ottimo in città, buono misto, meno in autostrada
    "petrol":          (70,  75, 65),
    "diesel":          (30,  80, 100),
    "lpg":             (65,  65, 50),
    "ng":              (50,  55, 45),
}

_FT_LABEL: dict[str, str] = {
    "electric":        "Elettrica",
    "petrol/electric": "Ibrida PHEV",
    "full_hybrid":     "Ibrido full HEV",
    "petrol":          "Benzina",
    "diesel":          "Diesel",
    "lpg":             "GPL",
    "ng":              "Metano",
}


def peso_motorizzazione(
    ft: str,
    mix_citta: float,
    mix_extra: float,
    mix_auto: float,
    ricarica_a_casa: bool,
) -> int:
    ft = ft.lower()
    if ft == "electric" and not ricarica_a_casa:
        return 15   # penalità forte — elettrico senza ricarica è sempre problematico
    pesi = PESI_PER_SCENARIO.get(ft, (50, 50, 50))
    score = pesi[0] * mix_citta + pesi[1] * mix_extra + pesi[2] * mix_auto
    return round(score)


def _alim_desc(ft: str, score: int, ricarica: bool) -> str:
    label = _FT_LABEL.get(ft, ft)
    if ft == "electric" and not ricarica:
        return f"{label}: senza ricarica domestica l'utilizzo è penalizzato"
    if score >= 80:
        return f"{label}: ottima scelta per il tuo mix di utilizzo"
    if score >= 60:
        return f"{label}: buona compatibilità con le tue abitudini"
    if score >= 40:
        return f"{label}: discreta compatibilità con il tuo utilizzo"
    return f"{label}: poco adatta al tuo mix di percorsi"


# ── Scoring principale ─────────────────────────────────────────────────────────

def score_auto(auto: Auto, profilo: ProfiloUtente) -> Optional[DettaglioScore]:
    """
    Ritorna None per auto escluse da vincoli hard (neopatentato, EV senza ricarica).
    Altrimenti DettaglioScore con punteggio complessivo.
    """
    voci: list[tuple[str, float, str]] = []

    km          = profilo.km_giorno
    ricarica    = profilo.ricarica_a_casa
    budget      = profilo.budget_acquisto_eur
    passeggeri  = profilo.n_passeggeri_abituali
    neopatentato= profilo.neopatentato
    contesto    = profilo.contesto
    mix_c       = profilo.mix_citta
    mix_e       = profilo.mix_extra
    mix_a       = profilo.mix_auto

    # ── Vincolo neopatentato (Italia: max 55 kW/t per i primi 3 anni) ──────────
    if neopatentato and auto.rapporto_peso_potenza is not None:
        if auto.rapporto_peso_potenza > 55:
            return None

    # ── Vincolo elettrica senza ricarica su uso prevalentemente autostradale ───
    if auto.is_elettrica and not ricarica:
        if mix_a > 0.40 or km > 80:
            return None

    # ── 1. Budget (Fix 1) ──────────────────────────────────────────────────────
    if auto.prezzo is not None:
        bs = budget_score(auto.prezzo, budget)
        voci.append(("budget", bs, _budget_desc(auto.prezzo, budget, bs)))
    else:
        voci.append(("budget", 3, "prezzo non disponibile (verifica concessionario)"))

    # ── 2. Alimentazione vs mix percorso (Fix 2) ───────────────────────────────
    ft_key = "full_hybrid" if auto.is_full_hybrid else auto.alimentazione
    alim_score = peso_motorizzazione(ft_key, mix_c, mix_e, mix_a, ricarica)
    voci.append(("alimentazione", alim_score, _alim_desc(ft_key, alim_score, ricarica)))

    # Bonus autonomia elettrica (EV e PHEV)
    if auto.is_elettrica and auto.autonomia_elettrica and auto.autonomia_elettrica > 0:
        margine = auto.autonomia_elettrica - km
        if margine >= km * 0.5:
            voci.append(("autonomia", 8,
                f"autonomia {auto.autonomia_elettrica:.0f} km, ampio margine sui {km:.0f} km/giorno"))
        elif margine >= 0:
            voci.append(("autonomia", 3,
                f"autonomia {auto.autonomia_elettrica:.0f} km, sufficiente per {km:.0f} km/giorno"))
        else:
            voci.append(("autonomia", -12,
                f"autonomia {auto.autonomia_elettrica:.0f} km insufficiente per {km:.0f} km/giorno"))

    if auto.is_phev and auto.autonomia_elettrica:
        voci.append(("autonomia", 5,
            f"autonomia elettrica {auto.autonomia_elettrica:.0f} km (tratti urbani in zero emissioni)"))

    # ── 3. Efficienza consumo (Fix 3 — bonus ridotti, basati su l/100km) ───────
    if auto.consumo and auto.consumo > 0 and not auto.is_elettrica:
        prezzo_carb = {"petrol": 1.75, "diesel": 1.65, "lpg": 0.80, "ng": 1.10}.get(
            auto.alimentazione, 1.75
        )
        consumo_eff = auto.consumo * 0.4 if auto.is_phev else auto.consumo
        costo_annuo = (km * 365 / 100) * consumo_eff * prezzo_carb

        if auto.consumo < 4.5:
            voci.append(("efficienza", 8,
                f"consumo molto contenuto {auto.consumo} l/100km (~{costo_annuo:.0f}€/anno)"))
        elif auto.consumo < 5.5:
            voci.append(("efficienza", 4,
                f"consumo nella media {auto.consumo} l/100km (~{costo_annuo:.0f}€/anno)"))
        # consumo >= 5.5: nessun bonus (non penalizza, è già gestito da alim_score)

    elif auto.is_elettrica:
        costo_annuo_el = (km * 365 / 100) * 18 * 0.25
        voci.append(("efficienza", 12,
            f"costo energia stimato ~{costo_annuo_el:.0f}€/anno (elettricità)"))

    # ── 4. Spazio / passeggeri ────────────────────────────────────────────────
    if passeggeri >= 4:
        if auto.peso_kg and auto.peso_kg < 1100:
            voci.append(("spazio", -8, "auto piccola/leggera: spazio ridotto per 4+ passeggeri"))
        elif auto.peso_kg and auto.peso_kg > 1400:
            voci.append(("spazio", 8, "auto spaziosa: adatta a 4-5 passeggeri"))
        else:
            voci.append(("spazio", 3, "spazio nella media per il numero di passeggeri"))
        if auto.bagagliaio and auto.bagagliaio >= 400:
            voci.append(("spazio", 5, f"bagagliaio {auto.bagagliaio:.0f}L: capiente per famiglie"))
        elif auto.bagagliaio and auto.bagagliaio < 280:
            voci.append(("spazio", -4, f"bagagliaio {auto.bagagliaio:.0f}L: ridotto per 4+ persone"))
    else:
        if auto.bagagliaio and auto.bagagliaio >= 300:
            voci.append(("spazio", 3, f"bagagliaio {auto.bagagliaio:.0f}L: ampio"))

    # ── 5. Contesto fiscale ───────────────────────────────────────────────────
    if contesto == "partita_iva":
        if auto.is_elettrica:
            voci.append(("fiscale", 10, "P.IVA: elettrica deducibile al 100% (uso aziendale esclusivo)"))
        elif auto.is_phev:
            voci.append(("fiscale", 8, "P.IVA: PHEV con CO2 bassa, deducibilità migliorata"))
        elif auto.is_diesel:
            voci.append(("fiscale", 6, "P.IVA: diesel deducibile al 20% + IVA parzialmente recuperabile"))
        elif auto.is_full_hybrid:
            voci.append(("fiscale", 5, "P.IVA: ibrido con CO2 bassa, buona deducibilità"))
        else:
            voci.append(("fiscale", 2, "P.IVA: deducibilità standard 20% (regime ordinario)"))

    # ── 6. Popolarità / proxy affidabilità ───────────────────────────────────
    if auto.immatricolazioni > 20000:
        voci.append(("popolarità", 5,
            f"tra le auto più vendute in Italia ({auto.immatricolazioni:,} immatr. 2024)"))
    elif auto.immatricolazioni > 10000:
        voci.append(("popolarità", 3,
            f"buona diffusione in Italia ({auto.immatricolazioni:,} immatr. 2024)"))
    else:
        voci.append(("popolarità", 1,
            f"meno comune ({auto.immatricolazioni:,} immatr. 2024)"))

    # ── 7. Emissioni CO2 ──────────────────────────────────────────────────────
    if auto.co2 is not None:
        if auto.co2 == 0:
            voci.append(("emissioni", 5, "zero emissioni CO2 allo scarico"))
        elif auto.co2 < 100:
            voci.append(("emissioni", 3, f"emissioni contenute: {auto.co2:.0f} g/km CO2"))
        elif auto.co2 > 150:
            voci.append(("emissioni", -3, f"emissioni elevate: {auto.co2:.0f} g/km CO2"))

    totale = sum(p for _, p, _ in voci)
    return DettaglioScore(totale=totale, voci=voci)


# ─── Engine di raccomandazione ─────────────────────────────────────────────────

@dataclass
class Raccomandazione:
    auto: Auto
    score: DettaglioScore
    rank: int


def raccomanda(
    profilo: ProfiloUtente,
    top_n: int = 3,
    catalogo: Optional[list[Auto]] = None,
) -> list[Raccomandazione]:
    if catalogo is None:
        catalogo = carica_auto()

    risultati: list[tuple[Auto, DettaglioScore]] = []
    for auto in catalogo:
        det = score_auto(auto, profilo)
        if det is not None:
            risultati.append((auto, det))

    risultati.sort(key=lambda x: (x[1].totale, x[0].immatricolazioni), reverse=True)
    return [
        Raccomandazione(auto=a, score=s, rank=i + 1)
        for i, (a, s) in enumerate(risultati[:top_n])
    ]


# ─── Stampa risultati ──────────────────────────────────────────────────────────

def _sep(char: str = "─", n: int = 60) -> str:
    return char * n


def stampa_raccomandazioni(raccomandazioni: list[Raccomandazione], titolo: str = "") -> None:
    if titolo:
        print(f"\n{'═' * 60}")
        print(f"  {titolo}")
        print(f"{'═' * 60}")

    for r in raccomandazioni:
        auto = r.auto
        score = r.score
        print(f"\n  #{r.rank}  {auto.nome}")
        print(f"  {_sep()}")
        print(f"  Score totale: {score.totale:.1f} punti")

        if auto.prezzo:
            print(f"  Prezzo base:  {auto.prezzo:,.0f} €")
        else:
            print(f"  ⚠  Prezzo non nel dataset: verifica sul sito del costruttore.")
        if auto.consumo:
            co2_str = f"  |  CO₂: {auto.co2:.0f} g/km" if auto.co2 else ""
            print(f"  Consumo:      {auto.consumo} l/100km{co2_str}")
        if auto.autonomia_elettrica:
            print(f"  Autonomia EV: {auto.autonomia_elettrica:.0f} km")

        print(f"\n  Perché questa auto:")
        for cat, punti, desc in score.voci:
            segno = "+" if punti > 0 else ""
            icona = "✓" if punti > 0 else "✗" if punti < 0 else "·"
            print(f"    {icona} [{segno}{punti:.0f}pt] {desc}")

    print(f"\n{'═' * 60}\n")


# ─── Helper percorso → mix (usato da CLI) ──────────────────────────────────────

_PERCORSO_TO_MIX: dict[str, tuple[float, float, float]] = {
    "città":      (0.75, 0.15, 0.10),
    "misto":      (0.40, 0.35, 0.25),
    "autostrada": (0.10, 0.20, 0.70),
}


# ─── Test con profili di esempio ───────────────────────────────────────────────

def test_profili():
    catalogo = carica_auto()

    profili = [
        (
            "Budget medio / mix equilibrato / no ricarica — atteso €30-40k, no citycar",
            ProfiloUtente(
                km_giorno=60,
                mix_citta=0.30, mix_extra=0.40, mix_auto=0.30,
                ricarica_a_casa=False,
                budget_acquisto_eur=40_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
            ),
        ),
        (
            "Budget basso / city / no ricarica — atteso Sandero/Panda",
            ProfiloUtente(
                km_giorno=20,
                mix_citta=0.80, mix_extra=0.10, mix_auto=0.10,
                ricarica_a_casa=False,
                budget_acquisto_eur=15_000,
                n_passeggeri_abituali=1,
                neopatentato=False,
                contesto="privato",
            ),
        ),
        (
            "Alta percorrenza autostradale / no ricarica — atteso diesel medio-alta fascia",
            ProfiloUtente(
                km_giorno=120,
                mix_citta=0.10, mix_extra=0.20, mix_auto=0.70,
                ricarica_a_casa=False,
                budget_acquisto_eur=35_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
            ),
        ),
    ]

    for nome, profilo in profili:
        risultati = raccomanda(profilo, top_n=3, catalogo=catalogo)
        stampa_raccomandazioni(risultati, titolo=f"Profilo: {nome}")


# ─── CLI interattiva ───────────────────────────────────────────────────────────

def _chiedi_float(domanda: str, minimo: float = 0, massimo: float = 1e9) -> float:
    while True:
        try:
            val = float(input(domanda).strip())
            if minimo <= val <= massimo:
                return val
            print(f"  Inserisci un valore tra {minimo} e {massimo}.")
        except ValueError:
            print("  Valore non valido, riprova.")


def _chiedi_scelta(domanda: str, opzioni: list[str]) -> str:
    opzioni_fmt = " / ".join(f"[{o}]" for o in opzioni)
    while True:
        val = input(f"{domanda} {opzioni_fmt}: ").strip().lower()
        if val in opzioni:
            return val
        print(f"  Scegli tra: {', '.join(opzioni)}")


def _chiedi_bool(domanda: str) -> bool:
    return _chiedi_scelta(domanda, ["si", "no"]) == "si"


def cli():
    print("\n" + "═" * 60)
    print("  Raccomandatore auto — Top 50 Italia 2024")
    print("═" * 60)
    print("  Rispondi alle domande per trovare l'auto più adatta a te.\n")

    km = _chiedi_float("  Quanti km percorri in media al giorno? ", 1, 2000)
    percorso = _chiedi_scelta("  Tipo di percorso prevalente?", ["città", "misto", "autostrada"])
    mix_c, mix_e, mix_a = _PERCORSO_TO_MIX[percorso]
    ricarica = _chiedi_bool("  Hai la possibilità di ricaricare a casa?")
    budget = _chiedi_float("  Qual è il tuo budget di acquisto (€)? ", 5_000, 500_000)
    passeggeri = int(_chiedi_float("  Quanti passeggeri trasporti abitualmente (incluso te)? ", 1, 5))
    neopatentato = _chiedi_bool("  Sei neopatentato (patente < 3 anni)?")
    contesto = _chiedi_scelta("  Acquisto per uso?", ["privato", "partita_iva"])

    profilo = ProfiloUtente(
        km_giorno=km,
        mix_citta=mix_c,
        mix_extra=mix_e,
        mix_auto=mix_a,
        ricarica_a_casa=ricarica,
        budget_acquisto_eur=budget,
        n_passeggeri_abituali=passeggeri,
        neopatentato=neopatentato,
        contesto=contesto,
    )

    print("\n  Calcolo raccomandazioni...")
    catalogo = carica_auto()
    risultati = raccomanda(profilo, top_n=3, catalogo=catalogo)

    if not risultati:
        print("\n  Nessuna auto trovata. Prova ad allargare il budget.")
    else:
        stampa_raccomandazioni(risultati, titolo="Le tue 3 auto consigliate")


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_profili()
    else:
        cli()
