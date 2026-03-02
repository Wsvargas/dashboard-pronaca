"""
PRONACA | Dashboard Producción Avícola
======================================
Ejecutar:  streamlit run dashboard_produccion.py
Requiere:  produccion_actual_final.xlsx  (misma carpeta)
"""

import os, numpy as np, pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

# ──────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────
#  BRAND TOKENS
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

CURVA_S = {
    1:0.173, 2:0.192, 3:0.212, 4:0.233, 5:0.255, 6:0.278, 7:0.302,
    8:0.337, 9:0.374,10:0.412,11:0.453,12:0.496,13:0.541,14:0.590,
   15:0.657,16:0.727,17:0.800,18:0.878,19:0.958,20:1.042,21:1.129,
   22:1.219,23:1.312,24:1.407,25:1.505,26:1.605,27:1.707,28:1.811,
   29:1.917,30:2.025,31:2.134,32:2.244,33:2.354,34:2.467,35:2.580,
   36:2.692,37:2.806,38:2.920,39:3.033,40:3.147,41:3.259,42:3.373,
   43:3.486,44:3.597,
}
CURVA_M = {k: round(v*1.075, 3) for k, v in CURVA_S.items()}
CURVA_H = {k: round(v*0.955, 3) for k, v in CURVA_S.items()}

def curva_bio(sexo, edad):
    try:
        e = int(edad)
        sx = str(sexo).upper()
        if sx == "M": return CURVA_M.get(e, np.nan)
        if sx == "H": return CURVA_H.get(e, np.nan)
        return CURVA_S.get(e, np.nan)
    except:
        return np.nan

def get_etapa(edad):
    try:
        e = int(edad)
        if e <= 14: return "INICIO (1-14)"
        if e <= 28: return "CRECIMIENTO (15-28)"
        if e <= 35: return "PRE-ACABADO (29-35)"
        return "ACABADO (36+)"
    except:
        return "INICIO (1-14)"

def tipo_granja(gid):
    # BUC1xxx / STO2xxx = PROPIA | BUC3xxx / STO5xxx = PAC
    try:
        return "PROPIA" if str(gid)[3] in ("1", "2") else "PAC"
    except:
        return "PROPIA"

def zona_nombre(lote):
    z = str(lote)[:3].upper()
    if z == "BUC": return "BUCAYÁ"
    if z == "STO": return "SANTO DOMINGO"
    return "OTRA"

def fmt_num(x, dec=2, suffix=""):
    try:
        if pd.isna(x): return "—"
        if dec == 0: return f"{int(x):,}{suffix}"
        return f"{float(x):.{dec}f}{suffix}"
    except:
        return "—"

# ──────────────────────────────────────────────────────────────
#  CSS — Pronaca Industrial · tipografía DM Sans + Bebas
# ──────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Bebas+Neue&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important;
    font-family: 'DM Sans', sans-serif !important;
    color: {TEXT} !important;
}}
.stApp *, .stApp p, .stApp span, .stApp div:not([class*="plotly"]),
.stApp label {{ color: {TEXT} !important; font-family: 'DM Sans', sans-serif !important; }}
section[data-testid="stSidebar"] {{
    background: {CARD} !important; border-right: 1px solid {BORDER};
}}
footer {{ visibility: hidden; }}
code {{ background: transparent !important; color: {TEXT} !important; padding:0!important; }}
.block-container {{ padding-top: 1.2rem !important; padding-bottom: 2rem !important;
                    max-width: 100% !important; }}
