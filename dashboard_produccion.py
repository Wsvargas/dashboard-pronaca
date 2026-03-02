"""
PRONACA | Dashboard Producción Avícola (Costos + Ideal vs Real)
==============================================================
Ejecutar:
    streamlit run dashboard_produccion_costos_v8.py

Requiere en la MISMA carpeta:
- produccion_actual_final_con_costos_alimento_v3.xlsx
- 20_MEJORES_LOTES_POR_CONVERSION.xlsx   (opcional; si falta, usa ideal interno por segmento)

Notas clave:
- Sección 02 ignora INICIO (<=14 días) y analiza desde día 15.
- Sección 02 muestra SOLO botones y SOLO lotes con problemas.
- Sección 03: Real vs Ideal (sin curva biológica) + gap $/kg y pérdida estimada.
- Fix: usa textwrap.dedent para que Streamlit NO muestre el HTML como texto.
"""

import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from textwrap import dedent

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
MAIN_FILE  = "produccion_actual_final_con_costos_alimento_v3.xlsx"
BENCH_FILE = "20_MEJORES_LOTES_POR_CONVERSION.xlsx"

EDAD_CORTE = 14
EDAD_MIN_ANALISIS = 15

# ──────────────────────────────────────────────────────────────
# PAGE
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola (Costos)",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────
# BRAND TOKENS
# ──────────────────────────────────────────────────────────────
RED    = "#DA291C"
BLACK  = "#0B0B0C"
BG     = "#F0F3F7"
CARD   = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT   = "#0F172A"
MUTED  = "#64748B"
GREEN  = "#16A34A"
AMBER  = "#D97706"
BLUE   = "#1D4ED8"

ETAPA_ORDER = ["INICIO (1-14)", "CRECIMIENTO (15-28)", "PRE-ACABADO (29-35)", "ACABADO (36+)"]
ETAPA_COLORS = {
    "INICIO (1-14)":       "#93C5FD",
    "CRECIMIENTO (15-28)": "#3B82F6",
    "PRE-ACABADO (29-35)": "#F59E0B",
    "ACABADO (36+)":       "#DA291C",
}

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
def md(html: str):
    """Render HTML en Streamlit sin que se vuelva 'code block' por indentación."""
    st.markdown(dedent(html), unsafe_allow_html=True)

def get_etapa(edad: int):
    try:
        e = int(edad)
        if e <= 14: return "INICIO (1-14)"
        if e <= 28: return "CRECIMIENTO (15-28)"
        if e <= 35: return "PRE-ACABADO (29-35)"
        return "ACABADO (36+)"
    except Exception:
        return "INICIO (1-14)"

def fmt_num(x, dec=2, prefix="", suffix=""):
    try:
        if x is None or pd.isna(x):
            return "—"
        v = float(x)
        if dec == 0:
            return f"{prefix}{int(round(v)):,}{suffix}"
        return f"{prefix}{v:,.{dec}f}{suffix}"
    except Exception:
        return "—"

def parse_num_series(s: pd.Series) -> pd.Series:
    """Convierte strings con coma decimal a float (ej: 0,115 -> 0.115; 1.234,56 -> 1234.56)."""
    if pd.api.types.is_numeric_dtype(s):
        return s
    ss = s.astype(str).str.strip()
    ss = ss.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    ss = ss.str.replace(r"[^0-9,\.\-]", "", regex=True)

    has_dot = ss.str.contains(r"\.", regex=True)
    has_comma = ss.str.contains(",", regex=False)
    mask = has_dot & has_comma

    ss.loc[mask] = ss.loc[mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    ss.loc[~mask] = ss.loc[~mask].str.replace(",", ".", regex=False)

    return pd.to_numeric(ss, errors="coerce")

def pick_first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
md(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Bebas+Neue&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important;
    font-family: 'DM Sans', sans-serif !important;
    color: {TEXT} !important;
}}
.block-container {{
    padding-top: 0.9rem !important;
    padding-bottom: 1.2rem !important;
    max-width: 100% !important;
}}
footer {{ visibility: hidden; }}

