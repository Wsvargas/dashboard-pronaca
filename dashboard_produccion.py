"""
PRONACA | Dashboard Producción Avícola v13
==========================================
Fixes v13:
  1. Top 5 Granjas: DF_ABIERTOS ahora respeta los filtros superiores
     (Zona / Tipo / Quintil / Estado) → no desaparece al quitar PAC/PROPIA.
  2. Predicción en cascada: usa SIEMPRE el lote seleccionado en Sec 03
     con TODO su historial real disponible (no solo hasta día 14).
  3. model_predictor.py: interfaz proyectar_curva() que mapea columnas
     del dashboard → modelo y proyecta hasta día 40.

Ejecutar:
    streamlit run dashboard_produccion_v13.py
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

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola v13",
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

def get_etapa(edad):
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
        if x is None or pd.isna(x): return "—"
        v = float(x)
        if dec == 0: return f"{prefix}{int(round(v)):,}{suffix}"
        return f"{prefix}{v:,.{dec}f}{suffix}"
    except Exception:
        return "—"

def parse_num_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s): return s
    ss = s.astype(str).str.strip()
    ss = ss.str.replace("\u00A0", "", regex=False).str.replace(" ", "", regex=False)
    ss = ss.str.replace(r"[^0-9,\.\-]", "", regex=True)
    has_dot   = ss.str.contains(r"\.", regex=True)
    has_comma = ss.str.contains(",", regex=False)
    mask = has_dot & has_comma
    ss.loc[mask]  = ss.loc[mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    ss.loc[~mask] = ss.loc[~mask].str.replace(",", ".", regex=False)
    return pd.to_numeric(ss, errors="coerce")

def pick_first_col(df, candidates):
    for c in candidates:
        if c in df.columns: return c
    return None

def extract_lote_codigo(lote_completo: str) -> str:
    parts = str(lote_completo).split("-")
    if len(parts) >= 3: return f"{parts[1]}-{parts[2]}"
    return str(lote_completo)

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
md(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Bebas+Neue&display=swap');
html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important; font-family: 'DM Sans', sans-serif !important; color: {TEXT} !important;
}}
.block-container {{ padding-top:.9rem!important; padding-bottom:1.2rem!important; max-width:100%!important; }}
footer {{ visibility:hidden; }}
.card {{ background:{CARD}; border:1px solid {BORDER}; border-radius:14px; padding:12px 14px;
         box-shadow:0 1px 6px rgba(0,0,0,.04); }}
.pronaca-header {{ background:{BLACK}; border-radius:14px; padding:14px 20px; margin-bottom:10px;
                   display:flex; align-items:center; gap:14px; }}
.pronaca-header-title {{ font-family:'Bebas Neue',sans-serif; font-size:2rem; color:#fff;
                         letter-spacing:1.4px; line-height:1.1; }}
.pronaca-header-sub {{ font-size:.82rem; color:rgba(255,255,255,.55); margin-top:2px; }}
.pronaca-header-pill {{ margin-left:auto; background:rgba(255,255,255,.08);
                        border:1px solid rgba(255,255,255,.15); border-radius:999px;
                        padding:6px 14px; font-size:.85rem; color:rgba(255,255,255,.75)!important; }}
.filter-bar {{ background:{CARD}; border:1px solid {BORDER}; border-radius:12px;
               padding:10px 14px; margin-bottom:10px; box-shadow:0 1px 6px rgba(0,0,0,.04); }}
.kpi-chip {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px;
             padding:10px 14px; flex:1; box-shadow:0 1px 5px rgba(0,0,0,.04); }}
.kpi-chip.accent {{ border-left:4px solid {RED}; }}
.kv {{ font-size:1.35rem; font-weight:900; color:{TEXT}; line-height:1; }}
.kl {{ font-size:.70rem; font-weight:800; text-transform:uppercase; letter-spacing:.8px;
       color:{MUTED}!important; margin-top:3px; }}
.sec-header {{ display:flex; align-items:baseline; gap:12px; padding:8px 0 6px;
               margin:4px 0 6px; border-bottom:2px solid {BORDER}; }}
.sec-num {{ font-family:'Bebas Neue',sans-serif; font-size:2rem; color:{RED}; line-height:1; }}
.sec-title {{ font-size:1rem; font-weight:900; color:{TEXT}; line-height:1.2; }}
.sec-sub {{ font-size:.78rem; color:{MUTED}!important; margin-top:1px; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:.72rem;
          font-weight:900; border:1px solid {BORDER}; background:#F8FAFC; }}
.badge.red   {{ color:{RED};   border-color:rgba(218,41,28,.25); background:rgba(218,41,28,.06); }}
.badge.amber {{ color:{AMBER}; border-color:rgba(217,119,6,.25);  background:rgba(217,119,6,.07); }}
.badge.green {{ color:{GREEN}; border-color:rgba(22,163,74,.25);  background:rgba(22,163,74,.07); }}
.sel-pill {{ display:inline-flex; align-items:center; gap:6px; background:rgba(218,41,28,.08);
             border:1px solid rgba(218,41,28,.25); border-radius:999px; padding:3px 10px;
             font-size:.72rem; font-weight:800; color:{RED}; margin-bottom:6px; }}
.sel-pill-neutral {{ display:inline-flex; align-items:center; gap:6px;
                     background:rgba(29,78,216,.08); border:1px solid rgba(29,78,216,.20);
                     border-radius:999px; padding:3px 10px; font-size:.72rem; font-weight:800;
                     color:{BLUE}; margin-bottom:6px; }}
.hint-text {{ font-size:.72rem; color:{MUTED}; font-style:italic; margin-bottom:4px; }}
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

    col_lote  = pick_first_col(df, ["LoteCompleto","Codigo_Unico","Lote"])
    if not col_lote: raise ValueError("No encuentro columna de lote.")

    col_edad  = pick_first_col(df, ["Edad","edad","X4=Edad"])
    col_peso  = pick_first_col(df, ["PesoFinal","Peso","Y=Peso comp","Peso comp"])
    col_aves  = pick_first_col(df, ["AvesVivas","Aves Vivas","Aves_netas","Aves Neto","Aves Neto "])
    col_cost  = pick_first_col(df, ["CostoAlimentoAcum","Costo alim acum","CostoAlimentoAcumulado","CostoAlimento_acumulado"])
    col_alimkg= pick_first_col(df, ["Alimento_acumulado_kg","Alimento acum","Alimento_acum","AlimAcumKg"])
    col_zona  = pick_first_col(df, ["zona","Zona"])
    col_tipo  = pick_first_col(df, ["TipoGranja","Tipo_Granja","Tipo de granja","X30=Granja Propia"])
    col_quint = pick_first_col(df, ["quintil","Quintil_Area_Crianza","Quintil"])
    col_est   = pick_first_col(df, ["Estatus","ESTATUS","Status"])
    col_estado = pick_first_col(df, ["EstadoLote","Estado_Lote","estado_lote","ESTADO LOTE"])

    df = df.rename(columns={
        col_lote: "LoteCompleto", col_edad: "Edad",
        col_peso: "PesoFinal",    col_aves: "AvesVivas",
    })
    for c in ["Edad","PesoFinal","AvesVivas"]:
        df[c] = parse_num_series(df[c])

    df["Estatus"]    = df[col_est].astype(str).str.upper().str.strip() if col_est else "ACTIVO"
    df["EstadoLote"] = df[col_estado].astype(str).str.upper().str.strip() if col_estado else "ABIERTO"

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
            df["TipoStd"] = np.where(parse_num_series(t).fillna(0).astype(int) == 1, "PROPIA", "PAC")
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

    col_mort = pick_first_col(df, ["MortalidadAcumulada","MORTALIDAD + DESCARTE"])
    col_neto = pick_first_col(df, ["Aves Neto","Aves_netas"])
    if col_mort and col_neto:
        df[col_mort] = parse_num_series(df[col_mort])
        df[col_neto] = parse_num_series(df[col_neto])
        df["MortPct"] = (df[col_mort] / df[col_neto].replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    return df.sort_values(["LoteCompleto","Edad"])

@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_excel(path, sheet_name="DATOS_COMPLETOS")
        df.columns = df.columns.astype(str).str.strip()
        zona_col = pick_first_col(df, ["Zona","zona"])
        if zona_col:
            df["Zona_Nombre"] = np.where(parse_num_series(df[zona_col]).fillna(0).astype(int) == 1, "BUCAY", "SANTO DOMINGO")
        else:
            df["Zona_Nombre"] = "BUCAY"
        tipo_col = pick_first_col(df, ["TipoGranja","Tipo_Granja"])
        df["TipoGranja"] = df[tipo_col].astype(str).str.upper().str.strip() if tipo_col else "PAC"
        quint_col = pick_first_col(df, ["Quintil_Area_Crianza","Quintil"])
        df["Quintil"] = df[quint_col].astype(str).str.upper().str.strip() if quint_col else "Q5"
        return df
    except Exception as e:
        st.warning(f"⚠️ Error cargando ideales: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def build_snapshot_activos(df_all: pd.DataFrame) -> pd.DataFrame:
    act = df_all[df_all["Estatus"].astype(str).str.upper().eq("ACTIVO")].copy()
    if act.empty: return pd.DataFrame()
    snap = act.sort_values(["LoteCompleto","Edad"]).groupby("LoteCompleto", as_index=False).last()
    snap["Etapa"] = snap["Edad"].apply(get_etapa)
    return snap

# ── Helper: calcular gap para una lista de lotes ─────────────
def calcular_gaps_lotes(lotes_ids, df_hist, ideales_df):
    """
    Devuelve lista de dicts {LoteCompleto, gap_promedio}
    para los lotes que presentan atraso vs ideal.
    """
    resultados = []
    for lote in lotes_ids:
        lote_hist = df_hist[
            (df_hist["LoteCompleto"] == lote) &
            (df_hist["Edad"] >= EDAD_MIN_ANALISIS)
        ]
        if lote_hist.empty:
            continue
        snap = lote_hist.iloc[-1]
        ideal = ideales_df[
            (ideales_df["Zona_Nombre"] == snap["ZonaNombre"]) &
            (ideales_df["TipoGranja"]  == snap["TipoStd"]) &
            (ideales_df["Quintil"]     == snap["Quintil"])
        ]
        if ideal.empty:
            continue
        gs = gc = 0
        for _, ir in ideal.iterrows():
            pr = lote_hist[lote_hist["Edad"] == ir.get("Edad")]
            if not pr.empty and pd.notna(ir.get("Peso")):
                g = ir["Peso"] - pr.iloc[0]["PesoFinal"]
                if g > 0:
                    gs += g; gc += 1
        if gc > 0:
            resultados.append({"LoteCompleto": lote, "gap_promedio": gs / gc})
    return resultados

# ── Carga de datos ───────────────────────────────────────────
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
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v13</div>
    <div class="pronaca-header-sub">Dashboard Interactivo · Selecciones en cascada · Predicción sincronizada</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS SUPERIORES
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

# ── Snapshot filtrado (SF) ────────────────────────────────────
SF = SNAP.copy()
SF = SF[SF["ZonaNombre"].isin(sel_zona)]
SF = SF[SF["TipoStd"].isin(sel_tipo)]
SF = SF[SF["Quintil"].isin(sel_quint)]
SF = SF[SF["EstadoLote"].isin(sel_estado)]

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
    st.stop()

# ── DF_FILTRADO: historial completo solo de lotes que pasan el filtro ──
# FIX v13: esto es la corrección principal del bug del Top 5
LOTES_FILTRADOS = SF["LoteCompleto"].unique()
DF_FILTRADO = DF[DF["LoteCompleto"].isin(LOTES_FILTRADOS)].copy()

# ──────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────
kg_total   = SF["KgLive"].sum()
costo_total= SF["CostoAcum"].sum()
cpkg       = costo_total / (kg_total if kg_total else np.nan)

k1,k2,k3,k4,k5 = st.columns(5)
for col_, val_, lbl_, acc in [
    (k1, f"{SF['LoteCompleto'].nunique():,}",       "Lotes activos",  True),
    (k2, f"{int(SF['AvesVivas'].sum()):,}",          "Aves vivas",     True),
    (k3, fmt_num(kg_total,0,suffix=" kg"),           "Kg live",        True),
    (k4, fmt_num(costo_total,0,prefix="$"),          "Costo total",    True),
    (k5, fmt_num(cpkg,3,prefix="$",suffix="/kg"),   "Costo medio/kg", False),
]:
    with col_:
        md(f'<div class="kpi-chip {"accent" if acc else ""}"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

# ──────────────────────────────────────────────────────────────
# LAYOUT PRINCIPAL
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════════════════════════
# COLUMNA IZQUIERDA
# ══════════════════════════════════════════════════════════════
with left:

    # ── SEC 01: Etapas ──────────────────────────────────────
    md(f"""<div class="sec-header"><span class="sec-num">01</span>
