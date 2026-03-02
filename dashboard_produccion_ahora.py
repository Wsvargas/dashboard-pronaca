"""
PRONACA | Dashboard Producción Avícola v11
===========================================
Basado en versión que funcionaba + cambios solicitados:
- Sección 01: Gráfico pequeño (izq) + Tabla (der) lado a lado
- Sección 02: Grid HTML/CSS interactivo de lotes
- Sección 03: Real vs Ideal + Gráfico Costo Perdido (sin tabla)
             Ideal limitado a +3 días del real

Ejecutar:
    streamlit run dashboard_produccion_v11.py
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
    page_title="PRONACA | Producción Avícola v11",
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

.lotes-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 10px;
    padding: 12px;
    background: #f8fafc;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    margin: 8px 0;
}}

.lote-card {{
    background: white;
    border: 2px solid #e2e8f0;
    border-radius: 6px;
    padding: 14px;
    cursor: pointer;
    transition: all 0.25s ease;
    user-select: none;
}}

.lote-card:hover {{
    border-color: #da291c;
    box-shadow: 0 2px 8px rgba(218, 41, 28, 0.15);
    transform: translateY(-2px);
}}

.lote-card.selected {{
    background: #da291c;
    border-color: #da291c;
    color: white;
    box-shadow: 0 4px 12px rgba(218, 41, 28, 0.3);
}}

.lote-codigo {{
    font-weight: 700;
    font-size: 0.80rem;
    margin-bottom: 6px;
    letter-spacing: 0.5px;
}}

.lote-gap {{
    font-size: 0.72rem;
    opacity: 0.7;
}}

.lote-card.selected .lote-gap {{
    opacity: 0.9;
}}
</style>
""")

# ──────────────────────────────────────────────────────────────
# DATA LOAD
# ──────────────────────────────────────────────────────────────
if not os.path.exists(MAIN_FILE):
    st.error(f"❌ No se encontró {MAIN_FILE}")
    st.stop()

