import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ============================================================
# CONFIG STREAMLIT
# ============================================================
st.set_page_config(
    page_title="Producción AHORA – Línea Productiva",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
def to_dt(s):
    return pd.to_datetime(s, errors="coerce")

def to_num(s):
    return pd.to_numeric(s, errors="coerce")

@st.cache_data(show_spinner=False)
def load_excel(file_path_or_bytes):
    try:
        df = pd.read_excel(file_path_or_bytes, sheet_name="final", engine="openpyxl")
    except Exception:
        df = pd.read_excel(file_path_or_bytes, engine="openpyxl")
    
    # Fechas
    for c in ["FechaTransaccion", "Cierre de campaña", "Fecha recepción"]:
        if c in df.columns:
            df[c] = to_dt(df[c])
    
    # Números
    num_cols = [
        "Edad","Peso","PesoFinal","Mortalidad","Descarte","MortalidadTotalDia","MortalidadAcumulada",
        "Aves Planta","Aves Neto","AvesVivas","EdadVenta","Kilos Neto","AvesVivasVenta","PesoSalidaKg",
        "UltimoReal7","Galpon"
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = to_num(df[c])
    
    # Strings
    if "Sexo" in df.columns:
        df["Sexo"] = df["Sexo"].astype(str).str.upper().replace({"NAN": np.nan, "NONE": np.nan})
    if "EstadoLote" in df.columns:
        df["EstadoLote"] = df["EstadoLote"].astype(str).str.upper()
    
    # Zona (de LoteCompleto: BUC = Bucaya, STD = Santo Domingo)
    if "LoteCompleto" in df.columns:
        df["Zona"] = df["LoteCompleto"].astype(str).str.extract(r"^(BUC|STO)", expand=False)
    
    return df

def extract_zona(lote_str):
    """Extrae zona (BUC, STD, etc.) del código de lote"""
    if pd.isna(lote_str):
        return "OTRO"
    lote = str(lote_str).upper()
    if lote.startswith("BUC"):
        return "BUCAYA"
    elif lote.startswith("STD"):
        return "SANTO DOMINGO"
    else:
        return "OTRO"

def get_etapa(edad):
    """Clasifica edad en etapas productivas"""
    try:
        e = float(edad)
    except:
        return "DESCONOCIDO"
    
    if e <= 14:
        return "Inicio (1-14)"
    elif e <= 28:
        return "Crecimiento (15-28)"
    elif e <= 35:
        return "Pre-acabado (29-35)"
    elif e <= 42:
        return "Acabado (36-42)"
    else:
        return "Final (43+)"

def build_snapshot(df, corte_dt=None):
    """
    Snapshot AHORA: última fila por lote (por edad más reciente)
    """
    if df.empty:
        return pd.DataFrame()
    
    d = df.copy()
    
    if corte_dt and "FechaTransaccion" in d.columns:
        d = d[d["FechaTransaccion"].notna() & (d["FechaTransaccion"] <= corte_dt)]
    
    # Última por lote
    if "FechaTransaccion" in d.columns:
        d = d.sort_values(["LoteCompleto", "FechaTransaccion", "Edad"])
    else:
        d = d.sort_values(["LoteCompleto", "Edad"])
    
    last = d.groupby("LoteCompleto").tail(1).copy()
    
    # Alias
    last["EdadActual"] = last["Edad"]
    last["PesoActual"] = last.get("PesoFinal", last.get("Peso", np.nan))
    
    # Mortalidad %
    if "Aves Neto" in last.columns and "MortalidadAcumulada" in last.columns:
        last["MortalidadPct"] = np.where(
            last["Aves Neto"].fillna(0) > 0,
            (last["MortalidadAcumulada"].fillna(0) / last["Aves Neto"].fillna(0)) * 100,
            np.nan
        )
    
    # Etapa
    last["Etapa"] = last["EdadActual"].apply(get_etapa)
    
    return last

# ============================================================
# LOAD DATA
# ============================================================
default_path = "produccion_actual_final.xlsx"

if not os.path.exists(default_path):
    st.error("❌ No se encontró 'produccion_actual_final.xlsx' en la carpeta actual.")
    st.stop()

df = load_excel(default_path)

if df.empty:
    st.error("Dataset vacío. Revisa el archivo.")
    st.stop()

# Corte
corte = df["FechaTransaccion"].max() if "FechaTransaccion" in df.columns else datetime.now()
snap = build_snapshot(df, corte_dt=corte)

with st.sidebar:
    st.header("📊 Datos")
    st.success(f"✅ Cargado: produccion_actual_final.xlsx")
    st.caption(f"Corte: {corte.date() if pd.notna(corte) else 'N/A'}")

# ============================================================
# SIDEBAR FILTROS
# ============================================================
with st.sidebar:
    st.divider()
    st.header("🎯 Filtros")
    
    # Zona
    zonas_avail = snap["Zona"].dropna().unique() if "Zona" in snap.columns else []
    zonas_default = sorted(zonas_avail) if len(zonas_avail) > 0 else []
    sel_zonas = st.multiselect("Zona", zonas_default, default=zonas_default, key="zonas")
    
    # Estado
    estados_avail = ["ABIERTO", "CERRADO"]
    if "EstadoLote" in snap.columns:
        estados_avail = sorted(snap["EstadoLote"].dropna().unique())
    sel_estados = st.multiselect("Estado lote", estados_avail, default=["ABIERTO", "CERRADO"], key="estados")
    
    # Sexo
    sexos_avail = snap["Sexo"].dropna().unique() if "Sexo" in snap.columns else []
    sel_sexos = st.multiselect("Sexo", sorted(sexos_avail), default=sorted(sexos_avail), key="sexos")
    
    st.divider()
    st.header("⚙️ Umbrales")
    
    mort_alert = st.slider("Alerta mortalidad (%)", 0, 20, 7, 1)
    st.divider()

# Aplicar filtros
snap_f = snap.copy()

if sel_zonas and "Zona" in snap_f.columns:
    snap_f = snap_f[snap_f["Zona"].isin(sel_zonas)]

if sel_estados and "EstadoLote" in snap_f.columns:
    snap_f = snap_f[snap_f["EstadoLote"].isin(sel_estados)]

if sel_sexos and "Sexo" in snap_f.columns:
    snap_f = snap_f[snap_f["Sexo"].isin(sel_sexos)]

# ============================================================
# MAIN LAYOUT
# ============================================================

# Header
st.markdown("""
<style>
    h1 { font-size: 2.8em; margin-bottom: 0.2em; }
</style>
""", unsafe_allow_html=True)

st.title("📈 Producción AHORA")
st.caption(f"Estado actual de la línea productiva | Corte: {corte.date() if pd.notna(corte) else 'N/A'}")

# ============================================================
# SECTION 1: KPIs GERENCIALES
# ============================================================
st.markdown("## 🎯 Situación Actual (Resumen Ejecutivo)")

kpi_cols = st.columns([1.2, 1, 1, 1.2, 1, 1])

# Total lotes
with kpi_cols[0]:
    lotes_tot = snap_f["LoteCompleto"].nunique()
    st.metric(
        "Lotes Total",
        f"{lotes_tot:,}",
        delta=None,
        help="Lotes únicos en período"
    )

# Abiertos
with kpi_cols[1]:
    lotes_abiertos = snap_f[snap_f["EstadoLote"] == "ABIERTO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
    st.metric("🔴 Activos", f"{lotes_abiertos:,}")

# Cerrados
with kpi_cols[2]:
    lotes_cerrados = snap_f[snap_f["EstadoLote"] == "CERRADO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
    st.metric("✅ Cerrados", f"{lotes_cerrados:,}")

# Aves vivas
with kpi_cols[3]:
    aves_vivas = snap_f["AvesVivas"].fillna(0).sum()
    st.metric(
        "Aves Vivas",
        f"{int(aves_vivas):,}",
        help="Población actual en engorde"
    )

# Mortalidad promedio
with kpi_cols[4]:
    mort_prom = snap_f["MortalidadPct"].mean() if "MortalidadPct" in snap_f.columns else np.nan
    color_mort = "🔴" if pd.notna(mort_prom) and mort_prom >= mort_alert else "🟢"
    st.metric(f"{color_mort} Mort. Prom.", f"{mort_prom:.2f}%" if pd.notna(mort_prom) else "—")

# Peso promedio
with kpi_cols[5]:
    peso_prom = snap_f["PesoActual"].mean() if "PesoActual" in snap_f.columns else np.nan
    st.metric("Peso Prom.", f"{peso_prom:.3f} kg" if pd.notna(peso_prom) else "—")

st.divider()

# ============================================================
# SECTION 2: LÍNEA PRODUCTIVA POR ETAPA
# ============================================================
st.markdown("## 📊 Línea Productiva – Distribución por Etapa")

col_etapa, col_zona = st.columns([2, 1.5])

# Etapas
with col_etapa:
    if "Etapa" in snap_f.columns:
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
            color_continuous_scale="Viridis",
            title="Lotes activos por etapa de engorde",
            labels={"Lotes": "# Lotes", "PesoPromedio": "Peso prom. (kg)"}
        )
        fig_etapa.update_layout(height=380, showlegend=True)
        st.plotly_chart(fig_etapa, use_container_width=True)

# Zonas
with col_zona:
    if "Zona" in snap_f.columns:
        by_zona = snap_f.groupby("Zona", as_index=False).agg(Lotes=("LoteCompleto", "nunique"))
        
        fig_zona = px.pie(
            by_zona,
            names="Zona",
            values="Lotes",
            title="Distribución por Zona",
            hole=0.4
        )
        fig_zona.update_layout(height=380)
        st.plotly_chart(fig_zona, use_container_width=True)

# Tabla resumen por etapa
st.markdown("### Detalle por Etapa")
etapa_detail = snap_f.groupby("Etapa", as_index=False).agg(
    **{
        "Lotes": ("LoteCompleto", "nunique"),
        "Aves Vivas": ("AvesVivas", "sum"),
        "Peso Prom (kg)": ("PesoActual", "mean"),
        "Mortalidad Pct": ("MortalidadPct", "mean"),
        "Edad Prom": ("EdadActual", "mean")
    }
).sort_values("Edad Prom")

st.dataframe(
    etapa_detail.round(2),
    use_container_width=True,
    hide_index=True
)

st.divider()

# ============================================================
# SECTION 3: IMPACTO POR ZONA
# ============================================================
if "Zona" in snap_f.columns and len(sel_zonas) > 0:
    st.markdown("## 🗺️ Impacto por Zona")
    
    cols_zona = st.columns(len(sel_zonas))
    
    for idx, zona in enumerate(sorted(sel_zonas)):
        snap_zona = snap_f[snap_f["Zona"] == zona]
        
        with cols_zona[idx]:
            st.markdown(f"### {zona}")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                lotes_z = snap_zona["LoteCompleto"].nunique()
                st.metric("Lotes", lotes_z)
            with c2:
                aves_z = snap_zona["AvesVivas"].fillna(0).sum()
                st.metric("Aves", f"{int(aves_z):,}")
            with c3:
                mort_z = snap_zona["MortalidadPct"].mean()
                st.metric("Mort %", f"{mort_z:.2f}%" if pd.notna(mort_z) else "—")

st.divider()

# ============================================================
# SECTION 4: ALERTAS DE MORTALIDAD
# ============================================================
st.markdown("## ⚠️ Alertas – Acción Requerida")

snap_alert = snap_f[snap_f["MortalidadPct"] >= mort_alert].copy() if "MortalidadPct" in snap_f.columns else pd.DataFrame()

if not snap_alert.empty:
    st.markdown(f"### 🔴 Mortalidad Alta (>= {mort_alert}%)")
    
    col_chart, col_table = st.columns([1.5, 1])
    
    with col_chart:
        alert_chart = snap_alert.nlargest(15, "MortalidadPct")[["LoteCompleto", "MortalidadPct", "Zona"]].copy()
        
        fig_alert = px.bar(
            alert_chart,
            x="LoteCompleto",
            y="MortalidadPct",
            color="Zona",
            title="Top lotes con mortalidad alta",
            labels={"MortalidadPct": "Mortalidad (%)", "LoteCompleto": "Lote"}
        )
        fig_alert.update_layout(xaxis_tickangle=-45, height=380)
        st.plotly_chart(fig_alert, use_container_width=True)
    
    with col_table:
        st.markdown(f"**Lotes en alerta: {snap_alert['LoteCompleto'].nunique()}**")
        alert_show = snap_alert[["LoteCompleto", "Zona", "EdadActual", "MortalidadPct", "Granja"]].drop_duplicates("LoteCompleto").sort_values("MortalidadPct", ascending=False).head(10)
        st.dataframe(alert_show.round(2), use_container_width=True, hide_index=True)
else:
    st.success("✅ Sin alertas de mortalidad en los filtros aplicados.")

st.divider()

# ============================================================
# SECTION 5: ANÁLISIS DETALLADO POR LOTE (CON RADIO BUTTONS)
# ============================================================
st.markdown("## 🔍 Análisis Detallado por Lote")

# Radio button para filtrar ABIERTO vs CERRADO
col_radio1, col_radio2 = st.columns([3, 1])
with col_radio1:
    tipo_lote = st.radio(
        "Filtrar por estado:",
        ["📊 Todos", "🔴 Abiertos", "✅ Cerrados"],
        horizontal=True,
        key="tipo_lote_radio"
    )
with col_radio2:
    st.empty()

# Aplicar filtro de tipo
if tipo_lote == "🔴 Abiertos":
    lotes_avail = snap_f[snap_f["EstadoLote"] == "ABIERTO"]["LoteCompleto"].unique()
elif tipo_lote == "✅ Cerrados":
    lotes_avail = snap_f[snap_f["EstadoLote"] == "CERRADO"]["LoteCompleto"].unique()
else:
    lotes_avail = snap_f["LoteCompleto"].unique()

lotes_list = sorted([l for l in lotes_avail if pd.notna(l)])

# Contabilización
conteo_cols = st.columns([1, 1, 1])

with conteo_cols[0]:
    total_lotes = snap_f["LoteCompleto"].nunique()
    st.metric("Total Lotes", f"{total_lotes:,}")

with conteo_cols[1]:
    abiertos = snap_f[snap_f["EstadoLote"] == "ABIERTO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
    st.metric("🔴 Abiertos", f"{abiertos:,}")

with conteo_cols[2]:
    cerrados = snap_f[snap_f["EstadoLote"] == "CERRADO"]["LoteCompleto"].nunique() if "EstadoLote" in snap_f.columns else 0
    st.metric("✅ Cerrados", f"{cerrados:,}")

# Mostrar según filtro
st.markdown(f"### Lotes disponibles ({len(lotes_list)})")

if len(lotes_list) > 0:
    lote_sel = st.selectbox(
        "Selecciona un lote",
        lotes_list,
        key="lote_detail"
    )
    
    # Datos completos del lote seleccionado
    lote_data = df[df["LoteCompleto"] == lote_sel].sort_values("Edad").copy()
    
    if not lote_data.empty:
        # Tarjetas
        card_cols = st.columns([1, 1, 1, 1, 1])
        
        with card_cols[0]:
            estado = lote_data["EstadoLote"].iloc[-1] if "EstadoLote" in lote_data.columns else "—"
            st.metric("Estado", f"🔴 {estado}" if estado == "ABIERTO" else f"✅ {estado}")
        
        with card_cols[1]:
            zona = lote_data["Zona"].iloc[-1] if "Zona" in lote_data.columns else "—"
            st.metric("Zona", zona)
        
        with card_cols[2]:
            granja = lote_data["Granja"].iloc[-1] if "Granja" in lote_data.columns else "—"
            st.metric("Granja", granja)
        
        with card_cols[3]:
            sexo = lote_data["Sexo"].iloc[-1] if "Sexo" in lote_data.columns else "—"
            st.metric("Sexo", sexo)
        
        with card_cols[4]:
            edad_max = int(lote_data["Edad"].max()) if "Edad" in lote_data.columns else 0
            st.metric("Edad Actual", edad_max)
        
        # Gráficos
        fig_col1, fig_col2 = st.columns(2)
        
        # Peso Final por Edad
        with fig_col1:
            if "PesoFinal" in lote_data.columns and "Edad" in lote_data.columns:
                fig_peso = px.line(
                    lote_data,
                    x="Edad",
                    y="PesoFinal",
                    markers=True,
                    title="PesoFinal por edad (curva + real)",
                    labels={"PesoFinal": "Peso (kg)", "Edad": "Edad (días)"}
                )
                fig_peso.update_traces(marker=dict(size=6))
                fig_peso.update_layout(height=380)
                st.plotly_chart(fig_peso, use_container_width=True)
        
        # Mortalidad acumulada
        with fig_col2:
            if "MortalidadAcumulada" in lote_data.columns and "Edad" in lote_data.columns:
                fig_mort = px.area(
                    lote_data,
                    x="Edad",
                    y="MortalidadAcumulada",
                    title="Mortalidad acumulada por edad",
                    labels={"MortalidadAcumulada": "# Aves", "Edad": "Edad (días)"}
                )
                fig_mort.update_layout(height=380)
                st.plotly_chart(fig_mort, use_container_width=True)
        
        # Tabla completa
        st.markdown("### Datos Completos del Lote")
        cols_show = [c for c in ["Edad", "Peso", "PesoFinal", "FechaTransaccion", "Mortalidad", 
                                  "Descarte", "MortalidadAcumulada", "AvesVivas", "Galpon"] 
                     if c in lote_data.columns]
        st.dataframe(
            lote_data[cols_show],
            use_container_width=True,
            height=350
        )
else:
    st.info(f"No hay lotes {tipo_lote} en los filtros aplicados.")

# ============================================================
# FOOTER
# ============================================================
st.divider()
st.markdown("""
---
**Dashboard de Producción AHORA** | Enfocado en estado actual, no comparaciones históricas ni proyecciones.
""")