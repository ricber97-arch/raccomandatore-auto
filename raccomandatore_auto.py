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
# Fallback: cerca nella cartella Downloads se non trovato accanto allo script
if not CSV_PATH.exists():
    CSV_PATH = Path.home() / "Downloads" / "auto_top50_con_prezzi.csv"


# ─── Strutture dati ────────────────────────────────────────────────────────────

@dataclass
class ProfiloUtente:
    km_giorno: float
    percorso: str            # "città" | "misto" | "autostrada"
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


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def score_auto(auto: Auto, profilo: ProfiloUtente) -> Optional[DettaglioScore]:
    """
    Ritorna None se l'auto è da escludere per vincoli hard (neopatentato, elettrica
    senza ricarica con percorso lungo). Altrimenti un DettaglioScore con punteggio
    da 0 a ~100.
    """
    voci: list[tuple[str, float, str]] = []

    km = profilo.km_giorno
    percorso = profilo.percorso
    ricarica = profilo.ricarica_a_casa
    budget = profilo.budget_acquisto_eur
    passeggeri = profilo.n_passeggeri_abituali
    neopatentato = profilo.neopatentato
    contesto = profilo.contesto

    # ── Vincolo neopatentato (Italia: max 55 kW/t per i primi 3 anni) ──────────
    if neopatentato and auto.rapporto_peso_potenza is not None:
        if auto.rapporto_peso_potenza > 55:
            return None  # esclusa per legge

    # ── Vincolo elettrica senza ricarica ───────────────────────────────────────
    # Elettrica pura senza ricarica domestica è un disagio severo ma non impossibile
    if auto.is_elettrica and not ricarica:
        if percorso == "autostrada" or km > 80:
            return None  # impraticabile per uso intensivo senza colonnina di casa

    # ── 1. Budget (peso 25 pt) ─────────────────────────────────────────────────
    if auto.prezzo is not None:
        delta = auto.prezzo - budget
        if delta > budget * 0.25:
            voci.append(("budget", -25, f"prezzo {auto.prezzo:,.0f}€ supera il budget del {delta/budget:.0%}"))
        elif delta > 0:
            penalità = -_clamp(delta / budget * 60, 0, 15)
            voci.append(("budget", penalità, f"prezzo {auto.prezzo:,.0f}€ leggermente sopra budget"))
        else:
            risparmio = min((-delta / budget) * 15, 15)
            voci.append(("budget", 10 + risparmio, f"prezzo {auto.prezzo:,.0f}€ nei limiti del budget"))
    else:
        voci.append(("budget", 3, "prezzo non disponibile (verifica concessionario)"))

    # ── 2. Alimentazione vs abitudini (peso 30 pt) ─────────────────────────────
    # Mappa: scenario → alimentazione ideale
    alta_percorrenza = km > 100
    bassa_percorrenza = km < 40
    uso_city = percorso == "città"
    uso_misto = percorso == "misto"
    uso_autostrada = percorso == "autostrada"

    if auto.is_elettrica:
        if not ricarica:
            voci.append(("alimentazione", -10, "elettrica senza ricarica domestica: ricarica pubblica obbligatoria"))
        if bassa_percorrenza and uso_city and ricarica:
            voci.append(("alimentazione", 30, "elettrica: ideale per percorsi brevi in città con ricarica casa"))
        elif km <= 80 and ricarica:
            voci.append(("alimentazione", 20, "elettrica: adatta con ricarica domestica"))
        elif alta_percorrenza or uso_autostrada:
            voci.append(("alimentazione", -15, "elettrica: autonomia limitata per percorrenza elevata/autostrada"))
        else:
            voci.append(("alimentazione", 10, "elettrica: usabile ma verificare autonomia"))
        # Verifica autonomia elettrica reale
        if auto.autonomia_elettrica and auto.autonomia_elettrica > 0:
            margine = auto.autonomia_elettrica - km
            if margine >= km * 0.5:   # 50% buffer
                voci.append(("autonomia", 8, f"autonomia {auto.autonomia_elettrica:.0f} km, ampio margine sui {km:.0f} km/giorno"))
            elif margine >= 0:
                voci.append(("autonomia", 3, f"autonomia {auto.autonomia_elettrica:.0f} km, sufficiente per {km:.0f} km/giorno"))
            else:
                voci.append(("autonomia", -12, f"autonomia {auto.autonomia_elettrica:.0f} km insufficiente per {km:.0f} km/giorno"))

    elif auto.is_phev:
        if ricarica and uso_misto:
            voci.append(("alimentazione", 28, "PHEV: combo ideale con ricarica casa e percorso misto"))
        elif ricarica and uso_city:
            voci.append(("alimentazione", 22, "PHEV: ottimo in città con ricarica casa, in elettrico quasi sempre"))
        elif ricarica and uso_autostrada and alta_percorrenza:
            voci.append(("alimentazione", 15, "PHEV: autonomia elettrica sfruttata in città, termico per l'autostrada"))
        elif not ricarica:
            voci.append(("alimentazione", -5, "PHEV senza ricarica: si comporta come un'auto pesante a benzina"))
        else:
            voci.append(("alimentazione", 12, "PHEV: buona versatilità"))
        if auto.autonomia_elettrica:
            voci.append(("autonomia", 5, f"autonomia elettrica {auto.autonomia_elettrica:.0f} km (tratti urbani in zero emissioni)"))

    elif auto.is_full_hybrid:
        if uso_city or uso_misto:
            voci.append(("alimentazione", 25, "ibrido full: eccellente in città/misto, no ricarica necessaria"))
        elif uso_autostrada and alta_percorrenza:
            voci.append(("alimentazione", 12, "ibrido full: efficiente ma il vantaggio si riduce in autostrada"))
        else:
            voci.append(("alimentazione", 18, "ibrido full: ottima efficienza senza dipendere da colonnine"))

    elif auto.is_diesel:
        if alta_percorrenza and uso_autostrada:
            voci.append(("alimentazione", 28, "diesel: ideale per alte percorrenze autostradali, consumo ridotto"))
        elif alta_percorrenza and uso_misto:
            voci.append(("alimentazione", 22, "diesel: ottimo per percorrenze miste elevate"))
        elif uso_city and bassa_percorrenza:
            voci.append(("alimentazione", -8, "diesel: sconsigliato per uso prevalentemente urbano a bassa percorrenza"))
        elif uso_city:
            voci.append(("alimentazione", -4, "diesel: meno adatto al traffico urbano (DPF, stop&go)"))
        else:
            voci.append(("alimentazione", 15, "diesel: buon consumo per percorrenze medio-alte"))

    elif auto.is_lpg:
        if uso_city or uso_misto:
            voci.append(("alimentazione", 20, "GPL: carburante economico, ideale per uso urbano/misto"))
        elif alta_percorrenza and uso_autostrada:
            voci.append(("alimentazione", 10, "GPL: economico ma autonomia ridotta (doppio serbatoio)"))
        else:
            voci.append(("alimentazione", 15, "GPL: buon compromesso costo/flessibilità"))

    elif auto.is_ng:  # metano
        if uso_city or uso_misto:
            voci.append(("alimentazione", 18, "metano: carburante molto economico, ideale per uso urbano"))
        else:
            voci.append(("alimentazione", 10, "metano: economico ma distributori meno diffusi"))

    else:  # mild petrol
        if alta_percorrenza and uso_autostrada:
            voci.append(("alimentazione", 5, "benzina: costo carburante elevato per alta percorrenza autostradale"))
        elif bassa_percorrenza and uso_city:
            voci.append(("alimentazione", 12, "benzina: adatta a bassa percorrenza urbana"))
        elif uso_misto:
            voci.append(("alimentazione", 15, "benzina: flessibile per uso misto"))
        else:
            voci.append(("alimentazione", 10, "benzina: soluzione versatile"))

    # ── 3. Efficienza / costo carburante (peso 15 pt) ──────────────────────────
    if auto.consumo and auto.consumo > 0 and not auto.is_elettrica:
        # Costo annuo carburante stimato
        prezzo_carb = {"petrol": 1.75, "diesel": 1.65, "lpg": 0.80, "ng": 1.10}.get(
            auto.alimentazione, 1.75
        )
        if auto.is_phev:
            consumo_eff = auto.consumo * 0.4  # assume 60% km in elettrico
            prezzo_carb = 1.75
        else:
            consumo_eff = auto.consumo

        costo_annuo = (km * 365 / 100) * consumo_eff * prezzo_carb
        if costo_annuo < 800:
            voci.append(("efficienza", 15, f"costo carburante stimato ~{costo_annuo:.0f}€/anno: eccellente"))
        elif costo_annuo < 1400:
            voci.append(("efficienza", 10, f"costo carburante stimato ~{costo_annuo:.0f}€/anno: buono"))
        elif costo_annuo < 2200:
            voci.append(("efficienza", 5, f"costo carburante stimato ~{costo_annuo:.0f}€/anno: nella media"))
        else:
            voci.append(("efficienza", -5, f"costo carburante stimato ~{costo_annuo:.0f}€/anno: elevato"))
    elif auto.is_elettrica:
        # Costo elettricità (0.25 €/kWh, ~18 kWh/100km medio)
        costo_annuo_el = (km * 365 / 100) * 18 * 0.25
        voci.append(("efficienza", 12, f"costo energia stimato ~{costo_annuo_el:.0f}€/anno (elettricità)"))

    # ── 4. Adeguatezza a passeggeri/spazio (peso 10 pt) ───────────────────────
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

    # ── 5. Contesto fiscale (peso 10 pt) ───────────────────────────────────────
    if contesto == "partita_iva":
        if auto.is_elettrica:
            voci.append(("fiscale", 10, "P.IVA: elettrica deducibile al 100% (uso aziendale esclusivo)"))
        elif auto.is_diesel:
            voci.append(("fiscale", 6, "P.IVA: diesel deducibile al 20% + IVA parzialmente recuperabile"))
        elif auto.is_phev:
            voci.append(("fiscale", 8, "P.IVA: PHEV con CO2 bassa, deducibilità migliorata"))
        elif auto.is_full_hybrid:
            voci.append(("fiscale", 5, "P.IVA: ibrido con CO2 bassa, buona deducibilità"))
        else:
            voci.append(("fiscale", 2, "P.IVA: deducibilità standard 20% (regime ordinario)"))

    # ── 6. Affidabilità/popolarità come proxy qualità (peso 5 pt) ─────────────
    if auto.immatricolazioni > 20000:
        voci.append(("popolarità", 5, f"tra le auto più vendute in Italia ({auto.immatricolazioni:,} immatr. 2024)"))
    elif auto.immatricolazioni > 10000:
        voci.append(("popolarità", 3, f"buona diffusione in Italia ({auto.immatricolazioni:,} immatr. 2024)"))
    else:
        voci.append(("popolarità", 1, f"meno comune ({auto.immatricolazioni:,} immatr. 2024)"))

    # ── 7. Emissioni CO2 (bonus ecologico) ────────────────────────────────────
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


