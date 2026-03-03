"""
PRONACA | Dashboard Producción Avícola v12 - INTERACTIVO
=========================================================
Mismo layout, métricas y cálculos que v11.
NUEVO: Selecciones en cascada usando on_select="rerun"
  - Gráfico Etapas (Sec 01)  → filtra granjas de Sec 02
  - Gráfico Granjas (Sec 02) → selecciona granja (reemplaza selectbox)
  - Tabla de Lotes (Sec 02)  → selecciona lote (reemplaza botones)
  - Sec 03 se alimenta de la selección de Sec 02
Ejecutar:
    streamlit run dashboard_produccion_v12_interactivo.py
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
EDAD_MIN_ANALISIS = 7
EDAD_CORTE = 14

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola v12",
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
    if pd.api.types.is_numeric_dtype(s):
        return s
    ss = s.astype(str).str.strip()
    ss = ss.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    ss = ss.str.replace(r"[^0-9,\.\-]", "", regex=True)
    has_dot   = ss.str.contains(r"\.", regex=True)
    has_comma = ss.str.contains(",", regex=False)
    mask = has_dot & has_comma
    ss.loc[mask]  = ss.loc[mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    ss.loc[~mask] = ss.loc[~mask].str.replace(",", ".", regex=False)
    return pd.to_numeric(ss, errors="coerce")

def pick_first_col(df: pd.DataFrame, candidates: list) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None

def extract_lote_codigo(lote_completo: str) -> str:
    parts = str(lote_completo).split('-')
    if len(parts) >= 3:
        return f"{parts[1]}-{parts[2]}"
    return str(lote_completo)

# ──────────────────────────────────────────────────────────────
# CSS (idéntico a v11)
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
.badge.red   {{ color:{RED};   border-color:rgba(218,41,28,.25); background:rgba(218,41,28,.06); }}
.badge.amber {{ color:{AMBER}; border-color:rgba(217,119,6,.25); background:rgba(217,119,6,.07); }}
.badge.green {{ color:{GREEN}; border-color:rgba(22,163,74,.25); background:rgba(22,163,74,.07); }}
/* Pill de selección activa */
.sel-pill {{
    display:inline-flex; align-items:center; gap:6px;
    background:rgba(218,41,28,0.08);
    border:1px solid rgba(218,41,28,0.25);
    border-radius:999px; padding:3px 10px;
    font-size:0.72rem; font-weight:800; color:{RED};
    margin-bottom:6px;
}}
.sel-pill-neutral {{
    display:inline-flex; align-items:center; gap:6px;
    background:rgba(29,78,216,0.08);
    border:1px solid rgba(29,78,216,0.20);
    border-radius:999px; padding:3px 10px;
    font-size:0.72rem; font-weight:800; color:{BLUE};
    margin-bottom:6px;
}}
.hint-text {{
    font-size:0.72rem; color:{MUTED}; font-style:italic; margin-bottom:4px;
}}
</style>
""")

# ──────────────────────────────────────────────────────────────
# DATA LOAD (idéntico a v11)
# ──────────────────────────────────────────────────────────────
if not os.path.exists(MAIN_FILE):
    st.error(f"❌ No se encontró {MAIN_FILE}")
    st.stop()

