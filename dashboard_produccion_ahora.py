import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ============================================================
# STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="PRONACA | Producción Avícola — AHORA",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# BRAND COLORS (Pronaca)
# ============================================================
PRONACA_RED = "#DA291C"
PRONACA_BLACK = "#0B0B0C"
PRONACA_GRAY = "#6B7280"

# Tema único (NO modo oscuro)
BG = "#EEF2F6"        # fondo gris suave (no blanco)
CARD = "#FBFCFE"      # tarjetas “off-white” (menos brillo)
TOPBAR = "#FBFCFE"
BORDER = "#D6D6E8"
TEXT = "#0F172A"
MUTED = "#475569"
PLOTLY_TEMPLATE = "plotly_white"
PRONACA_COLORWAY = [PRONACA_RED, PRONACA_BLACK, PRONACA_GRAY, "#F59E0B", "#16A34A"]

# ============================================================
# CURVA BIOLOGICA (kg/ave)
# ============================================================
CURVA = {
  1: {"M":0.179, "H":0.168, "S":0.173},
  2: {"M":0.198, "H":0.186, "S":0.192},
  3: {"M":0.219, "H":0.205, "S":0.212},
  4: {"M":0.241, "H":0.226, "S":0.233},
  5: {"M":0.263, "H":0.247, "S":0.255},
  6: {"M":0.287, "H":0.269, "S":0.278},
  7: {"M":0.312, "H":0.292, "S":0.302},
  8: {"M":0.347, "H":0.326, "S":0.337},
  9: {"M":0.385, "H":0.362, "S":0.374},
  10: {"M":0.425, "H":0.399, "S":0.412},
  11: {"M":0.468, "H":0.439, "S":0.453},
  12: {"M":0.511, "H":0.480, "S":0.496},
  13: {"M":0.558, "H":0.524, "S":0.541},
  14: {"M":0.606, "H":0.568, "S":0.590},
  15: {"M":0.675, "H":0.645, "S":0.657},
  16: {"M":0.749, "H":0.724, "S":0.727},
  17: {"M":0.826, "H":0.803, "S":0.800},
  18: {"M":0.909, "H":0.883, "S":0.878},
  19: {"M":0.994, "H":0.962, "S":0.958},
  20: {"M":1.084, "H":1.042, "S":1.042},
  21: {"M":1.177, "H":1.121, "S":1.129},
  22: {"M":1.274, "H":1.209, "S":1.219},
  23: {"M":1.374, "H":1.296, "S":1.312},
  24: {"M":1.477, "H":1.383, "S":1.407},
  25: {"M":1.584, "H":1.470, "S":1.505},
  26: {"M":1.693, "H":1.561, "S":1.605},
  27: {"M":1.805, "H":1.651, "S":1.707},
  28: {"M":1.918, "H":1.742, "S":1.811},
  29: {"M":2.035, "H":1.843, "S":1.917},
  30: {"M":2.153, "H":1.945, "S":2.025},
  31: {"M":2.273, "H":2.046, "S":2.134},
  32: {"M":2.395, "H":2.148, "S":2.244},
  33: {"M":2.518, "H":2.249, "S":2.354},
  34: {"M":2.642, "H":2.351, "S":2.467},
  35: {"M":2.768, "H":2.456, "S":2.580},
  36: {"M":2.893, "H":2.561, "S":2.692},
  37: {"M":3.020, "H":2.665, "S":2.806},
  38: {"M":3.147, "H":2.770, "S":2.920},
  39: {"M":3.275, "H":2.875, "S":3.033},
  40: {"M":3.403, "H":2.980, "S":3.147},
  41: {"M":3.530, "H":3.085, "S":3.259},
  42: {"M":3.658, "H":3.190, "S":3.373},
  43: {"M":3.785, "H":3.294, "S":3.486},
  44: {"M":3.911, "H":3.399, "S":3.597},
  45: {"M":4.038, "H":3.504, "S":3.771},
  46: {"M":4.165, "H":3.609, "S":3.887},
  47: {"M":4.292, "H":3.714, "S":4.003},
  48: {"M":4.419, "H":3.819, "S":4.119},
  49: {"M":4.546, "H":3.924, "S":4.235},
}