.card {{
    background:{CARD};
    border:1px solid {BORDER};
    border-radius:14px;
    padding:12px 14px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}
.pronaca-header {{
    background: {BLACK};
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 14px;
}}
.pronaca-header-title {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.0rem; color: #fff; letter-spacing: 1.4px; line-height: 1.1;
}}
.pronaca-header-sub {{ font-size: 0.82rem; color: rgba(255,255,255,0.55); margin-top: 2px; }}
.pronaca-header-pill {{
    margin-left: auto;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 999px; padding: 6px 14px;
    font-size: 0.85rem; color: rgba(255,255,255,0.75) !important; white-space: nowrap;
}}
.filter-bar {{
    background: {CARD}; border: 1px solid {BORDER};
    border-radius: 12px; padding: 10px 14px; margin-bottom: 10px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}
.kpi-chip {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 10px 14px; min-width: 150px; flex: 1;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
}}
.kpi-chip.accent {{ border-left: 4px solid {RED}; }}
.kv {{ font-size: 1.35rem; font-weight: 900; color: {TEXT}; line-height: 1; }}
.kl {{ font-size: 0.70rem; font-weight: 800; text-transform: uppercase;
       letter-spacing: 0.8px; color: {MUTED} !important; margin-top: 3px; }}

.sec-header {{
    display: flex; align-items: baseline; gap: 12px;
    padding: 8px 0 6px 0; margin: 4px 0 6px 0;
    border-bottom: 2px solid {BORDER};
}}
.sec-num {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.0rem; color: {RED}; line-height: 1;
}}
.sec-title {{
    font-size: 1.0rem; font-weight: 900; color: {TEXT}; line-height: 1.2;
}}
.sec-sub {{ font-size: 0.78rem; color: {MUTED} !important; margin-top: 1px; }}