<div><div class="sec-title">Resumen por Etapa</div>
<div class="sec-sub">🖱️ Clic en barra para filtrar granjas abajo</div></div></div>""")

    rows_etapa = []
    for etapa in ETAPA_ORDER:
        g = SF[SF["Etapa"] == etapa]
        if g.empty: continue
        n   = g["LoteCompleto"].nunique()
        av  = g["AvesVivas"].sum()
        kg  = g["KgLive"].sum()
        co  = g["CostoAcum"].sum()
        mo  = g["MortPct"].mean()
        al  = g["AlimAcumKg"].sum()
        fcr = al / kg if kg > 0 else np.nan
        ck  = co / kg if kg > 0 else np.nan
        bdg = "green"
        if pd.notna(ck) and ck >= 0.9: bdg = "red"
        elif pd.notna(ck) and ck >= 0.75: bdg = "amber"
        rows_etapa.append((etapa, n, av, kg, fcr, co, ck, mo, bdg))

    cg, ct = st.columns([0.4, 0.6], gap="small")
    with cg:
        fig_e = go.Figure()
        fig_e.add_trace(go.Bar(
            x=[r[0] for r in rows_etapa], y=[r[1] for r in rows_etapa],
            marker=dict(color=[ETAPA_COLORS.get(r[0], BLUE) for r in rows_etapa]),
            text=[r[1] for r in rows_etapa], textposition="auto",
            hovertemplate="<b>%{x}</b><br>Lotes: %{y}<extra></extra>",
        ))
        fig_e.update_layout(
            template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=240, margin=dict(l=8,r=8,t=18,b=50),
            font=dict(family="DM Sans",size=9,color=TEXT), showlegend=False,
            xaxis=dict(title="",gridcolor=BORDER,color=TEXT,tickangle=-45),
            yaxis=dict(title="Lotes",gridcolor=BORDER,color=TEXT),
        )
        sel_e = st.plotly_chart(fig_e, on_select="rerun", selection_mode="points",
                                key="chart_etapas", config={"displayModeBar":False},
                                width="stretch")
        etapas_sel = [p["x"] for p in sel_e.selection.get("points",[]) if "x" in p]
        if etapas_sel:
            md(f'<div class="sel-pill">🔍 Filtrando: {" + ".join([e.split("(")[0].strip() for e in etapas_sel])}</div>')
        else:
            md(f'<div class="hint-text">Clic en barra para filtrar ↓</div>')

    with ct:
        tbody = ""
        for etapa, n, av, kg, fcr, co, ck, mo, bdg in rows_etapa:
            dot = ETAPA_COLORS.get(etapa, BLUE)
            act = etapa in etapas_sel if etapas_sel else False
            tbody += f"""<tr style="border-bottom:1px solid {BORDER};background:{'rgba(218,41,28,.05)' if act else 'transparent'}">
  <td style="padding:6px 8px;font-weight:{'900' if act else '700'};font-size:.73rem;text-align:left">
    <span style="display:inline-block;width:7px;height:7px;border-radius:2px;background:{dot};margin-right:5px;vertical-align:middle"></span>
    {etapa.split('(')[0].strip()}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{int(av):,}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(kg,0)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(fcr,3)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(co,0,prefix="$")}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem"><span class="badge {bdg}">{fmt_num(ck,3,prefix="$")}</span></td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(mo,2,suffix="%")}</td>