def raccomanda(profilo: ProfiloUtente, top_n: int = 3, catalogo: Optional[list[Auto]] = None) -> list[Raccomandazione]:
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
        if auto.consumo:
            print(f"  Consumo:      {auto.consumo} l/100km  |  CO₂: {auto.co2:.0f} g/km" if auto.co2 else f"  Consumo: {auto.consumo} l/100km")
        if auto.autonomia_elettrica:
            print(f"  Autonomia EV: {auto.autonomia_elettrica:.0f} km")

        if not auto.prezzo:
            print(f"  ⚠  Prezzo non presente nel dataset: verifica sul sito del costruttore.")

        print(f"\n  Perché questa auto:")
        for cat, punti, desc in score.voci:
            segno = "+" if punti > 0 else ""
            icona = "✓" if punti > 0 else "✗" if punti < 0 else "·"
            print(f"    {icona} [{segno}{punti:.0f}pt] {desc}")

    print(f"\n{'═' * 60}\n")


# ─── Test con profili di esempio ───────────────────────────────────────────────

def test_profili():
    catalogo = carica_auto()

    profili = [
        (
            "Pendolare urbano / Neopatentato",
            ProfiloUtente(
                km_giorno=25,
                percorso="città",
                ricarica_a_casa=True,
                budget_acquisto_eur=25_000,
                n_passeggeri_abituali=1,
                neopatentato=True,
                contesto="privato",
            ),
        ),
        (
            "Famiglia misto / Partita IVA",
            ProfiloUtente(
                km_giorno=80,
                percorso="misto",
                ricarica_a_casa=True,
                budget_acquisto_eur=35_000,
                n_passeggeri_abituali=4,
                neopatentato=False,
                contesto="partita_iva",
            ),
        ),
        (
            "Grande percorrenza autostradale / Privato",
            ProfiloUtente(
                km_giorno=180,
                percorso="autostrada",
                ricarica_a_casa=False,
                budget_acquisto_eur=40_000,
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
    ricarica = _chiedi_bool("  Hai la possibilità di ricaricare a casa?")
    budget = _chiedi_float("  Qual è il tuo budget di acquisto (€)? ", 5_000, 500_000)
    passeggeri = int(_chiedi_float("  Quanti passeggeri trasporti abitualmente (incluso te)? ", 1, 5))
    neopatentato = _chiedi_bool("  Sei neopatentato (patente < 3 anni)?")
    contesto = _chiedi_scelta("  Acquisto per uso?", ["privato", "partita_iva"])

    profilo = ProfiloUtente(
        km_giorno=km,
        percorso=percorso,
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
        print("\n  Nessuna auto trovata con i criteri inseriti. Prova ad allargare il budget.")
    else:
        stampa_raccomandazioni(risultati, titolo="Le tue 3 auto consigliate")


# ─── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_profili()
    else:
        cli()