/* ── Header ── */
.pronaca-header {{
    background: {BLACK};
    border-radius: 14px;
    padding: 16px 24px;
    margin-bottom: 10px;
    display: flex; align-items: center; gap: 18px;
}}
.pronaca-header-title {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2rem; color: #fff; letter-spacing: 1.5px; line-height: 1.1;
}}
.pronaca-header-sub {{ font-size: 0.82rem; color: rgba(255,255,255,0.55); margin-top: 2px; }}
.pronaca-header-pill {{
    margin-left: auto;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 999px; padding: 6px 16px;
    font-size: 0.85rem; color: rgba(255,255,255,0.75) !important; white-space: nowrap;
}}
/* ── Filter bar ── */
.filter-bar {{
    background: {CARD}; border: 1px solid {BORDER};
    border-radius: 12px; padding: 12px 18px; margin-bottom: 12px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.05);
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}}
.filter-label {{
    font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 1px; color: {MUTED} !important; padding-right: 6px;
    border-right: 2px solid {RED}; margin-right: 4px;
}}
/* ── Section header ── */
.sec-header {{
    display: flex; align-items: baseline; gap: 12px;
    padding: 8px 0 6px 0; margin-bottom: 4px;
    border-bottom: 2px solid {BORDER};
}}
.sec-num {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.2rem; color: {RED}; line-height: 1;
}}
.sec-title {{
    font-size: 1.05rem; font-weight: 800; color: {TEXT}; line-height: 1.2;
}}
.sec-sub {{ font-size: 0.78rem; color: {MUTED} !important; margin-top: 1px; }}
/* ── KPI chips ── */
.kpi-row {{ display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
.kpi-chip {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 10px 16px; min-width: 120px; flex: 1;
    box-shadow: 0 1px 5px rgba(0,0,0,0.05);
}}
.kpi-chip.accent {{ border-left: 4px solid {RED}; }}
.kv {{ font-size: 1.4rem; font-weight: 800; color: {TEXT}; line-height: 1; }}
.kl {{ font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
       letter-spacing: 0.8px; color: {MUTED} !important; margin-top: 3px; }}
/* ── Etapa inline table ── */
.etapa-tbl {{ width:100%; border-collapse:collapse; font-size:0.82rem;
              background:{CARD}; border:1px solid {BORDER}; border-radius:10px;
              overflow:hidden; }}
.etapa-tbl th {{
    background:#F8FAFC; color:{MUTED} !important; font-size:0.7rem;
    font-weight:800; text-transform:uppercase; letter-spacing:0.6px;
    padding:8px 10px; border-bottom:1px solid {BORDER}; text-align:right;
}}
.etapa-tbl th:first-child {{ text-align:left; }}
.etapa-tbl td {{ padding:8px 10px; border-bottom:1px solid {BORDER};
                 font-weight:600; text-align:right; color:{TEXT}; }}
.etapa-tbl td:first-child {{ text-align:left; font-weight:800; }}
.etapa-tbl tr:last-child td {{ border-bottom:none; font-weight:900;
    background:#F8FAFC; border-top:2px solid {BORDER}; }}
.etapa-tbl tr:hover td {{ background:#FAFBFD; }}
/* ── Granja expander label ── */
.granja-label {{
    display:flex; align-items:center; gap:10px;
    font-size:0.92rem; font-weight:700;
}}
.rank-badge {{
    background:{RED}; color:#fff !important; border-radius:6px;
    padding:2px 8px; font-size:0.72rem; font-weight:900;
    font-family:'Bebas Neue',sans-serif; letter-spacing:1px;
}}
.tag {{
    border-radius:999px; padding:2px 9px; font-size:0.72rem; font-weight:800;
    border: 1px solid;
}}
.tag-red   {{ color:{RED}!important;   border-color:rgba(218,41,28,0.3);  background:rgba(218,41,28,0.08); }}
.tag-green {{ color:{GREEN}!important; border-color:rgba(22,163,74,0.3);  background:rgba(22,163,74,0.08); }}
.tag-amber {{ color:{AMBER}!important; border-color:rgba(217,119,6,0.3);  background:rgba(217,119,6,0.08); }}
.tag-gray  {{ color:{MUTED}!important; border-color:{BORDER};             background:#F8FAFC; }}
/* Plotly container */
div[data-testid="stPlotlyChart"] {{
    background:{CARD}; border:1px solid {BORDER}; border-radius:12px; padding:4px;
}}
div[data-testid="stDataFrame"] {{
    background:{CARD}; border:1px solid {BORDER}; border-radius:10px; overflow:hidden;
}}
/* Streamlit multiselect pills */
[data-baseweb="select"] {{ background:{CARD} !important; }}
div[data-testid="stExpander"] {{
    background:{CARD}; border:1px solid {BORDER}; border-radius:12px;
    margin-bottom:6px; overflow:hidden;
}}
div[data-testid="stExpander"]:hover {{ border-color:{RED}; }}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  CARGA Y PREPARACIÓN
# ──────────────────────────────────────────────────────────────
ARCHIVO = "produccion_actual_final.xlsx"
if not os.path.exists(ARCHIVO):
    st.error(f"❌ No se encontró **{ARCHIVO}**. Colócalo en la misma carpeta.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_and_prepare(path: str):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()

    for c in ["Edad","Peso","PesoFinal","MortalidadAcumulada","Aves Neto",
              "AvesVivas","EdadVenta","Kilos Neto","PesoSalidaKg","UltimoReal7"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["Sexo"]       = df["Sexo"].astype(str).str.upper().str.strip().replace(
                         {"NAN":"S","NONE":"S","":"S"}).fillna("S")
    df["ZonaNombre"] = df["LoteCompleto"].apply(zona_nombre)
    df["GranjaID"]   = df["LoteCompleto"].str[:7]
    df["TipoGranja"] = df["GranjaID"].apply(tipo_granja)
    return df

with st.spinner("Cargando datos…"):
    DF = load_and_prepare(ARCHIVO)

# ──────────────────────────────────────────────────────────────
#  SNAPSHOT ACTIVOS
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_activos_snap(_df):
    act = _df[_df["Estatus"] == "ACTIVO"].copy()

    # Promedio de PesoFinal de TODA la flota activa por día → referencia de conversión
    prom_flota = act.groupby("Edad")["PesoFinal"].mean().round(4).to_dict()

    # Snapshot: último registro por lote
    snap = act.sort_values("Edad").groupby("LoteCompleto").last().reset_index()

    snap["Etapa"]     = snap["Edad"].apply(get_etapa)
    snap["MortPct"]   = (snap["MortalidadAcumulada"] /
                         snap["Aves Neto"].replace(0, np.nan) * 100).round(2)
    snap["KgTotales"] = (snap["PesoFinal"] * snap["AvesVivas"] / 1000).round(1)

    # Conversión = % desviación vs promedio de flota EN EL DÍA DE ÚLTIMA MEDICIÓN
    def conv_vs_flota(row):
        dia = row.get("UltimoReal7")
        if pd.isna(dia):
            return np.nan
        dia = int(dia)
        prom = prom_flota.get(dia, np.nan)
        if pd.isna(prom) or prom == 0:
            return np.nan
        # Buscar el PesoFinal del lote en ese día específico
        return np.nan  # se calcula abajo por merge

    # Merge para obtener PesoFinal en el día de medición
    dias_medicion = act[["LoteCompleto", "Edad", "PesoFinal"]].copy()
    dias_medicion = dias_medicion.rename(columns={"Edad": "DiaMed", "PesoFinal": "PesoEnMed"})

    snap2 = snap.copy()
    snap2["DiaMed"] = snap2["UltimoReal7"].where(snap2["UltimoReal7"].notna())
    snap2["DiaMed"] = snap2["DiaMed"].astype("Int64", errors="ignore")

    merged = snap2.merge(
        dias_medicion,
        left_on=["LoteCompleto", "DiaMed"],
        right_on=["LoteCompleto", "DiaMed"],
        how="left"
    )
    # Promedio de flota por día
    merged["PromFlota"] = merged["DiaMed"].map(prom_flota)
    merged["ConvPct"]   = ((merged["PesoEnMed"] / merged["PromFlota"].replace(0, np.nan) - 1) * 100).round(2)

    return merged, prom_flota

with st.spinner("Procesando métricas…"):
    SNAP, PROM_FLOTA = build_activos_snap(DF)

# ──────────────────────────────────────────────────────────────
#  HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
st.markdown(f"""
<div class="pronaca-header">
  <div style="font-size:2.4rem;line-height:1">🐔</div>
  <div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA</div>
    <div class="pronaca-header-sub">Panel operativo de seguimiento zootécnico · Lotes activos en campo</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  FILTROS SUPERIORES
# ──────────────────────────────────────────────────────────────
with st.container():
    fc1, fc2, fc3 = st.columns([1.4, 1.4, 3.2])
    with fc1:
        sel_zona = st.multiselect(
            "📍 Zona",
            options=["BUCAYÁ", "SANTO DOMINGO"],
            default=["BUCAYÁ", "SANTO DOMINGO"],
            key="fz",
        )
    with fc2:
        sel_tipo = st.multiselect(
            "🏠 Tipo de granja",
            options=["PROPIA", "PAC"],
            default=["PROPIA", "PAC"],
            key="ft",
        )
    with fc3:
        st.markdown(
            f"<div style='padding:10px 0 0 4px;font-size:0.78rem;color:{MUTED};'>"
            "<b>Clasificación automática:</b> &nbsp;"
            f"<span style='color:{TEXT}'>BUC1xxx / STO2xxx</span> = PROPIA &nbsp;·&nbsp; "
            f"<span style='color:{TEXT}'>BUC3xxx / STO5xxx</span> = PAC</div>",
            unsafe_allow_html=True,
        )

# ── Aplicar filtros ───────────────────────────────────────────
SF = SNAP.copy()
if sel_zona:
    SF = SF[SF["ZonaNombre"].isin(sel_zona)]
if sel_tipo:
    SF = SF[SF["TipoGranja"].isin(sel_tipo)]

# DF filtrado completo para series de lotes
DF_ACT_F = DF[(DF["Estatus"] == "ACTIVO") &
              (DF["ZonaNombre"].isin(sel_zona if sel_zona else ["BUCAYÁ","SANTO DOMINGO"])) &
              (DF["TipoGranja"].isin(sel_tipo if sel_tipo else ["PROPIA","PAC"]))].copy()

# ── KPIs globales ─────────────────────────────────────────────
n_lotes   = SF["LoteCompleto"].nunique()
n_aves    = int(SF["AvesVivas"].sum()) if not SF.empty else 0
kg_tot    = SF["KgTotales"].sum() if not SF.empty else 0
peso_prom = SF["PesoFinal"].mean() if not SF.empty else 0
mort_prom = SF["MortPct"].mean() if not SF.empty else 0
n_alerta  = int((SF["MortPct"] >= 5).sum()) if not SF.empty else 0

k1,k2,k3,k4,k5,k6 = st.columns(6)
for col, val, lab, is_acc in [
    (k1, f"{n_lotes:,}",         "Lotes activos",      True),
    (k2, f"{n_aves:,}",          "Aves vivas",         True),
    (k3, f"{kg_tot:,.0f} kg",    "Kg estimados",       True),
    (k4, f"{peso_prom:.3f} kg",  "Peso promedio",      False),
    (k5, f"{mort_prom:.2f}%",    "Mortalidad prom.",   False),
    (k6, str(n_alerta),          "Lotes ≥ 5% mort.",   True),
]:
    alert_color = f"color:{RED}!important;" if lab == "Lotes ≥ 5% mort." and n_alerta > 0 else ""
    with col:
        st.markdown(
            f'<div class="kpi-chip {"accent" if is_acc else ""}">'
            f'<div class="kv" style="{alert_color}">{val}</div>'
            f'<div class="kl">{lab}</div></div>',
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECCIÓN 1 — DATOS ZOOTÉCNICOS POR ETAPA
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Datos Zootécnicos por Etapa de Crecimiento</div>
    <div class="sec-sub">Barras = aves vivas por etapa · Tabla = métricas operativas</div>
  </div>
</div>
""", unsafe_allow_html=True)

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
else:
    # Agrupación por etapa
    etapa_agg = SF.groupby("Etapa", as_index=False).agg(
        Lotes       = ("LoteCompleto", "nunique"),
        Unidades    = ("AvesVivas",    "sum"),
        KgTotales   = ("KgTotales",   "sum"),
        KgXUnidad   = ("PesoFinal",   "mean"),
        MortPct     = ("MortPct",     "mean"),
    )
    etapa_agg["_ord"] = etapa_agg["Etapa"].map({e: i for i, e in enumerate(ETAPA_ORDER)})
    etapa_agg = etapa_agg.sort_values("_ord").reset_index(drop=True)

    col_chart, col_table = st.columns([2.4, 1.0])

    with col_chart:
        # ── GRÁFICO: barras horizontales dobles ──────────────
        fig1 = go.Figure()

        bar_colors = [ETAPA_COLORS.get(e, BLUE) for e in etapa_agg["Etapa"]]
        max_aves   = etapa_agg["Unidades"].max()

        # Barras de Aves Vivas
        fig1.add_trace(go.Bar(
            y       = etapa_agg["Etapa"],
            x       = etapa_agg["Unidades"],
            name    = "Aves vivas",
            orientation = "h",
            marker  = dict(color=bar_colors, cornerradius=5),
            text    = [f"  {int(v):,}" for v in etapa_agg["Unidades"]],
            textposition = "inside",
            insidetextanchor = "start",
            textfont = dict(color="white", size=13, family="DM Sans"),
            hovertemplate = "<b>%{y}</b><br>Aves vivas: %{x:,}<extra></extra>",
            showlegend = True,
        ))

        # Diamantes de Kg totales (eje X secundario)
        fig1.add_trace(go.Scatter(
            y       = etapa_agg["Etapa"],
            x       = etapa_agg["KgTotales"],
            name    = "Kg totales estimados",
            xaxis   = "x2",
            mode    = "markers",
            marker  = dict(symbol="diamond", size=16, color=BLACK,
                           line=dict(color="white", width=2)),
            hovertemplate = "<b>%{y}</b><br>Kg estimados: %{x:,.0f}<extra></extra>",
        ))

        fig1.update_layout(
            template      = "plotly_white",
            paper_bgcolor = CARD,
            plot_bgcolor  = CARD,
            height        = 260,
            margin        = dict(l=8, r=70, t=16, b=10),
            font          = dict(family="DM Sans", size=13, color=TEXT),
            showlegend    = True,
            legend        = dict(orientation="h", y=-0.22, x=0,
                                 bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
            xaxis  = dict(title="Aves vivas",
                          showgrid=True, gridcolor=BORDER, zeroline=False,
                          color=TEXT, range=[0, max_aves * 1.18]),
            xaxis2 = dict(overlaying="x", side="top",
                          title="Kg totales estimados",
                          showgrid=False, zeroline=False, color=MUTED),
            yaxis  = dict(showgrid=False, zeroline=False, color=TEXT,
                          categoryorder="array",
                          categoryarray=list(reversed(ETAPA_ORDER))),
            bargap = 0.4,
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col_table:
        # ── TABLA INLINE ──────────────────────────────────────
        tbody = ""
        for _, r in etapa_agg.iterrows():
            dot  = ETAPA_COLORS.get(r["Etapa"], BLUE)
            mc   = f"color:{RED};font-weight:900" if r["MortPct"]>=5 else \
                   (f"color:{AMBER};font-weight:800" if r["MortPct"]>=3 else
                    f"color:{GREEN};font-weight:700")
            tbody += f"""<tr>
              <td><span style="display:inline-block;width:9px;height:9px;
                  border-radius:2px;background:{dot};margin-right:5px;
                  vertical-align:middle"></span>
                  {r['Etapa'].split(' ')[0]}</td>
              <td>{int(r['Unidades']):,}</td>
              <td>{r['KgTotales']:,.0f}</td>
              <td>{r['KgXUnidad']:.3f}</td>
              <td style="{mc}">{r['MortPct']:.2f}%</td>
            </tr>"""

        # Fila de totales
        tot_u = int(etapa_agg["Unidades"].sum())
        tot_k = etapa_agg["KgTotales"].sum()
        avg_ku = etapa_agg["KgXUnidad"].mean()
        avg_m  = etapa_agg["MortPct"].mean()
        mc_t   = f"color:{RED}" if avg_m>=5 else (f"color:{AMBER}" if avg_m>=3 else f"color:{GREEN}")
        tbody += f"""<tr>
          <td>TOTAL</td>
          <td>{tot_u:,}</td>
          <td>{tot_k:,.0f}</td>
          <td>{avg_ku:.3f}</td>
          <td style="{mc_t};font-weight:900">{avg_m:.2f}%</td>
        </tr>"""

        st.markdown(f"""
        <div style="overflow-x:auto;margin-top:0px">
        <table class="etapa-tbl">
          <thead><tr>
            <th>Etapa</th><th>Unidades</th><th>Kg totales</th>
            <th>Kg/unid</th><th>Mort%</th>
          </tr></thead>
          <tbody>{tbody}</tbody>
        </table></div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECCIÓN 2 — TOP 10 PEORES CONVERSIONES POR GRANJA
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 10 Granjas con Peor Conversión</div>
    <div class="sec-sub">
      Conversión = % desviación del peso real vs promedio de flota en el mismo día de pesaje ·
      Haz clic en una granja para ver sus lotes
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# Granjas con datos de conversión (solo lotes con UltimoReal7)
SF_CONV = SF[SF["ConvPct"].notna()].copy()

if SF_CONV.empty:
    st.info("Sin datos de conversión disponibles con los filtros actuales.")
else:
    granja_top = (SF_CONV
        .groupby("GranjaID", as_index=False)
        .agg(
            Zona       = ("ZonaNombre",   "first"),
            Tipo       = ("TipoGranja",   "first"),
            Lotes      = ("LoteCompleto", "nunique"),
            AvesVivas  = ("AvesVivas",    "sum"),
            KgXUnidad  = ("PesoFinal",    "mean"),
            MortPct    = ("MortPct",      "mean"),
            ConvPct    = ("ConvPct",      "mean"),
        )
        .sort_values("ConvPct")
        .head(10)
        .reset_index(drop=True)
    )
    granja_top.index += 1   # ranking 1-based

    # ── GRÁFICO TORNADO ──────────────────────────────────────
    bar_c10 = [RED if v < -5 else (AMBER if v < 0 else MUTED)
               for v in granja_top["ConvPct"]]

    fig2 = go.Figure(go.Bar(
        y           = granja_top["GranjaID"],
        x           = granja_top["ConvPct"],
        orientation = "h",
        marker      = dict(color=bar_c10, cornerradius=4),
        text        = [f"{v:+.1f}%" for v in granja_top["ConvPct"]],
        textposition= "outside",
        textfont    = dict(size=12, color=TEXT, family="DM Sans"),
        hovertemplate = "<b>%{y}</b><br>vs flota: %{x:+.2f}%<extra></extra>",
    ))
    fig2.add_vline(x=0, line_color=MUTED, line_width=1.5, line_dash="dash")
    fig2.update_layout(
        template      = "plotly_white",
        paper_bgcolor = CARD,
        plot_bgcolor  = CARD,
        height        = 300,
        margin        = dict(l=8, r=80, t=14, b=10),
        font          = dict(family="DM Sans", size=12, color=TEXT),
        xaxis = dict(title="Desviación % vs promedio de flota",
                     gridcolor=BORDER, zeroline=False,
                     tickformat="+.1f", ticksuffix="%", color=TEXT),
        yaxis = dict(gridcolor=BORDER, zeroline=False,
                     autorange="reversed", color=TEXT),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── EXPANDERS POR GRANJA ─────────────────────────────────
    st.markdown(
        f"<div style='font-size:0.75rem;color:{MUTED};font-weight:700;"
        f"text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;'>"
        f"Expand una granja para ver sus lotes →</div>",
        unsafe_allow_html=True,
    )

    for rank, row in granja_top.iterrows():
        conv_col  = RED   if row["ConvPct"] < -5 else (AMBER if row["ConvPct"] < 0 else MUTED)
        mort_col  = RED   if row["MortPct"] >= 5  else (AMBER if row["MortPct"] >= 3 else GREEN)
        tipo_tag  = "tag-gray"
        conv_tag  = "tag-red" if row["ConvPct"] < 0 else "tag-green"
        mort_tag  = "tag-red" if row["MortPct"] >= 5 else ("tag-amber" if row["MortPct"] >= 3 else "tag-green")

        exp_label = (
            f"#{rank}  {row['GranjaID']}   "
            f"vs flota: {row['ConvPct']:+.1f}%   "
            f"Mort: {row['MortPct']:.2f}%   "
            f"{int(row['Lotes'])} lote{'s' if row['Lotes']>1 else ''}   "
            f"{row['Zona']}  ·  {row['Tipo']}"
        )

        with st.expander(exp_label, expanded=False):
            lotes_granja = SF[SF["GranjaID"] == row["GranjaID"]].copy()
            lotes_granja = lotes_granja.sort_values("ConvPct")

            # Mini KPIs de la granja
            ek1, ek2, ek3, ek4, ek5 = st.columns(5)
            for ec, val, lab, extra_style in [
                (ek1, f"{int(row['Lotes'])}",          "Lotes activos", ""),
                (ek2, f"{int(row['AvesVivas']):,}",    "Aves vivas",    ""),
                (ek3, f"{row['ConvPct']:+.1f}%",       "vs flota",      f"color:{conv_col}!important"),
                (ek4, f"{row['MortPct']:.2f}%",        "Mortalidad",    f"color:{mort_col}!important"),
                (ek5, f"{row['KgXUnidad']:.3f} kg",    "Kg/unidad prom",""),
            ]:
                with ec:
                    st.markdown(
                        f'<div class="kpi-chip">'
                        f'<div class="kv" style="{extra_style}">{val}</div>'
                        f'<div class="kl">{lab}</div></div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # Tabla de lotes de la granja
            cols_show = ["LoteCompleto","Sexo","Edad","Etapa","PesoFinal",
                         "KgTotales","MortPct","ConvPct","AvesVivas","TipoGranja"]
            cols_show = [c for c in cols_show if c in lotes_granja.columns]

            df_show = lotes_granja[cols_show].copy().round(3).rename(columns={
                "LoteCompleto":"Lote",
                "PesoFinal":   "Peso actual (kg)",
                "KgTotales":   "Kg totales",
                "MortPct":     "Mort %",
                "ConvPct":     "vs flota %",
                "AvesVivas":   "Aves vivas",
                "TipoGranja":  "Tipo",
            })

            def _c_conv(v):
                try:
                    f = float(v)
                    if f < -5:  return f"color:{RED};font-weight:900"
                    if f < 0:   return f"color:{AMBER};font-weight:800"
                    return f"color:{GREEN};font-weight:700"
                except: return ""

            def _c_mort(v):
                try:
                    f = float(v)
                    if f >= 5:  return f"color:{RED};font-weight:900"
                    if f >= 3:  return f"color:{AMBER};font-weight:800"
                    return f"color:{GREEN};font-weight:700"
                except: return ""

            style = df_show.style
            try:
                if "vs flota %" in df_show.columns:
                    style = style.map(_c_conv, subset=["vs flota %"])
                if "Mort %" in df_show.columns:
                    style = style.map(_c_mort, subset=["Mort %"])
            except AttributeError:
                if "vs flota %" in df_show.columns:
                    style = style.applymap(_c_conv, subset=["vs flota %"])
                if "Mort %" in df_show.columns:
                    style = style.applymap(_c_mort, subset=["Mort %"])

            st.dataframe(style, use_container_width=True, hide_index=True)

            # Botón para ver curva
            if not lotes_granja.empty:
                peor = lotes_granja.sort_values("ConvPct").iloc[0]["LoteCompleto"]
                if st.button(
                    f"📈 Ver curva del lote más crítico: {peor}",
                    key=f"btn_{row['GranjaID']}_{rank}",
                    type="primary",
                ):
                    st.session_state["lote_curva"] = peor
                    st.rerun()

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECCIÓN 3 — CURVA DE CRECIMIENTO
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="sec-header">
  <span class="sec-num">03</span>
  <div>
    <div class="sec-title">Curva de Crecimiento por Lote</div>
    <div class="sec-sub">
      Peso acumulado por edad · Curva biológica esperada (por sexo) ·
      Comparación con el mejor lote activo de referencia
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Selector de lote ─────────────────────────────────────────
lotes_disp = sorted(SF["LoteCompleto"].unique().tolist())
default_lote = st.session_state.get("lote_curva",
               lotes_disp[0] if lotes_disp else None)
if default_lote not in lotes_disp and lotes_disp:
    default_lote = lotes_disp[0]

s3l, s3r = st.columns([1.6, 2.4])
with s3l:
    buscar_txt = st.text_input("🔍 Buscar lote", placeholder="Ej: BUC3018, STO5014…",
                                key="s3_buscar")
    lotes_f = ([l for l in lotes_disp if buscar_txt.upper() in l.upper()]
               if buscar_txt else lotes_disp)
    if not lotes_f:
        lotes_f = lotes_disp

    lote_sel = st.selectbox(
        "Lote a analizar",
        lotes_f,
        index = lotes_f.index(default_lote) if default_lote in lotes_f else 0,
        key   = "s3_lote",
    )
    st.session_state["lote_curva"] = lote_sel

with s3r:
    info = SF[SF["LoteCompleto"] == lote_sel]
    if not info.empty:
        il = info.iloc[0]
        cc = RED if il.get("ConvPct", 0) < -3 else (AMBER if il.get("ConvPct", 0) < 0 else GREEN)
        mc = RED if il["MortPct"] >= 5 else (AMBER if il["MortPct"] >= 3 else GREEN)
        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;
             padding:12px 18px;display:flex;flex-wrap:wrap;gap:20px;margin-top:4px">
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Granja</div>
               <div style="font-weight:900;font-size:1.05rem">{il['GranjaID']}</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Sexo</div>
               <div style="font-weight:900;font-size:1.05rem">{il['Sexo']}</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Edad actual</div>
               <div style="font-weight:900;font-size:1.05rem">{int(il['Edad'])} días</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Etapa</div>
               <div style="font-weight:800;font-size:0.9rem">{il['Etapa']}</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">vs flota</div>
               <div style="font-weight:900;font-size:1.05rem;color:{cc}">
               {fmt_num(il.get('ConvPct', np.nan), 1, '%')}</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Mortalidad</div>
               <div style="font-weight:900;font-size:1.05rem;color:{mc}">
               {fmt_num(il['MortPct'], 2, '%')}</div></div>
          <div><div style="font-size:.7rem;font-weight:800;text-transform:uppercase;
               color:{MUTED}">Aves vivas</div>
               <div style="font-weight:900;font-size:1.05rem">{int(il['AvesVivas']):,}</div></div>
        </div>
        """, unsafe_allow_html=True)

# ── Datos para graficar ──────────────────────────────────────
lote_data = DF_ACT_F[DF_ACT_F["LoteCompleto"] == lote_sel].sort_values("Edad")
sexo_lote = lote_data["Sexo"].iloc[0] if not lote_data.empty else "S"
edades_l  = lote_data["Edad"].astype(int).tolist()
pesos_l   = lote_data["PesoFinal"].tolist()

# Curva biológica esperada para ese sexo
bio_y = [curva_bio(sexo_lote, e) for e in edades_l]

# Mejor lote de referencia (mayor ConvPct entre activos con al menos 7 días de datos)
lotes_cnt = DF_ACT_F.groupby("LoteCompleto")["Edad"].count()
lotes_ok  = lotes_cnt[lotes_cnt >= 7].index
snap_ref  = SF[SF["LoteCompleto"].isin(lotes_ok) & SF["ConvPct"].notna()]

if not snap_ref.empty:
    snap_ref_sorted = snap_ref.sort_values("ConvPct", ascending=False)
    mejor_id = snap_ref_sorted.iloc[0]["LoteCompleto"]
    if mejor_id == lote_sel and len(snap_ref_sorted) > 1:
        mejor_id = snap_ref_sorted.iloc[1]["LoteCompleto"]
    mejor_data   = DF_ACT_F[DF_ACT_F["LoteCompleto"] == mejor_id].sort_values("Edad")
    mejor_conv_v = snap_ref[snap_ref["LoteCompleto"] == mejor_id]["ConvPct"].values
    mejor_conv_v = mejor_conv_v[0] if len(mejor_conv_v) else 0
    mejor_sexo   = mejor_data["Sexo"].iloc[0] if not mejor_data.empty else "S"
else:
    mejor_id, mejor_data, mejor_conv_v, mejor_sexo = None, pd.DataFrame(), 0, "S"

# ── FIGURA A: curva de peso acumulado ────────────────────────
figA = go.Figure()

# Banda biológica ±3%
bio_hi = [v * 1.03 if pd.notna(v) else np.nan for v in bio_y]
bio_lo = [v * 0.97 if pd.notna(v) else np.nan for v in bio_y]
figA.add_trace(go.Scatter(
    x=edades_l + edades_l[::-1], y=bio_hi + bio_lo[::-1],
    fill="toself", fillcolor="rgba(29,78,216,0.06)",
    line=dict(color="rgba(0,0,0,0)"),
    name="Rango biológico ±3%", hoverinfo="skip",
))

# Curva biológica
figA.add_trace(go.Scatter(
    x=edades_l, y=bio_y,
    mode="lines", name=f"Curva biológica ({sexo_lote})",
    line=dict(color=BLUE, width=2, dash="dash"),
    hovertemplate="Día %{x}<br>Esperado: %{y:.3f} kg<extra></extra>",
))

# Mejor lote
if mejor_id and not mejor_data.empty:
    figA.add_trace(go.Scatter(
        x=mejor_data["Edad"].tolist(),
        y=mejor_data["PesoFinal"].tolist(),
        mode="lines",
        name=f"Mejor ref.: {mejor_id} ({mejor_conv_v:+.1f}%)",
        line=dict(color=GREEN, width=2.5),
        hovertemplate="Día %{x}<br>Mejor lote: %{y:.3f} kg<extra></extra>",
    ))

# Lote seleccionado
figA.add_trace(go.Scatter(
    x=edades_l, y=pesos_l,
    mode="lines+markers",
    name=lote_sel,
    line=dict(color=RED, width=3),
    marker=dict(size=6, color=RED, line=dict(color="white", width=1.5)),
    hovertemplate="Día %{x}<br>Peso real: %{y:.3f} kg<extra></extra>",
))

# Anotación final
if edades_l and pesos_l:
    p_final = pesos_l[-1]
    b_final = bio_y[-1]
    if pd.notna(p_final) and pd.notna(b_final) and b_final > 0:
        pct = (p_final / b_final - 1) * 100
        ac  = RED if pct < -3 else (AMBER if pct < 0 else GREEN)
        figA.add_annotation(
            x=edades_l[-1], y=p_final,
            text=f"  {pct:+.1f}% vs bio",
            showarrow=False, xanchor="left",
            font=dict(size=12, color=ac, family="DM Sans"),
        )

figA.update_layout(
    template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
    height=390, margin=dict(l=6, r=10, t=20, b=10),
    font=dict(family="DM Sans", size=13, color=TEXT),
    legend=dict(orientation="h", y=-0.18, x=0,
                bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    xaxis=dict(title="Edad (días)", gridcolor=BORDER,
               zeroline=False, dtick=7, color=TEXT),
    yaxis=dict(title="Peso por ave (kg)", gridcolor=BORDER,
               zeroline=False, color=TEXT),
    hovermode="x unified",
)

# ── FIGURA B: ganancia diaria ─────────────────────────────────
figB = go.Figure()

if len(pesos_l) > 1 and len(edades_l) > 1:
    deltas_l  = [0.0] + [(pesos_l[i] - pesos_l[i-1]) * 1000
                          for i in range(1, len(pesos_l))]
    deltas_bio = [0.0] + [(bio_y[i] - bio_y[i-1]) * 1000
                           if pd.notna(bio_y[i]) and pd.notna(bio_y[i-1]) else np.nan
                           for i in range(1, len(bio_y))]

    bar_clrs = []
    for d, db in zip(deltas_l, deltas_bio):
        if pd.isna(db) or db == 0:
            bar_clrs.append(BLUE)
        elif d < db * 0.90:
            bar_clrs.append(RED)
        elif d < db:
            bar_clrs.append(AMBER)
        else:
            bar_clrs.append(GREEN)

    figB.add_trace(go.Bar(
        x=edades_l, y=deltas_l,
        name="Ganancia/día (g)",
        marker=dict(color=bar_clrs, cornerradius=3),
        hovertemplate="Día %{x}<br>Ganancia: %{y:.0f} g<extra></extra>",
    ))
    figB.add_trace(go.Scatter(
        x=edades_l, y=deltas_bio,
        mode="lines",
        name="Ganancia esperada",
        line=dict(color=BLUE, width=2, dash="dot"),
        hovertemplate="Día %{x}<br>Esperado: %{y:.0f} g<extra></extra>",
    ))

    # Ganancia del mejor lote
    if mejor_id and not mejor_data.empty and len(mejor_data) > 1:
        m_pes = mejor_data["PesoFinal"].tolist()
        m_eda = mejor_data["Edad"].tolist()
        m_del = [0.0] + [(m_pes[i]-m_pes[i-1])*1000 for i in range(1,len(m_pes))]
        figB.add_trace(go.Scatter(
            x=m_eda, y=m_del,
            mode="lines",
            name=f"Ganancia mejor ({mejor_id})",
            line=dict(color=GREEN, width=1.8, dash="dot"),
            hovertemplate="Día %{x}<br>Mejor lote: %{y:.0f} g<extra></extra>",
        ))

figB.update_layout(
    template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
    height=240, margin=dict(l=6, r=10, t=16, b=10),
    font=dict(family="DM Sans", size=12, color=TEXT),
    legend=dict(orientation="h", y=-0.26, x=0,
                bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    xaxis=dict(title="Edad (días)", gridcolor=BORDER,
               zeroline=False, dtick=7, color=TEXT),
    yaxis=dict(title="Ganancia (g/día)", gridcolor=BORDER,
               zeroline=False, color=TEXT),
    barmode="overlay", bargap=0.25,
)

# ── Layout gráficos ───────────────────────────────────────────
gc1, gc2 = st.columns([2.2, 1.0])
with gc1:
    st.markdown(f"<div style='font-size:0.8rem;font-weight:700;color:{MUTED};"
                f"margin-bottom:4px'>Peso acumulado por edad (kg/ave)</div>",
                unsafe_allow_html=True)
    st.plotly_chart(figA, use_container_width=True)

    st.markdown(f"<div style='font-size:0.8rem;font-weight:700;color:{MUTED};"
                f"margin-bottom:4px'>Ganancia diaria (g/día)</div>",
                unsafe_allow_html=True)
    st.plotly_chart(figB, use_container_width=True)

with gc2:
    # Tabla de hitos
    st.markdown(f"<div style='font-size:0.8rem;font-weight:700;color:{MUTED};"
                f"margin-bottom:6px'>Hitos vs curva biológica</div>",
                unsafe_allow_html=True)

    hitos = [7, 14, 21, 28, 35]
    if edades_l:
        last = edades_l[-1]
        if last not in hitos: hitos.append(last)

    h_rows = []
    for h in hitos:
        reg = lote_data[lote_data["Edad"] == h]
        if reg.empty: continue
        p_r = float(reg["PesoFinal"].iloc[0])
        p_b = curva_bio(sexo_lote, h)
        if pd.notna(p_b) and p_b > 0:
            d_kg  = round(p_r - p_b, 3)
            d_pct = round((p_r/p_b - 1)*100, 1)
        else:
            d_kg  = np.nan
            d_pct = np.nan
        # Mejor lote en ese día
        m_reg = mejor_data[mejor_data["Edad"] == h] if not mejor_data.empty else pd.DataFrame()
        m_p   = float(m_reg["PesoFinal"].iloc[0]) if not m_reg.empty else np.nan

        h_rows.append({
            "Día":         h,
            "Lote (kg)":   round(p_r, 3),
            "Bio (kg)":    round(p_b, 3) if pd.notna(p_b) else "—",
            "Mejor (kg)":  round(m_p, 3) if pd.notna(m_p) else "—",
            "Diff (kg)":   d_kg,
            "Diff %":      d_pct,
        })

    if h_rows:
        df_hitos = pd.DataFrame(h_rows)
        try:
            stl = (df_hitos.style
                   .map(lambda v: f"color:{RED};font-weight:900"
                        if isinstance(v, (int,float)) and v < -0.05
                        else (f"color:{GREEN};font-weight:800"
                              if isinstance(v,(int,float)) and v > 0.05 else ""),
                        subset=["Diff (kg)","Diff %"])
                   )
        except AttributeError:
            stl = (df_hitos.style
                   .applymap(lambda v: f"color:{RED};font-weight:900"
                        if isinstance(v,(int,float)) and v < -0.05
                        else (f"color:{GREEN};font-weight:800"
                              if isinstance(v,(int,float)) and v > 0.05 else ""),
                        subset=["Diff (kg)","Diff %"])
                   )
        st.dataframe(stl, use_container_width=True, hide_index=True, height=280)

    # Mini info del mejor lote
    if mejor_id and not mejor_data.empty:
        m_info = SF[SF["LoteCompleto"]==mejor_id]
        m_cv   = m_info["ConvPct"].values[0] if not m_info.empty else 0
        m_mort = m_info["MortPct"].values[0] if not m_info.empty else 0
        m_peso = m_info["PesoFinal"].values[0] if not m_info.empty else 0
        m_edad = m_info["Edad"].values[0]     if not m_info.empty else 0

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:10px;
             padding:12px 14px;">
          <div style="font-size:0.7rem;font-weight:800;text-transform:uppercase;
               color:{GREEN};letter-spacing:0.7px;margin-bottom:6px">
               ✅ Mejor lote de referencia</div>
          <div style="font-weight:900;font-size:1rem;color:{TEXT}">{mejor_id}</div>
          <div style="display:flex;gap:16px;margin-top:6px;flex-wrap:wrap">
            <div><span style="font-size:0.7rem;color:{MUTED}">vs flota</span>
                 <div style="font-weight:900;color:{GREEN}">{m_cv:+.1f}%</div></div>
            <div><span style="font-size:0.7rem;color:{MUTED}">Mortalidad</span>
                 <div style="font-weight:800">{m_mort:.2f}%</div></div>
            <div><span style="font-size:0.7rem;color:{MUTED}">Peso actual</span>
                 <div style="font-weight:800">{m_peso:.3f} kg</div></div>
            <div><span style="font-size:0.7rem;color:{MUTED}">Edad</span>
                 <div style="font-weight:800">{int(m_edad)} días</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  FOOTER
# ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='text-align:center;font-size:0.72rem;color:{MUTED};"
    f"border-top:1px solid {BORDER};padding-top:12px'>"
    f"PRONACA · Panel Operativo Avícola · "
    f"{n_lotes} lotes activos · {n_aves:,} aves en campo · "
    f"Generado {hoy:%d/%m/%Y %H:%M}</div>",
    unsafe_allow_html=True,
)