.badge {{
    display:inline-block;
    padding:2px 8px;
    border-radius:999px;
    font-size:0.72rem;
    font-weight:900;
    border:1px solid {BORDER};
    background:#F8FAFC;
}}
.badge.red {{ color:{RED}; border-color:rgba(218,41,28,.25); background:rgba(218,41,28,.06); }}
.badge.amber {{ color:{AMBER}; border-color:rgba(217,119,6,.25); background:rgba(217,119,6,.07); }}
.badge.green {{ color:{GREEN}; border-color:rgba(22,163,74,.25); background:rgba(22,163,74,.07); }}
</style>
""")

# ──────────────────────────────────────────────────────────────
# DATA LOAD
# ──────────────────────────────────────────────────────────────
if not os.path.exists(MAIN_FILE):
    st.error(f"❌ No se encontró {MAIN_FILE} en la carpeta.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()

    # Detectar columnas principales (más robusto)
    col_lote = pick_first_col(df, ["LoteCompleto", "Codigo_Unico", "Lote"])
    if not col_lote:
        raise ValueError("No encuentro columna de lote (LoteCompleto / Codigo_Unico / Lote).")

    col_edad = pick_first_col(df, ["Edad", "edad", "X4=Edad"])
    col_peso = pick_first_col(df, ["PesoFinal", "Peso", "Y=Peso comp", "Peso comp"])
    col_aves = pick_first_col(df, ["AvesVivas", "Aves Vivas", "Aves_netas", "Aves Neto", "Aves Neto ", "Aves Neto"])
    col_cost = pick_first_col(df, ["CostoAlimentoAcum", "Costo alim acum", "CostoAlimentoAcumulado", "CostoAlimento_acumulado"])
    col_unit = pick_first_col(df, ["unit_cost_final", "unit_cost", "$/kg (real)", "Costo unitario"])
    col_alimkg = pick_first_col(df, ["Alimento_acumulado_kg", "Alimento acum", "Alimento_acum", "AlimAcumKg"])

    col_zona = pick_first_col(df, ["zona", "Zona"])
    col_tipo = pick_first_col(df, ["TipoGranja", "Tipo_Granja", "Tipo de granja", "X30=Granja Propia"])
    col_quint = pick_first_col(df, ["quintil", "Quintil_Area_Crianza", "Quintil"])
    col_est = pick_first_col(df, ["Estatus", "ESTATUS", "Status"])

    # Renombrar internamente
    df = df.rename(columns={
        col_lote: "LoteCompleto",
        col_edad: "Edad",
        col_peso: "PesoFinal",
        col_aves: "AvesVivas",
    })

    # Parse numéricas
    for c in ["Edad", "PesoFinal", "AvesVivas"]:
        df[c] = parse_num_series(df[c])

    # Estatus
    if col_est:
        df["Estatus"] = df[col_est].astype(str).str.upper().str.strip()
    else:
        df["Estatus"] = "ACTIVO"

    # ZonaNombre
    if col_zona:
        z = parse_num_series(df[col_zona]).fillna(0).astype(int)
        df["ZonaNombre"] = np.where(z == 1, "BUCAY", "SANTO DOMINGO")
    else:
        pref = df["LoteCompleto"].astype(str).str[:3].str.upper()
        df["ZonaNombre"] = pref.map({"BUC":"BUCAY", "STO":"SANTO DOMINGO"}).fillna("OTRA")

    # GranjaID
    df["GranjaID"] = df["LoteCompleto"].astype(str).str[:7]

    # TipoStd
    if col_tipo:
        # si viene como texto o dummy (1/0)
        t = df[col_tipo]
        if pd.api.types.is_numeric_dtype(t) or t.astype(str).str.fullmatch(r"[01]").fillna(False).any():
            # si X30=Granja Propia: 1=PROPIA, 0=PAC
            tt = parse_num_series(t).fillna(0).astype(int)
            df["TipoStd"] = np.where(tt == 1, "PROPIA", "PAC")
        else:
            ts = t.astype(str).str.upper().str.strip()
            df["TipoStd"] = np.where(ts.str.contains("PROPIA"), "PROPIA", "PAC")
            df.loc[ts.eq("PCA"), "TipoStd"] = "PAC"
    else:
        # regla por código (como tu v5)
        df["TipoStd"] = df["GranjaID"].apply(lambda g: "PROPIA" if str(g)[3] in ("1","2") else "PAC")

    # Quintil
    if col_quint:
        df["Quintil"] = df[col_quint].astype(str).str.upper().str.strip()
    else:
        df["Quintil"] = "Q5"

    # Etapa
    df["Etapa"] = df["Edad"].apply(get_etapa)

    # Costos / alimento
    if col_cost:
        df["CostoAcum"] = parse_num_series(df[col_cost])
    else:
        df["CostoAcum"] = np.nan

    if col_alimkg:
        df["AlimAcumKg"] = parse_num_series(df[col_alimkg])
    else:
        # si no hay alimento en kg, intentar derivar usando unit_cost_final
        if col_unit and col_cost:
            unit = parse_num_series(df[col_unit]).replace(0, np.nan)
            df["AlimAcumKg"] = df["CostoAcum"] / unit
        else:
            df["AlimAcumKg"] = np.nan

    # Kg live REAL (clave para que $/kg sea realista)
    df["KgLive"] = (df["AvesVivas"] * df["PesoFinal"]).astype(float)

    # $/kg acumulado (global)
    df["CostoKg_Cum"] = df["CostoAcum"] / df["KgLive"].replace(0, np.nan)

    # FCR acumulado (si hay alimento kg)
    df["FCR_Cum"] = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)

    # Mortalidad %
    col_mort_acum = pick_first_col(df, ["MortalidadAcumulada", "MORTALIDAD + DESCARTE"])
    col_aves_neto = pick_first_col(df, ["Aves Neto", "Aves_netas"])
    if col_mort_acum and col_aves_neto and col_mort_acum in df.columns and col_aves_neto in df.columns:
        df[col_mort_acum] = parse_num_series(df[col_mort_acum])
        df[col_aves_neto] = parse_num_series(df[col_aves_neto])
        df["MortPct"] = (df[col_mort_acum] / df[col_aves_neto].replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    # Orden y post15 (restar base a día 14)
    df = df.sort_values(["LoteCompleto", "Edad"])
    base14 = (df[df["Edad"] <= EDAD_CORTE]
              .groupby("LoteCompleto", as_index=False)
              .last()[["LoteCompleto", "KgLive", "AlimAcumKg", "CostoAcum"]]
              .rename(columns={"KgLive":"KgBase14", "AlimAcumKg":"AlimBase14", "CostoAcum":"CostoBase14"}))

    df = df.merge(base14, on="LoteCompleto", how="left")
    df[["KgBase14","AlimBase14","CostoBase14"]] = df[["KgBase14","AlimBase14","CostoBase14"]].fillna(0)

    df["KgPost15"]   = df["KgLive"] - df["KgBase14"]
    df["AlimPost15"] = df["AlimAcumKg"] - df["AlimBase14"]
    df["CostoPost15"]= df["CostoAcum"] - df["CostoBase14"]

    df["FCR_Post15"]     = df["AlimPost15"] / df["KgPost15"].replace(0, np.nan)
    df["CostoKg_Post15"] = df["CostoPost15"] / df["KgPost15"].replace(0, np.nan)

    return df

@st.cache_data(show_spinner=False)
def build_snapshot_activos(df_all: pd.DataFrame) -> pd.DataFrame:
    act = df_all[df_all["Estatus"].astype(str).str.upper().eq("ACTIVO")].copy()
    if act.empty:
        return pd.DataFrame()
    snap = (act.sort_values(["LoteCompleto","Edad"])
              .groupby("LoteCompleto", as_index=False)
              .last())
    snap["Etapa"] = snap["Edad"].apply(get_etapa)
    return snap

@st.cache_data(show_spinner=False)
def build_segment_ideals(df_all: pd.DataFrame, top_n: int = 5):
    """
    IDEAL por segmento (Zona, Tipo, Quintil): usa top N lotes con menor FCR_Post15
    en su último registro (Edad >= 15), y calcula curva promedio por edad.
    """
    act = df_all[df_all["Estatus"].astype(str).str.upper().eq("ACTIVO")].copy()
    if act.empty:
        act = df_all.copy()

    snap = (act.sort_values(["LoteCompleto","Edad"])
              .groupby("LoteCompleto", as_index=False)
              .last())

    snap = snap[snap["Edad"] >= EDAD_MIN_ANALISIS].copy()
    snap = snap[snap["FCR_Post15"].notna()].copy()
    ideals = {}

    if snap.empty:
        return ideals

    for (zona, tipo, quint), g in snap.groupby(["ZonaNombre","TipoStd","Quintil"]):
        g2 = g.sort_values("FCR_Post15", ascending=True).head(top_n)
        lotes_top = g2["LoteCompleto"].tolist()
        cur = act[act["LoteCompleto"].isin(lotes_top)].copy()
        if cur.empty:
            continue

        agg = (cur.groupby("Edad", as_index=False)
               .agg(PesoFinal=("PesoFinal","mean"),
                    CostoKg_Post15=("CostoKg_Post15","mean")))
        agg = agg.sort_values("Edad")

        ideals[(zona, tipo, quint)] = {
            "edad": agg["Edad"].to_numpy(),
            "peso": agg["PesoFinal"].to_numpy(),
            "costkg_post15": agg["CostoKg_Post15"].to_numpy(),
            "lotes_base": lotes_top,
        }
    return ideals

def interp_at_age(x_arr, y_arr, age):
    try:
        if x_arr is None or y_arr is None or len(x_arr) < 2:
            return np.nan
        age = float(age)
        x = np.asarray(x_arr, dtype=float)
        y = np.asarray(y_arr, dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        x = x[ok]; y = y[ok]
        if len(x) < 2:
            return np.nan
        if age <= x.min(): return float(y[x.argmin()])
        if age >= x.max(): return float(y[x.argmax()])
        return float(np.interp(age, x, y))
    except Exception:
        return np.nan

with st.spinner("Cargando datos…"):
    DF = load_and_prepare(MAIN_FILE)

with st.spinner("Procesando snapshot e ideal…"):
    SNAP = build_snapshot_activos(DF)
    SEG_IDEALS = build_segment_ideals(DF, top_n=5)

if SNAP.empty:
    st.warning("No hay lotes ACTIVO en el archivo (o el estatus no coincide).")
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
md(f"""
<div class="pronaca-header">
  <div style="font-size:2.2rem;line-height:1">🐔</div>
  <div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA</div>
    <div class="pronaca-header-sub">Panel operativo basado en costos (FCR y $/kg) · Ideal vs Real</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS FULL WIDTH
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')
fc1, fc2, fc3 = st.columns([1.3, 1.2, 1.2])
with fc1:
    sel_zona = st.multiselect("📍 Zona", ["BUCAY","SANTO DOMINGO"], default=["BUCAY","SANTO DOMINGO"])
