"""
Raccomandatore auto - Top 50 Italia 2024
Dati EEA reali + prezzi di listino
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

CSV_PATH = Path(__file__).parent / "database_auto_2026_v4.csv"
if not CSV_PATH.exists():
    CSV_PATH = Path.home() / "Downloads" / "database_auto_2026_v4.csv"


# ─── Strutture dati ────────────────────────────────────────────────────────────

@dataclass
class ProfiloUtente:
    mix_citta: float          # frequenza uso urbano  (0.0–1.0, somma con gli altri = 1.0)
    mix_extra: float          # frequenza extraurbano
    mix_auto: float           # frequenza autostrada
    km_giorno: int            # km medi al giorno
    autonomia_viaggio: int    # autonomia tipica di un singolo viaggio (km)
    ricarica_a_casa: bool
    budget_acquisto_eur: float
    n_passeggeri_abituali: int   # 1-5
    neopatentato: bool
    contesto: str             # "privato" | "partita_iva"
    mentalita: str            # "minimo" | "qualita" | "premium"
    contesto_stradale: str    # "centro" | "periferia" | "montagna"
    autonomia_utente: str     # "corta" | "media" | "lunga"
    pref_carrozzeria: str = "nessuna"  # "nessuna" | "suv" | "berlina" | "station_wagon" | "monovolume"


@dataclass
class Auto:
    marca: str
    modello: str
    alimentazione: str
    prezzo: Optional[float]
    consumo: Optional[float]      # l/100km (termici) oppure kWh/100km (elettrici)
    potenza_kw: Optional[float]
    peso_kg: Optional[float]      # sempre None nel DB 2026
    bagagliaio: Optional[float]   # litri
    lunghezza_mm: Optional[float]      # proxy dimensione vettura
    trazione_prevalente: Optional[str] # 'anteriore' | 'integrale permanente' | ecc.
    consumo_stimato: bool = False      # True = valore stimato per categoria
    n_versioni: int = 1                # numero versioni disponibili (tiebreaker)
    carrozzeria_prevalente: Optional[str] = None  # es. "Suv/Fuoristrada", "berlina 3/5 porte"

    @property
    def nome(self) -> str:
        return f"{self.marca} {self.modello} ({self.alimentazione.upper()})"

    @property
    def rapporto_peso_potenza(self) -> Optional[float]:
        """kW per tonnellata — None se peso non disponibile"""
        if self.potenza_kw and self.peso_kg:
            return self.potenza_kw / (self.peso_kg / 1000)
        return None

    @property
    def is_elettrica(self) -> bool:
        return self.alimentazione == "electric"

    @property
    def is_phev(self) -> bool:
        return self.alimentazione == "phev"

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
        return self.alimentazione == "full_hybrid"

    @property
    def is_mild_petrol(self) -> bool:
        return self.alimentazione == "petrol"


# ─── Caricamento dati ──────────────────────────────────────────────────────────

def _opt(val) -> Optional[float]:
    """Converte un valore pandas in float opzionale."""
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def carica_auto(path: Path = CSV_PATH) -> list[Auto]:
    df = pd.read_csv(path)
    # Rinomina colonne per mapping interno
    df = df.rename(columns={
        "marca":         "Mk",
        "modello":       "Cn",
        "ft":            "Ft",
        "prezzo_min":    "prezzo_listino_base_eur",
        "bagagliaio_l":  "bagagliaio_litri",
        "consumo_medio": "consumo_medio_l100km",
    })

    auto_list = []
    for _, row in df.iterrows():
        try:
            trazione_raw = row.get("trazione_prevalente", None)
            trazione = str(trazione_raw).strip() if not pd.isna(trazione_raw) else None
            carr_raw = row.get("carrozzeria_prevalente", None)
            carrozzeria = str(carr_raw).strip() if not pd.isna(carr_raw) else None
            auto_list.append(Auto(
                marca               = str(row["Mk"]).strip(),
                modello             = str(row["Cn"]).strip(),
                alimentazione       = str(row["Ft"]).strip().lower(),
                prezzo              = _opt(row["prezzo_listino_base_eur"]),
                consumo             = _opt(row["consumo_medio_l100km"]),
                potenza_kw          = _opt(row["potenza_media_kw"]),
                peso_kg             = _opt(row.get("peso_medio_kg")),
                bagagliaio          = _opt(row["bagagliaio_litri"]),
                lunghezza_mm        = _opt(row.get("lunghezza_mm")),
                trazione_prevalente = trazione,
                consumo_stimato     = str(row.get("consumo_stimato", "False")).strip().lower() == "true",
                n_versioni          = int(row.get("n_versioni", 1) or 1),
                carrozzeria_prevalente = carrozzeria,
            ))
        except (ValueError, KeyError, TypeError):
            continue
    return auto_list


# ─── Logica di scoring ─────────────────────────────────────────────────────────

@dataclass
class DettaglioScore:
    totale: float
    voci: list[tuple[str, float, str]]   # (categoria, punti, descrizione)
    motorizzazione: float = 0.0   # contributo puro peso motorizzazione
    budget: float = 0.0           # contributo budget
    marca_s: float = 0.0          # contributo marca
    carrozzeria: float = 0.0      # contributo preferenza carrozzeria
    malus: float = 0.0            # malus PHEV autostrada

    def positivi(self):
        return [(c, p, d) for c, p, d in self.voci if p > 0]

    def negativi(self):
        return [(c, p, d) for c, p, d in self.voci if p < 0]


# ── Budget score (dipende dalla mentalità d'acquisto) ─────────────────────────

def budget_score(prezzo: Optional[float], budget: float, mentalita: str = "qualita") -> int:
    """Premia il rapporto prezzo/budget in base alla mentalità dell'utente."""
    if prezzo is None or pd.isna(prezzo):
        return 0
    ratio = prezzo / budget
    if mentalita == "minimo":
        if ratio < 0.50:    return 45   # spendere poco = ottimo
        if ratio < 0.70:    return 35
        if ratio < 0.85:    return 15
        if ratio <= 1.0:    return 5
        return 0
    elif mentalita == "premium":
        # Budget molto alto (>55k): tolleranza più ampia su auto di lusso
        if budget >= 55_000:
            if ratio < 0.45:    return 0    # troppo economico anche per il premium alto
            if ratio < 0.65:    return 15
            if ratio < 0.85:    return 30
            if ratio <= 1.15:   return 45   # sweet spot luxury (fino a +15%)
            if ratio <= 1.20:   return 20
            return 0
        if ratio < 0.60:    return 0    # troppo economico per questo profilo
        if ratio < 0.75:    return 15
        if ratio < 0.90:    return 30
        if ratio <= 1.10:   return 45   # sweet spot premium (fino a +10%)
        if ratio <= 1.20:   return 25
        return 0
    else:  # qualita (default)
        if ratio < 0.40:    return 0
        if ratio < 0.55:    return 10
        if ratio < 0.70:    return 20
        if ratio < 0.85:    return 35
        if ratio <= 1.0:    return 45
        if ratio <= 1.10:   return 20
        return 0