# ============================================================
# HELPERS
# ============================================================
def to_dt(s): return pd.to_datetime(s, errors="coerce")
def to_num(s): return pd.to_numeric(s, errors="coerce")

def fmt_int(x):
    try: return f"{int(x):,}"
    except: return "—"

def fmt_float(x, nd=2, suf=""):
    try:
        if pd.isna(x): return "—"
        return f"{float(x):.{nd}f}{suf}"
    except:
        return "—"

def get_etapa(edad):
    try: e = float(edad)
    except: return "Desconocido"
    if e <= 14: return "Inicio (1-14)"
    if e <= 28: return "Crecimiento (15-28)"
    if e <= 35: return "Pre-acabado (29-35)"
    if e <= 42: return "Acabado (36-42)"
    return "Final (43+)"

def zona_nombre(z):
    z = str(z).upper()
    if z == "BUC": return "Bucay"
    if z == "STO": return "Santo Domingo"
    return "Otro"

def curva_series(sexo: str, edades: list[int]):
    sexo = (sexo or "S").upper()
    out = []
    for e in edades:
        if e in CURVA:
            out.append(CURVA[e].get(sexo, CURVA[e].get("S", np.nan)))
        else:
            out.append(np.nan)
    return out

def reset_filters():
    keys = ["zonas", "estados", "sexos", "mort_alert", "lote_search", "lote_detail", "tipo_lote"]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]

