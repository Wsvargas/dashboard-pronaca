
"""
PRONACA | Dashboard Producción Avícola (Zootecnia + Costos de Alimento)
========================================================================
Ejecutar:  streamlit run dashboard_produccion_costos_v5.py

Requiere (en la MISMA carpeta):
- produccion_actual_final_con_costos_alimento_v3.xlsx   (recomendado)
  o cualquier .xlsx equivalente que incluya:
  CostoAlimentoAcum, CostoAlimentoPorAveAcum, CostoAlimentoDia, ...

Notas:
- Este dashboard solo construye la MITAD IZQUIERDA (3 secciones).
- La MITAD DERECHA queda en blanco (placeholder) como pediste.
"""

import os
import numpy as np
import pandas as pd
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

# Curva biológica base (S = mixto)
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
        sx = str(sexo).upper().strip()
        if sx == "M": return CURVA_M.get(e, np.nan)
        if sx == "H": return CURVA_H.get(e, np.nan)
        return CURVA_S.get(e, np.nan)
    except Exception:
        return np.nan

def get_etapa(edad):
    try:
        e = int(edad)
        if e <= 14: return "INICIO (1-14)"
        if e <= 28: return "CRECIMIENTO (15-28)"
        if e <= 35: return "PRE-ACABADO (29-35)"
        return "ACABADO (36+)"
    except Exception:
        return "INICIO (1-14)"

def tipo_granja(granja_id: str):
    # BUC1xxx / STO2xxx = PROPIA | BUC3xxx / STO5xxx = PAC
    try:
        return "PROPIA" if str(granja_id)[3] in ("1", "2") else "PAC"
    except Exception:
        return "PROPIA"

def zona_nombre(lote: str):
    z = str(lote)[:3].upper()
    if z == "BUC": return "BUCAY"           # 🔥 sin tilde, como pediste
    if z == "STO": return "SANTO DOMINGO"
    return "OTRA"

def fmt_num(x, dec=2, prefix="", suffix=""):
    try:
        if pd.isna(x): return "—"
        if dec == 0: return f"{prefix}{int(round(float(x))):,}{suffix}"
        return f"{prefix}{float(x):,.{dec}f}{suffix}"
    except Exception:
        return "—"