def _budget_desc(prezzo: float, budget: float, score: int, mentalita: str = "qualita") -> str:
    ratio = prezzo / budget
    if score == 0:
        if mentalita == "premium" and ratio < 0.60:
            return f"prezzo {prezzo:,.0f}€ — troppo basso per il tuo profilo premium"
        return f"prezzo {prezzo:,.0f}€ fuori budget (+{(ratio - 1):.0%})"
    if ratio <= 1.0:
        return f"prezzo {prezzo:,.0f}€ ({ratio:.0%} del budget utilizzato)"
    return f"prezzo {prezzo:,.0f}€ — appena sopra budget (+{(ratio - 1):.0%}, tollerato)"


# ── Marca score (dipende dalla mentalità) ─────────────────────────────────────

MARCHE_PREMIUM = {
    "AUDI", "BMW", "MERCEDES", "VOLVO", "LEXUS", "LAND ROVER",
    "PORSCHE", "MASERATI", "ALFA ROMEO", "DS", "CUPRA", "ALPINE",
    "TESLA", "GENESIS", "ASTON MARTIN", "BENTLEY", "FERRARI", "LAMBORGHINI",
}
MARCHE_ENTRY = {
    "DACIA", "FIAT", "CITROEN", "RENAULT", "SEAT",
    "HYUNDAI", "KIA", "MG", "BYD", "SUZUKI", "TOYOTA",
}


def marca_score(marca: str, mentalita: str) -> int:
    """Bonus/malus marca in base alla mentalità dell'utente."""
    marca = marca.upper()
    if mentalita == "premium":
        return 20 if marca in MARCHE_PREMIUM else 0
    elif mentalita == "minimo":
        if marca in MARCHE_ENTRY:   return 15
        if marca in MARCHE_PREMIUM: return -10
        return 5
    return 0  # qualita: neutro


# ── Contesto stradale score ────────────────────────────────────────────────────