@st.cache_data(show_spinner=False)
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()

    col_lote  = pick_first_col(df, ["LoteCompleto","Codigo_Unico","Lote"])
    if not col_lote:
        raise ValueError("No encuentro columna de lote.")

    col_edad  = pick_first_col(df, ["Edad","edad","X4=Edad"])
    col_peso  = pick_first_col(df, ["PesoFinal","Peso","Y=Peso comp","Peso comp"])
    col_aves  = pick_first_col(df, ["AvesVivas","Aves Vivas","Aves_netas","Aves Neto","Aves Neto "])
    col_cost  = pick_first_col(df, ["CostoAlimentoAcum","Costo alim acum","CostoAlimentoAcumulado","CostoAlimento_acumulado"])
    col_alimkg= pick_first_col(df, ["Alimento_acumulado_kg","Alimento acum","Alimento_acum","AlimAcumKg"])
    col_zona  = pick_first_col(df, ["zona","Zona"])
    col_tipo  = pick_first_col(df, ["TipoGranja","Tipo_Granja","Tipo de granja","X30=Granja Propia"])
    col_quint = pick_first_col(df, ["quintil","Quintil_Area_Crianza","Quintil"])
    col_est   = pick_first_col(df, ["Estatus","ESTATUS","Status"])
    col_estado_lote = pick_first_col(df, ["EstadoLote","Estado_Lote","estado_lote","ESTADO LOTE"])

    df = df.rename(columns={
        col_lote: "LoteCompleto",
        col_edad: "Edad",
        col_peso: "PesoFinal",
        col_aves: "AvesVivas",
    })

    for c in ["Edad","PesoFinal","AvesVivas"]:
        df[c] = parse_num_series(df[c])

    df["Estatus"]    = df[col_est].astype(str).str.upper().str.strip() if col_est else "ACTIVO"
    df["EstadoLote"] = df[col_estado_lote].astype(str).str.upper().str.strip() if col_estado_lote else "ABIERTO"

    if col_zona:
        z = parse_num_series(df[col_zona]).fillna(0).astype(int)
        df["ZonaNombre"] = np.where(z == 1, "BUCAY", "SANTO DOMINGO")
    else:
        pref = df["LoteCompleto"].astype(str).str[:3].str.upper()
        df["ZonaNombre"] = pref.map({"BUC":"BUCAY","STO":"SANTO DOMINGO"}).fillna("OTRA")

    df["GranjaID"] = df["LoteCompleto"].astype(str).str[:7]

    if col_tipo:
        t = df[col_tipo]
        if pd.api.types.is_numeric_dtype(t) or t.astype(str).str.fullmatch(r"[01]").fillna(False).any():
            tt = parse_num_series(t).fillna(0).astype(int)
            df["TipoStd"] = np.where(tt == 1, "PROPIA", "PAC")
        else:
            ts = t.astype(str).str.upper().str.strip()
            df["TipoStd"] = np.where(ts.str.contains("PROPIA"), "PROPIA", "PAC")
            df.loc[ts.eq("PCA"), "TipoStd"] = "PAC"
    else:
        df["TipoStd"] = df["GranjaID"].apply(lambda g: "PROPIA" if str(g)[3] in ("1","2") else "PAC")

    df["Quintil"] = df[col_quint].astype(str).str.upper().str.strip() if col_quint else "Q5"
    df["Etapa"]   = df["Edad"].apply(get_etapa)

    df["CostoAcum"]  = parse_num_series(df[col_cost])  if col_cost   else np.nan
    df["AlimAcumKg"] = parse_num_series(df[col_alimkg]) if col_alimkg else np.nan

    df["KgLive"]     = (df["AvesVivas"] * df["PesoFinal"]).astype(float)
    df["CostoKg_Cum"]= df["CostoAcum"]  / df["KgLive"].replace(0, np.nan)
    df["FCR_Cum"]    = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)

    col_mort_acum = pick_first_col(df, ["MortalidadAcumulada","MORTALIDAD + DESCARTE"])
    col_aves_neto = pick_first_col(df, ["Aves Neto","Aves_netas"])
    if col_mort_acum and col_aves_neto:
        df[col_mort_acum] = parse_num_series(df[col_mort_acum])
        df[col_aves_neto] = parse_num_series(df[col_aves_neto])
        df["MortPct"] = (df[col_mort_acum] / df[col_aves_neto].replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    return df.sort_values(["LoteCompleto","Edad"])

@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_excel(path, sheet_name="DATOS_COMPLETOS")
        df.columns = df.columns.astype(str).str.strip()
        df["Zona_Nombre"] = np.where(df.get("Zona", 1) == 1, "BUCAY", "SANTO DOMINGO")
        df["TipoGranja"]  = df.get("TipoGranja","PAC").astype(str).str.upper().str.strip()
        df["Quintil"]     = df.get("Quintil_Area_Crianza","Q5").astype(str).str.upper().str.strip()
        return df
    except Exception as e:
        st.warning(f"⚠️ Error cargando ideales: {e}")
        return pd.DataFrame()

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

# ── Carga ────────────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    DF      = load_and_prepare(MAIN_FILE)
    IDEALES = load_ideales(BENCH_FILE)

with st.spinner("Procesando snapshot…"):
    SNAP = build_snapshot_activos(DF)

if SNAP.empty:
    st.warning("No hay lotes ACTIVO en el archivo.")
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
md(f"""
<div class="pronaca-header">
  <div style="font-size:2.2rem;line-height:1">🐔</div>
  <div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v12</div>
    <div class="pronaca-header-sub">Dashboard Interactivo · Selecciona gráficos para filtrar en cascada</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS SUPERIORES (sin cambios respecto a v11)
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')
fc1, fc2, fc3, fc4 = st.columns([1.3, 1.2, 1.2, 1.2])
with fc1:
    sel_zona  = st.multiselect("📍 Zona",   ["BUCAY","SANTO DOMINGO"],  default=["BUCAY","SANTO DOMINGO"])
with fc2:
    sel_tipo  = st.multiselect("🏠 Tipo",   ["PROPIA","PAC"],           default=["PROPIA","PAC"])
with fc3:
    sel_quint = st.multiselect("🧩 Quintil",["Q1","Q2","Q3","Q4","Q5"],default=["Q1","Q2","Q3","Q4","Q5"])
with fc4:
    sel_estado= st.multiselect("🔄 Estado", ["ABIERTO","CERRADO"],      default=["ABIERTO"])
md("</div>")

SF = SNAP.copy()
SF = SF[SF["ZonaNombre"].isin(sel_zona)]
SF = SF[SF["TipoStd"].isin(sel_tipo)]
SF = SF[SF["Quintil"].isin(sel_quint)]
SF = SF[SF["EstadoLote"].isin(sel_estado)]

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
    st.stop()

# ──────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────
kg_live_total = SF["KgLive"].sum()
costo_total   = SF["CostoAcum"].sum()
cost_per_kg   = costo_total / (kg_live_total if kg_live_total else np.nan)

k1, k2, k3, k4, k5 = st.columns(5)
kpi_data = [
    (k1, f"{SF['LoteCompleto'].nunique():,}",         "Lotes activos",  True),
    (k2, f"{int(SF['AvesVivas'].sum()):,}",            "Aves vivas",     True),
    (k3, fmt_num(kg_live_total,0,suffix=" kg"),        "Kg live",        True),
    (k4, fmt_num(costo_total,0,prefix="$"),            "Costo total",    True),
    (k5, fmt_num(cost_per_kg,3,prefix="$",suffix="/kg"),"Costo medio/kg",False),
]
for col, val, lab, accent in kpi_data:
    with col:
        md(f'<div class="kpi-chip {"accent" if accent else ""}"><div class="kv">{val}</div><div class="kl">{lab}</div></div>')

# ──────────────────────────────────────────────────────────────
# LAYOUT PRINCIPAL
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════════════════════════
# MITAD IZQUIERDA — SECCIONES INTERACTIVAS EN CASCADA
# ══════════════════════════════════════════════════════════════
with left:

    # ══════════════════════════════════════════════════════════
    # SECCIÓN 01 — Resumen por Etapa
    # Clic en barra → filtra granjas en Sec 02
    # ══════════════════════════════════════════════════════════
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa</div>
    <div class="sec-sub">🖱️ Haz clic en una barra para filtrar granjas abajo</div>
  </div>
</div>
""")

    # ── Calcular filas de etapa ────────────────────────────────
    rows_etapa = []
    for etapa in ETAPA_ORDER:
        g = SF[SF["Etapa"] == etapa].copy()
        if g.empty:
            continue
        n_lotes = g["LoteCompleto"].nunique()
        aves    = g["AvesVivas"].sum()
        kg      = g["KgLive"].sum()
        cost    = g["CostoAcum"].sum()
        mort    = g["MortPct"].mean()
        alim    = g["AlimAcumKg"].sum()
        fcr     = alim / kg if kg > 0 else np.nan
        ck      = cost / kg if kg > 0 else np.nan
        badge   = "green"
        if pd.notna(ck) and ck >= 0.9: badge = "red"
        elif pd.notna(ck) and ck >= 0.75: badge = "amber"
        rows_etapa.append((etapa, n_lotes, aves, kg, fcr, cost, ck, mort, badge))

    col_graf, col_tabla = st.columns([0.4, 0.6], gap="small")

    with col_graf:
        etapas_names     = [r[0] for r in rows_etapa]
        lotes_por_etapa  = [r[1] for r in rows_etapa]

        fig_barras = go.Figure()
        fig_barras.add_trace(go.Bar(
            x=etapas_names,
            y=lotes_por_etapa,
            marker=dict(color=[ETAPA_COLORS.get(e, BLUE) for e in etapas_names]),
            text=lotes_por_etapa,
            textposition="auto",
            hovertemplate="<b>%{x}</b><br>Lotes: %{y}<extra></extra>",
        ))
        fig_barras.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=240,
            margin=dict(l=8, r=8, t=18, b=50),
            font=dict(family="DM Sans", size=9, color=TEXT),
            showlegend=False,
            xaxis=dict(title="", gridcolor=BORDER, color=TEXT, tickangle=-45),
            yaxis=dict(title="Lotes", gridcolor=BORDER, color=TEXT),
        )

        # ── on_select="rerun" → selección interactiva ──────────
        sel_etapa_chart = st.plotly_chart(
            fig_barras,
            on_select="rerun",
            selection_mode="points",
            key="chart_etapas",
            config={"displayModeBar": False},
            width="stretch",
        )

        # Etapas seleccionadas desde el gráfico
        etapas_sel = [
            p["x"]
            for p in sel_etapa_chart.selection.get("points", [])
            if "x" in p
        ]

        # Indicador visual de filtro activo
        if etapas_sel:
            etapa_label = " + ".join([e.split("(")[0].strip() for e in etapas_sel])
            md(f'<div class="sel-pill">🔍 Filtrando: {etapa_label}</div>')
        else:
            md(f'<div class="hint-text">Clic en barra para filtrar ↓</div>')

    with col_tabla:
        tbody = ""
        for etapa, n_lotes, aves, kg, fcr, cost, ck, mort, badge in rows_etapa:
            dot      = ETAPA_COLORS.get(etapa, BLUE)
            activa   = etapa in etapas_sel if etapas_sel else False
            row_bg   = "rgba(218,41,28,0.05)" if activa else "transparent"
            fw       = "900" if activa else "700"
            tbody += f"""
<tr style="border-bottom:1px solid {BORDER};background:{row_bg}">
  <td style="text-align:left;padding:6px 8px;font-weight:{fw};font-size:0.73rem">
    <span style="display:inline-block;width:7px;height:7px;border-radius:2px;
                 background:{dot};margin-right:5px;vertical-align:middle"></span>
    {etapa.split('(')[0].strip()}
  </td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{int(aves):,}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(kg,0)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(fcr,3)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(cost,0,prefix="$")}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">
    <span class="badge {badge}">{fmt_num(ck,3,prefix="$")}</span></td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(mort,2,suffix="%")}</td>
</tr>"""

        md(f"""
<div class="card" style="padding:0;overflow:auto;height:240px">
  <table style="width:100%;border-collapse:collapse">
    <thead style="position:sticky;top:0;background:#F8FAFC;z-index:1">
      <tr style="border-bottom:1px solid {BORDER}">
        <th style="text-align:left;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">Etapa</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">Aves</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">Kg</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">FCR</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">Costo</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">$/kg</th>
        <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:0.63rem;text-transform:uppercase;letter-spacing:0.3px">M%</th>
      </tr>
    </thead>
    <tbody>{tbody}</tbody>
  </table>
</div>
""")

    # ══════════════════════════════════════════════════════════
    # SECCIÓN 02 — Top 5 Granjas con Problemas
    # Clic en barra → selecciona granja (reemplaza selectbox)
    # Tabla de lotes → clic en fila selecciona lote para Sec 03
    # ══════════════════════════════════════════════════════════
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 5 Granjas con Problemas</div>
    <div class="sec-sub">🖱️ Clic en granja → ver lotes · Clic en lote → análisis Sec 03</div>
  </div>