# ──────────────────────────────────────────────────────────────
#  CSS — Pronaca industrial (se mantiene similar, más compacta)
# ──────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Bebas+Neue&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important;
    font-family: 'DM Sans', sans-serif !important;
    color: {TEXT} !important;
}}
.block-container {{
    padding-top: 1.0rem !important;
    padding-bottom: 1.8rem !important;
    max-width: 100% !important;
}}
footer {{ visibility: hidden; }}
div[data-testid="stPlotlyChart"] {{
    background:{CARD}; border:1px solid {BORDER}; border-radius:12px; padding:4px;
}}
div[data-testid="stDataFrame"] {{
    background:{CARD}; border:1px solid {BORDER}; border-radius:10px; overflow:hidden;
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
/* Filter bar */
.filter-bar {{
    background: {CARD}; border: 1px solid {BORDER};
    border-radius: 12px; padding: 10px 14px; margin-bottom: 10px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}
/* KPI chips */
.kpi-row {{ display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
.kpi-chip {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 10px 14px; min-width: 150px; flex: 1;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
}}
.kpi-chip.accent {{ border-left: 4px solid {RED}; }}
.kv {{ font-size: 1.35rem; font-weight: 900; color: {TEXT}; line-height: 1; }}
.kl {{ font-size: 0.70rem; font-weight: 800; text-transform: uppercase;
       letter-spacing: 0.8px; color: {MUTED} !important; margin-top: 3px; }}
/* Section header */
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

/* Etapa inline table */
.etapa-tbl {{ width:100%; border-collapse:collapse; font-size:0.80rem;
              background:{CARD}; border:1px solid {BORDER}; border-radius:10px;
              overflow:hidden; }}
.etapa-tbl th {{
    background:#F8FAFC; color:{MUTED} !important; font-size:0.68rem;
    font-weight:900; text-transform:uppercase; letter-spacing:0.6px;
    padding:7px 9px; border-bottom:1px solid {BORDER}; text-align:right;
}}
.etapa-tbl th:first-child {{ text-align:left; }}
.etapa-tbl td {{ padding:7px 9px; border-bottom:1px solid {BORDER};
                 font-weight:600; text-align:right; color:{TEXT}; }}
.etapa-tbl td:first-child {{ text-align:left; font-weight:900; }}
.etapa-tbl tr:last-child td {{ border-bottom:none; font-weight:900;
    background:#F8FAFC; border-top:2px solid {BORDER}; }}

</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  DATA LOAD
# ──────────────────────────────────────────────────────────────
# Prioridad: el archivo "con costos"
DEFAULT_FILE = "produccion_actual_final_con_costos_alimento_v3.xlsx"
FALLBACKS = [
    "produccion_actual_final_con_costos_alimento.xlsx",
    "produccion_actual_final.xlsx",
]
ARCHIVO = DEFAULT_FILE if os.path.exists(DEFAULT_FILE) else next((f for f in FALLBACKS if os.path.exists(f)), None)

if not ARCHIVO:
    st.error("❌ No se encontró un archivo de producción en la carpeta.\n"
             "Coloca **produccion_actual_final_con_costos_alimento_v3.xlsx** junto al dashboard.")
    st.stop()

@st.cache_data(show_spinner=False)
def load_and_prepare(path: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()

    # Convert numéricas comunes
    num_cols = [
        "Edad", "PesoFinal", "Peso", "Aves Neto", "AvesVivas", "EdadVenta",
        "Kilos Neto", "MortalidadAcumulada", "UltimoReal7",
        # costos (las que vemos en tu archivo v3)
        "unit_cost_final", "CostoAlimentoDia", "CostoAlimentoAcum",
        "CostoAlimentoPorAveDia", "CostoAlimentoPorAveAcum",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Normalizar sexo
    if "Sexo" in df.columns:
        df["Sexo"] = (df["Sexo"].astype(str).str.upper().str.strip()
                      .replace({"NAN":"S","NONE":"S","":"S"})
                      .fillna("S"))
    else:
        df["Sexo"] = "S"

    # Campos derivados
    df["ZonaNombre"] = df["LoteCompleto"].apply(zona_nombre) if "LoteCompleto" in df.columns else "OTRA"
    df["GranjaID"]   = df["LoteCompleto"].astype(str).str[:7]
    df["TipoGranja"] = df["GranjaID"].apply(tipo_granja)
    return df

with st.spinner("Cargando datos…"):
    DF = load_and_prepare(ARCHIVO)

# ──────────────────────────────────────────────────────────────
#  SNAPSHOT ACTIVOS (último registro por lote)
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_activos_snap(_df: pd.DataFrame):
    act = _df[_df["Estatus"].astype(str).str.upper().eq("ACTIVO")].copy()

    # Promedio de PesoFinal de toda la flota activa por día (Edad)
    prom_flota = act.groupby("Edad")["PesoFinal"].mean().round(4).to_dict()

    # Snapshot: último registro por lote (por Edad)
    snap = act.sort_values("Edad").groupby("LoteCompleto").last().reset_index()

    snap["Etapa"]   = snap["Edad"].apply(get_etapa)
    snap["MortPct"] = (snap["MortalidadAcumulada"] /
                       snap["Aves Neto"].replace(0, np.nan) * 100).round(2)

    # Kg totales (live weight) y conversión vs flota en el día de pesaje
    snap["KgTotales"] = (snap["PesoFinal"] * snap["AvesVivas"]).round(1)

    # Merge para PesoFinal en el día de medición (UltimoReal7)
    dias_medicion = act[["LoteCompleto", "Edad", "PesoFinal"]].rename(columns={"Edad": "DiaMed", "PesoFinal": "PesoEnMed"})
    dias_medicion["DiaMed"] = pd.to_numeric(dias_medicion["DiaMed"], errors="coerce").round().astype("Int64")
    snap2 = snap.copy()
    snap2["DiaMed"] = pd.to_numeric(snap2["UltimoReal7"], errors="coerce").round().astype("Int64")

    merged = snap2.merge(
        dias_medicion,
        on=["LoteCompleto", "DiaMed"],
        how="left"
    )
    merged["PromFlota"] = merged["DiaMed"].map(prom_flota)
    merged["ConvPct"]   = ((merged["PesoEnMed"] / merged["PromFlota"].replace(0, np.nan) - 1) * 100).round(2)

    # Costos (si existen)
    if "CostoAlimentoAcum" in merged.columns:
        merged["CostoTotalAlim"] = merged["CostoAlimentoAcum"]
    else:
        merged["CostoTotalAlim"] = np.nan

    if "CostoAlimentoPorAveAcum" in merged.columns:
        merged["CostoAveAlim"] = merged["CostoAlimentoPorAveAcum"]
    else:
        # fallback: costo total / aves
        merged["CostoAveAlim"] = merged["CostoTotalAlim"] / merged["AvesVivas"].replace(0, np.nan)

    merged["CostoKgAlim"] = merged["CostoTotalAlim"] / merged["KgTotales"].replace(0, np.nan)

    return merged, prom_flota, act

with st.spinner("Procesando métricas…"):
    SNAP, PROM_FLOTA, DF_ACTIVOS = build_activos_snap(DF)

# ──────────────────────────────────────────────────────────────
#  HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
st.markdown(f"""
<div class="pronaca-header">
  <div style="font-size:2.2rem;line-height:1">🐔</div>
  <div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA</div>
    <div class="pronaca-header-sub">Panel operativo: zootecnia + costos de alimento (lotes activos)</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
#  LAYOUT: 2 MITADES (IZQ con 3 secciones / DER vacío)
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    # ──────────────────────────────────────────────────────────
    #  FILTROS (arriba)
    # ──────────────────────────────────────────────────────────
    with st.container():
        st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
        fc1, fc2, fc3 = st.columns([1.4, 1.4, 3.2])
        with fc1:
            sel_zona = st.multiselect(
                "📍 Zona",
                options=["BUCAY", "SANTO DOMINGO"],
                default=["BUCAY", "SANTO DOMINGO"],
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
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Aplicar filtros ───────────────────────────────────────
    SF = SNAP.copy()
    if sel_zona:
        SF = SF[SF["ZonaNombre"].isin(sel_zona)]
    if sel_tipo:
        SF = SF[SF["TipoGranja"].isin(sel_tipo)]

    DF_ACT_F = DF_ACTIVOS.copy()
    if sel_zona:
        DF_ACT_F = DF_ACT_F[DF_ACT_F["ZonaNombre"].isin(sel_zona)]
    if sel_tipo:
        DF_ACT_F = DF_ACT_F[DF_ACT_F["TipoGranja"].isin(sel_tipo)]

    # ──────────────────────────────────────────────────────────
    #  KPIs (SIEMPRE arriba y DINÁMICOS por filtros)
    # ──────────────────────────────────────────────────────────
    n_lotes = int(SF["LoteCompleto"].nunique()) if not SF.empty else 0
    n_aves  = int(SF["AvesVivas"].sum()) if not SF.empty else 0
    kg_tot  = float(SF["KgTotales"].sum()) if not SF.empty else 0.0
    mort_p  = float(SF["MortPct"].mean()) if not SF.empty else np.nan

    cost_tot = float(SF["CostoTotalAlim"].sum()) if ("CostoTotalAlim" in SF.columns and not SF.empty) else np.nan
    # $/kg: ponderado (total cost / total kg)
    cost_per_kg = (cost_tot / kg_tot) if (pd.notna(cost_tot) and kg_tot > 0) else np.nan

    # Lotes críticos: vs flota < -5%
    n_crit = int((SF["ConvPct"] < -5).sum()) if ("ConvPct" in SF.columns and not SF.empty) else 0

    k1,k2,k3,k4,k5,k6 = st.columns(6)
    kpi_data = [
        (k1, f"{n_lotes:,}", "Lotes activos", True, ""),
        (k2, f"{n_aves:,}", "Aves vivas", True, ""),
        (k3, fmt_num(kg_tot, 0, suffix=" kg"), "Kg totales", True, ""),
        (k4, fmt_num(mort_p, 2, suffix="%"), "Mortalidad prom.", False, f"color:{RED}!important;" if pd.notna(mort_p) and mort_p>=5 else ""),
        (k5, fmt_num(cost_tot, 0, prefix="$"), "Costo alimento (acum)", True, ""),
        (k6, fmt_num(cost_per_kg, 3, prefix="$", suffix="/kg"), "Costo $/kg (prom)", True, ""),
    ]
    for col, val, lab, accent, extra_style in kpi_data:
        with col:
            st.markdown(
                f'<div class="kpi-chip {"accent" if accent else ""}">'
                f'<div class="kv" style="{extra_style}">{val}</div>'
                f'<div class="kl">{lab}</div></div>',
                unsafe_allow_html=True,
            )

    if SF.empty:
        st.info("Sin datos para los filtros seleccionados.")
        st.stop()

    # ══════════════════════════════════════════════════════════
    #  SECCIÓN 01 — ETAPAS (gráfico pequeño + TABLA grande)
    # ══════════════════════════════════════════════════════════
    st.markdown("""
    <div class="sec-header">
      <span class="sec-num">01</span>
      <div>
        <div class="sec-title">Datos por Etapa de Crecimiento</div>
        <div class="sec-sub">Gráfico pequeño = aves vivas · Tabla = métricas + costo por etapa</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    etapa_agg = (SF.groupby("Etapa", as_index=False)
        .agg(
            Unidades    = ("AvesVivas",  "sum"),
            KgTotales   = ("KgTotales", "sum"),
            KgXUnidad   = ("PesoFinal", "mean"),
            MortPct     = ("MortPct",   "mean"),
            CostoTotal  = ("CostoTotalAlim", "sum"),
        )
    )
    etapa_agg["CostoKg"] = etapa_agg["CostoTotal"] / etapa_agg["KgTotales"].replace(0, np.nan)
    etapa_agg["_ord"] = etapa_agg["Etapa"].map({e:i for i,e in enumerate(ETAPA_ORDER)})
    etapa_agg = etapa_agg.sort_values("_ord").reset_index(drop=True)

    c_chart, c_table = st.columns([1.0, 1.8], gap="medium")

    with c_chart:
        # ── mini chart (pequeño) ──
        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=etapa_agg["Etapa"],
            y=etapa_agg["Unidades"],
            marker=dict(color=[ETAPA_COLORS.get(e, BLUE) for e in etapa_agg["Etapa"]], cornerradius=4),
            hovertemplate="<b>%{x}</b><br>Aves vivas: %{y:,}<extra></extra>",
            showlegend=False,
        ))
        fig1.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=150, margin=dict(l=6, r=6, t=10, b=10),
            font=dict(family="DM Sans", size=12, color=TEXT),
            xaxis=dict(title="", tickangle=-20, gridcolor=BORDER, color=TEXT),
            yaxis=dict(title="Aves", gridcolor=BORDER, color=TEXT),
        )
        st.plotly_chart(fig1, use_container_width=True)

    with c_table:
        # ── tabla principal (con costo por etapa) ──
        tbody = ""
        for _, r in etapa_agg.iterrows():
            dot = ETAPA_COLORS.get(r["Etapa"], BLUE)
            mc  = f"color:{RED};font-weight:900" if r["MortPct"]>=5 else \
                  (f"color:{AMBER};font-weight:800" if r["MortPct"]>=3 else
                   f"color:{GREEN};font-weight:700")
            tbody += f"""<tr>
              <td><span style="display:inline-block;width:9px;height:9px;
                  border-radius:2px;background:{dot};margin-right:6px;
                  vertical-align:middle"></span>
                  {r['Etapa']}</td>
              <td>{int(r['Unidades']):,}</td>
              <td>{r['KgTotales']:,.0f}</td>
              <td>{r['KgXUnidad']:.3f}</td>
              <td style="{mc}">{r['MortPct']:.2f}%</td>
              <td>{fmt_num(r['CostoTotal'], 0, prefix='$')}</td>
              <td>{fmt_num(r['CostoKg'], 3, prefix='$', suffix='/kg')}</td>
            </tr>"""

        # Totales
        tot_u = int(etapa_agg["Unidades"].sum())
        tot_k = float(etapa_agg["KgTotales"].sum())
        tot_c = float(etapa_agg["CostoTotal"].sum())
        avg_ku = float(etapa_agg["KgXUnidad"].mean())
        avg_m  = float(etapa_agg["MortPct"].mean())
        avg_ck = (tot_c / tot_k) if tot_k>0 else np.nan
        mc_t   = f"color:{RED}" if avg_m>=5 else (f"color:{AMBER}" if avg_m>=3 else f"color:{GREEN}")
        tbody += f"""<tr>
          <td>TOTAL</td>
          <td>{tot_u:,}</td>
          <td>{tot_k:,.0f}</td>
          <td>{avg_ku:.3f}</td>
          <td style="{mc_t};font-weight:900">{avg_m:.2f}%</td>
          <td>{fmt_num(tot_c, 0, prefix='$')}</td>
          <td>{fmt_num(avg_ck, 3, prefix='$', suffix='/kg')}</td>
        </tr>"""

        st.markdown(f"""
        <div style="overflow-x:auto">
        <table class="etapa-tbl">
          <thead><tr>
            <th style="text-align:left">Etapa</th>
            <th>Unidades</th><th>Kg totales</th><th>Kg/unid</th><th>Mort%</th>
            <th>Costo ($)</th><th>$/kg</th>
          </tr></thead>
          <tbody>{tbody}</tbody>
        </table></div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    #  SECCIÓN 02 — TOP 10 peores conversiones (compacto + selector)
    # ══════════════════════════════════════════════════════════
    st.markdown("""
    <div class="sec-header">
      <span class="sec-num">02</span>
      <div>
        <div class="sec-title">Top 10 Granjas con Peor Conversión</div>
        <div class="sec-sub">Conversión = % desviación del peso real vs promedio de flota en el mismo día de pesaje. Incluye costo acumulado.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    SF_CONV = SF[SF["ConvPct"].notna()].copy()
    if SF_CONV.empty:
        st.info("Sin datos de conversión (ConvPct) con los filtros actuales.")
    else:
        granja_top = (SF_CONV.groupby("GranjaID", as_index=False)
            .agg(
                Zona      = ("ZonaNombre",   "first"),
                Tipo      = ("TipoGranja",   "first"),
                Lotes     = ("LoteCompleto", "nunique"),
                AvesVivas = ("AvesVivas",    "sum"),
                KgTot     = ("KgTotales",    "sum"),
                MortPct   = ("MortPct",      "mean"),
                ConvPct   = ("ConvPct",      "mean"),
                CostoTot  = ("CostoTotalAlim","sum"),
            )
            .sort_values("ConvPct")
            .head(10)
            .reset_index(drop=True)
        )
        granja_top["CostoKg"] = granja_top["CostoTot"] / granja_top["KgTot"].replace(0, np.nan)

        # ── Chart tornado ──
        fig2 = go.Figure(go.Bar(
            y=granja_top["GranjaID"],
            x=granja_top["ConvPct"],
            orientation="h",
            marker=dict(color=[RED if v < -5 else (AMBER if v < 0 else MUTED) for v in granja_top["ConvPct"]],
                        cornerradius=4),
            text=[f"{v:+.1f}%" for v in granja_top["ConvPct"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>vs flota: %{x:+.2f}%<extra></extra>",
            showlegend=False
        ))
        fig2.add_vline(x=0, line_color=MUTED, line_width=1.5, line_dash="dash")
        fig2.update_layout(
            template="plotly_white",
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=260, margin=dict(l=6, r=60, t=10, b=10),
            font=dict(family="DM Sans", size=12, color=TEXT),
            xaxis=dict(title="Desviación % vs promedio de flota",
                       gridcolor=BORDER, zeroline=False, tickformat="+.1f", ticksuffix="%", color=TEXT),
            yaxis=dict(gridcolor=BORDER, zeroline=False, autorange="reversed", color=TEXT),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # ── Selector compacto ──
        st.markdown(f"<div style='font-size:0.78rem;color:{MUTED};font-weight:800;"
                    f"text-transform:uppercase;letter-spacing:0.6px;margin:6px 0 4px'>"
                    f"Selecciona una granja (Top 10) para ver lotes + costos</div>", unsafe_allow_html=True)

        granja_sel = st.selectbox(
            "Granja",
            granja_top["GranjaID"].tolist(),
            index=0,
            key="granja_sel",
        )
        g_row = granja_top[granja_top["GranjaID"] == granja_sel].iloc[0]

        # KPIs granja seleccionada
        g1,g2,g3,g4,g5,g6 = st.columns(6)
        with g1: st.markdown(f'<div class="kpi-chip"><div class="kv">{int(g_row["Lotes"])}</div><div class="kl">Lotes</div></div>', unsafe_allow_html=True)
        with g2: st.markdown(f'<div class="kpi-chip"><div class="kv">{int(g_row["AvesVivas"]):,}</div><div class="kl">Aves vivas</div></div>', unsafe_allow_html=True)
        with g3:
            cc = RED if g_row["ConvPct"] < -5 else (AMBER if g_row["ConvPct"] < 0 else GREEN)
            st.markdown(f'<div class="kpi-chip"><div class="kv" style="color:{cc}">{g_row["ConvPct"]:+.1f}%</div><div class="kl">vs flota</div></div>', unsafe_allow_html=True)
        with g4:
            mc = RED if g_row["MortPct"] >= 5 else (AMBER if g_row["MortPct"] >= 3 else GREEN)
            st.markdown(f'<div class="kpi-chip"><div class="kv" style="color:{mc}">{g_row["MortPct"]:.2f}%</div><div class="kl">Mort.</div></div>', unsafe_allow_html=True)
        with g5:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{fmt_num(g_row["CostoTot"],0,prefix="$")}</div><div class="kl">Costo acum</div></div>', unsafe_allow_html=True)
        with g6:
            st.markdown(f'<div class="kpi-chip"><div class="kv">{fmt_num(g_row["CostoKg"],3,prefix="$",suffix="/kg")}</div><div class="kl">Costo $/kg</div></div>', unsafe_allow_html=True)

        # Tabla de lotes (con costos)
        lotes_granja = SF[SF["GranjaID"] == granja_sel].copy().sort_values(["ConvPct","CostoKgAlim"], ascending=[True, False])
        lotes_granja["CostoKgAlim"] = lotes_granja["CostoTotalAlim"] / lotes_granja["KgTotales"].replace(0, np.nan)

        cols_show = ["LoteCompleto","Sexo","Edad","Etapa","PesoFinal","KgTotales",
                     "MortPct","ConvPct","AvesVivas","CostoTotalAlim","CostoAveAlim","CostoKgAlim"]
        cols_show = [c for c in cols_show if c in lotes_granja.columns]

        df_show = lotes_granja[cols_show].copy()
        df_show = df_show.rename(columns={
            "LoteCompleto":"Lote",
            "PesoFinal":"Kg/unid",
            "KgTotales":"Kg totales",
            "MortPct":"Mort %",
            "ConvPct":"vs flota %",
            "AvesVivas":"Aves vivas",
            "CostoTotalAlim":"Costo $ (acum)",
            "CostoAveAlim":"$/ave (acum)",
            "CostoKgAlim":"$/kg (acum)",
        })
        # Formatos
        for c in ["Kg/unid","$/ave (acum)","$/kg (acum)"]:
            if c in df_show.columns:
                df_show[c] = pd.to_numeric(df_show[c], errors="coerce").round(3)
        for c in ["Kg totales","Costo $ (acum)"]:
            if c in df_show.columns:
                df_show[c] = pd.to_numeric(df_show[c], errors="coerce").round(0)
        for c in ["Mort %","vs flota %"]:
            if c in df_show.columns:
                df_show[c] = pd.to_numeric(df_show[c], errors="coerce").round(2)

        st.dataframe(df_show, use_container_width=True, hide_index=True, height=220)

        # Botón: enviar lote crítico a la sección 03
        if not lotes_granja.empty:
            peor_lote = lotes_granja.sort_values("ConvPct").iloc[0]["LoteCompleto"]
            if st.button(f"📈 Ver curva del lote más crítico: {peor_lote}", key="btn_peor", type="primary"):
                st.session_state["lote_curva"] = peor_lote
                st.rerun()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════
    #  SECCIÓN 03 — CURVA por LOTE + COSTO (más valor)
    # ══════════════════════════════════════════════════════════
    st.markdown("""
    <div class="sec-header">
      <span class="sec-num">03</span>
      <div>
        <div class="sec-title">Curva de Crecimiento + Costos por Lote</div>
        <div class="sec-sub">Peso por edad vs curva biológica · Costo acumulado (total / ave / kg) hasta el día actual</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    lotes_disp = sorted(SF["LoteCompleto"].unique().tolist())
    default_lote = st.session_state.get("lote_curva", lotes_disp[0] if lotes_disp else None)
    if default_lote not in lotes_disp and lotes_disp:
        default_lote = lotes_disp[0]

    csel1, csel2 = st.columns([1.2, 1.8])
    with csel1:
        buscar_txt = st.text_input("🔍 Buscar lote", placeholder="Ej: BUC3018-2504-02-S", key="s3_buscar")
        lotes_f = [l for l in lotes_disp if buscar_txt.upper() in l.upper()] if buscar_txt else lotes_disp
        if not lotes_f:
            lotes_f = lotes_disp
        lote_sel = st.selectbox("Lote a analizar", lotes_f, index=lotes_f.index(default_lote) if default_lote in lotes_f else 0, key="s3_lote")
        st.session_state["lote_curva"] = lote_sel

    info = SF[SF["LoteCompleto"] == lote_sel]
    if info.empty:
        st.warning("No hay snapshot para el lote seleccionado.")
        st.stop()
    il = info.iloc[0]

    # KPIs de cabecera del lote (incluye costos con más sentido)
    # - Costo total alimento (USD)
    # - Costo/ave (USD/ave)
    # - Costo/kg (USD/kg)
    # - Costo alimento día (USD/día) si existe en DF (último valor del lote)
    lote_hist = DF_ACT_F[DF_ACT_F["LoteCompleto"] == lote_sel].sort_values("Edad")
    cost_dia = float(lote_hist["CostoAlimentoDia"].dropna().iloc[-1]) if ("CostoAlimentoDia" in lote_hist.columns and not lote_hist["CostoAlimentoDia"].dropna().empty) else np.nan

    h1,h2,h3,h4,h5,h6 = st.columns(6)
    with h1: st.markdown(f'<div class="kpi-chip"><div class="kv">{il["GranjaID"]}</div><div class="kl">Granja</div></div>', unsafe_allow_html=True)
    with h2: st.markdown(f'<div class="kpi-chip"><div class="kv">{int(il["Edad"])} días</div><div class="kl">Edad actual</div></div>', unsafe_allow_html=True)
    with h3:
        cc = RED if il.get("ConvPct", 0) < -5 else (AMBER if il.get("ConvPct", 0) < 0 else GREEN)
        st.markdown(f'<div class="kpi-chip"><div class="kv" style="color:{cc}">{fmt_num(il.get("ConvPct",np.nan),1,suffix="%")}</div><div class="kl">vs flota</div></div>', unsafe_allow_html=True)
    with h4: st.markdown(f'<div class="kpi-chip"><div class="kv">{fmt_num(il["CostoTotalAlim"],0,prefix="$")}</div><div class="kl">Costo total alim</div></div>', unsafe_allow_html=True)
    with h5: st.markdown(f'<div class="kpi-chip"><div class="kv">{fmt_num(il["CostoAveAlim"],3,prefix="$",suffix="/ave")}</div><div class="kl">Costo por ave</div></div>', unsafe_allow_html=True)
    with h6: st.markdown(f'<div class="kpi-chip"><div class="kv">{fmt_num(il["CostoKgAlim"],3,prefix="$",suffix="/kg")}</div><div class="kl">Costo por kg</div></div>', unsafe_allow_html=True)

    # ── Datos para curva ──
    sexo_lote = lote_hist["Sexo"].iloc[0] if not lote_hist.empty else "S"
    edades_l  = lote_hist["Edad"].astype(int).tolist()
    pesos_l   = lote_hist["PesoFinal"].tolist()
    bio_y     = [curva_bio(sexo_lote, e) for e in edades_l]

    # Mejor lote referencia (mejor ConvPct) con al menos 7 días
    lotes_cnt = DF_ACT_F.groupby("LoteCompleto")["Edad"].count()
    lotes_ok  = lotes_cnt[lotes_cnt >= 7].index
    snap_ref  = SF[SF["LoteCompleto"].isin(lotes_ok) & SF["ConvPct"].notna()]
    if not snap_ref.empty:
        snap_ref_sorted = snap_ref.sort_values("ConvPct", ascending=False)
        mejor_id = snap_ref_sorted.iloc[0]["LoteCompleto"]
        if mejor_id == lote_sel and len(snap_ref_sorted) > 1:
            mejor_id = snap_ref_sorted.iloc[1]["LoteCompleto"]
        mejor_data   = DF_ACT_F[DF_ACT_F["LoteCompleto"] == mejor_id].sort_values("Edad")
        mejor_conv_v = float(snap_ref[snap_ref["LoteCompleto"] == mejor_id]["ConvPct"].iloc[0])
    else:
        mejor_id, mejor_data, mejor_conv_v = None, pd.DataFrame(), 0.0

    # ── FIGURA: peso vs edad ──
    figA = go.Figure()

    # Banda biológica ±3%
    bio_hi = [v * 1.03 if pd.notna(v) else np.nan for v in bio_y]
    bio_lo = [v * 0.97 if pd.notna(v) else np.nan for v in bio_y]
    figA.add_trace(go.Scatter(
        x=edades_l + edades_l[::-1], y=bio_hi + bio_lo[::-1],
        fill="toself", fillcolor="rgba(29,78,216,0.06)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Rango bio ±3%", hoverinfo="skip",
    ))
    figA.add_trace(go.Scatter(
        x=edades_l, y=bio_y, mode="lines",
        name=f"Curva bio ({sexo_lote})",
        line=dict(color=BLUE, width=2, dash="dash"),
        hovertemplate="Día %{x}<br>Esperado: %{y:.3f} kg<extra></extra>",
    ))
    if mejor_id and not mejor_data.empty:
        figA.add_trace(go.Scatter(
            x=mejor_data["Edad"].tolist(),
            y=mejor_data["PesoFinal"].tolist(),
            mode="lines",
            name=f"Mejor ref: {mejor_id} ({mejor_conv_v:+.1f}%)",
            line=dict(color=GREEN, width=2.5),
            hovertemplate="Día %{x}<br>Ref: %{y:.3f} kg<extra></extra>",
        ))
    figA.add_trace(go.Scatter(
        x=edades_l, y=pesos_l,
        mode="lines+markers", name=lote_sel,
        line=dict(color=RED, width=3),
        marker=dict(size=6, color=RED, line=dict(color="white", width=1.5)),
        hovertemplate="Día %{x}<br>Peso real: %{y:.3f} kg<extra></extra>",
    ))

    figA.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=340, margin=dict(l=6, r=10, t=18, b=10),
        font=dict(family="DM Sans", size=12, color=TEXT),
        legend=dict(orientation="h", y=-0.22, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(title="Edad (días)", gridcolor=BORDER, zeroline=False, dtick=7, color=TEXT),
        yaxis=dict(title="Peso por ave (kg)", gridcolor=BORDER, zeroline=False, color=TEXT),
        hovermode="x unified",
    )
    st.plotly_chart(figA, use_container_width=True)

    # ── FIGURA: costo acumulado (por ave y por kg) ──
    # Usamos y2 para que se entienda la magnitud de $/ave vs $/kg.
    figC = go.Figure()
    if "CostoAlimentoPorAveAcum" in lote_hist.columns:
        figC.add_trace(go.Scatter(
            x=edades_l,
            y=lote_hist["CostoAlimentoPorAveAcum"].tolist(),
            mode="lines+markers",
            name="$/ave (acum)",
            line=dict(color=AMBER, width=2.5),
            marker=dict(size=5),
            hovertemplate="Día %{x}<br>$/ave acum: %{y:.3f}<extra></extra>",
        ))
    # $/kg acumulado: costo total / kg totales (si hay)
    if "CostoAlimentoAcum" in lote_hist.columns and "AvesVivas" in lote_hist.columns and "PesoFinal" in lote_hist.columns:
        kg_series = (lote_hist["AvesVivas"] * lote_hist["PesoFinal"]).replace(0, np.nan)
        costo_kg_series = lote_hist["CostoAlimentoAcum"] / kg_series
        figC.add_trace(go.Scatter(
            x=edades_l,
            y=costo_kg_series.tolist(),
            mode="lines",
            name="$/kg (acum)",
            yaxis="y2",
            line=dict(color=BLUE, width=2, dash="dot"),
            hovertemplate="Día %{x}<br>$/kg acum: %{y:.3f}<extra></extra>",
        ))

    figC.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=220, margin=dict(l=6, r=10, t=12, b=10),
        font=dict(family="DM Sans", size=12, color=TEXT),
        legend=dict(orientation="h", y=-0.28, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(title="Edad (días)", gridcolor=BORDER, zeroline=False, dtick=7, color=TEXT),
        yaxis=dict(title="$/ave acum", gridcolor=BORDER, zeroline=False, color=TEXT),
        yaxis2=dict(title="$/kg acum", overlaying="y", side="right", showgrid=False, zeroline=False, color=MUTED),
        hovermode="x unified",
    )
    st.plotly_chart(figC, use_container_width=True)

with right:
    # Mitad derecha en blanco, solo un placeholder visual leve
    st.markdown(
        f"""
        <div style="background:{BG};border:1px dashed {BORDER};border-radius:12px;
                    padding:16px;min-height:980px;">
          <div style="color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:0.7px;">
            Mitad derecha (pendiente)
          </div>
          <div style="color:{MUTED};font-size:0.85rem;margin-top:6px;">
            Espacio reservado para futuras visualizaciones. (Según tu pedido, aquí queda en blanco).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────
#  FOOTER
# ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='text-align:center;font-size:0.72rem;color:{MUTED};"
    f"border-top:1px solid {BORDER};padding-top:10px'>"
    f"PRONACA · Panel Operativo Avícola · Archivo: {ARCHIVO} · "
    f"Generado {hoy:%d/%m/%Y %H:%M}</div>",
    unsafe_allow_html=True,
)