def contesto_stradale_score(auto: "Auto", contesto_stradale: str) -> int:
    """Bonus/malus dimensione e trazione in base al contesto stradale."""
    score = 0
    if contesto_stradale == "centro":
        lunghezza = getattr(auto, "lunghezza_mm", None)
        if lunghezza is not None:
            if lunghezza < 4000:    score += 20
            elif lunghezza < 4200:  score += 10
            elif lunghezza > 4500:  score -= 15
            elif lunghezza > 4300:  score -= 5
    elif contesto_stradale == "montagna":
        trazione = getattr(auto, "trazione_prevalente", None)
        if trazione:
            t = trazione.lower()
            if "integrale" in t:    score += 30
            elif "inseribile" in t: score += 15
    return score


# ── Carrozzeria score ─────────────────────────────────────────────────────────

def carrozzeria_score(carrozzeria_auto: Optional[str], preferenza: str) -> int:
    """Bonus se la carrozzeria corrisponde alla preferenza; malus se opposta."""
    if preferenza == "nessuna" or carrozzeria_auto is None:
        return 0
    carr = carrozzeria_auto.lower()
    if preferenza == "suv":
        if "suv" in carr or "fuoristrada" in carr:
            return 15
        if "berlina 2" in carr or "coupé" in carr or "cabrio" in carr:
            return -10
    elif preferenza == "berlina":
        if "berlina" in carr:
            return 15
        if "monovolume" in carr or ("suv" in carr and "fuoristrada" in carr):
            return -10
    elif preferenza == "station_wagon":
        if "station wagon" in carr:
            return 15
        if "coupé" in carr or "cabrio" in carr:
            return -10
    elif preferenza == "monovolume":
        if "monovolume" in carr:
            return 15
        if "coupé" in carr or "cabrio" in carr or "berlina 2" in carr:
            return -10
    return 0


# ── Autonomia score (rilevante solo con ricarica a casa) ──────────────────────

def autonomia_score(ft: str, autonomia_utente: str, ricarica_a_casa: bool) -> int:
    """Bonus/malus per elettrici e PHEV in base all'autonomia richiesta dall'utente."""
    if not ricarica_a_casa:
        return 0
    ft = ft.lower()
    if ft == "electric":
        if autonomia_utente == "corta":  return 15
        if autonomia_utente == "media":  return 0
        if autonomia_utente == "lunga":  return -20
    if ft == "phev":
        if autonomia_utente == "lunga":  return 10
    return 0


# ── Costo carburante / energia ─────────────────────────────────────────────────

PREZZI_CARBURANTE: dict[str, float] = {
    "petrol":      1.78,
    "diesel":      1.68,
    "lpg":         0.85,
    "ng":          1.10,
    "phev":        1.78,   # quota termica PHEV senza ricarica
    "full_hybrid": 1.78,   # benzina con recupero energetico
}


def stima_costo_mensile(consumo: Optional[float], ft: str, km_giorno: int,
                         ricarica: bool = False) -> float:
    """Stima costo mensile carburante/energia in €."""
    if not consumo or consumo <= 0:
        return 0.0
    ft = ft.lower()
    if ft == "electric":
        return round(km_giorno * 30 * (consumo / 100) * 0.25, 0)
    if ft == "phev" and ricarica:
        consumo_eff = consumo * 0.4   # uso parzialmente elettrico
        return round(km_giorno * 30 * (consumo_eff / 100) * PREZZI_CARBURANTE["petrol"], 0)
    prezzo = PREZZI_CARBURANTE.get(ft, 1.78)
    return round(km_giorno * 30 * (consumo / 100) * prezzo, 0)


# ── Peso motorizzazione con mix percorso ──────────────────────────────────────

PESI_BASE: dict[str, tuple[int, int, int]] = {
    # chiave → (punteggio_città, punteggio_extraurbano, punteggio_autostrada) 0-100
    "electric":         (100, 60, 20),
    "phev_ricarica":    (90,  80, 60),
    "phev_no_ricarica": (70,  60, 30),
    "full_hybrid":      (88,  72, 50),   # HEV: ottimo in città, buono misto, meno in autostrada
    "petrol":           (70,  75, 65),
    "diesel":           (30,  80, 100),
    "lpg":              (65,  65, 50),
    "ng":               (50,  55, 45),
}