@st.cache_data(show_spinner=False)
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.astype(str).str.strip()
    
    col_lote = pick_first_col(df, ["LoteCompleto", "Codigo_Unico", "Lote"])
    if not col_lote:
        raise ValueError("No encuentro columna de lote.")
    
    col_edad = pick_first_col(df, ["Edad", "edad", "X4=Edad"])
    col_peso = pick_first_col(df, ["PesoFinal", "Peso", "Y=Peso comp", "Peso comp"])
    col_aves = pick_first_col(df, ["AvesVivas", "Aves Vivas", "Aves_netas", "Aves Neto", "Aves Neto ", "Aves Neto"])
    col_cost = pick_first_col(df, ["CostoAlimentoAcum", "Costo alim acum", "CostoAlimentoAcumulado", "CostoAlimento_acumulado"])
    col_alimkg = pick_first_col(df, ["Alimento_acumulado_kg", "Alimento acum", "Alimento_acum", "AlimAcumKg"])
    col_zona = pick_first_col(df, ["zona", "Zona"])
    col_tipo = pick_first_col(df, ["TipoGranja", "Tipo_Granja", "Tipo de granja", "X30=Granja Propia"])
    col_quint = pick_first_col(df, ["quintil", "Quintil_Area_Crianza", "Quintil"])
    col_est = pick_first_col(df, ["Estatus", "ESTATUS", "Status"])
    col_estado_lote = pick_first_col(df, ["EstadoLote", "Estado_Lote", "estado_lote", "ESTADO LOTE"])
    
    df = df.rename(columns={
        col_lote: "LoteCompleto",
        col_edad: "Edad",
        col_peso: "PesoFinal",
        col_aves: "AvesVivas",
    })
    
    for c in ["Edad", "PesoFinal", "AvesVivas"]:
        df[c] = parse_num_series(df[c])
    
    if col_est:
        df["Estatus"] = df[col_est].astype(str).str.upper().str.strip()
    else:
        df["Estatus"] = "ACTIVO"
    
    if col_estado_lote:
        df["EstadoLote"] = df[col_estado_lote].astype(str).str.upper().str.strip()
    else:
        df["EstadoLote"] = "ABIERTO"
    
    if col_zona:
        z = parse_num_series(df[col_zona]).fillna(0).astype(int)
        df["ZonaNombre"] = np.where(z == 1, "BUCAY", "SANTO DOMINGO")
    else:
        pref = df["LoteCompleto"].astype(str).str[:3].str.upper()
        df["ZonaNombre"] = pref.map({"BUC":"BUCAY", "STO":"SANTO DOMINGO"}).fillna("OTRA")
    
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
    
    if col_quint:
        df["Quintil"] = df[col_quint].astype(str).str.upper().str.strip()
    else:
        df["Quintil"] = "Q5"
    
    df["Etapa"] = df["Edad"].apply(get_etapa)
    
    if col_cost:
        df["CostoAcum"] = parse_num_series(df[col_cost])
    else:
        df["CostoAcum"] = np.nan
    
    if col_alimkg:
        df["AlimAcumKg"] = parse_num_series(df[col_alimkg])
    else:
        df["AlimAcumKg"] = np.nan
    
    df["KgLive"] = (df["AvesVivas"] * df["PesoFinal"]).astype(float)
    df["CostoKg_Cum"] = df["CostoAcum"] / df["KgLive"].replace(0, np.nan)
    df["FCR_Cum"] = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)
    
    col_mort_acum = pick_first_col(df, ["MortalidadAcumulada", "MORTALIDAD + DESCARTE"])
    col_aves_neto = pick_first_col(df, ["Aves Neto", "Aves_netas"])
    if col_mort_acum and col_aves_neto and col_mort_acum in df.columns and col_aves_neto in df.columns:
        df[col_mort_acum] = parse_num_series(df[col_mort_acum])
        df[col_aves_neto] = parse_num_series(df[col_aves_neto])
        df["MortPct"] = (df[col_mort_acum] / df[col_aves_neto].replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan
    
    df = df.sort_values(["LoteCompleto", "Edad"])
    
    return df

@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    
    try:
        df = pd.read_excel(path, sheet_name="DATOS_COMPLETOS")
        df.columns = df.columns.astype(str).str.strip()
        df["Zona_Nombre"] = np.where(df.get("Zona", 1) == 1, "BUCAY", "SANTO DOMINGO")
        df["TipoGranja"] = df.get("TipoGranja", "PAC").astype(str).str.upper().str.strip()
        df["Quintil"] = df.get("Quintil_Area_Crianza", "Q5").astype(str).str.upper().str.strip()
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

with st.spinner("Cargando datos…"):
    DF = load_and_prepare(MAIN_FILE)
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
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v11</div>
    <div class="pronaca-header-sub">Dashboard optimizado · Ideal vs Real</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')
fc1, fc2, fc3, fc4 = st.columns([1.3, 1.2, 1.2, 1.2])
with fc1:
    sel_zona = st.multiselect("📍 Zona", ["BUCAY","SANTO DOMINGO"], default=["BUCAY","SANTO DOMINGO"])
with fc2:
    sel_tipo = st.multiselect("🏠 Tipo", ["PROPIA","PAC"], default=["PROPIA","PAC"])
with fc3:
    sel_quint = st.multiselect("🧩 Quintil", ["Q1","Q2","Q3","Q4","Q5"], default=["Q1","Q2","Q3","Q4","Q5"])
with fc4:
    sel_estado = st.multiselect("🔄 Estado", ["ABIERTO","CERRADO"], default=["ABIERTO"])
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
costo_total = SF["CostoAcum"].sum()
cost_per_kg = costo_total / (kg_live_total if kg_live_total else np.nan)

k1,k2,k3,k4,k5 = st.columns(5)
kpi = [
    (k1, f"{SF['LoteCompleto'].nunique():,}", "Lotes activos", True, ""),
    (k2, f"{int(SF['AvesVivas'].sum()):,}", "Aves vivas", True, ""),
    (k3, fmt_num(kg_live_total,0,suffix=" kg"), "Kg live", True, ""),
    (k4, fmt_num(costo_total,0,prefix="$"), "Costo total", True, ""),
    (k5, fmt_num(cost_per_kg,3,prefix="$",suffix="/kg"), "Costo medio/kg", False, ""),
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
# LAYOUT: MITAD IZQUIERDA + MITAD DERECHA
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════════════════════════
# MITAD IZQUIERDA
# ══════════════════════════════════════════════════════════════
with left:
    
    # ──────────────────────────────────────────────────────────
    # SECCIÓN 01: Gráfico PEQUEÑO (izq) + Tabla (der) LADO A LADO
    # ──────────────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa</div>
    <div class="sec-sub">Lotes, aves, costos y conversión</div>
  </div>
</div>
""")
    
    rows = []
    for etapa in ETAPA_ORDER:
        g = SF[SF["Etapa"] == etapa].copy()
        if g.empty:
            continue
        n_lotes = g["LoteCompleto"].nunique()
        aves = g["AvesVivas"].sum()
        kg   = g["KgLive"].sum()
        cost = g["CostoAcum"].sum()
        mort = g["MortPct"].mean()
        alim = g["AlimAcumKg"].sum()
        fcr  = alim / kg if kg > 0 else np.nan
        ck   = cost / kg if kg > 0 else np.nan
        
        badge = "green"
        if pd.notna(ck) and ck >= 0.9: badge = "red"
        elif pd.notna(ck) and ck >= 0.75: badge = "amber"
        rows.append((etapa, n_lotes, aves, kg, fcr, cost, ck, mort, badge))
    
    # LAYOUT 50/50: Gráfico izquierda + Tabla derecha
    col_graf, col_tabla = st.columns([0.4, 0.6], gap="small")
    
    with col_graf:
        # Gráfico pequeño
        lotes_por_etapa = [r[1] for r in rows]
        etapas_names = [r[0] for r in rows]
        
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
            paper_bgcolor=CARD, 
            plot_bgcolor=CARD,
            height=240,
            margin=dict(l=8, r=8, t=18, b=50),
            font=dict(family="DM Sans", size=9, color=TEXT),
            showlegend=False,
            xaxis=dict(title="", gridcolor=BORDER, color=TEXT, tickangle=-45),
            yaxis=dict(title="Lotes", gridcolor=BORDER, color=TEXT),
        )
        st.plotly_chart(fig_barras, width='stretch', config={"displayModeBar": False})
    
    with col_tabla:
        # Tabla compacta
        tbody = ""
        for etapa, n_lotes, aves, kg, fcr, cost, ck, mort, badge in rows:
            dot = ETAPA_COLORS.get(etapa, BLUE)
            tbody += f"""
<tr style="border-bottom:1px solid {BORDER}">
  <td style="text-align:left;padding:6px 8px;font-weight:900;font-size:0.73rem">
    <span style="display:inline-block;width:7px;height:7px;border-radius:2px;background:{dot};margin-right:5px;vertical-align:middle"></span>
    {etapa.split('(')[0].strip()}
  </td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{int(aves):,}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(kg,0)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(fcr,3)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(cost,0,prefix="$")}</td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem"><span class="badge {badge}">{fmt_num(ck,3,prefix="$")}</span></td>
  <td style="text-align:right;padding:6px 8px;font-size:0.73rem">{fmt_num(mort,2,suffix="%")}</td>
</tr>
"""
        
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
    
    # ──────────────────────────────────────────────────────────
    # SECCIÓN 02: Top 5 Granjas + Grid Interactivo de Lotes
    # ──────────────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 5 Granjas con Problemas</div>
    <div class="sec-sub">Lotes abiertos con gap de peso vs ideal (día 7+)</div>
  </div>
</div>
""")
    
    SF_ABIERTOS = SF[SF["EstadoLote"] == "ABIERTO"].copy()
    DF_ABIERTOS = DF[DF["EstadoLote"] == "ABIERTO"].copy()
    
    if SF_ABIERTOS.empty:
        st.warning("No hay lotes ABIERTOS con los filtros actuales.")
    else:
        problemas_por_granja = []
        
        for granja in SF_ABIERTOS["GranjaID"].unique():
            lotes_granja = DF_ABIERTOS[
                (DF_ABIERTOS["GranjaID"] == granja) & 
                (DF_ABIERTOS["Edad"] >= EDAD_MIN_ANALISIS)
            ].copy()
            
            if lotes_granja.empty:
                continue
            
            lotes_lista = lotes_granja["LoteCompleto"].unique()
            n_lotes_problema = 0
            gap_promedio_granja = 0
            gap_count = 0
            
            for lote in lotes_lista:
                lote_data = lotes_granja[lotes_granja["LoteCompleto"] == lote].copy()
                snapshot_lote = lote_data.iloc[-1] if len(lote_data) > 0 else None
                if snapshot_lote is None:
                    continue
                
                ideal_data = IDEALES[
                    (IDEALES["Zona_Nombre"] == snapshot_lote["ZonaNombre"]) &
                    (IDEALES["TipoGranja"] == snapshot_lote["TipoStd"]) &
                    (IDEALES["Quintil"] == snapshot_lote["Quintil"])
                ].copy()
                
                if ideal_data.empty:
                    continue
                
                gap_suma = 0
                gap_count_lote = 0
                
                for _, ideal_row in ideal_data.iterrows():
                    edad_ideal = ideal_row.get("Edad")
                    peso_ideal = ideal_row.get("Peso")
                    peso_real_row = lote_data[lote_data["Edad"] == edad_ideal]
                    
                    if not peso_real_row.empty and pd.notna(peso_ideal):
                        peso_real = peso_real_row.iloc[0]["PesoFinal"]
                        gap = peso_ideal - peso_real
                        
                        if gap > 0:
                            gap_suma += gap
                            gap_count_lote += 1
                
                if gap_count_lote > 0:
                    n_lotes_problema += 1
                    gap_promedio_granja += (gap_suma / gap_count_lote)
                    gap_count += 1
            
            if n_lotes_problema > 0:
                gap_final = gap_promedio_granja / gap_count if gap_count > 0 else 0
                problemas_por_granja.append({
                    "GranjaID": granja,
                    "NumLotesProblema": n_lotes_problema,
                    "GapPromedio": gap_final,
                })
        
        if not problemas_por_granja:
            st.warning("No hay granjas con lotes abiertos que presenten gap de peso vs ideal.")
        else:
            df_problemas = pd.DataFrame(problemas_por_granja)
            df_problemas = df_problemas.sort_values("NumLotesProblema", ascending=False).head(5)
            
            # Gráfico
            fig_granjas = go.Figure()
            fig_granjas.add_trace(go.Bar(
                x=df_problemas["GranjaID"],
                y=df_problemas["NumLotesProblema"],
                marker=dict(color=RED),
                text=df_problemas["NumLotesProblema"],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Lotes problema: %{y}<extra></extra>",
            ))
            fig_granjas.update_layout(
                template="plotly_white",
                paper_bgcolor=CARD, 
                plot_bgcolor=CARD,
                height=200,
                margin=dict(l=8, r=8, t=18, b=8),
                font=dict(family="DM Sans", size=10, color=TEXT),
                showlegend=False,
                xaxis=dict(title="Granja", gridcolor=BORDER, color=TEXT),
                yaxis=dict(title="# Lotes Problema", gridcolor=BORDER, color=TEXT),
            )
            st.plotly_chart(fig_granjas, width='stretch')
            
            # Selector granja
            st.caption("**Selecciona granja para ver lotes:**")
            granjas_list = df_problemas["GranjaID"].tolist()
            sel_granja = st.selectbox("Granja", granjas_list, key="sel_granja_sec02")
            
            # Obtener lotes
            lotes_granja_prob = []
            lotes_granja = DF_ABIERTOS[
                (DF_ABIERTOS["GranjaID"] == sel_granja) & 
                (DF_ABIERTOS["Edad"] >= EDAD_MIN_ANALISIS)
            ].copy()
            
            for lote in lotes_granja["LoteCompleto"].unique():
                lote_data = lotes_granja[lotes_granja["LoteCompleto"] == lote].copy()
                snapshot_lote = lote_data.iloc[-1] if len(lote_data) > 0 else None
                
                if snapshot_lote is None:
                    continue
                
                ideal_data = IDEALES[
                    (IDEALES["Zona_Nombre"] == snapshot_lote["ZonaNombre"]) &
                    (IDEALES["TipoGranja"] == snapshot_lote["TipoStd"]) &
                    (IDEALES["Quintil"] == snapshot_lote["Quintil"])
                ].copy()
                
                if ideal_data.empty:
                    continue
                
                gap_suma = 0
                gap_count_lote = 0
                
                for _, ideal_row in ideal_data.iterrows():
                    edad_ideal = ideal_row.get("Edad")
                    peso_ideal = ideal_row.get("Peso")
                    peso_real_row = lote_data[lote_data["Edad"] == edad_ideal]
                    
                    if not peso_real_row.empty and pd.notna(peso_ideal):
                        peso_real = peso_real_row.iloc[0]["PesoFinal"]
                        gap = peso_ideal - peso_real
                        
                        if gap > 0:
                            gap_suma += gap
                            gap_count_lote += 1
                
                if gap_count_lote > 0:
                    gap_promedio = gap_suma / gap_count_lote
                    lotes_granja_prob.append({
                        "LoteCompleto": lote,
                        "Edad": int(snapshot_lote["Edad"]),
                        "Gap": gap_promedio,
                    })
            
            if not lotes_granja_prob:
                st.info(f"No hay lotes con problema en {sel_granja}.")
            else:
                df_lotes_prob = pd.DataFrame(lotes_granja_prob).sort_values("Gap", ascending=False)
                st.caption(f"**Lotes con problema en {sel_granja}:**")
                
                # Mostrar como lista de botones compacta (SIN HTML)
                for _, row in df_lotes_prob.iterrows():
                    label = f"{row['LoteCompleto']} · Gap: {fmt_num(row['Gap'], 3, suffix=' kg')} · {int(row['Edad'])} días"
                    if st.button(label, key=f"lote_{row['LoteCompleto']}", width='stretch'):
                        st.session_state["lote_sel_sec03"] = row["LoteCompleto"]
                        st.rerun()
    
    # ──────────────────────────────────────────────────────────
    # SECCIÓN 03: Ideal vs Real + Gráfico Costo Perdido
    # ──────────────────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">03</span>
  <div>
    <div class="sec-title">Lote Seleccionado: IDEAL vs REAL</div>
    <div class="sec-sub">Comparación con el ideal + Costo perdido acumulado</div>
  </div>