</div>
""")

    # ── Filtro por etapa si viene de Sec 01 ───────────────────
    SF_SEC02 = SF.copy()
    if etapas_sel:
        SF_SEC02 = SF_SEC02[SF_SEC02["Etapa"].isin(etapas_sel)]

    SF_ABIERTOS  = SF_SEC02[SF_SEC02["EstadoLote"] == "ABIERTO"].copy()
    DF_ABIERTOS  = DF[DF["EstadoLote"] == "ABIERTO"].copy()

    if SF_ABIERTOS.empty:
        st.info("No hay lotes ABIERTOS con los filtros actuales.")
    else:
        # ── Calcular granjas con problema ─────────────────────
        problemas_por_granja = []
        for granja in SF_ABIERTOS["GranjaID"].unique():
            lotes_granja = DF_ABIERTOS[
                (DF_ABIERTOS["GranjaID"] == granja) &
                (DF_ABIERTOS["Edad"] >= EDAD_MIN_ANALISIS)
            ].copy()
            if lotes_granja.empty:
                continue
            n_lotes_problema = 0
            gap_acum = 0
            gap_n    = 0
            for lote in lotes_granja["LoteCompleto"].unique():
                lote_data    = lotes_granja[lotes_granja["LoteCompleto"] == lote]
                snap_lote    = lote_data.iloc[-1] if len(lote_data) > 0 else None
                if snap_lote is None:
                    continue
                ideal_data = IDEALES[
                    (IDEALES["Zona_Nombre"] == snap_lote["ZonaNombre"]) &
                    (IDEALES["TipoGranja"]  == snap_lote["TipoStd"]) &
                    (IDEALES["Quintil"]     == snap_lote["Quintil"])
                ].copy()
                if ideal_data.empty:
                    continue
                gs = gc = 0
                for _, ir in ideal_data.iterrows():
                    pr = lote_data[lote_data["Edad"] == ir.get("Edad")]
                    if not pr.empty and pd.notna(ir.get("Peso")):
                        g = ir["Peso"] - pr.iloc[0]["PesoFinal"]
                        if g > 0:
                            gs += g; gc += 1
                if gc > 0:
                    n_lotes_problema += 1
                    gap_acum += gs / gc
                    gap_n    += 1
            if n_lotes_problema > 0:
                problemas_por_granja.append({
                    "GranjaID": granja,
                    "NumLotesProblema": n_lotes_problema,
                    "GapPromedio": gap_acum / gap_n if gap_n > 0 else 0,
                })

        if not problemas_por_granja:
            st.warning("No hay granjas con gap de peso vs ideal.")
        else:
            df_prob = (pd.DataFrame(problemas_por_granja)
                       .sort_values("NumLotesProblema", ascending=False)
                       .head(5))

            # ── Gráfico granjas — INTERACTIVO ──────────────────
            fig_granjas = go.Figure()
            fig_granjas.add_trace(go.Bar(
                x=df_prob["GranjaID"],
                y=df_prob["NumLotesProblema"],
                marker=dict(color=RED),
                text=df_prob["NumLotesProblema"],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Lotes problema: %{y}<extra></extra>",
            ))
            fig_granjas.update_layout(
                template="plotly_white",
                paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=200,
                margin=dict(l=8, r=8, t=18, b=8),
                font=dict(family="DM Sans", size=10, color=TEXT),
                showlegend=False,
                xaxis=dict(title="Granja", gridcolor=BORDER, color=TEXT),
                yaxis=dict(title="# Lotes Problema", gridcolor=BORDER, color=TEXT),
            )

            sel_granja_chart = st.plotly_chart(
                fig_granjas,
                on_select="rerun",
                selection_mode="points",
                key="chart_granjas",
                width="stretch",
            )

            # ── Granja activa ──────────────────────────────────
            granjas_sel = [
                p["x"]
                for p in sel_granja_chart.selection.get("points", [])
                if "x" in p
            ]
            granja_activa = granjas_sel[0] if granjas_sel else df_prob.iloc[0]["GranjaID"]

            if granjas_sel:
                md(f'<div class="sel-pill">🏭 Granja seleccionada: <strong>{granja_activa}</strong></div>')
            else:
                md(f'<div class="hint-text">Clic en barra para seleccionar granja · Mostrando: <strong>{granja_activa}</strong></div>')

            # ── Calcular lotes de la granja activa ────────────
            lotes_granja_prob = []
            lotes_g = DF_ABIERTOS[
                (DF_ABIERTOS["GranjaID"] == granja_activa) &
                (DF_ABIERTOS["Edad"] >= EDAD_MIN_ANALISIS)
            ].copy()

            for lote in lotes_g["LoteCompleto"].unique():
                lote_data = lotes_g[lotes_g["LoteCompleto"] == lote]
                snap_lote = lote_data.iloc[-1] if len(lote_data) > 0 else None
                if snap_lote is None:
                    continue
                ideal_data = IDEALES[
                    (IDEALES["Zona_Nombre"] == snap_lote["ZonaNombre"]) &
                    (IDEALES["TipoGranja"]  == snap_lote["TipoStd"]) &
                    (IDEALES["Quintil"]     == snap_lote["Quintil"])
                ].copy()
                if ideal_data.empty:
                    continue
                gs = gc = 0
                for _, ir in ideal_data.iterrows():
                    pr = lote_data[lote_data["Edad"] == ir.get("Edad")]
                    if not pr.empty and pd.notna(ir.get("Peso")):
                        g = ir["Peso"] - pr.iloc[0]["PesoFinal"]
                        if g > 0: gs += g; gc += 1
                if gc > 0:
                    snap_r = SF[SF["LoteCompleto"] == lote]
                    fcr_v  = float(snap_r.iloc[0]["FCR_Cum"])  if not snap_r.empty and pd.notna(snap_r.iloc[0]["FCR_Cum"])  else np.nan
                    ck_v   = float(snap_r.iloc[0]["CostoKg_Cum"]) if not snap_r.empty and pd.notna(snap_r.iloc[0]["CostoKg_Cum"]) else np.nan
                    lotes_granja_prob.append({
                        "LoteCompleto": lote,
                        "Código":       extract_lote_codigo(lote),
                        "Edad":         int(snap_lote["Edad"]),
                        "Gap kg":       round(gs / gc, 3),
                        "FCR":          round(fcr_v, 3) if pd.notna(fcr_v) else None,
                        "$/kg":         round(ck_v, 3)  if pd.notna(ck_v)  else None,
                    })

            if not lotes_granja_prob:
                st.info(f"No hay lotes con problema en {granja_activa}.")
            else:
                df_lotes = (pd.DataFrame(lotes_granja_prob)
                             .sort_values("Gap kg", ascending=False)
                             .reset_index(drop=True))

                md(f'<div class="hint-text">Clic en una fila para analizar ese lote en Sec 03 ↓</div>')

                # ── Tabla INTERACTIVA de lotes ──────────────────
                # Columnas visibles (sin LoteCompleto que va en sesión)
                df_display = df_lotes[["Código","Edad","Gap kg","FCR","$/kg"]].copy()

                sel_lote_table = st.dataframe(
                    df_display,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_lotes_sec02",
                    hide_index=True,
                    use_container_width=True,
                    height=180,
                    column_config={
                        "Código":  st.column_config.TextColumn("🔖 Código", width="small"),
                        "Edad":    st.column_config.NumberColumn("Días", format="%d d", width="small"),
                        "Gap kg":  st.column_config.NumberColumn("Gap kg ↑", format="%.3f", width="small"),
                        "FCR":     st.column_config.NumberColumn("FCR", format="%.3f", width="small"),
                        "$/kg":    st.column_config.NumberColumn("$/kg", format="$%.3f", width="small"),
                    },
                )

                # ── Actualizar lote seleccionado en session_state
                rows_sel = sel_lote_table.selection.get("rows", [])
                if rows_sel:
                    lote_desde_tabla = df_lotes.iloc[rows_sel[0]]["LoteCompleto"]
                    if st.session_state.get("lote_sel_sec03") != lote_desde_tabla:
                        st.session_state["lote_sel_sec03"] = lote_desde_tabla
                        st.rerun()

    # ══════════════════════════════════════════════════════════
    # SECCIÓN 03 — Lote Seleccionado: IDEAL vs REAL
    # Se alimenta de la selección en la tabla de Sec 02
    # ══════════════════════════════════════════════════════════
    md(f"""