_FT_LABEL: dict[str, str] = {
    "electric":    "Elettrica",
    "phev":        "Ibrida plug-in",
    "full_hybrid": "Ibrido full-HEV",
    "petrol":      "Benzina",
    "diesel":      "Diesel",
    "lpg":         "GPL",
    "ng":          "Metano",
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
    if ft == "phev":
        key = "phev_ricarica" if ricarica_a_casa else "phev_no_ricarica"
        pesi = PESI_BASE[key]
    else:
        pesi = PESI_BASE.get(ft, (50, 50, 50))
    score = pesi[0] * mix_citta + pesi[1] * mix_extra + pesi[2] * mix_auto
    return round(score)


def calcola_malus_phev(ft: str, mix_auto: float, ricarica_a_casa: bool) -> int:
    """Malus aggiuntivo per PHEV su percorsi autostradali (dove il motore termico domina)."""
    if ft.lower() != "phev":
        return 0
    if not ricarica_a_casa:
        if mix_auto >= 0.50:  return -35   # no ricarica + autostrada pesante = molto penalizzato
        if mix_auto >= 0.30:  return -15
        return -5
    else:
        if mix_auto >= 0.50:  return -10   # con ricarica: solo malus moderato
        return 0


def _alim_desc(ft: str, score: int, ricarica: bool) -> str:
    label = _FT_LABEL.get(ft, ft)
    if ft == "electric" and not ricarica:
        return f"{label}: senza ricarica domestica l'utilizzo è penalizzato"
    if ft == "phev" and not ricarica:
        return f"{label}: senza ricarica funziona come termico (consumi reali superiori al dichiarato)"
    if score >= 80:
        return f"{label}: ottima scelta per il tuo mix di utilizzo"
    if score >= 60:
        return f"{label}: buona compatibilità con le tue abitudini"
    if score >= 40:
        return f"{label}: discreta compatibilità con il tuo utilizzo"
    return f"{label}: poco adatta al tuo mix di percorsi"


# ── Spiegazioni dinamiche ─────────────────────────────────────────────────────

def spiega_motorizzazione(ft: str, profilo: "ProfiloUtente") -> str:
    """Spiega in linguaggio naturale perché la motorizzazione si adatta al profilo."""
    ft = ft.lower()
    ricarica = profilo.ricarica_a_casa
    km       = profilo.km_giorno
    mix_c    = profilo.mix_citta
    mix_a    = profilo.mix_auto

    if ft == "electric":
        if ricarica and mix_c >= 0.55:
            costo_anno = round(km * 365 * 0.15 * 0.25)
            return (f"Uso urbano + ricarica a casa: costo energia stimato ~{costo_anno}€/anno. "
                    f"Zero emissioni in città, manutenzione ridotta al minimo.")
        if ricarica:
            return ("Con ricarica domestica elimini quasi del tutto il costo del carburante. "
                    "Ideale per chi ha percorsi quotidiani prevedibili.")
        return ("Elettrico senza ricarica a casa: richiede accesso frequente a colonnine pubbliche "
                "nei pressi di casa o del lavoro.")
    if ft == "phev":
        if ricarica:
            return ("Ibrido plug-in: i tragitti brevi in modalità elettrica, i lunghi col termico. "
                    "Con ricarica domestica è la scelta più versatile per uso misto.")
        return ("Ibrido plug-in senza ricarica: funziona come un termico efficiente, "
                "con il motore benzina sempre disponibile come backup.")
    if ft == "full_hybrid":
        return ("L'ibrido full-HEV si ricarica da solo frenando e in decelerazione. "
                "Nessun bisogno di presa elettrica, consumi ridotti soprattutto in città e nel traffico.")
    if ft == "diesel":
        if mix_a >= 0.40 or km > 80:
            return (f"Diesel: la motorizzazione più efficiente per chi percorre molti km "
                    f"in autostrada o su extraurbano ({km} km/giorno medi).")
        return ("Diesel efficiente nei percorsi misti. Consumi ridotti su lunghi tragitti, "
                "meno vantaggioso nell'uso esclusivamente urbano.")
    if ft == "lpg":
        return ("GPL a ~0,85 €/L: a parità di km percorsi, circa la metà del costo rispetto alla "
                "benzina. Rete distributori capillare in Italia.")
    if ft == "petrol":
        if mix_c >= 0.60:
            return ("Benzina semplice e affidabile per uso prevalentemente urbano. "
                    "Rete distributori ovunque, manutenzione senza sorprese.")
        return ("Benzina affidabile e flessibile per utilizzo misto. "
                "La scelta più diffusa, senza dipendere da infrastrutture specifiche.")
    return "Motorizzazione compatibile con il tuo profilo di utilizzo."


def spiega_scelta(auto: "Auto", profilo: "ProfiloUtente", rank: int,
                  score: Optional["DettaglioScore"] = None) -> str:
    """Genera una frase narrativa che giustifica la scelta dell'auto."""
    RANK_INTRO = {1: "La scelta migliore per te", 2: "Ottima alternativa", 3: "Valida opzione"}
    intro = RANK_INTRO.get(rank, f"Opzione #{rank}")

    if score is None:
        return f"{intro}: ottimo compromesso tra budget, motorizzazione e dimensioni."

    punti = {c: sum(p for cc, p, _ in score.voci if cc == c) for c in set(c for c, _, _ in score.voci)}
    frasi: list[str] = []

    # Budget
    budget_pts = punti.get("budget", 0)
    if budget_pts >= 35 and auto.prezzo:
        pct = round(auto.prezzo / profilo.budget_acquisto_eur * 100)
        frasi.append(f"usa il {pct}% del tuo budget")

    # Alimentazione
    alim_pts = punti.get("alimentazione", 0)
    _FT_IT = {
        "electric":    "elettrica",
        "phev":        "ibrida PHEV",
        "full_hybrid": "ibrido full-HEV",
        "diesel":      "diesel",
        "lpg":         "GPL",
        "petrol":      "benzina",
    }
    ft_it = _FT_IT.get(auto.alimentazione, auto.alimentazione)
    if alim_pts >= 70:
        frasi.append(f"motorizzazione {ft_it} ideale per il tuo mix di percorsi")
    elif alim_pts >= 50:
        frasi.append(f"motorizzazione {ft_it} compatibile con le tue abitudini")

    # Contesto stradale
    cs_pts = punti.get("contesto_stradale", 0)
    if cs_pts >= 20:
        if profilo.contesto_stradale == "centro" and auto.lunghezza_mm:
            frasi.append(f"compatta ({auto.lunghezza_mm / 1000:.2f} m) per centro e ZTL")
        elif profilo.contesto_stradale == "montagna":
            frasi.append("trazione integrale per fondi sdrucciolevoli")

    # Spazio/bagagliaio
    sp_pos = [(c, p, d) for c, p, d in score.voci if c == "spazio" and p > 0]
    if sp_pos and auto.bagagliaio and profilo.n_passeggeri_abituali >= 4:
        frasi.append(f"bagagliaio da {auto.bagagliaio:.0f} L per tutta la famiglia")

    # Marca
    marca_pts = punti.get("marca", 0)
    if marca_pts >= 15:
        frasi.append(f"brand {auto.marca} in linea con il tuo profilo")

    if not frasi:
        return f"{intro}: il miglior punteggio complessivo tra tutte le auto del catalogo."

    return f"{intro}: " + ", ".join(frasi) + "."


# ── Scoring principale ─────────────────────────────────────────────────────────

def score_auto(auto: Auto, profilo: ProfiloUtente) -> Optional[DettaglioScore]:
    """
    Ritorna None per auto escluse da vincoli hard (neopatentato, EV senza ricarica).
    Altrimenti DettaglioScore con punteggio complessivo.
    """
    voci: list[tuple[str, float, str]] = []

    km                = profilo.km_giorno
    ricarica          = profilo.ricarica_a_casa
    budget            = profilo.budget_acquisto_eur
    passeggeri        = profilo.n_passeggeri_abituali
    neopatentato      = profilo.neopatentato
    contesto          = profilo.contesto
    mentalita         = profilo.mentalita
    contesto_str      = profilo.contesto_stradale
    autonomia_ut      = profilo.autonomia_utente
    pref_carr         = getattr(profilo, "pref_carrozzeria", "nessuna")
    mix_c             = profilo.mix_citta
    mix_e             = profilo.mix_extra
    mix_a             = profilo.mix_auto

    # ── Vincolo assoluto: auto di lusso oltre 150k escluse (fuori mercato di massa) ─
    if auto.prezzo is not None and auto.prezzo > 150_000:
        return None

    # ── Vincolo neopatentato (Italia: max 55 kW/t per i primi 3 anni) ──────────
    if neopatentato and auto.rapporto_peso_potenza is not None:
        if auto.rapporto_peso_potenza > 55:
            return None

    # ── Vincolo elettrica senza ricarica su uso prevalentemente autostradale ───
    if auto.is_elettrica and not ricarica:
        if mix_a > 0.40 or km > 80:
            return None

    # ── Vincolo elettrico puro con viaggi lunghi (anche con ricarica) ───────────
    if auto.is_elettrica and autonomia_ut == "lunga" and ricarica:
        return None

    # ── Vincolo auto troppo grande per centro storico ───────────────────────────
    if contesto_str == "centro" and auto.lunghezza_mm and auto.lunghezza_mm > 4600:
        return None

    # ── Vincolo budget per mentalità ────────────────────────────────────────────
    if auto.prezzo is not None:
        ratio = auto.prezzo / budget
        if mentalita == "minimo" and ratio > 1.05:    return None
        if mentalita == "qualita" and ratio > 1.10:   return None
        if mentalita == "premium" and ratio > 1.20:   return None

    # ── Componenti con nome per debug panel ────────────────────────────────────
    _bs = 3
    _alim_score = 0
    _ms = 0
    _carr_s = 0
    _malus_phev = 0

    # ── 1. Budget ──────────────────────────────────────────────────────────────
    if auto.prezzo is not None:
        _bs = budget_score(auto.prezzo, budget, mentalita)
        voci.append(("budget", _bs, _budget_desc(auto.prezzo, budget, _bs, mentalita)))
    else:
        voci.append(("budget", _bs, "prezzo non disponibile (verifica concessionario)"))

    # ── 2. Alimentazione vs mix percorso ───────────────────────────────────────
    _alim_score = peso_motorizzazione(auto.alimentazione, mix_c, mix_e, mix_a, ricarica)
    voci.append(("alimentazione", _alim_score,
                 _alim_desc(auto.alimentazione, _alim_score, ricarica)))

    # ── 2b. Malus PHEV percorsi autostradali ───────────────────────────────────
    _malus_phev = calcola_malus_phev(auto.alimentazione, mix_a, ricarica)
    if _malus_phev != 0:
        if not ricarica:
            desc_malus = "PHEV senza ricarica: penalizzazione su percorsi autostradali"
        else:
            desc_malus = "PHEV: uso del termico prevalente in autostrada"
        voci.append(("phev_malus", _malus_phev, desc_malus))

    # ── 3. Efficienza consumo ──────────────────────────────────────────────────
    if auto.consumo and auto.consumo > 0:
        if auto.is_elettrica:
            costo_mensile = stima_costo_mensile(auto.consumo, auto.alimentazione, km, ricarica)
            voci.append(("efficienza", 12,
                f"consumo {auto.consumo:.1f} kWh/100km — ~{costo_mensile:.0f}€/mese energia"))
        else:
            costo_mensile = stima_costo_mensile(auto.consumo, auto.alimentazione, km, ricarica)
            unita = "l/100km"
            if auto.consumo < 4.5:
                voci.append(("efficienza", 8,
                    f"consumo contenuto {auto.consumo} {unita} (~{costo_mensile:.0f}€/mese)"))
            elif auto.consumo < 5.5:
                voci.append(("efficienza", 4,
                    f"consumo {auto.consumo} {unita} (~{costo_mensile:.0f}€/mese)"))

    # ── 4. Spazio / passeggeri ────────────────────────────────────────────────
    if passeggeri >= 4:
        if auto.lunghezza_mm:
            if auto.lunghezza_mm < 3800:
                voci.append(("spazio", -20, "auto molto compatta: spazio insufficiente per 4+ passeggeri"))
            elif auto.lunghezza_mm < 4000:
                voci.append(("spazio", -12, "auto compatta: spazio limitato per 4+ passeggeri"))
            elif auto.lunghezza_mm > 4400:
                voci.append(("spazio", 10, "auto spaziosa: ideale per 4-5 passeggeri"))
            else:
                voci.append(("spazio", 3, "dimensioni adeguate per 4+ passeggeri"))
        if auto.bagagliaio:
            if auto.bagagliaio < 200:
                voci.append(("spazio", -15, f"bagagliaio {auto.bagagliaio:.0f}L: insufficiente per 4+ persone"))
            elif auto.bagagliaio < 280:
                voci.append(("spazio", -10, f"bagagliaio {auto.bagagliaio:.0f}L: ridotto per 4+ persone"))
            elif auto.bagagliaio >= 400:
                voci.append(("spazio", 7, f"bagagliaio {auto.bagagliaio:.0f}L: capiente per famiglie"))
            elif auto.bagagliaio >= 350:
                voci.append(("spazio", 3, f"bagagliaio {auto.bagagliaio:.0f}L: adeguato per famiglie"))
    else:
        if auto.bagagliaio and auto.bagagliaio >= 300:
            voci.append(("spazio", 3, f"bagagliaio {auto.bagagliaio:.0f}L: ampio"))

    # ── 5. Contesto fiscale ───────────────────────────────────────────────────
    if contesto == "partita_iva":
        if auto.is_elettrica:
            voci.append(("fiscale", 10, "P.IVA: elettrica deducibile al 100% (uso aziendale esclusivo)"))
        elif auto.is_phev:
            voci.append(("fiscale", 8, "P.IVA: ibrido plug-in con basse emissioni, deducibilità migliorata"))
        elif auto.is_diesel:
            voci.append(("fiscale", 6, "P.IVA: diesel deducibile al 20% + IVA parzialmente recuperabile"))
        else:
            voci.append(("fiscale", 2, "P.IVA: deducibilità standard 20% (regime ordinario)"))

    # ── 6. Varietà di scelta (n_versioni come proxy disponibilità/affidabilità) ─
    if auto.n_versioni >= 5:
        voci.append(("disponibilità", 4,
            f"ampia scelta: {auto.n_versioni} versioni disponibili"))
    elif auto.n_versioni >= 3:
        voci.append(("disponibilità", 2,
            f"{auto.n_versioni} versioni disponibili"))

    # ── 7. Marca vs mentalità acquisto ────────────────────────────────────────
    _ms = marca_score(auto.marca, mentalita)
    if _ms != 0:
        if _ms > 0:
            voci.append(("marca", _ms,
                f"{auto.marca}: marca adatta al tuo profilo d'acquisto"))
        else:
            voci.append(("marca", _ms,
                f"{auto.marca}: marca premium, non ottimale per chi cerca il minimo"))

    # ── 8. Contesto stradale (dimensione / trazione) ──────────────────────────
    cs = contesto_stradale_score(auto, contesto_str)
    if cs != 0:
        if contesto_str == "centro":
            desc = ("dimensioni compatte: ideale per centro e ZTL" if cs > 0
                    else "auto lunga: manovre difficili in centro città")
        else:  # montagna
            desc = ("trazione integrale: ottima su strade di montagna" if cs > 10
                    else "trazione inseribile: buona per fondi sdrucciolevoli")
        voci.append(("contesto_stradale", cs, desc))

    # ── 9. Autonomia utente (rilevante solo con ricarica a casa) ─────────────
    aus = autonomia_score(auto.alimentazione, autonomia_ut, ricarica)
    if aus != 0:
        if aus > 0:
            voci.append(("autonomia", aus,
                "autonomia adatta ai tuoi tragitti con ricarica domestica"))
        else:
            voci.append(("autonomia", aus,
                "autonomia elettrica limitata per i tuoi viaggi lunghi"))

    # ── 10. Preferenza carrozzeria ────────────────────────────────────────────
    carr_auto = getattr(auto, "carrozzeria_prevalente", None)
    _carr_s = carrozzeria_score(carr_auto, pref_carr)
    if _carr_s != 0:
        if _carr_s > 0:
            voci.append(("carrozzeria", _carr_s,
                f"carrozzeria {carr_auto}: in linea con la tua preferenza"))
        else:
            voci.append(("carrozzeria", _carr_s,
                f"carrozzeria {carr_auto}: non è il tipo che preferisci"))

    totale = sum(p for _, p, _ in voci)
    return DettaglioScore(
        totale=totale,
        voci=voci,
        motorizzazione=float(_alim_score),
        budget=float(_bs),
        marca_s=float(_ms),
        carrozzeria=float(_carr_s),
        malus=float(_malus_phev),
    )


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

    risultati.sort(key=lambda x: (x[1].totale, x[0].n_versioni), reverse=True)
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
        print(f"  [motoriz={score.motorizzazione:.0f} budget={score.budget:.0f} "
              f"marca={score.marca_s:.0f} carr={score.carrozzeria:.0f} malus={score.malus:.0f}]")

        if auto.prezzo:
            print(f"  Prezzo base:  {auto.prezzo:,.0f} €")
        else:
            print(f"  ⚠  Prezzo non nel dataset: verifica sul sito del costruttore.")
        if auto.consumo:
            unita = "kWh/100km" if auto.is_elettrica else "l/100km"
            stim = " *" if auto.consumo_stimato else ""
            print(f"  Consumo:      {auto.consumo} {unita}{stim}")
        if auto.bagagliaio:
            print(f"  Bagagliaio:   {auto.bagagliaio:.0f} L")
        if auto.carrozzeria_prevalente:
            print(f"  Carrozzeria:  {auto.carrozzeria_prevalente}")

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
            "minimo / centro / 18k / no ricarica — atteso: compatte <4200mm, marche entry",
            ProfiloUtente(
                mix_citta=0.75, mix_extra=0.20, mix_auto=0.05,
                km_giorno=20, autonomia_viaggio=40,
                ricarica_a_casa=False,
                budget_acquisto_eur=18_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
                mentalita="minimo",
                contesto_stradale="centro",
                autonomia_utente="media",
            ),
        ),
        (
            "premium / periferia / 55k / ricarica / autonomia lunga — atteso: premium no EV puro",
            ProfiloUtente(
                mix_citta=0.30, mix_extra=0.35, mix_auto=0.35,
                km_giorno=70, autonomia_viaggio=280,
                ricarica_a_casa=True,
                budget_acquisto_eur=55_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
                mentalita="premium",
                contesto_stradale="periferia",
                autonomia_utente="lunga",
            ),
        ),
        (
            "qualita / montagna / 38k / 4 pass / no ricarica — atteso: 4x4, bagagliaio >350L",
            ProfiloUtente(
                mix_citta=0.25, mix_extra=0.45, mix_auto=0.30,
                km_giorno=60, autonomia_viaggio=150,
                ricarica_a_casa=False,
                budget_acquisto_eur=38_000,
                n_passeggeri_abituali=4,
                neopatentato=False,
                contesto="privato",
                mentalita="qualita",
                contesto_stradale="montagna",
                autonomia_utente="media",
            ),
        ),
        (
            "PHEV test / autostrada / no ricarica — atteso: diesel >> PHEV",
            ProfiloUtente(
                mix_citta=0.15, mix_extra=0.25, mix_auto=0.60,
                km_giorno=90, autonomia_viaggio=280,
                ricarica_a_casa=False,
                budget_acquisto_eur=40_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
                mentalita="qualita",
                contesto_stradale="periferia",
                autonomia_utente="media",
            ),
        ),
        (
            "PHEV test / autostrada / CON ricarica — atteso: PHEV competitivo",
            ProfiloUtente(
                mix_citta=0.15, mix_extra=0.25, mix_auto=0.60,
                km_giorno=90, autonomia_viaggio=280,
                ricarica_a_casa=True,
                budget_acquisto_eur=40_000,
                n_passeggeri_abituali=2,
                neopatentato=False,
                contesto="privato",
                mentalita="qualita",
                contesto_stradale="periferia",
                autonomia_utente="media",
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
    print("  Raccomandatore auto — Database 2026 v4")
    print("═" * 60)
    print("  Rispondi alle domande per trovare l'auto più adatta a te.\n")

    km = int(_chiedi_float("  Quanti km percorri in media al giorno? ", 1, 2000))
    percorso = _chiedi_scelta("  Tipo di percorso prevalente?", ["città", "misto", "autostrada"])
    mix_c, mix_e, mix_a = _PERCORSO_TO_MIX[percorso]
    autonomia = {"città": 40, "misto": 150, "autostrada": 280}[percorso]
    ricarica = _chiedi_bool("  Hai la possibilità di ricaricare a casa?")
    budget = _chiedi_float("  Qual è il tuo budget di acquisto (€)? ", 5_000, 500_000)
    passeggeri = int(_chiedi_float("  Quanti passeggeri trasporti abitualmente (incluso te)? ", 1, 5))
    neopatentato = _chiedi_bool("  Sei neopatentato (patente < 3 anni)?")
    contesto = _chiedi_scelta("  Acquisto per uso?", ["privato", "partita_iva"])

    mentalita_cli    = _chiedi_scelta("  Mentalità acquisto?", ["minimo", "qualita", "premium"])
    contesto_str_cli = _chiedi_scelta("  Contesto stradale?", ["centro", "periferia", "montagna"])
    autonomia_ut_cli = _chiedi_scelta("  Autonomia viaggi?", ["corta", "media", "lunga"]) if ricarica else "media"
    pref_carr_cli    = _chiedi_scelta("  Preferenza carrozzeria?",
                                      ["nessuna", "suv", "berlina", "station_wagon", "monovolume"])

    profilo = ProfiloUtente(
        mix_citta=mix_c,
        mix_extra=mix_e,
        mix_auto=mix_a,
        km_giorno=km,
        autonomia_viaggio=autonomia,
        ricarica_a_casa=ricarica,
        budget_acquisto_eur=budget,
        n_passeggeri_abituali=passeggeri,
        neopatentato=neopatentato,
        contesto=contesto,
        mentalita=mentalita_cli,
        contesto_stradale=contesto_str_cli,
        autonomia_utente=autonomia_ut_cli,
        pref_carrozzeria=pref_carr_cli,
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