</div>
""")
    
    if "lote_sel_sec03" not in st.session_state:
        lotes_disp = SF_ABIERTOS["LoteCompleto"].unique().tolist()
        if lotes_disp:
            st.session_state["lote_sel_sec03"] = lotes_disp[0]
        else:
            st.warning("No hay lotes abiertos para analizar.")
            st.stop()
    
    lote_sel = st.session_state.get("lote_sel_sec03")
    lotes_disp = SF["LoteCompleto"].unique().tolist()
    
    if lote_sel not in lotes_disp:
        lote_sel = lotes_disp[0] if lotes_disp else None
        st.session_state["lote_sel_sec03"] = lote_sel
    
    if not lote_sel:
        st.stop()
    
    with st.expander("🔎 Cambiar lote", expanded=False):
        lote_pick = st.selectbox("Selecciona lote", lotes_disp, 
                                 index=lotes_disp.index(lote_sel) if lote_sel in lotes_disp else 0,
                                 key="lote_pick_sec03")
        if lote_pick != lote_sel:
            st.session_state["lote_sel_sec03"] = lote_pick
            st.rerun()
    
    lote_sel = st.session_state.get("lote_sel_sec03", lotes_disp[0] if lotes_disp else None)
    
    il = SF[SF["LoteCompleto"] == lote_sel].iloc[0]
    hist = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
    
    if hist.empty:
        st.warning("No hay historial para este lote.")
        st.stop()
    
    edad_act = float(il["Edad"])
    
    ideal_data = IDEALES[
        (IDEALES["Zona_Nombre"] == il["ZonaNombre"]) &
        (IDEALES["TipoGranja"] == il["TipoStd"]) &
        (IDEALES["Quintil"] == il["Quintil"])
    ].copy()
    
    if ideal_data.empty:
        st.error(f"❌ No hay ideal en el archivo para: {il['ZonaNombre']} · {il['TipoStd']} · {il['Quintil']}")
        st.info("No se puede proceder sin el ideal. Verifica que el archivo de benchmarks contenga este segmento.")
    else:
        h1,h2,h3,h4 = st.columns(4)
        with h1:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{il["GranjaID"]}</div><div class="kl">Granja</div></div>', unsafe_allow_html=True)
        with h2:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{il["ZonaNombre"]}</div><div class="kl">Zona</div></div>', unsafe_allow_html=True)
        with h3:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{il["TipoStd"]}</div><div class="kl">Tipo</div></div>', unsafe_allow_html=True)
        with h4:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{int(edad_act)} días</div><div class="kl">Edad</div></div>', unsafe_allow_html=True)
        
        # GRÁFICO 1: Peso Real vs Ideal (limitado a +3 días)
        fig = go.Figure()
        
        hist_valid = hist[hist["PesoFinal"].notna()].copy()
        fig.add_trace(go.Scatter(
            x=hist_valid["Edad"], 
            y=hist_valid["PesoFinal"],
            mode="lines+markers",
            name="REAL",
            line=dict(color=RED, width=3),
            marker=dict(size=6),
            hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
        ))
        
        # Ideal limitado a +3 días del real
        edad_max_real = float(hist_valid["Edad"].max())
        ideal_sorted = ideal_data.sort_values("Edad")
        ideal_sorted = ideal_sorted[ideal_sorted["Edad"] <= edad_max_real + 3]
        
        fig.add_trace(go.Scatter(
            x=ideal_sorted["Edad"], 
            y=ideal_sorted["Peso"],
            mode="lines+markers",
            name="IDEAL",
            line=dict(color=GREEN, width=3, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
            hovertemplate="Día %{x}<br>IDEAL: %{y:.3f} kg<extra></extra>",
        ))
        
        # GAP sombreado
        ideal_for_merge = ideal_sorted[["Edad", "Peso"]].rename(columns={"Peso": "PesoIdeal"})
        hist_merge = hist_valid.merge(ideal_for_merge, on="Edad", how="inner")
        if not hist_merge.empty:
            fig.add_trace(go.Scatter(
                x=hist_merge["Edad"].tolist() + hist_merge["Edad"].tolist()[::-1],
                y=hist_merge["PesoFinal"].tolist() + hist_merge["PesoIdeal"].tolist()[::-1],
                fill="toself",
                name="GAP",
                fillcolor="rgba(218,41,28,0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip",
            ))
        
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, 
            plot_bgcolor=CARD,
            height=300,
            margin=dict(l=8, r=8, t=18, b=8),
            font=dict(family="DM Sans", size=11, color=TEXT),
            legend=dict(orientation="h", y=-0.15, x=0, bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
            yaxis=dict(title="Peso (kg)", gridcolor=BORDER, color=TEXT),
            hovermode="x unified",
        )
        
        st.plotly_chart(fig, width='stretch')
        
        # GRÁFICO 2: Costo Perdido Acumulado (SIN TABLA)
        st.caption("**Costo perdido (Real vs Ideal) acumulado:**")
        
        hist_costo = hist[hist["Edad"] >= EDAD_MIN_ANALISIS].copy()
        ideal_for_cost = ideal_sorted[["Edad", "Peso"]].rename(columns={"Peso": "PesoIdeal"})
        hist_costo = hist_costo.merge(ideal_for_cost, on="Edad", how="left")
        
        hist_costo["KgRealAcum"] = (hist_costo["AvesVivas"] * hist_costo["PesoFinal"]).cumsum()
        hist_costo["KgIdealAcum"] = (hist_costo["AvesVivas"] * hist_costo["PesoIdeal"]).cumsum()
        
        hist_costo["CostoRealAcum"] = hist_costo["CostoAcum"]
        hist_costo["CostoIdealAcum"] = hist_costo["KgIdealAcum"] * hist_costo["CostoKg_Cum"]
        
        hist_costo["CostoPerdido"] = hist_costo["CostoRealAcum"] - hist_costo["CostoIdealAcum"]
        hist_costo["CostoPerdido"] = hist_costo["CostoPerdido"].clip(lower=0)
        
        hist_costo_clean = hist_costo[["Edad", "CostoPerdido"]].dropna()
        
        fig_costo = go.Figure()
        fig_costo.add_trace(go.Scatter(
            x=hist_costo_clean["Edad"],
            y=hist_costo_clean["CostoPerdido"],
            mode="lines+markers",
            name="Costo Perdido",
            line=dict(color=RED, width=3),
            marker=dict(size=7),
            fill="tozeroy",
            fillcolor="rgba(218,41,28,0.2)",
            hovertemplate="Día %{x}<br>Pérdida: $%{y:,.2f}<extra></extra>",
        ))
        
        fig_costo.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD,
            plot_bgcolor=CARD,
            height=280,
            margin=dict(l=8, r=8, t=18, b=8),
            font=dict(family="DM Sans", size=11, color=TEXT),
            showlegend=False,
            xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
            yaxis=dict(title="Costo Perdido ($)", gridcolor=BORDER, color=TEXT),
            hovermode="x unified",
        )
        
        st.plotly_chart(fig_costo, width='stretch')

# ──────────────────────────────────────────────────────────────
# MITAD DERECHA: VACÍA
# ──────────────────────────────────────────────────────────────
with right:
    md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:1300px;display:flex;align-items:center;justify-content:center;">
  <div style="text-align:center;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.7px;">
    Espacio reservado<br>para futuras visualizaciones
  </div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:0.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v11 · {hoy:%d/%m/%Y %H:%M}
</div>
""")