</tr>"""
        md(f"""<div class="card" style="padding:0;overflow:auto;height:240px">
<table style="width:100%;border-collapse:collapse">
<thead style="position:sticky;top:0;background:#F8FAFC;z-index:1">
<tr style="border-bottom:1px solid {BORDER}">
  <th style="text-align:left;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase;letter-spacing:.3px">Etapa</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">Aves</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">Kg</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">FCR</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">Costo</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">$/kg</th>
  <th style="text-align:right;padding:6px 8px;color:{MUTED};font-size:.63rem;text-transform:uppercase">M%</th>
</tr></thead><tbody>{tbody}</tbody></table></div>""")

    # ── SEC 02: Top 5 Granjas ────────────────────────────────
    md(f"""<div class="sec-header"><span class="sec-num">02</span>
<div><div class="sec-title">Top 5 Granjas con Problemas</div>
<div class="sec-sub">🖱️ Clic en granja → ver lotes · Clic en lote → análisis Sec 03</div>
</div></div>""")

    # ── Filtro cascada desde Sec 01
    SF_02 = SF.copy()
    if etapas_sel:
        SF_02 = SF_02[SF_02["Etapa"].isin(etapas_sel)]

    # Solo lotes ABIERTOS que pasaron el filtro
    SF_AB = SF_02[SF_02["EstadoLote"] == "ABIERTO"].copy()

    if SF_AB.empty:
        st.info("No hay lotes ABIERTOS con los filtros actuales.")
    else:
        # ── FIX v13: DF_AB solo contiene historial de lotes filtrados ──
        lotes_ab = SF_AB["LoteCompleto"].unique()
        DF_AB = DF_FILTRADO[
            (DF_FILTRADO["EstadoLote"] == "ABIERTO") &
            (DF_FILTRADO["LoteCompleto"].isin(lotes_ab))
        ].copy()

        # Calcular problemas por granja
        probs = []
        for granja in SF_AB["GranjaID"].unique():
            lotes_g = SF_AB[SF_AB["GranjaID"] == granja]["LoteCompleto"].unique()
            gaps = calcular_gaps_lotes(lotes_g, DF_AB, IDEALES)
            if gaps:
                n_prob = len(gaps)
                g_prom = np.mean([x["gap_promedio"] for x in gaps])
                probs.append({"GranjaID": granja, "NumLotesProblema": n_prob, "GapPromedio": g_prom})

        if not probs:
            # Mostrar aviso útil con info de debug
            combos = SF_AB.groupby(["ZonaNombre","TipoStd","Quintil"]).size().reset_index()
            combos_str = " | ".join([f"{r['ZonaNombre']}·{r['TipoStd']}·{r['Quintil']}" for _, r in combos.iterrows()])
            st.warning(
                f"No se encontraron granjas con gap vs ideal para los filtros actuales.\n\n"
                f"**Combinaciones buscadas en ideales:** {combos_str}\n\n"
                f"Verifica que `{BENCH_FILE}` contenga curvas ideales para estas combinaciones."
            )
        else:
            df_prob = pd.DataFrame(probs).sort_values("NumLotesProblema", ascending=False).head(5)

            fig_g = go.Figure()
            fig_g.add_trace(go.Bar(
                x=df_prob["GranjaID"], y=df_prob["NumLotesProblema"],
                marker=dict(color=RED), text=df_prob["NumLotesProblema"], textposition="auto",
                hovertemplate="<b>%{x}</b><br>Lotes problema: %{y}<extra></extra>",
            ))
            fig_g.update_layout(
                template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=200, margin=dict(l=8,r=8,t=18,b=8),
                font=dict(family="DM Sans",size=10,color=TEXT), showlegend=False,
                xaxis=dict(title="Granja",gridcolor=BORDER,color=TEXT),
                yaxis=dict(title="# Lotes Problema",gridcolor=BORDER,color=TEXT),
            )
            sel_g = st.plotly_chart(fig_g, on_select="rerun", selection_mode="points",
                                    key="chart_granjas", width="stretch")
            granjas_sel = [p["x"] for p in sel_g.selection.get("points",[]) if "x" in p]
            granja_activa = granjas_sel[0] if granjas_sel else df_prob.iloc[0]["GranjaID"]

            if granjas_sel:
                md(f'<div class="sel-pill">🏭 Granja: <strong>{granja_activa}</strong></div>')
            else:
                md(f'<div class="hint-text">Clic en barra para seleccionar granja · Activa: <strong>{granja_activa}</strong></div>')

            # Lotes con problema de la granja activa
            lotes_g_act = SF_AB[SF_AB["GranjaID"] == granja_activa]["LoteCompleto"].unique()
            gaps_lotes   = calcular_gaps_lotes(lotes_g_act, DF_AB, IDEALES)

            if not gaps_lotes:
                st.info(f"No hay lotes con gap en {granja_activa} para los filtros actuales.")
            else:
                filas_tabla = []
                for gap_info in sorted(gaps_lotes, key=lambda x: -x["gap_promedio"]):
                    lote = gap_info["LoteCompleto"]
                    snap_r = SF[SF["LoteCompleto"] == lote]
                    fcr_v = float(snap_r.iloc[0]["FCR_Cum"]) if not snap_r.empty and pd.notna(snap_r.iloc[0]["FCR_Cum"]) else None
                    ck_v  = float(snap_r.iloc[0]["CostoKg_Cum"]) if not snap_r.empty and pd.notna(snap_r.iloc[0]["CostoKg_Cum"]) else None
                    edad_v= int(snap_r.iloc[0]["Edad"]) if not snap_r.empty else 0
                    filas_tabla.append({
                        "LoteCompleto": lote,
                        "Código":       extract_lote_codigo(lote),
                        "Edad":         edad_v,
                        "Gap kg":       round(gap_info["gap_promedio"], 3),
                        "FCR":          round(fcr_v, 3) if fcr_v else None,
                        "$/kg":         round(ck_v, 3) if ck_v else None,
                    })

                df_lotes = pd.DataFrame(filas_tabla).reset_index(drop=True)
                md(f'<div class="hint-text">Clic en fila para analizar en Sec 03 ↓</div>')

                sel_t = st.dataframe(
                    df_lotes[["Código","Edad","Gap kg","FCR","$/kg"]],
                    on_select="rerun", selection_mode="single-row",
                    key="df_lotes_sec02", hide_index=True,
                    use_container_width=True, height=180,
                    column_config={
                        "Código": st.column_config.TextColumn("🔖 Código", width="small"),
                        "Edad":   st.column_config.NumberColumn("Días", format="%d d", width="small"),
                        "Gap kg": st.column_config.NumberColumn("Gap kg ↑", format="%.3f", width="small"),
                        "FCR":    st.column_config.NumberColumn("FCR", format="%.3f", width="small"),
                        "$/kg":   st.column_config.NumberColumn("$/kg", format="$%.3f", width="small"),
                    },
                )
                rows_sel = sel_t.selection.get("rows", [])
                if rows_sel:
                    nuevo_lote = df_lotes.iloc[rows_sel[0]]["LoteCompleto"]
                    if st.session_state.get("lote_sel_sec03") != nuevo_lote:
                        st.session_state["lote_sel_sec03"] = nuevo_lote
                        st.rerun()

    # ── SEC 03: IDEAL vs REAL ────────────────────────────────
    md(f"""<div class="sec-header"><span class="sec-num">03</span>