with fc2:
    sel_tipo = st.multiselect("🏠 Tipo", ["PROPIA","PAC"], default=["PROPIA","PAC"])
with fc3:
    sel_quint = st.multiselect("🧩 Quintil", ["Q1","Q2","Q3","Q4","Q5"], default=["Q1","Q2","Q3","Q4","Q5"])
md("</div>")

SF = SNAP.copy()
SF = SF[SF["ZonaNombre"].isin(sel_zona)]
SF = SF[SF["TipoStd"].isin(sel_tipo)]
SF = SF[SF["Quintil"].isin(sel_quint)]

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
    st.stop()

# ──────────────────────────────────────────────────────────────
# KPIs FULL WIDTH (ARRIBA)
# ──────────────────────────────────────────────────────────────
SF15 = SF[SF["Edad"] >= EDAD_MIN_ANALISIS].copy()

kg_live_total = SF["KgLive"].sum()
costo_total = SF["CostoAcum"].sum()
cost_per_kg = costo_total / (kg_live_total if kg_live_total else np.nan)

# FCR ponderado desde 15
fcr_post = (SF15["AlimPost15"].sum() / SF15["KgPost15"].sum()) if (SF15["KgPost15"].sum() > 0) else np.nan

# Pérdida est vs ideal (post15) por lote
def loss_row(r):
    if r["Edad"] < EDAD_MIN_ANALISIS or pd.isna(r["CostoKg_Post15"]) or pd.isna(r["KgPost15"]) or r["KgPost15"] <= 0:
        return (np.nan, np.nan, np.nan)
    key = (r["ZonaNombre"], r["TipoStd"], r["Quintil"])
    ideal = SEG_IDEALS.get(key)
    if not ideal:
        return (np.nan, np.nan, np.nan)
    ideal_ck = interp_at_age(ideal["edad"], ideal["costkg_post15"], r["Edad"])
    delta = r["CostoKg_Post15"] - ideal_ck if pd.notna(ideal_ck) else np.nan
    loss = max(0.0, delta) * float(r["KgPost15"]) if pd.notna(delta) else np.nan
    return (ideal_ck, delta, loss)