<div class="sec-header">
  <span class="sec-num">03</span>
  <div>
    <div class="sec-title">Lote Seleccionado: IDEAL vs REAL</div>
    <div class="sec-sub">Análisis detallado · selecciona un lote en la tabla de arriba</div>
  </div>
</div>
""")

    # ── Lote activo ───────────────────────────────────────────
    lotes_disp = SF["LoteCompleto"].unique().tolist()

    if "lote_sel_sec03" not in st.session_state:
        st.session_state["lote_sel_sec03"] = lotes_disp[0] if lotes_disp else None

    lote_sel = st.session_state.get("lote_sel_sec03")
    if lote_sel not in lotes_disp:
        lote_sel = lotes_disp[0] if lotes_disp else None
        st.session_state["lote_sel_sec03"] = lote_sel

    if not lote_sel:
        st.info("Selecciona un lote en la tabla de arriba.")
        st.stop()

    # Indicador del lote activo
    md(f'<div class="sel-pill-neutral">📋 Analizando: <strong>{extract_lote_codigo(lote_sel)}</strong> · {lote_sel}</div>')

    il   = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    hist = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()

    if hist.empty:
        st.warning("No hay historial para este lote.")
        st.stop()

    edad_act   = float(il["Edad"])
    ideal_data = IDEALES[
        (IDEALES["Zona_Nombre"] == il["ZonaNombre"]) &
        (IDEALES["TipoGranja"]  == il["TipoStd"]) &
        (IDEALES["Quintil"]     == il["Quintil"])
    ].copy()

    if ideal_data.empty:
        st.error(f"❌ Sin ideal para: {il['ZonaNombre']} · {il['TipoStd']} · {il['Quintil']}")
    else:
        # KPIs del lote
        h1, h2, h3, h4 = st.columns(4)
        for col_, val_, lbl_ in [
            (h1, il["GranjaID"],       "Granja"),
            (h2, il["ZonaNombre"],     "Zona"),
            (h3, il["TipoStd"],        "Tipo"),
            (h4, f"{int(edad_act)} d", "Edad"),
        ]:
            with col_:
                md(f'<div class="kpi-chip"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

        # ── Gráfico Peso Real vs Ideal ─────────────────────────
        hist_valid   = hist[hist["PesoFinal"].notna()].copy()
        edad_max_real= float(hist_valid["Edad"].max())
        ideal_sorted = ideal_data.sort_values("Edad")
        ideal_sorted = ideal_sorted[ideal_sorted["Edad"] <= edad_max_real + 3]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_valid["Edad"], y=hist_valid["PesoFinal"],
            mode="lines+markers", name="REAL",
            line=dict(color=RED, width=3), marker=dict(size=6),
            hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=ideal_sorted["Edad"], y=ideal_sorted["Peso"],
            mode="lines+markers", name="IDEAL",
            line=dict(color=GREEN, width=3, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
            hovertemplate="Día %{x}<br>IDEAL: %{y:.3f} kg<extra></extra>",
        ))
        ideal_merge = ideal_sorted[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"})
        hm = hist_valid.merge(ideal_merge, on="Edad", how="inner")
        if not hm.empty:
            fig.add_trace(go.Scatter(
                x=hm["Edad"].tolist() + hm["Edad"].tolist()[::-1],
                y=hm["PesoFinal"].tolist() + hm["PesoIdeal"].tolist()[::-1],
                fill="toself", name="GAP",
                fillcolor="rgba(218,41,28,0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip",
            ))
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=300, margin=dict(l=8, r=8, t=18, b=8),
            font=dict(family="DM Sans", size=11, color=TEXT),
            legend=dict(orientation="h", y=-0.15, x=0, bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
            yaxis=dict(title="Peso (kg)", gridcolor=BORDER, color=TEXT),
            hovermode="x unified",
        )
        st.plotly_chart(fig, width="stretch")

        # ── Gráfico Costo Perdido Acumulado ────────────────────
        st.caption("**Costo perdido (Real vs Ideal) acumulado:**")

        hist_costo = hist[hist["Edad"] >= EDAD_MIN_ANALISIS].copy()
        ideal_cost = ideal_sorted[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"})
        hist_costo = hist_costo.merge(ideal_cost, on="Edad", how="left")

        hist_costo["KgRealAcum"]   = (hist_costo["AvesVivas"] * hist_costo["PesoFinal"]).cumsum()
        hist_costo["KgIdealAcum"]  = (hist_costo["AvesVivas"] * hist_costo["PesoIdeal"]).cumsum()
        hist_costo["CostoRealAcum"]  = hist_costo["CostoAcum"]
        hist_costo["CostoIdealAcum"] = hist_costo["KgIdealAcum"] * hist_costo["CostoKg_Cum"]
        hist_costo["CostoPerdido"]   = (hist_costo["CostoRealAcum"] - hist_costo["CostoIdealAcum"]).clip(lower=0)

        hc_clean = hist_costo[["Edad","CostoPerdido"]].dropna()

        fig_costo = go.Figure()
        fig_costo.add_trace(go.Scatter(
            x=hc_clean["Edad"], y=hc_clean["CostoPerdido"],
            mode="lines+markers", name="Costo Perdido",
            line=dict(color=RED, width=3), marker=dict(size=7),
            fill="tozeroy", fillcolor="rgba(218,41,28,0.2)",
            hovertemplate="Día %{x}<br>Pérdida: $%{y:,.2f}<extra></extra>",
        ))
        fig_costo.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=280, margin=dict(l=8, r=8, t=18, b=8),
            font=dict(family="DM Sans", size=11, color=TEXT),
            showlegend=False,
            xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
            yaxis=dict(title="Costo Perdido ($)", gridcolor=BORDER, color=TEXT),
            hovermode="x unified",
        )
        st.plotly_chart(fig_costo, width="stretch")

# ══════════════════════════════════════════════════════════════
# MITAD DERECHA — PREDICCIÓN (PROYECCIÓN A DÍA 40 DEL LOTE DE SEC 03)
# ══════════════════════════════════════════════════════════════
with right:
    try:
        from model_predictor import cargar_predictor
        predictor = cargar_predictor("modelo_rf_avicola.joblib")
        predictor_disponible = predictor.model is not None
    except Exception as e:
        st.warning(f"⚠️ No se pudo cargar el predictor: {e}")
        predictor_disponible = False

    if not predictor_disponible:
        md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:1300px;
display:flex;align-items:center;justify-content:center;">
  <div style="text-align:center;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.7px;">
    📊 Predicción de Lotes<br><br>
    ⚠️ Modelo no disponible<br>
    Coloca <strong>modelo_rf_avicola.joblib</strong> en la carpeta del app
  </div>
</div>
""")
    else:
        # Usamos el MISMO lote seleccionado en Sec 03 (lote_sel) y su histórico (DF)
        md(f"""
<div class="sec-header">
  <span class="sec-num">📊</span>
  <div>
    <div class="sec-title">Predicción de Peso</div>
    <div class="sec-sub">Proyección al día 40 para el lote seleccionado</div>
  </div>
</div>
""")

        # lote_sel viene de Sec 03
        if "lote_sel" not in locals() or not lote_sel:
            st.info("Selecciona un lote en la Sección 03 para ver la predicción.")
        else:
            hist_pred = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
            hist_pred = hist_pred[hist_pred["PesoFinal"].notna()].copy()

            if hist_pred.empty:
                st.warning(f"No hay historial válido de peso para {lote_sel}")
            else:
                # Proyección D40 (curva completa)
                try:
                    res = predictor.proyectar_curva(
                        hist_lote=hist_pred,
                        target_edad=40,
                        enforce_monotonic="isotonic"
                    )
                except Exception as e:
                    res = {"error": str(e), "df": None}

                if res.get("error"):
                    st.error(f"Error en predicción: {res['error']}")
                else:
                    df_curve = res["df"]
                    edad_actual = int(res["edad_actual"])
                    peso_actual = float(hist_pred.iloc[-1]["PesoFinal"])
                    peso_d40 = float(res["peso_d40"])
                    dias_faltantes = max(0, 40 - edad_actual)

                    # KPIs
                    c1, c2 = st.columns(2)
                    with c1:
                        md(f'<div class="kpi-chip accent"><div class="kv">{peso_d40:.3f} kg</div><div class="kl">Peso proyectado Día 40</div></div>')
                    with c2:
                        md(f'<div class="kpi-chip"><div class="kv">{dias_faltantes} d</div><div class="kl">Días restantes a 40</div></div>')

                    # Gráfico: REAL (histórico) + PROYECCIÓN (curva hasta 40)
                    fig_pred40 = go.Figure()

                    fig_pred40.add_trace(go.Scatter(
                        x=hist_pred["Edad"], y=hist_pred["PesoFinal"],
                        mode="lines+markers", name="REAL",
                        line=dict(color=BLUE, width=3), marker=dict(size=7),
                        hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
                    ))

                    fig_pred40.add_trace(go.Scatter(
                        x=df_curve["Dia"], y=df_curve["Peso_pred_kg"],
                        mode="lines", name="PROYECCIÓN D40",
                        line=dict(color=RED, width=3, dash="dash"),
                        hovertemplate="Día %{x}<br>PROY: %{y:.3f} kg<extra></extra>",
                    ))

                    # punto final D40
                    fig_pred40.add_trace(go.Scatter(
                        x=[40], y=[peso_d40],
                        mode="markers", name="D40",
                        marker=dict(size=10, symbol="diamond", color=RED),
                        hovertemplate="Día 40<br>%{y:.3f} kg<extra></extra>",
                    ))

                    fig_pred40.update_layout(
                        template="plotly_white",
                        paper_bgcolor=CARD, plot_bgcolor=CARD,
                        height=320, margin=dict(l=8, r=8, t=18, b=8),
                        font=dict(family="DM Sans", size=11, color=TEXT),
                        legend=dict(orientation="h", y=-0.15, x=0, bgcolor="rgba(0,0,0,0)"),
                        xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
                        yaxis=dict(title="Peso (kg)", gridcolor=BORDER, color=TEXT),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_pred40, width="stretch")

                    # Comparación con IDEAL en día 40 (si existe)
                    try:
                        fila_sf = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
                        ideal_d40 = IDEALES[
                            (IDEALES["Zona_Nombre"] == fila_sf["ZonaNombre"]) &
                            (IDEALES["TipoGranja"]  == fila_sf["TipoStd"]) &
                            (IDEALES["Quintil"]     == fila_sf["Quintil"]) &
                            (IDEALES["Edad"] == 40)
                        ]
                        if not ideal_d40.empty and pd.notna(ideal_d40.iloc[0]["Peso"]):
                            peso_ideal_40 = float(ideal_d40.iloc[0]["Peso"])
                            dif = peso_ideal_40 - peso_d40
                            badge_c = "red" if dif > 0 else "green"
                            texto = f"Atraso proyectado: {dif:.3f} kg" if dif > 0 else f"Adelante proyectado: {abs(dif):.3f} kg"
                            md(f'<div class="badge {badge_c}">{texto}</div>')
                    except Exception:
                        pass

                    st.caption("**Info de la proyección:**")
                    m1, m2, m3 = st.columns(3)
                    with m1: st.metric("Edad actual", f"{edad_actual} días")
                    with m2: st.metric("Peso actual", f"{peso_actual:.3f} kg")
                    with m3: st.metric("Peso proyectado D40", f"{peso_d40:.3f} kg")
                    # ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:0.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v12 · Interactivo · {hoy:%d/%m/%Y %H:%M}
</div>
""")