<div><div class="sec-title">Lote Seleccionado: IDEAL vs REAL</div>
<div class="sec-sub">Análisis detallado · selecciona un lote en la tabla de arriba</div>
</div></div>""")

    lotes_disp = SF["LoteCompleto"].unique().tolist()
    if "lote_sel_sec03" not in st.session_state or st.session_state["lote_sel_sec03"] not in lotes_disp:
        st.session_state["lote_sel_sec03"] = lotes_disp[0] if lotes_disp else None

    lote_sel = st.session_state.get("lote_sel_sec03")
    if not lote_sel:
        st.info("Selecciona un lote en la tabla de arriba.")
        st.stop()

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
        st.warning(
            f"⚠️ Sin curva ideal para: **{il['ZonaNombre']} · {il['TipoStd']} · {il['Quintil']}**\n\n"
            f"Se mostrará solo la curva real."
        )
        ideal_data = pd.DataFrame(columns=["Edad","Peso"])

    # KPIs del lote
    h1,h2,h3,h4 = st.columns(4)
    for col_, val_, lbl_ in [
        (h1, il["GranjaID"],"Granja"), (h2, il["ZonaNombre"],"Zona"),
        (h3, il["TipoStd"],"Tipo"),   (h4, f"{int(edad_act)} d","Edad"),
    ]:
        with col_:
            md(f'<div class="kpi-chip"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

    # Gráfico Peso Real vs Ideal
    hist_v = hist[hist["PesoFinal"].notna()].copy()
    edad_max = float(hist_v["Edad"].max()) if not hist_v.empty else 0
    ideal_s  = ideal_data.sort_values("Edad") if not ideal_data.empty else pd.DataFrame()
    if not ideal_s.empty:
        ideal_s = ideal_s[ideal_s["Edad"] <= edad_max + 3]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist_v["Edad"], y=hist_v["PesoFinal"],
        mode="lines+markers", name="REAL",
        line=dict(color=RED,width=3), marker=dict(size=6),
        hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
    ))
    if not ideal_s.empty:
        fig.add_trace(go.Scatter(
            x=ideal_s["Edad"], y=ideal_s["Peso"],
            mode="lines+markers", name="IDEAL",
            line=dict(color=GREEN,width=3,dash="dash"), marker=dict(size=6,symbol="diamond"),
            hovertemplate="Día %{x}<br>IDEAL: %{y:.3f} kg<extra></extra>",
        ))
        hm = hist_v.merge(ideal_s[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"}), on="Edad", how="inner")
        if not hm.empty:
            fig.add_trace(go.Scatter(
                x=hm["Edad"].tolist()+hm["Edad"].tolist()[::-1],
                y=hm["PesoFinal"].tolist()+hm["PesoIdeal"].tolist()[::-1],
                fill="toself", name="GAP", fillcolor="rgba(218,41,28,0.15)",
                line=dict(color="rgba(255,255,255,0)"), hoverinfo="skip",
            ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=300, margin=dict(l=8,r=8,t=18,b=8),
        font=dict(family="DM Sans",size=11,color=TEXT),
        legend=dict(orientation="h",y=-0.15,x=0,bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title="Edad (días)",gridcolor=BORDER,color=TEXT),
        yaxis=dict(title="Peso (kg)",gridcolor=BORDER,color=TEXT),
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    # Gráfico Costo Perdido
    st.caption("**Costo perdido (Real vs Ideal) acumulado:**")
    hc = hist[hist["Edad"] >= EDAD_MIN_ANALISIS].copy()
    if not ideal_s.empty:
        hc = hc.merge(ideal_s[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"}), on="Edad", how="left")
        hc["KgIdealAcum"]    = (hc["AvesVivas"] * hc["PesoIdeal"]).cumsum()
        hc["CostoIdealAcum"] = hc["KgIdealAcum"] * hc["CostoKg_Cum"]
        hc["CostoPerdido"]   = (hc["CostoAcum"] - hc["CostoIdealAcum"]).clip(lower=0)
    else:
        hc["CostoPerdido"] = np.nan
    hc_clean = hc[["Edad","CostoPerdido"]].dropna()

    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(
        x=hc_clean["Edad"], y=hc_clean["CostoPerdido"],
        mode="lines+markers", line=dict(color=RED,width=3), marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(218,41,28,0.2)",
        hovertemplate="Día %{x}<br>Pérdida: $%{y:,.2f}<extra></extra>",
    ))
    fig_c.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=280, margin=dict(l=8,r=8,t=18,b=8),
        font=dict(family="DM Sans",size=11,color=TEXT), showlegend=False,
        xaxis=dict(title="Edad (días)",gridcolor=BORDER,color=TEXT),
        yaxis=dict(title="Costo Perdido ($)",gridcolor=BORDER,color=TEXT),
        hovermode="x unified",
    )
    st.plotly_chart(fig_c, width="stretch")

# ══════════════════════════════════════════════════════════════
# COLUMNA DERECHA — PREDICCIÓN SINCRONIZADA CON lote_sel
# ══════════════════════════════════════════════════════════════
with right:
    try:
        from model_predictor import cargar_predictor
        predictor     = cargar_predictor("modelo_rf_avicola.joblib")
        pred_activo   = predictor.model is not None
    except Exception as e:
        st.warning(f"⚠️ No se pudo cargar el predictor: {e}")
        pred_activo = False

    if not pred_activo:
        md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:900px;
display:flex;align-items:center;justify-content:center;">
  <div style="text-align:center;color:{MUTED};font-weight:800;text-transform:uppercase;letter-spacing:.7px;">
    📊 Predicción de Lotes<br><br>⚠️ Modelo no disponible<br>
    Coloca <strong>modelo_rf_avicola.joblib</strong><br>en la carpeta del app
  </div>
</div>""")
    else:
        md(f"""<div class="sec-header"><span class="sec-num">04</span>
<div><div class="sec-title">Predicción: Proyección al Día 40</div>
<div class="sec-sub">Sincronizado con el lote seleccionado en Sec 03</div>
</div></div>""")

        # ── lote_sel viene de session_state, actualizado por Sec 03 ──
        if not lote_sel:
            st.info("Selecciona un lote en la Sección 03.")
        else:
            # FIX v13: usamos TODO el historial del lote, no solo hasta día 14
            hist_pred = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
            hist_pred = hist_pred[hist_pred["PesoFinal"].notna()].copy()

            if hist_pred.empty:
                st.warning(f"No hay historial de peso para {lote_sel}")
            else:
                # Pill mostrando que está sincronizado
                md(f'<div class="sel-pill-neutral">🔗 Lote: <strong>{extract_lote_codigo(lote_sel)}</strong> · {int(hist_pred["Edad"].max())} días de historial</div>')

                res = predictor.proyectar_curva(
                    hist_lote=hist_pred,
                    target_edad=40,
                    enforce_monotonic="isotonic",
                )

                if res.get("error"):
                    st.error(f"Error en predicción: {res['error']}")
                else:
                    df_curve    = res["df"]
                    edad_actual = int(res["edad_actual"])
                    peso_actual = float(hist_pred.iloc[-1]["PesoFinal"])
                    peso_d40    = float(res["peso_d40"])
                    dias_rest   = max(0, 40 - edad_actual)

                    # KPIs
                    c1, c2 = st.columns(2)
                    with c1:
                        md(f'<div class="kpi-chip accent"><div class="kv">{peso_d40:.3f} kg</div><div class="kl">Peso proyectado Día 40</div></div>')
                    with c2:
                        md(f'<div class="kpi-chip"><div class="kv">{dias_rest} d</div><div class="kl">Días restantes a D40</div></div>')

                    # Gráfico REAL + PROYECCIÓN
                    fig_p = go.Figure()
                    fig_p.add_trace(go.Scatter(
                        x=hist_pred["Edad"], y=hist_pred["PesoFinal"],
                        mode="lines+markers", name="REAL",
                        line=dict(color=BLUE,width=3), marker=dict(size=7),
                        hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
                    ))
                    if df_curve is not None and not df_curve.empty:
                        fig_p.add_trace(go.Scatter(
                            x=df_curve["Dia"], y=df_curve["Peso_pred_kg"],
                            mode="lines", name="PROYECCIÓN D40",
                            line=dict(color=RED,width=3,dash="dash"),
                            hovertemplate="Día %{x}<br>PROY: %{y:.3f} kg<extra></extra>",
                        ))
                    fig_p.add_trace(go.Scatter(
                        x=[40], y=[peso_d40],
                        mode="markers", name="D40",
                        marker=dict(size=10,symbol="diamond",color=RED),
                        hovertemplate="Día 40<br>%{y:.3f} kg<extra></extra>",
                    ))
                    fig_p.update_layout(
                        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
                        height=320, margin=dict(l=8,r=8,t=18,b=8),
                        font=dict(family="DM Sans",size=11,color=TEXT),
                        legend=dict(orientation="h",y=-0.15,x=0,bgcolor="rgba(0,0,0,0)"),
                        xaxis=dict(title="Edad (días)",gridcolor=BORDER,color=TEXT),
                        yaxis=dict(title="Peso (kg)",gridcolor=BORDER,color=TEXT),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_p, width="stretch")

                    # Comparación con ideal día 40
                    try:
                        ideal_40 = IDEALES[
                            (IDEALES["Zona_Nombre"] == il["ZonaNombre"]) &
                            (IDEALES["TipoGranja"]  == il["TipoStd"]) &
                            (IDEALES["Quintil"]     == il["Quintil"]) &
                            (IDEALES["Edad"] == 40)
                        ]
                        if not ideal_40.empty and pd.notna(ideal_40.iloc[0]["Peso"]):
                            pi40 = float(ideal_40.iloc[0]["Peso"])
                            dif  = pi40 - peso_d40
                            bc   = "red" if dif > 0 else "green"
                            txt  = f"Atraso proyectado: {dif:.3f} kg" if dif > 0 else f"Adelante proyectado: {abs(dif):.3f} kg"
                            md(f'<div class="badge {bc}">{txt}</div>')
                    except Exception:
                        pass

                    # Info
                    st.caption("**Resumen de la proyección:**")
                    m1, m2, m3 = st.columns(3)
                    with m1: st.metric("Edad actual", f"{edad_actual} días")
                    with m2: st.metric("Peso actual", f"{peso_actual:.3f} kg")
                    with m3: st.metric("Peso proy. D40", f"{peso_d40:.3f} kg")

# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v13 · Interactivo · {hoy:%d/%m/%Y %H:%M}
</div>
""")