if not SF15.empty:
    tmp = SF15.apply(lambda r: loss_row(r), axis=1, result_type="expand")
    tmp.columns = ["IdealCk", "DeltaCk", "Loss"]
    SF15 = pd.concat([SF15.reset_index(drop=True), tmp.reset_index(drop=True)], axis=1)
    loss_total = SF15["Loss"].sum(skipna=True)
else:
    loss_total = np.nan

k1,k2,k3,k4,k5,k6 = st.columns(6)
kpi = [
    (k1, f"{SF['LoteCompleto'].nunique():,}", "Lotes activos", True, ""),
    (k2, f"{int(SF['AvesVivas'].sum()):,}", "Aves vivas", True, ""),
    (k3, fmt_num(kg_live_total,0,suffix=" kg"), "Kg live (total)", True, ""),
    (k4, fmt_num(fcr_post,3), "FCR (desde día 15)", False, ""),
    (k5, fmt_num(costo_total,0,prefix="$"), "Costo alim (acum)", True, ""),
    (k6, fmt_num(loss_total,0,prefix="$"), "Pérdida est. vs ideal", False, f"color:{RED}!important;" if pd.notna(loss_total) and loss_total>0 else ""),
]
for col, val, lab, accent, extra_style in kpi:
    with col:
        st.markdown(
            f'<div class="kpi-chip {"accent" if accent else ""}">'
            f'<div class="kv" style="{extra_style}">{val}</div>'
            f'<div class="kl">{lab}</div></div>',
            unsafe_allow_html=True
        )

# ──────────────────────────────────────────────────────────────
# LAYOUT: 2 MITADES
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ──────────────────────────────────────────────────────────────
# SECCIÓN 01 — RESUMEN POR ETAPA
# ──────────────────────────────────────────────────────────────
with left:
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa (Costos reales)</div>
    <div class="sec-sub">Aves, Kg live, FCR y $/kg · (FCR desde día 15 en adelante)</div>
  </div>