@st.cache_data(show_spinner=False)
def load_excel(file_path_or_bytes):
    try:
        df = pd.read_excel(file_path_or_bytes, sheet_name="final", engine="openpyxl")
    except Exception:
        df = pd.read_excel(file_path_or_bytes, engine="openpyxl")

    for c in ["FechaTransaccion", "Cierre de campaña", "Fecha recepción"]:
        if c in df.columns:
            df[c] = to_dt(df[c])

    num_cols = [
        "Edad","Peso","PesoFinal","Mortalidad","Descarte","MortalidadTotalDia","MortalidadAcumulada",
        "Aves Planta","Aves Neto","AvesVivas","EdadVenta","Kilos Neto","AvesVivasVenta","PesoSalidaKg",
        "UltimoReal7","Galpon"
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = to_num(df[c])

    if "Sexo" in df.columns:
        df["Sexo"] = df["Sexo"].astype(str).str.upper().replace({"NAN": np.nan, "NONE": np.nan})
    if "EstadoLote" in df.columns:
        df["EstadoLote"] = df["EstadoLote"].astype(str).str.upper()

    if "LoteCompleto" in df.columns:
        df["Zona"] = df["LoteCompleto"].astype(str).str.extract(r"^(BUC|STO)", expand=False)

    return df

def build_snapshot(df, corte_dt=None):
    if df.empty:
        return pd.DataFrame()

    d = df.copy()
    if corte_dt is not None and "FechaTransaccion" in d.columns:
        d = d[d["FechaTransaccion"].notna() & (d["FechaTransaccion"] <= corte_dt)]

    if "FechaTransaccion" in d.columns:
        d = d.sort_values(["LoteCompleto", "FechaTransaccion", "Edad"])
    else:
        d = d.sort_values(["LoteCompleto", "Edad"])

    last = d.groupby("LoteCompleto").tail(1).copy()
    last["EdadActual"] = last.get("Edad", np.nan)
    last["PesoActual"] = last.get("PesoFinal", last.get("Peso", np.nan))
    last["Etapa"] = last["EdadActual"].apply(get_etapa)

    if "Aves Neto" in last.columns and "MortalidadAcumulada" in last.columns:
        last["MortalidadPct"] = np.where(
            last["Aves Neto"].fillna(0) > 0,
            (last["MortalidadAcumulada"].fillna(0) / last["Aves Neto"].fillna(0)) * 100,
            np.nan
        )

    if "Zona" in last.columns:
        last["ZonaNombre"] = last["Zona"].apply(zona_nombre)

    return last

# ============================================================
# CSS (Tema único Pronaca + fondo suave)
# ============================================================
st.markdown(f"""
<style>
  html, body, [data-testid="stAppViewContainer"], .stApp {{
    background: {BG} !important;
  }}

  .stApp, .stApp p, .stApp span, .stApp div, .stApp label {{
    color: {TEXT} !important;
  }}

  /* Sidebar */
  section[data-testid="stSidebar"] {{
    background: {CARD} !important;
    border-right: 1px solid {BORDER} !important;
  }}

  /* Evitar bloques raros en <code> */
  code {{
    background: transparent !important;
    color: {TEXT} !important;
    padding: 0 !important;
  }}

  /* Header */
  .topbar {{
    background: {TOPBAR} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 16px;
    padding: 14px 16px;
    box-shadow: 0 1px 12px rgba(0,0,0,0.08);
    margin-bottom: 12px;
  }}
  .topbar h2 {{
    margin: 0;
    font-weight: 900;
    color: {TEXT} !important;
  }}
  .muted {{
    color: {MUTED} !important;
    font-size: 0.95rem;
    margin-top: 2px;
  }}

  /* KPI */
  .kpi-card {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 14px;
    padding: 14px 14px 12px 14px;
    box-shadow: 0 1px 10px rgba(0,0,0,0.08);
  }}
  .kpi-accent {{
    border-left: 6px solid {PRONACA_RED} !important;
  }}
  .kpi-label {{
    color: {MUTED} !important;
    font-size: 0.85rem;
    margin-bottom: 6px;
    font-weight: 800;
  }}
  .kpi-value {{
    font-size: 1.55rem;
    font-weight: 950;
    line-height: 1.1;
    color: {TEXT} !important;
  }}

  /* Corte pill */
  .pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border: 1px solid {BORDER} !important;
    border-radius: 999px;
    background: {CARD} !important;
    color: {TEXT} !important;
    font-size: 1.06rem;
    font-weight: 900;
    box-shadow: 0 1px 10px rgba(0,0,0,0.08);
  }}
  .pill span {{
    color: {MUTED} !important;
    font-weight: 900;
  }}

  /* Tabs */
  div[data-baseweb="tab-list"] {{
    background: transparent !important;
    padding: 6px 2px 10px 2px;
    border-bottom: none !important;
    gap: 8px !important;
  }}
  button[data-baseweb="tab"] {{
    background: #F5F8FC !important;
    border: 1px solid {BORDER} !important;
    border-radius: 12px !important;
    padding: 10px 14px !important;
    font-weight: 900 !important;
    color: {TEXT} !important;
    font-size: 1.02rem !important;
  }}
  button[data-baseweb="tab"][aria-selected="true"] {{
    background: {CARD} !important;
    border: 2px solid {PRONACA_RED} !important;
    box-shadow: 0 1px 12px rgba(0,0,0,0.10);
  }}

  /* Plotly container */
  div[data-testid="stPlotlyChart"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 14px !important;
    padding: 8px !important;
  }}

  /* Dataframe container */
  div[data-testid="stDataFrame"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 14px !important;
    overflow: hidden !important;
  }}
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOAD DATA
# ============================================================
default_path = "produccion_actual_final.xlsx"
if not os.path.exists(default_path):
    st.error("No se encontró el archivo 'produccion_actual_final.xlsx' en la carpeta actual.")
    st.stop()

df = load_excel(default_path)
if df.empty:
    st.error("El dataset está vacío. Revisar el archivo de entrada.")
    st.stop()

corte = df["FechaTransaccion"].max() if "FechaTransaccion" in df.columns else datetime.now()
snap = build_snapshot(df, corte_dt=corte)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("### Datos")
    st.markdown(f"**Archivo:** {default_path}")
    st.markdown(f"**Corte:** {corte:%Y-%m-%d}")

    c1, c2 = st.columns(2)
    with c1:
        st.button("Reset filtros", use_container_width=True, on_click=reset_filters)
    with c2:
        st.download_button(
            "Descargar snapshot",
            data=snap.to_csv(index=False).encode("utf-8"),
            file_name="snapshot_pronaca.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()
    st.markdown("### Filtros")

    zonas_avail = sorted(snap["ZonaNombre"].dropna().unique()) if "ZonaNombre" in snap.columns else []
    sel_zonas = st.multiselect("Zona", options=zonas_avail, default=zonas_avail, key="zonas")

    estados_avail = sorted(snap["EstadoLote"].dropna().unique()) if "EstadoLote" in snap.columns else ["ABIERTO", "CERRADO"]
    sel_estados = st.multiselect("Estado lote", options=estados_avail, default=estados_avail, key="estados")

    sexos_avail = sorted(snap["Sexo"].dropna().unique()) if "Sexo" in snap.columns else []
    sel_sexos = st.multiselect("Sexo", options=sexos_avail, default=sexos_avail, key="sexos")

    st.divider()
    st.markdown("### Umbral")
    mort_alert = st.slider("Alerta mortalidad (%)", 0, 20, 7, 1, key="mort_alert")

# ============================================================
# APPLY FILTERS
# ============================================================
snap_f = snap.copy()
if sel_zonas and "ZonaNombre" in snap_f.columns:
    snap_f = snap_f[snap_f["ZonaNombre"].isin(sel_zonas)]
if sel_estados and "EstadoLote" in snap_f.columns:
    snap_f = snap_f[snap_f["EstadoLote"].isin(sel_estados)]
if sel_sexos and "Sexo" in snap_f.columns:
    snap_f = snap_f[snap_f["Sexo"].isin(sel_sexos)]

# ============================================================
# PLOTLY STYLING
# ============================================================
def apply_pronaca_plotly(fig, height=380):
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=height,
        colorway=PRONACA_COLORWAY,
        font=dict(family="Arial", size=13, color=TEXT),
        title=dict(font=dict(size=16, color=TEXT)),
        margin=dict(l=10, r=10, t=55, b=10),
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=True, gridcolor=BORDER, zeroline=False, color=TEXT)
    fig.update_yaxes(showgrid=True, gridcolor=BORDER, zeroline=False, color=TEXT)
    return fig

def kpi_card(label, value, sub=None, accent=True):
    cls = "kpi-card kpi-accent" if accent else "kpi-card"
    sub_html = f"<div class='muted'>{sub}</div>" if sub else ""
    st.markdown(f"""
    <div class="{cls}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {sub_html}
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
logo_path = "assets/pronaca.png"
c1, c2, c3 = st.columns([0.18, 0.60, 0.22], vertical_alignment="center")
with c1:
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
with c2:
    st.markdown(
        "<div class='topbar'>"
        "<h2>Producción Avícola — Estado Actual</h2>"
        "<div class='muted'>Seguimiento operativo por lote, zona y alertas</div>"
        "</div>",
        unsafe_allow_html=True
    )
with c3:
    st.markdown(f"<div class='pill'><span>Corte</span> {corte:%d-%m-%Y}</div>", unsafe_allow_html=True)

# ============================================================
# KPIs
# ============================================================
lotes_tot = snap_f["LoteCompleto"].nunique() if "LoteCompleto" in snap_f.columns else 0
lotes_abiertos = snap_f[snap_f.get("EstadoLote", "") == "ABIERTO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
lotes_cerrados = snap_f[snap_f.get("EstadoLote", "") == "CERRADO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
aves_vivas = snap_f["AvesVivas"].fillna(0).sum() if "AvesVivas" in snap_f.columns else 0
mort_prom = snap_f["MortalidadPct"].mean() if "MortalidadPct" in snap_f.columns else np.nan
peso_prom = snap_f["PesoActual"].mean() if "PesoActual" in snap_f.columns else np.nan

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1: kpi_card("Lotes total", f"{lotes_tot:,}", "Lotes únicos", True)
with k2: kpi_card("Activos", f"{lotes_abiertos:,}", "Estado ABIERTO", True)
with k3: kpi_card("Cerrados", f"{lotes_cerrados:,}", "Estado CERRADO", False)
with k4: kpi_card("Aves vivas", fmt_int(aves_vivas), "Población actual", True)
with k5: kpi_card("Mortalidad promedio", fmt_float(mort_prom, 2, "%"), f"Alerta ≥ {mort_alert}%", True)
with k6: kpi_card("Peso promedio", fmt_float(peso_prom, 3, " kg"), "Peso actual", True)

st.divider()

# ============================================================
# TABS
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs(["Resumen", "Zonas", "Alertas", "Detalle por lote"])

# ============================================================
# TAB 1: RESUMEN
# ============================================================
with tab1:
    st.subheader("Distribución por etapa")

    colA, colB = st.columns([2, 1.3])

    with colA:
        if "Etapa" in snap_f.columns and not snap_f.empty:
            etapas_order = ["Inicio (1-14)", "Crecimiento (15-28)", "Pre-acabado (29-35)", "Acabado (36-42)", "Final (43+)"]
            by_etapa = snap_f.groupby("Etapa", as_index=False).agg(
                Lotes=("LoteCompleto", "nunique"),
                AvesVivas=("AvesVivas", "sum"),
                PesoPromedio=("PesoActual", "mean")
            )
            by_etapa["Etapa"] = pd.Categorical(by_etapa["Etapa"], categories=etapas_order, ordered=True)
            by_etapa = by_etapa.sort_values("Etapa")

            fig_etapa = px.bar(
                by_etapa,
                x="Etapa",
                y="Lotes",
                color="PesoPromedio",
                color_continuous_scale=[(0, "#F1F5F9"), (1, PRONACA_RED)],
                title="Lotes por etapa (color = peso promedio)",
                labels={"Lotes": "Cantidad de lotes", "PesoPromedio": "Peso promedio (kg)"}
            )
            st.plotly_chart(apply_pronaca_plotly(fig_etapa, 390), use_container_width=True)
        else:
            st.info("No hay datos para mostrar con los filtros actuales.")

    with colB:
        if "ZonaNombre" in snap_f.columns and not snap_f.empty:
            by_zona = snap_f.groupby("ZonaNombre", as_index=False).agg(Lotes=("LoteCompleto", "nunique"))
            fig_zona = px.pie(
                by_zona,
                names="ZonaNombre",
                values="Lotes",
                hole=0.55,
                title="Participación por zona"
            )
            fig_zona.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(apply_pronaca_plotly(fig_zona, 390), use_container_width=True)
        else:
            st.info("No hay datos por zona para mostrar con los filtros actuales.")

    st.subheader("Detalle por etapa")
    if "Etapa" in snap_f.columns and not snap_f.empty:
        etapa_detail = snap_f.groupby("Etapa", as_index=False).agg(
            **{
                "Lotes": ("LoteCompleto", "nunique"),
                "Aves vivas": ("AvesVivas", "sum"),
                "Peso promedio (kg)": ("PesoActual", "mean"),
                "Mortalidad (%)": ("MortalidadPct", "mean"),
                "Edad promedio": ("EdadActual", "mean")
            }
        ).sort_values("Edad promedio")
        st.dataframe(etapa_detail.round(2), use_container_width=True, hide_index=True)
    else:
        st.info("No hay detalle por etapa disponible con los filtros actuales.")

# ============================================================
# TAB 2: ZONAS
# ============================================================
with tab2:
    st.subheader("Indicadores por zona")

    if "ZonaNombre" not in snap_f.columns or snap_f.empty:
        st.info("No hay datos por zona con los filtros actuales.")
    else:
        by_z = snap_f.groupby("ZonaNombre", as_index=False).agg(
            AvesVivas=("AvesVivas", "sum"),
            Lotes=("LoteCompleto", "nunique"),
            PesoProm=("PesoActual", "mean"),
            MortProm=("MortalidadPct", "mean"),
        )

        fig = px.bar(
            by_z,
            x="ZonaNombre",
            y="AvesVivas",
            color="Lotes",
            title="Aves vivas por zona (color = cantidad de lotes)",
            labels={"ZonaNombre": "Zona", "AvesVivas": "Aves vivas", "Lotes": "Lotes"},
            # 👇 Escala que NUNCA llega a blanco
            color_continuous_scale=[
                (0.0, "#64748B"),   # gris/azul oscuro para el mínimo
                (1.0, PRONACA_RED)  # rojo Pronaca para el máximo
            ],
            range_color=(by_z["Lotes"].min(), by_z["Lotes"].max())
        )
        st.plotly_chart(apply_pronaca_plotly(fig, 420), use_container_width=True)
        st.dataframe(by_z.round(2), use_container_width=True, hide_index=True)

# ============================================================
# TAB 3: ALERTAS
# ============================================================
with tab3:
    st.subheader("Alertas operativas")

    if "MortalidadPct" not in snap_f.columns:
        st.info("No existe la columna MortalidadPct en el dataset.")
    else:
        snap_alert = snap_f[snap_f["MortalidadPct"] >= mort_alert].copy()

        if snap_alert.empty:
            st.success("Sin lotes en alerta con el umbral actual.")
        else:
            st.warning(f"Lotes en alerta: {snap_alert['LoteCompleto'].nunique():,} (mortalidad ≥ {mort_alert}%)")

            colC, colD = st.columns([1.6, 1])
            with colC:
                top = (snap_alert.drop_duplicates("LoteCompleto")
                              .nlargest(15, "MortalidadPct")[["LoteCompleto", "MortalidadPct", "ZonaNombre"]])
                top = top.sort_values("MortalidadPct")

                fig = px.bar(
                    top,
                    x="MortalidadPct",
                    y="LoteCompleto",
                    color="ZonaNombre",
                    orientation="h",
                    title="Top 15 lotes con mayor mortalidad",
                    labels={"MortalidadPct": "Mortalidad (%)", "LoteCompleto": "Lote", "ZonaNombre": "Zona"}
                )
                st.plotly_chart(apply_pronaca_plotly(fig, 430), use_container_width=True)

            with colD:
                cols_show = [c for c in ["LoteCompleto", "ZonaNombre", "Granja", "EdadActual", "MortalidadPct"] if c in snap_alert.columns]
                table = (snap_alert[cols_show]
                         .drop_duplicates("LoteCompleto")
                         .sort_values("MortalidadPct", ascending=False)
                         .head(12))
                st.dataframe(table.round(2), use_container_width=True, hide_index=True)

# ============================================================
# TAB 4: DETALLE POR LOTE
# ============================================================
with tab4:
    st.subheader("Análisis detallado por lote")

    tipo = st.radio("Estado", ["Todos", "Abiertos", "Cerrados"], horizontal=True, key="tipo_lote")

    if tipo == "Abiertos":
        lotes_avail = snap_f[snap_f.get("EstadoLote", "") == "ABIERTO"]["LoteCompleto"].unique()
    elif tipo == "Cerrados":
        lotes_avail = snap_f[snap_f.get("EstadoLote", "") == "CERRADO"]["LoteCompleto"].unique()
    else:
        lotes_avail = snap_f["LoteCompleto"].unique()

    lotes_list = sorted([l for l in lotes_avail if pd.notna(l)])
    search = st.text_input("Buscar lote", key="lote_search", placeholder="Ej: BUC1006, STO5069, 2506-01")
    if search:
        lotes_list = [x for x in lotes_list if search.upper() in str(x).upper()]

    if not lotes_list:
        st.info("No hay lotes disponibles con los filtros actuales.")
        st.stop()

    lote_sel = st.selectbox("Seleccionar lote", lotes_list, key="lote_detail")
    lote_data = df[df["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
    if lote_data.empty:
        st.info("No hay información para el lote seleccionado.")
        st.stop()

    estado = lote_data["EstadoLote"].iloc[-1] if "EstadoLote" in lote_data.columns else "—"
    zona = zona_nombre(lote_data["Zona"].iloc[-1]) if "Zona" in lote_data.columns else "—"
    granja = lote_data["Granja"].iloc[-1] if "Granja" in lote_data.columns else "—"
    sexo = lote_data["Sexo"].iloc[-1] if "Sexo" in lote_data.columns else "S"
    edad_max = int(lote_data["Edad"].max()) if "Edad" in lote_data.columns and pd.notna(lote_data["Edad"].max()) else 0

    peso_last = lote_data["PesoFinal"].iloc[-1] if "PesoFinal" in lote_data.columns else np.nan
    exp_last = CURVA.get(edad_max, {}).get(str(sexo).upper(), CURVA.get(edad_max, {}).get("S", np.nan))
    delta_curva = (peso_last - exp_last) if pd.notna(peso_last) and pd.notna(exp_last) else np.nan

    # Tarjetas del lote
    def kpi_card_local(label, value, accent=False):
        cls = "kpi-card kpi-accent" if accent else "kpi-card"
        st.markdown(f"""
        <div class="{cls}">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value" style="font-size:1.25rem">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    a, b, c, d, e, f = st.columns(6)
    with a: kpi_card_local("Lote", str(lote_sel), accent=True)
    with b: kpi_card_local("Estado", str(estado))
    with c: kpi_card_local("Zona", str(zona))
    with d: kpi_card_local("Granja", str(granja))
    with e: kpi_card_local("Edad actual", f"{edad_max}")
    with f: kpi_card_local("Desviación vs curva", fmt_float(delta_curva, 3, " kg"), accent=True)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if "PesoFinal" in lote_data.columns and "Edad" in lote_data.columns:
            edades = lote_data["Edad"].dropna().astype(int).tolist()
            curva_y = curva_series(sexo, edades)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=lote_data["Edad"], y=lote_data["PesoFinal"], mode="lines+markers", name="Real (PesoFinal)"))
            fig.add_trace(go.Scatter(x=edades, y=curva_y, mode="lines", name="Curva biológica", line=dict(dash="dash")))
            fig.update_layout(title="Peso por edad (real vs curva)", xaxis_title="Edad (días)", yaxis_title="Peso (kg)")
            st.plotly_chart(apply_pronaca_plotly(fig, 430), use_container_width=True)
        else:
            st.info("No existe información suficiente para graficar PesoFinal vs Edad.")

    with col2:
        if "MortalidadAcumulada" in lote_data.columns and "Edad" in lote_data.columns:
            fig_m = px.area(
                lote_data, x="Edad", y="MortalidadAcumulada",
                title="Mortalidad acumulada por edad",
                labels={"MortalidadAcumulada": "Aves", "Edad": "Edad (días)"}
            )
            st.plotly_chart(apply_pronaca_plotly(fig_m, 430), use_container_width=True)
        else:
            st.info("No existe información suficiente para graficar MortalidadAcumulada vs Edad.")

    st.subheader("Datos del lote")
    cols_show = [c for c in [
        "FechaTransaccion", "Edad", "Peso", "PesoFinal",
        "Mortalidad", "Descarte", "MortalidadAcumulada",
        "AvesVivas", "Aves Neto", "Galpon"
    ] if c in lote_data.columns]
    st.dataframe(lote_data[cols_show], use_container_width=True, height=420)

st.divider()
st.caption("PRONACA | Producción Avícola — Panel operativo (estado actual)")