</div>
""")

    rows = []
    for etapa in ETAPA_ORDER:
        g = SF[SF["Etapa"] == etapa].copy()
        if g.empty:
            continue

        aves = g["AvesVivas"].sum()
        kg   = g["KgLive"].sum()
        cost = g["CostoAcum"].sum()
        mort = g["MortPct"].mean()

        if etapa == "INICIO (1-14)":
            # acumulado completo
            alim = g["AlimAcumKg"].sum()
            fcr  = alim / kg if kg > 0 else np.nan
            ck   = cost / kg if kg > 0 else np.nan
        else:
            g2 = g[g["Edad"] >= EDAD_MIN_ANALISIS]
            kgp = g2["KgPost15"].sum()
            alim = g2["AlimPost15"].sum()
            cpost = g2["CostoPost15"].sum()
            fcr  = alim / kgp if kgp > 0 else np.nan
            ck   = cpost / kgp if kgp > 0 else np.nan

        badge = "green"
        if pd.notna(ck) and ck >= 0.9: badge = "red"
        elif pd.notna(ck) and ck >= 0.75: badge = "amber"

        rows.append((etapa, aves, kg, fcr, cost, ck, mort, badge))

    tbody = ""
    for etapa, aves, kg, fcr, cost, ck, mort, badge in rows:
        dot = ETAPA_COLORS.get(etapa, BLUE)
        tbody += f"""
<tr style="border-bottom:1px solid {BORDER}">
  <td style="text-align:left;padding:8px 10px;font-weight:900">
    <span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:{dot};margin-right:6px;vertical-align:middle"></span>
    {etapa}
  </td>
  <td style="text-align:right;padding:8px 10px">{int(aves):,}</td>
  <td style="text-align:right;padding:8px 10px">{fmt_num(kg,0)}</td>
  <td style="text-align:right;padding:8px 10px">{fmt_num(fcr,3)}</td>
  <td style="text-align:right;padding:8px 10px">{fmt_num(cost,0,prefix="$")}</td>
  <td style="text-align:right;padding:8px 10px"><span class="badge {badge}">{fmt_num(ck,3,prefix="$",suffix="/kg")}</span></td>
  <td style="text-align:right;padding:8px 10px">{fmt_num(mort,2,suffix="%")}</td>
</tr>
"""

    md(f"""
<div class="card" style="padding:0;overflow:auto">
  <table style="width:100%;border-collapse:collapse;font-size:0.82rem">
    <thead>
      <tr style="background:#F8FAFC;border-bottom:1px solid {BORDER}">
        <th style="text-align:left;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">Etapa</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">Aves</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">Kg live</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">FCR</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">Costo</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">$/kg</th>
        <th style="text-align:right;padding:8px 10px;color:{MUTED};font-size:0.70rem;text-transform:uppercase;letter-spacing:0.6px">Mort%</th>
      </tr>
    </thead>
    <tbody>{tbody}</tbody>
  </table>
</div>
""")

    # ──────────────────────────────────────────────────────────
    # SECCIÓN 02 — PEOR CONVERSIÓN (DÍA 15+) SOLO BOTONES
    # ──────────────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Peores conversiones (desde día 15) · Solo lotes con problemas</div>
    <div class="sec-sub">Ranking por pérdida estimada vs ideal (Δ $/kg y $) · Click y se grafica en la 03 automáticamente</div>
  </div>
</div>
""")

    if SF15.empty:
        st.info("No hay lotes con Edad ≥ 15 con los filtros actuales.")
    else:
        sf_ok = SF15[SF15["Loss"].notna()].copy()
        if sf_ok.empty:
            st.warning("No se pudo calcular ideal/pérdida para este segmento (no hay base suficiente de ideal interno).")
        else:
            granja_rank = (sf_ok.groupby("GranjaID", as_index=False)
                           .agg(
                               Zona=("ZonaNombre","first"),
                               Tipo=("TipoStd","first"),
                               Quintil=("Quintil","first"),
                               Lotes=("LoteCompleto","nunique"),
                               LossTotal=("Loss","sum"),
                               DeltaCkProm=("DeltaCk","mean"),
                           )
                           .sort_values("LossTotal", ascending=False)
                           .head(10)
                           .reset_index(drop=True))

            with st.expander("📌 Top 10 granjas (click para seleccionar)", expanded=True):
                cols = st.columns(2)
                for i, row in granja_rank.iterrows():
                    label = f"{row['GranjaID']} · {fmt_num(row['LossTotal'],0,prefix='$')} · Δ$/kg {fmt_num(row['DeltaCkProm'],3,prefix='$')}"
                    if cols[i % 2].button(label, key=f"farm_{row['GranjaID']}"):
                        st.session_state["farm_sel"] = row["GranjaID"]
                        st.rerun()

            farm_sel = st.session_state.get("farm_sel", granja_rank.iloc[0]["GranjaID"])
            if farm_sel not in granja_rank["GranjaID"].tolist():
                farm_sel = granja_rank.iloc[0]["GranjaID"]

            lotes_prob = sf_ok[sf_ok["GranjaID"] == farm_sel].copy()
            lotes_prob = lotes_prob[(lotes_prob["Loss"] > 0) | (lotes_prob["DeltaCk"] > 0)]
            lotes_prob = lotes_prob.sort_values("Loss", ascending=False)

            if lotes_prob.empty:
                st.info("Esta granja no tiene lotes con pérdida positiva vs ideal (para estos filtros).")
            else:
                st.caption(f"Lotes con problemas en {farm_sel} (Top {min(10,len(lotes_prob))})")
                cols = st.columns(2)
                for i, r in lotes_prob.head(10).iterrows():
                    lab = f"{r['LoteCompleto']} · Δ$/kg {fmt_num(r['DeltaCk'],3,prefix='$')} · {fmt_num(r['Loss'],0,prefix='$')}"
                    if cols[i % 2].button(lab, key=f"lot_{r['LoteCompleto']}"):
                        st.session_state["lote_sel"] = r["LoteCompleto"]
                        st.rerun()

                if len(lotes_prob) > 10:
                    with st.expander("Ver más lotes con problemas"):
                        cols2 = st.columns(2)
                        for j, r in lotes_prob.iloc[10:].iterrows():
                            lab = f"{r['LoteCompleto']} · Δ$/kg {fmt_num(r['DeltaCk'],3,prefix='$')} · {fmt_num(r['Loss'],0,prefix='$')}"
                            if cols2[j % 2].button(lab, key=f"lot_more_{r['LoteCompleto']}"):
                                st.session_state["lote_sel"] = r["LoteCompleto"]
                                st.rerun()

    # ──────────────────────────────────────────────────────────
    # SECCIÓN 03 — REAL vs IDEAL (SIN BIO) + GAP COSTO
    # ──────────────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">03</span>
  <div>
    <div class="sec-title">REAL vs IDEAL + GAP en Costos</div>
    <div class="sec-sub">Sin curva biológica · solo comparación directa y pérdida estimada</div>
  </div>
</div>
""")

    lotes_disp = sorted(SF["LoteCompleto"].unique().tolist())
    if not lotes_disp:
        st.stop()

    default_lote = st.session_state.get("lote_sel", lotes_disp[0])
    if default_lote not in lotes_disp:
        default_lote = lotes_disp[0]
        st.session_state["lote_sel"] = default_lote

    # Buscar lote SOLO si quieres (como pediste)
    with st.expander("🔎 Buscar lote específico (solo si necesitas)", expanded=False):
        q = st.text_input("Buscar", value="", placeholder="Ej: BUC1002-2505A-06-M")
        lotes_filtered = [x for x in lotes_disp if q.upper() in x.upper()] if q else lotes_disp
        lote_pick = st.selectbox("Lote", lotes_filtered, index=lotes_filtered.index(default_lote) if default_lote in lotes_filtered else 0)
        if lote_pick != default_lote:
            st.session_state["lote_sel"] = lote_pick
            st.rerun()

    lote_sel = st.session_state.get("lote_sel", default_lote)

    il = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    key_seg = (il["ZonaNombre"], il["TipoStd"], il["Quintil"])
    ideal_seg = SEG_IDEALS.get(key_seg)

    hist = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
    if hist.empty:
        st.warning("No hay historial del lote seleccionado.")
        st.stop()

    edad_act = float(il["Edad"])
    peso_act = float(il["PesoFinal"])

    # elegir costo $/kg para comparación (post15 si aplica)
    ck_act = float(il["CostoKg_Post15"]) if (il["Edad"] >= EDAD_MIN_ANALISIS and pd.notna(il["CostoKg_Post15"])) else float(il["CostoKg_Cum"])
    kg_post = float(il["KgPost15"]) if (il["Edad"] >= EDAD_MIN_ANALISIS and pd.notna(il["KgPost15"])) else np.nan

    if not ideal_seg:
        st.warning("⚠️ No hay IDEAL interno para esta combinación (Zona/Tipo/Quintil).")
    else:
        ideal_peso = interp_at_age(ideal_seg["edad"], ideal_seg["peso"], edad_act)
        ideal_ck   = interp_at_age(ideal_seg["edad"], ideal_seg["costkg_post15"], edad_act)

        delta_ck = ck_act - ideal_ck if pd.notna(ideal_ck) else np.nan
        loss_est = (max(0.0, delta_ck) * kg_post) if (pd.notna(delta_ck) and pd.notna(kg_post) and kg_post > 0 and edad_act >= EDAD_MIN_ANALISIS) else np.nan

        # KPIs lote
        h1,h2,h3,h4,h5,h6 = st.columns(6)
        with h1: st.markdown(f'<div class="kpi-chip"><div class="kv">{il["GranjaID"]}</div><div class="kl">Granja</div></div>', unsafe_allow_html=True)
        with h2: st.markdown(f'<div class="kpi-chip"><div class="kv">{il["ZonaNombre"]} · {il["TipoStd"]}</div><div class="kl">Segmento</div></div>', unsafe_allow_html=True)
        with h3: st.markdown(f'<div class="kpi-chip"><div class="kv">{il["Quintil"]}</div><div class="kl">Quintil</div></div>', unsafe_allow_html=True)
        with h4: st.markdown(f'<div class="kpi-chip"><div class="kv">{int(edad_act)} días</div><div class="kl">Edad</div></div>', unsafe_allow_html=True)
        with h5:
            col = RED if (pd.notna(delta_ck) and delta_ck > 0.03) else (AMBER if (pd.notna(delta_ck) and delta_ck > 0) else GREEN)
            st.markdown(f'<div class="kpi-chip"><div class="kv" style="color:{col}">Δ {fmt_num(delta_ck,3,prefix="$",suffix="/kg")}</div><div class="kl">Gap $/kg</div></div>', unsafe_allow_html=True)
        with h6:
            col = RED if (pd.notna(loss_est) and loss_est > 0) else MUTED
            st.markdown(f'<div class="kpi-chip"><div class="kv" style="color:{col}">{fmt_num(loss_est,0,prefix="$")}</div><div class="kl">Pérdida est.</div></div>', unsafe_allow_html=True)

        # Chart Real vs Ideal (peso)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist["Edad"], y=hist["PesoFinal"],
            mode="lines+markers",
            name="REAL",
            line=dict(color=RED, width=3),
            marker=dict(size=5),
            hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=ideal_seg["edad"], y=ideal_seg["peso"],
            mode="lines",
            name="IDEAL (segmento)",
            line=dict(color=GREEN, width=3),
            hovertemplate="Día %{x}<br>IDEAL: %{y:.3f} kg<extra></extra>",
        ))
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=320,
            margin=dict(l=8, r=8, t=18, b=8),
            font=dict(family="DM Sans", size=12, color=TEXT),
            legend=dict(orientation="h", y=-0.22, x=0, bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(title="Edad (días)", gridcolor=BORDER, zeroline=False, dtick=7, color=TEXT),
            yaxis=dict(title="Peso por ave (kg)", gridcolor=BORDER, zeroline=False, color=TEXT),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        base_lotes = ideal_seg.get("lotes_base", [])
        if base_lotes:
            st.caption("IDEAL interno construido con los mejores lotes disponibles en este archivo (top 5 por FCR desde día 15): "
                       + ", ".join(base_lotes[:5]) + ("..." if len(base_lotes) > 5 else ""))

# ──────────────────────────────────────────────────────────────
# MITAD DERECHA (placeholder)
# ──────────────────────────────────────────────────────────────
with right:
    md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:980px;">
  <div style="color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.7px;">
    Mitad derecha (pendiente)
  </div>
  <div style="color:{MUTED};font-size:0.85rem;margin-top:6px;">
    Espacio reservado para futuras visualizaciones.
  </div>
</div>
""")

md(f"""
<div style="text-align:center;font-size:0.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:10px">
PRONACA · Dashboard costos · Archivo: {MAIN_FILE} · Generado {hoy:%d/%m/%Y %H:%M}
</div>
""")