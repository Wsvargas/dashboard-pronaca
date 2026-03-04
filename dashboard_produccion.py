"""
PRONACA | Dashboard Producción Avícola v15 - CON BOTÓN DE PREDICCIÓN
====================================================================

Mejora principal:
  - Botón "Ejecutar Predicción" que permite ejecutar manualmente
  - Muestra debug info para verificar qué datos se están pasando
  - Sincronización correcta de datos con el lote seleccionado

Ejecutar:
    streamlit run dashboard_produccion_v15_CON_BOTON.py
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
MAIN_FILE         = "produccion_actual_final_con_costos_alimento_v3.xlsx"
BENCH_FILE        = "20_MEJORES_LOTES_POR_CONVERSION.xlsx"
EDAD_MIN_ANALISIS = 7

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PRONACA | Producción Avícola v15",
    layout="wide",
    initial_sidebar_state="collapsed",
)
# ✅ Router simple (dashboard / predictiva)
if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"
if st.session_state["page"] == "predictiva":
    import tool_predictiva
    tool_predictiva.render()
    st.stop()
def go_predictiva():
    st.session_state["page"] = "predictiva"
    st.rerun()

def go_dashboard():
    st.session_state["page"] = "dashboard"
    st.rerun()

# ✅ Si estoy en la herramienta, salto TODO lo demás (no cargo Excel)
if st.session_state["page"] == "predictiva":
    import tool_predictiva
    tool_predictiva.render(go_dashboard=go_dashboard)
    st.stop()
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


def _file_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0

@st.cache_resource(show_spinner=False)
def get_predictor_cached(model_path: str, model_mtime: float):
    # Import interno para evitar recargas raras / circular imports
    from model_predictor import cargar_predictor
    return cargar_predictor(model_path)
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


def _console_df_info(df: pd.DataFrame, nombre: str, cols: list[str] | None = None, head: int = 8):
    try:
        print("\n" + "="*90)
        print(f"[DEBUG] {nombre}")
        print(f"  shape: {df.shape}")
        if cols:
            cols_ok = [c for c in cols if c in df.columns]
            print(f"  cols: {cols_ok}")
        if len(df) > 0:
            if cols:
                print(df[cols_ok].head(head).to_string(index=False))
            else:
                print(df.head(head).to_string(index=False))
        print("="*90 + "\n")
    except Exception as e:
        print(f"[DEBUG] Error imprimiendo df '{nombre}': {e}")

def _reset_pred_if_lote_changed(lote_sel: str):
    # Limpia predicción guardada si cambiaste de lote
    if st.session_state.get("lote_anterior") != lote_sel:
        st.session_state["prediccion_resultado"] = None
        st.session_state["lote_anterior"] = lote_sel
        print(f"[DEBUG] Lote cambió -> reset prediccion_resultado. lote_anterior={lote_sel}")
        

def _limpiar_historial_para_modelo(hist: pd.DataFrame) -> pd.DataFrame:
    h = hist.copy()

    # Edad
    h["Edad"] = pd.to_numeric(h.get("Edad"), errors="coerce")
    h = h[h["Edad"].notna()].copy()
    h["Edad"] = h["Edad"].astype(int)

    # PesoFinal
    h["PesoFinal"] = pd.to_numeric(h.get("PesoFinal"), errors="coerce")
    h = h[h["PesoFinal"].notna()].copy()
    h = h[h["PesoFinal"] > 0].copy()   # ✅ clave: fuera ceros

    h = h.sort_values("Edad").copy()

    # ✅ si está ABIERTO: usar múltiplos de 7 PERO conservar el último registro válido
    estado = str(h.get("EstadoLote").iloc[-1] if "EstadoLote" in h.columns else "ABIERTO").upper()
    if estado != "CERRADO":
        h7 = h[h["Edad"] % 7 == 0].copy()

        # último registro válido (siempre)
        last_row = h.iloc[[-1]].copy()

        if not h7.empty:
            h = pd.concat([h7, last_row], ignore_index=True)
        else:
            h = last_row

        # por si last_row ya era múltiplo de 7, evita duplicar esa edad
        h = h.drop_duplicates(subset=["Edad"], keep="last").copy()

    # duplicados por edad (seguridad)
    h = h.drop_duplicates(subset=["Edad"], keep="last").copy()
    return h

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
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 12px 14px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}
.pronaca-header {{
    background: {BLACK};
    border-radius: 14px;
    padding: 14px 20px;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 14px;
}}
.pronaca-header-title {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.0rem;
    color: #fff;
    letter-spacing: 1.4px;
    line-height: 1.1;
}}
.pronaca-header-sub {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.55);
    margin-top: 2px;
}}
.pronaca-header-pill {{
    margin-left: auto;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 0.85rem;
    color: rgba(255,255,255,0.75) !important;
    white-space: nowrap;
}}
.filter-bar {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 10px 14px;
    margin-bottom: 10px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}}
.kpi-chip {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 10px 14px;
    min-width: 150px;
    flex: 1;
    box-shadow: 0 1px 5px rgba(0,0,0,0.04);
}}
.kpi-chip.accent {{ border-left: 4px solid {RED}; }}
.kv {{
    font-size: 1.35rem;
    font-weight: 900;
    color: {TEXT};
    line-height: 1;
}}
.kl {{
    font-size: 0.70rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: {MUTED} !important;
    margin-top: 3px;
}}
.sec-header {{
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 8px 0 6px 0;
    margin: 4px 0 6px 0;
    border-bottom: 2px solid {BORDER};
}}
.sec-num {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.0rem;
    color: {RED};
    line-height: 1;
}}
.sec-title {{
    font-size: 1.0rem;
    font-weight: 900;
    color: {TEXT};
    line-height: 1.2;
}}
.sec-sub {{
    font-size: 0.78rem;
    color: {MUTED} !important;
    margin-top: 1px;
}}
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 900;
    border: 1px solid {BORDER};
    background: #F8FAFC;
}}
.badge.red   {{ color: {RED};   border-color: rgba(218,41,28,.25); background: rgba(218,41,28,.06); }}
.badge.amber {{ color: {AMBER}; border-color: rgba(217,119,6,.25);  background: rgba(217,119,6,.07); }}
.badge.green {{ color: {GREEN}; border-color: rgba(22,163,74,.25);  background: rgba(22,163,74,.07); }}
.sel-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(218,41,28,0.08);
    border: 1px solid rgba(218,41,28,0.25);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 800;
    color: {RED};
    margin-bottom: 6px;
}}
.sel-pill-neutral {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(29,78,216,0.08);
    border: 1px solid rgba(29,78,216,0.20);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 800;
    color: {BLUE};
    margin-bottom: 6px;
}}
.hint-text {{
    font-size: 0.72rem;
    color: {MUTED};
    font-style: italic;
    margin-bottom: 4px;
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

    col_lote   = pick_first_col(df, ["LoteCompleto","Codigo_Unico","Lote"])
    if not col_lote:
        raise ValueError("No encuentro columna de lote.")

    col_edad   = pick_first_col(df, ["Edad","edad","X4=Edad"])
    col_peso   = pick_first_col(df, ["PesoFinal","Peso","Y=Peso comp","Peso comp"])
    col_aves   = pick_first_col(df, ["AvesVivas","Aves Vivas","Aves_netas","Aves Neto","Aves Neto "])

    col_cost   = pick_first_col(df, ["CostoAlimentoAcum","Costo alim acum","CostoAlimentoAcumulado","CostoAlimento_acumulado"])
    col_alimkg = pick_first_col(df, ["Alimento_acumulado_kg","Alimento acum","Alimento_acum","AlimAcumKg"])
    col_alim_dia = pick_first_col(df, ["AlimentoConsumido","Alimento Consumido","Alimento_consumido"])

    col_zona   = pick_first_col(df, ["zona","Zona"])
    col_tipo   = pick_first_col(df, ["TipoGranja","Tipo_Granja","Tipo de granja","X30=Granja Propia"])
    col_quint  = pick_first_col(df, ["quintil","Quintil_Area_Crianza","Quintil"])
    col_est    = pick_first_col(df, ["Estatus","ESTATUS","Status"])
    col_estado = pick_first_col(df, ["EstadoLote","Estado_Lote","estado_lote","ESTADO LOTE"])

    # opcional: detectar “cierre” (en tu Excel viene como "Cierre de campaña")
    col_cierre = pick_first_col(df, ["Cierre de campaña","CierreCampaña","FechaCierre","Cierre"])

    # Renombres base
    df = df.rename(columns={
        col_lote: "LoteCompleto",
        col_edad: "Edad",
        col_peso: "PesoFinal",
        col_aves: "AvesVivas",
    })

    # Parse numéricos
    for c in [
        "unit_cost_final",
        "CostoAlimentoDia",
        "CostoAlimentoAcum",
        "CostoKgAlim",
        "CostoAlimentoPorAveDia",
        "CostoAlimentoPorAveAcum",
        "AlimentoConsumido",
    ]:
        if c in df.columns:
            df[c] = parse_num_series(df[c])

    # Estados
    df["Estatus"]    = df[col_est].astype(str).str.upper().str.strip() if col_est else "ACTIVO"
    df["EstadoLote"] = df[col_estado].astype(str).str.upper().str.strip() if col_estado else "ABIERTO"

    # Zona
    if col_zona:
        z = parse_num_series(df[col_zona]).fillna(0).astype(int)
        df["ZonaNombre"] = np.where(z == 1, "BUCAY", "SANTO DOMINGO")
    else:
        pref = df["LoteCompleto"].astype(str).str[:3].str.upper()
        df["ZonaNombre"] = pref.map({"BUC":"BUCAY","STO":"SANTO DOMINGO"}).fillna("OTRA")

    df["GranjaID"] = df["LoteCompleto"].astype(str).str[:7]

    # Tipo granja
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

    # Quintil (texto normalizado)
    df["Quintil"] = df[col_quint].astype(str).str.upper().str.strip() if col_quint else "Q5"

    # ✅ limpia formatos raros (ej: "Q5 ", "quintil Q5", "Q5.0", etc.)
    df["Quintil"] = (
        df["Quintil"]
        .astype(str)
        .str.upper()
        .str.strip()
        .str.extract(r"(Q[1-5])", expand=False)   # toma solo Q1..Q5
        .fillna("Q5")
    )

    # ✅ versión numérica para el modelo
    df["Quintil_num"] = df["Quintil"].map({"Q1":1, "Q2":2, "Q3":3, "Q4":4, "Q5":5}).astype(float)
    df["Etapa"]   = df["Edad"].apply(get_etapa)

    # Costos / alimento
    df["CostoAcum"] = parse_num_series(df[col_cost]) if col_cost else np.nan

    # 1) Si ya existe alimento acumulado, úsalo
    if col_alimkg:
        df["AlimAcumKg"] = parse_num_series(df[col_alimkg])
    else:
        df["AlimAcumKg"] = np.nan

    # 2) Si existe AlimentoConsumido, construye acumulado real por lote (tu regla)
    if col_alim_dia:
        df["_alim_dia"] = parse_num_series(df[col_alim_dia]).fillna(0)

        # orden base
        df = df.sort_values(["LoteCompleto","Edad"]).copy()

        # acumulado por lote
        df["AlimAcumKg"] = df.groupby("LoteCompleto")["_alim_dia"].cumsum()

    # ──────────────────────────────────────────────────────────
    # ✅ CORTE POR LOTE (tu lógica de múltiplos de 7)
    # ABIERTO: cortar en último múltiplo de 7 con PesoFinal válido (>0)
    # CERRADO o con fecha de cierre: cortar en último día con PesoFinal válido (>0)
    # ──────────────────────────────────────────────────────────
    df = df.sort_values(["LoteCompleto","Edad"]).copy()

    # marca “tiene cierre” si hay columna y no es NaN
    if col_cierre and col_cierre in df.columns:
        cierre_flag = df[col_cierre].notna()
    else:
        cierre_flag = pd.Series(False, index=df.index)

    # define “peso válido”
    peso_ok = df["PesoFinal"].notna() & (df["PesoFinal"] > 0)

    def _corte_por_lote(g: pd.DataFrame) -> int:
        estado = str(g["EstadoLote"].iloc[0]).upper()
        tiene_cierre = bool(cierre_flag.loc[g.index].any()) or (estado == "CERRADO")

        gg = g.copy()
        # candidatos con peso válido
        gg = gg[peso_ok.loc[g.index]].copy()
        if gg.empty:
            # si no hay peso válido, al menos devuelve el máximo edad que exista
            return int(g["Edad"].max()) if g["Edad"].notna().any() else 0

        if tiene_cierre:
            return int(gg["Edad"].max())

        # ABIERTO: último múltiplo de 7 con peso válido
        gg7 = gg[gg["Edad"].astype(int) % 7 == 0]
        if not gg7.empty:
            return int(gg7["Edad"].max())

        # fallback: si no hay múltiplos de 7, usa el último con peso válido
        return int(gg["Edad"].max())

    cortes = df.groupby("LoteCompleto", sort=False).apply(_corte_por_lote).rename("EdadCorte")
    df = df.merge(cortes, on="LoteCompleto", how="left")
    df = df[df["Edad"] <= df["EdadCorte"]].copy()

    # Métricas derivadas
    df["KgLive"]      = (df["AvesVivas"] * df["PesoFinal"]).astype(float)
    df["CostoKg_Cum"] = df["CostoAcum"]  / df["KgLive"].replace(0, np.nan)
    df["FCR_Cum"]     = df["AlimAcumKg"] / df["KgLive"].replace(0, np.nan)

    # Mortalidad (si existe)
    col_mort = pick_first_col(df, ["MortalidadAcumulada","MORTALIDAD + DESCARTE"])
    col_neto = pick_first_col(df, ["Aves Neto","Aves_netas"])
    if col_mort and col_neto:
        df[col_mort] = parse_num_series(df[col_mort])
        df[col_neto] = parse_num_series(df[col_neto])
        df["MortPct"] = (df[col_mort] / df[col_neto].replace(0, np.nan) * 100).round(2)
    else:
        df["MortPct"] = np.nan

    # ✅ Columnas que el modelo ML necesita
    if "X4=Edad" not in df.columns:
        df["X4=Edad"] = df["Edad"]

    if "Edad^2" not in df.columns:
        df["Edad^2"] = df["Edad"] ** 2

    # el modelo usa "alimento acumulado"
    if "alimento acumulado" not in df.columns:
        df["alimento acumulado"] = df["AlimAcumKg"]

    return df.sort_values(["LoteCompleto","Edad"])

@st.cache_data(show_spinner=False)
def load_ideales(path: str) -> pd.DataFrame:
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_excel(path, sheet_name="DATOS_COMPLETOS")
        df.columns = df.columns.astype(str).str.strip()
        zona_col = pick_first_col(df, ["Zona","zona"])
        if zona_col:
            df["Zona_Nombre"] = np.where(
                parse_num_series(df[zona_col]).fillna(0).astype(int) == 1,
                "BUCAY", "SANTO DOMINGO"
            )
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

def calcular_gaps_lotes(lotes_ids, df_hist, ideales_df):
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

# ── Carga de datos ────────────────────────────────────────────
with st.spinner("Cargando datos…"):
    DF      = load_and_prepare(MAIN_FILE)
    IDEALES = load_ideales(BENCH_FILE)

with st.spinner("Procesando snapshot…"):
    SNAP = build_snapshot_activos(DF)



if SNAP.empty:
    st.warning("No hay lotes ACTIVO en el archivo.")
    st.stop()

# ✅ Inicializar session_state
if "lote_anterior" not in st.session_state:
    st.session_state.lote_anterior = None

if "prediccion_resultado" not in st.session_state:
    st.session_state.prediccion_resultado = None



# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
hoy = datetime.today()
md(f"""
<div class="pronaca-header">
  <div style="font-size:2.2rem;line-height:1">🐔</div>
  <div>
    <div class="pronaca-header-title">PRONACA · PRODUCCIÓN AVÍCOLA v15</div>
    <div class="pronaca-header-sub">Dashboard Interactivo · Con Botón de Predicción Manual</div>
  </div>
  <div class="pronaca-header-pill">📅 Corte {hoy:%d %b %Y}</div>
</div>
""")

# ──────────────────────────────────────────────────────────────
# FILTROS SUPERIORES
# ──────────────────────────────────────────────────────────────
md('<div class="filter-bar">')
fc1, fc2, fc3, fc4, fc5 = st.columns([1.3, 1.2, 1.2, 1.2, 1.35])

with fc1:
    sel_zona  = st.multiselect("📍 Zona",    ["BUCAY","SANTO DOMINGO"],  default=["BUCAY","SANTO DOMINGO"])

with fc2:
    sel_tipo  = st.multiselect("🏠 Tipo",    ["PROPIA","PAC"],           default=["PROPIA","PAC"])

with fc3:
    sel_quint = st.multiselect("🧩 Quintil", ["Q1","Q2","Q3","Q4","Q5"], default=["Q1","Q2","Q3","Q4","Q5"])

with fc4:
    sel_estado = st.multiselect("🔄 Estado", ["ABIERTO","CERRADO"], default=["ABIERTO"])

# 🧠 NUEVO BOTÓN
with fc5:
    st.button("🧠 Herramienta predictiva", use_container_width=True, on_click=go_predictiva)

md("</div>")

SF = SNAP.copy()
SF = SF[SF["ZonaNombre"].isin(sel_zona)]
SF = SF[SF["TipoStd"].isin(sel_tipo)]
SF = SF[SF["Quintil"].isin(sel_quint)]
SF = SF[SF["EstadoLote"].isin(sel_estado)]

if SF.empty:
    st.info("Sin datos para los filtros seleccionados.")
    st.stop()

LOTES_FILTRADOS = SF["LoteCompleto"].unique()
DF_FILTRADO     = DF[DF["LoteCompleto"].isin(LOTES_FILTRADOS)].copy()

# ──────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────
kg_total    = SF["KgLive"].sum()
costo_total = SF["CostoAcum"].sum()
cpkg        = costo_total / (kg_total if kg_total else np.nan)

k1, k2, k3, k4, k5 = st.columns(5)
for col_, val_, lbl_, acc in [
    (k1, f"{SF['LoteCompleto'].nunique():,}",          "Lotes activos",  True),
    (k2, f"{int(SF['AvesVivas'].sum()):,}",             "Aves vivas",     True),
    (k3, fmt_num(kg_total, 0, suffix=" kg"),            "Kg live",        True),
    (k4, fmt_num(costo_total, 0, prefix="$"),           "Costo total",    True),
    (k5, fmt_num(cpkg, 3, prefix="$", suffix="/kg"),   "Costo medio/kg", False),
]:
    with col_:
        md(f'<div class="kpi-chip {"accent" if acc else ""}"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

# ──────────────────────────────────────────────────────────────
# LAYOUT PRINCIPAL
# ──────────────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

with left:
    # ── SEC 01 ───────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">01</span>
  <div>
    <div class="sec-title">Resumen por Etapa</div>
    <div class="sec-sub">🖱️ Haz clic en una barra para filtrar granjas abajo</div>
  </div>
</div>""")
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
        if pd.notna(ck) and ck >= 0.9:    bdg = "red"
        elif pd.notna(ck) and ck >= 0.75: bdg = "amber"
        rows_etapa.append((etapa, n, av, kg, fcr, co, ck, mo, bdg))
    
    cg, ct = st.columns([0.4, 0.6], gap="small")
    with cg:
        fig_e = go.Figure()
        fig_e.add_trace(go.Bar(
            x=[r[0] for r in rows_etapa],
            y=[r[1] for r in rows_etapa],
            marker=dict(color=[ETAPA_COLORS.get(r[0], BLUE) for r in rows_etapa]),
            text=[r[1] for r in rows_etapa],
            textposition="auto",
            hovertemplate="<b>%{x}</b><br>Lotes: %{y}<extra></extra>",
        ))
        fig_e.update_layout(
            template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=240, margin=dict(l=8, r=8, t=18, b=50),
            font=dict(family="DM Sans", size=9, color=TEXT), showlegend=False,
            xaxis=dict(title="", gridcolor=BORDER, color=TEXT, tickangle=-45),
            yaxis=dict(title="Lotes", gridcolor=BORDER, color=TEXT),
        )
        sel_e = st.plotly_chart(
            fig_e,
            on_select="rerun",
            selection_mode="points",
            key="chart_etapas",
            config={"displayModeBar": False},
            width="stretch",
        )
        etapas_sel = [p["x"] for p in sel_e.selection.get("points", []) if "x" in p]
        if etapas_sel:
            md(f'<div class="sel-pill">🔍 Filtrando: {" + ".join([e.split("(")[0].strip() for e in etapas_sel])}</div>')
        else:
            md(f'<div class="hint-text">Clic en barra para filtrar ↓</div>')
    
    with ct:
        tbody = ""
        for etapa, n, av, kg, fcr, co, ck, mo, bdg in rows_etapa:
            dot = ETAPA_COLORS.get(etapa, BLUE)
            act = etapa in etapas_sel if etapas_sel else False
            tbody += f"""
<tr style="border-bottom:1px solid {BORDER};background:{'rgba(218,41,28,.05)' if act else 'transparent'}">
  <td style="padding:6px 8px;font-weight:{'900' if act else '700'};font-size:.73rem;text-align:left">
    <span style="display:inline-block;width:7px;height:7px;border-radius:2px;
                 background:{dot};margin-right:5px;vertical-align:middle"></span>
    {etapa.split('(')[0].strip()}
  </td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{int(av):,}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(kg,0)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(fcr,3)}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(co,0,prefix="$")}</td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">
    <span class="badge {bdg}">{fmt_num(ck,3,prefix="$")}</span>
  </td>
  <td style="text-align:right;padding:6px 8px;font-size:.73rem">{fmt_num(mo,2,suffix="%")}</td>
</tr>"""
        md(f"""
<div class="card" style="padding:0;overflow:auto;height:240px">
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
</tr></thead><tbody>{tbody}</tbody>
</table></div>""")

    # ── SEC 02 ───────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">02</span>
  <div>
    <div class="sec-title">Top 5 Granjas con Problemas</div>
    <div class="sec-sub">🖱️ Clic en granja → ver lotes · Clic en lote → análisis Sec 03</div>
  </div>
</div>""")
    SF_02 = SF.copy()
    if etapas_sel:
        SF_02 = SF_02[SF_02["Etapa"].isin(etapas_sel)]
    SF_AB = SF_02[SF_02["EstadoLote"] == "ABIERTO"].copy()
    if SF_AB.empty:
        st.info("No hay lotes ABIERTOS con los filtros actuales.")
    else:
        lotes_ab = SF_AB["LoteCompleto"].unique()
        DF_AB = DF_FILTRADO[
            (DF_FILTRADO["EstadoLote"] == "ABIERTO") &
            (DF_FILTRADO["LoteCompleto"].isin(lotes_ab))
        ].copy()
        probs = []
        for granja in SF_AB["GranjaID"].unique():
            lotes_g = SF_AB[SF_AB["GranjaID"] == granja]["LoteCompleto"].unique()
            gaps = calcular_gaps_lotes(lotes_g, DF_AB, IDEALES)
            if gaps:
                probs.append({
                    "GranjaID":         granja,
                    "NumLotesProblema": len(gaps),
                    "GapPromedio":      np.mean([x["gap_promedio"] for x in gaps]),
                })
        if not probs:
            combos = SF_AB.groupby(["ZonaNombre","TipoStd","Quintil"]).size().reset_index()
            combos_str = " | ".join([f"{r['ZonaNombre']}·{r['TipoStd']}·{r['Quintil']}" for _, r in combos.iterrows()])
            st.warning(
                f"No se encontraron granjas con gap vs ideal.\n\n"
                f"**Combinaciones buscadas:** {combos_str}\n\n"
                f"Verifica que `{BENCH_FILE}` contenga curvas para estas combinaciones."
            )
        else:
            df_prob = pd.DataFrame(probs).sort_values("NumLotesProblema", ascending=False).head(5)
            fig_g = go.Figure()
            fig_g.add_trace(go.Bar(
                x=df_prob["GranjaID"],
                y=df_prob["NumLotesProblema"],
                marker=dict(color=RED),
                text=df_prob["NumLotesProblema"],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Lotes problema: %{y}<extra></extra>",
            ))
            fig_g.update_layout(
                template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=200, margin=dict(l=8, r=8, t=18, b=8),
                font=dict(family="DM Sans", size=10, color=TEXT), showlegend=False,
                xaxis=dict(title="Granja", gridcolor=BORDER, color=TEXT),
                yaxis=dict(title="# Lotes Problema", gridcolor=BORDER, color=TEXT),
            )
            sel_g = st.plotly_chart(
                fig_g,
                on_select="rerun",
                selection_mode="points",
                key="chart_granjas",
                width="stretch",
            )
            granjas_sel   = [p["x"] for p in sel_g.selection.get("points", []) if "x" in p]
            granja_activa = granjas_sel[0] if granjas_sel else df_prob.iloc[0]["GranjaID"]
            if granjas_sel:
                md(f'<div class="sel-pill">🏭 Granja: <strong>{granja_activa}</strong></div>')
            else:
                md(f'<div class="hint-text">Clic en barra para seleccionar granja · Activa: <strong>{granja_activa}</strong></div>')
            lotes_g_act = SF_AB[SF_AB["GranjaID"] == granja_activa]["LoteCompleto"].unique()
            gaps_lotes  = calcular_gaps_lotes(lotes_g_act, DF_AB, IDEALES)
            if not gaps_lotes:
                st.info(f"No hay lotes con gap en {granja_activa} para los filtros actuales.")
            else:
                filas_tabla = []
                for gap_info in sorted(gaps_lotes, key=lambda x: -x["gap_promedio"]):
                    lote   = gap_info["LoteCompleto"]
                    snap_r = SF[SF["LoteCompleto"] == lote]
                    fcr_v  = float(snap_r.iloc[0]["FCR_Cum"])     if not snap_r.empty and pd.notna(snap_r.iloc[0]["FCR_Cum"])     else None
                    ck_v   = float(snap_r.iloc[0]["CostoKg_Cum"]) if not snap_r.empty and pd.notna(snap_r.iloc[0]["CostoKg_Cum"]) else None
                    edad_v = int(snap_r.iloc[0]["Edad"])           if not snap_r.empty else 0
                    filas_tabla.append({
                        "LoteCompleto": lote,
                        "Código":       extract_lote_codigo(lote),
                        "Edad":         edad_v,
                        "Gap kg":       round(gap_info["gap_promedio"], 3),
                        "FCR":          round(fcr_v, 3) if fcr_v is not None else None,
                        "$/kg":         round(ck_v, 3)  if ck_v  is not None else None,
                    })
                df_lotes = pd.DataFrame(filas_tabla).reset_index(drop=True)
                md(f'<div class="hint-text">Clic en fila para analizar en Sec 03 ↓</div>')
                sel_t = st.dataframe(
                    df_lotes[["Código","Edad","Gap kg","FCR","$/kg"]],
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_lotes_sec02",
                    hide_index=True,
                    width="stretch",
                    height=180,
                    column_config={
                        "Código":  st.column_config.TextColumn("🔖 Código", width="small"),
                        "Edad":    st.column_config.NumberColumn("Días", format="%d d", width="small"),
                        "Gap kg":  st.column_config.NumberColumn("Gap kg ↑", format="%.3f", width="small"),
                        "FCR":     st.column_config.NumberColumn("FCR", format="%.3f", width="small"),
                        "$/kg":    st.column_config.NumberColumn("$/kg", format="$%.3f", width="small"),
                    },
                )
                rows_sel = sel_t.selection.get("rows", [])
                idx = rows_sel[0] if rows_sel else None

                if idx is not None and 0 <= int(idx) < len(df_lotes):
                    nuevo_lote = df_lotes.iloc[int(idx)]["LoteCompleto"]
                    if st.session_state.get("lote_sel_sec03") != nuevo_lote:
                        st.session_state["lote_sel_sec03"] = nuevo_lote
                        st.rerun()
                elif idx is not None:
                    # Selección quedó desfasada por cambio de filtros/granja
                    st.info("La lista cambió por los filtros. Selecciona un lote nuevamente 👇")

    # ── SEC 03 ───────────────────────────────────────────────
    md(f"""
<div class="sec-header">
  <span class="sec-num">03</span>
  <div>
    <div class="sec-title">Lote Seleccionado: IDEAL vs REAL</div>
    <div class="sec-sub">Análisis detallado · selecciona un lote en la tabla de arriba</div>
  </div>
</div>""")
    lotes_disp = SF["LoteCompleto"].unique().tolist()
    if (
        "lote_sel_sec03" not in st.session_state
        or st.session_state["lote_sel_sec03"] not in lotes_disp
    ):
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
            "Se mostrará solo la curva real."
        )
        ideal_data = pd.DataFrame(columns=["Edad","Peso"])
    
    # ──────────────────────────────────────────────────────────
    # KPIs (info del lote)
    # ──────────────────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns(4)
    for col_, val_, lbl_ in [
        (h1, il["GranjaID"],"Granja"),
        (h2, il["ZonaNombre"],"Zona"),
        (h3, il["TipoStd"],"Tipo"),
        (h4, f"{int(edad_act)} d","Edad"),
    ]:
        with col_:
            md(f'<div class="kpi-chip"><div class="kv">{val_}</div><div class="kl">{lbl_}</div></div>')

    # ──────────────────────────────────────────────────────────
    # ✅ KPIs de COSTOS del lote/galpón (último día del historial)
    # ──────────────────────────────────────────────────────────
    hist_ord  = hist.sort_values("Edad").copy()
    snap_last = hist_ord.iloc[-1]
    snap_prev = hist_ord.iloc[-2] if len(hist_ord) >= 2 else None

    galpon_v  = snap_last.get("Galpon", "—")
    alimento_t = snap_last.get("TipoAlimento", "—")

    aves_v     = snap_last.get("AvesVivas", np.nan)
    mort_pct   = snap_last.get("MortPct", np.nan)
    fcr_cum    = snap_last.get("FCR_Cum", np.nan)

    # costos (según tu load_and_prepare)
    costo_acum = snap_last.get("CostoAcum", np.nan)          # acumulado
    costo_kg   = snap_last.get("CostoKg_Cum", np.nan)        # $/kg live (acum)
    costo_ave  = snap_last.get("CostoAlimentoPorAveAcum", np.nan)
    unit_cost  = snap_last.get("unit_cost_final", np.nan)

    # costo del día (si no viene, lo calculo por diferencia)
    costo_dia = snap_last.get("CostoAlimentoDia", np.nan)
    if (costo_dia is None or pd.isna(costo_dia)) and snap_prev is not None:
        prev_costo = snap_prev.get("CostoAcum", np.nan)
        if pd.notna(costo_acum) and pd.notna(prev_costo):
            costo_dia = costo_acum - prev_costo

    # alimento acumulado (y alimento día si existe)
    alim_acum = snap_last.get("AlimAcumKg", np.nan)
    alim_dia  = snap_last.get("_alim_dia", np.nan)
    if (alim_dia is None or pd.isna(alim_dia)) and snap_prev is not None:
        prev_alim = snap_prev.get("AlimAcumKg", np.nan)
        if pd.notna(alim_acum) and pd.notna(prev_alim):
            alim_dia = alim_acum - prev_alim

    md(f'''
    <div class="hint-text">
      💰 Costos del lote · Galpón <strong>{galpon_v}</strong> · Alimento <strong>{alimento_t}</strong>
    </div>
    ''')

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        md(f'<div class="kpi-chip"><div class="kv">{galpon_v}</div><div class="kl">Galpón</div></div>')
    with k2:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(aves_v,0)}</div><div class="kl">Aves vivas</div></div>')
    with k3:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(mort_pct,2,suffix="%")}</div><div class="kl">Mortalidad</div></div>')
    with k4:
        md(f'<div class="kpi-chip accent"><div class="kv">{fmt_num(costo_acum,0,prefix="$")}</div><div class="kl">Costo alim. acum</div></div>')
    with k5:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(costo_kg,3,prefix="$",suffix="/kg")}</div><div class="kl">Costo $/kg (acum)</div></div>')
    with k6:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(fcr_cum,3)}</div><div class="kl">FCR acum</div></div>')

    k7, k8, k9, k10 = st.columns(4)
    with k7:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(alim_acum,0,suffix=" kg")}</div><div class="kl">Alimento acum</div></div>')
    with k8:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(alim_dia,0,suffix=" kg")}</div><div class="kl">Alimento día</div></div>')
    with k9:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(costo_dia,0,prefix="$")}</div><div class="kl">Costo alim día</div></div>')
    with k10:
        md(f'<div class="kpi-chip"><div class="kv">{fmt_num(costo_ave,3,prefix="$",suffix="/ave")}</div><div class="kl">$/ave (acum)</div></div>')

    md(f'<div class="hint-text">Unit cost alimento: <strong>{fmt_num(unit_cost,3,prefix="$",suffix="/kg alim")}</strong></div>')

    # ──────────────────────────────────────────────────────────
    # REAL vs IDEAL (igual que tu bloque)
    # ──────────────────────────────────────────────────────────
    hist_v   = hist[hist["PesoFinal"].notna()].copy()
    edad_max = float(hist_v["Edad"].max()) if not hist_v.empty else 0
    ideal_s  = ideal_data.sort_values("Edad").copy() if not ideal_data.empty else pd.DataFrame()
    if not ideal_s.empty:
        ideal_s = ideal_s[ideal_s["Edad"] <= edad_max + 3]

    fig_ri = go.Figure()
    fig_ri.add_trace(go.Scatter(
        x=hist_v["Edad"], y=hist_v["PesoFinal"],
        mode="lines+markers", name="REAL",
        line=dict(color=RED, width=3), marker=dict(size=6),
        hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
    ))
    if not ideal_s.empty:
        fig_ri.add_trace(go.Scatter(
            x=ideal_s["Edad"], y=ideal_s["Peso"],
            mode="lines+markers", name="IDEAL",
            line=dict(color=GREEN, width=3, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
            hovertemplate="Día %{x}<br>IDEAL: %{y:.3f} kg<extra></extra>",
        ))
        hm = hist_v.merge(
            ideal_s[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"}),
            on="Edad", how="inner"
        )
        if not hm.empty:
            fig_ri.add_trace(go.Scatter(
                x=hm["Edad"].tolist() + hm["Edad"].tolist()[::-1],
                y=hm["PesoFinal"].tolist() + hm["PesoIdeal"].tolist()[::-1],
                fill="toself", name="GAP",
                fillcolor="rgba(218,41,28,0.15)",
                line=dict(color="rgba(255,255,255,0)"),
                hoverinfo="skip",
            ))
    fig_ri.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=300, margin=dict(l=8, r=8, t=18, b=8),
        font=dict(family="DM Sans", size=11, color=TEXT),
        legend=dict(orientation="h", y=-0.15, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
        yaxis=dict(title="Peso (kg)", gridcolor=BORDER, color=TEXT),
        hovermode="x unified",
    )

    st.plotly_chart(fig_ri, width="stretch", key=f"chart_real_ideal_{lote_sel}")

    st.caption("**Costo perdido (Real vs Ideal) acumulado:**")
    hc = hist[hist["Edad"] >= EDAD_MIN_ANALISIS].copy()
    if not ideal_s.empty:
        hc = hc.merge(
            ideal_s[["Edad","Peso"]].rename(columns={"Peso":"PesoIdeal"}),
            on="Edad", how="left"
        )
        hc["KgIdealAcum"]    = (hc["AvesVivas"] * hc["PesoIdeal"]).cumsum()
        hc["CostoIdealAcum"] = hc["KgIdealAcum"] * hc["CostoKg_Cum"]
        hc["CostoPerdido"]   = (hc["CostoAcum"] - hc["CostoIdealAcum"]).clip(lower=0)
    else:
        hc["CostoPerdido"] = np.nan
    hc_clean = hc[["Edad","CostoPerdido"]].dropna()
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(
        x=hc_clean["Edad"], y=hc_clean["CostoPerdido"],
        mode="lines+markers",
        line=dict(color=RED, width=3), marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(218,41,28,0.2)",
        hovertemplate="Día %{x}<br>Pérdida: $%{y:,.2f}<extra></extra>",
    ))
    fig_c.update_layout(
        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=280, margin=dict(l=8, r=8, t=18, b=8),
        font=dict(family="DM Sans", size=11, color=TEXT), showlegend=False,
        xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
        yaxis=dict(title="Costo Perdido ($)", gridcolor=BORDER, color=TEXT),
        hovermode="x unified",
    )

    st.plotly_chart(fig_c, width="stretch", key=f"chart_costo_{lote_sel}")

# ══════════════════════════════════════════════════════════════
# COLUMNA DERECHA — PREDICCIÓN CON BOTÓN
# ══════════════════════════════════════════════════════════════
with right:
    # 1) Cargar predictor (cacheado)
    try:
        MODEL_PATH = "modelo_rf_avicola.joblib"

        if os.path.exists(MODEL_PATH):
            predictor = get_predictor_cached(MODEL_PATH, _file_mtime(MODEL_PATH))
        else:
            predictor = None
        pred_activo = predictor is not None and predictor.model is not None
    except Exception as e:
        st.warning(f"⚠️ No se pudo cargar el predictor: {e}")
        pred_activo = False

    if not pred_activo:
        md(f"""
<div class="card" style="border:1px dashed {BORDER};background:{BG};min-height:900px;
display:flex;align-items:center;justify-content:center;">
  <div style="text-align:center;color:{MUTED};font-weight:800;
              text-transform:uppercase;letter-spacing:.7px;">
    📊 Predicción de Lotes<br><br>⚠️ Modelo no disponible<br>
    Coloca <strong>modelo_rf_avicola.joblib</strong><br>en la carpeta del app
  </div>
</div>""")
    else:
        md(f"""
<div class="sec-header">
  <span class="sec-num">04</span>
  <div>
    <div class="sec-title">Predicción: Proyección al Día 40</div>
    <div class="sec-sub">Automática · cambia con el lote seleccionado</div>
  </div>
</div>""")

        if not lote_sel:
            st.info("Selecciona un lote en la Sección 03 para ver la predicción.")
        else:
            st.write(f"📋 Lote: **{extract_lote_codigo(lote_sel)}**")

            # (Opcional) toggle de debug
            debug_pred = st.checkbox("Mostrar debug por consola", value=False, key="dbg_pred")

            # 2) Cache simple por lote (para que no recalcular en cada rerun por clicks)
            if "pred_cache" not in st.session_state:
                st.session_state["pred_cache"] = {}

            if lote_sel not in st.session_state["pred_cache"]:
                with st.spinner("⏳ Calculando predicción..."):
                    # a) historial del lote
                    hist_raw = DF[DF["LoteCompleto"] == lote_sel].sort_values("Edad").copy()

                    if debug_pred:
                        _console_df_info(
                            hist_raw,
                            f"HIST_RAW lote={lote_sel}",
                            cols=["LoteCompleto","Edad","PesoFinal","X4=Edad","Edad^2","alimento acumulado","AlimAcumKg",
                                  "AvesVivas","ZonaNombre","TipoStd","Quintil","Quintil_num","EstadoLote"],
                            head=12
                        )

                    # b) limpiar
                    hist_pred = _limpiar_historial_para_modelo(hist_raw)

                    if debug_pred:
                        _console_df_info(
                            hist_pred,
                            f"HIST_LIMPIO lote={lote_sel}",
                            cols=["Edad","PesoFinal","X4=Edad","Edad^2","alimento acumulado","AlimAcumKg","Quintil","Quintil_num"],
                            head=12
                        )

                    # c) validar
                    if hist_pred.empty:
                        st.session_state["pred_cache"][lote_sel] = {"error": "Historial vacío (PesoFinal válido)"}  # guardo error
                    else:
                        # d) predecir
                        res = predictor.proyectar_curva(
                            hist_lote=hist_pred,
                            target_edad=40,
                            enforce_monotonic="isotonic",
                        )
                        st.session_state["pred_cache"][lote_sel] = {
                            "res": res,
                            "hist_pred": hist_pred
                        }

            # 3) Leer cache y mostrar
            cache_item = st.session_state["pred_cache"].get(lote_sel, {})
            if cache_item.get("error"):
                st.error(f"❌ {cache_item['error']}")
            else:
                res = cache_item.get("res", {})
                hist_pred_guardado = cache_item.get("hist_pred")

                if res.get("error"):
                    st.error(f"❌ Error en predicción: {res['error']}")
                else:
                    df_curve = res.get("df")
                    edad_actual = int(res.get("edad_actual", int(hist_pred_guardado.iloc[-1]["Edad"])))
                    peso_actual = float(hist_pred_guardado.iloc[-1]["PesoFinal"])
                    peso_d40 = float(res["peso_d40"])
                    dias_rest = max(0, 40 - edad_actual)

                    # ---- Ajuste SHIFT/ANCLA (tu versión buena) ----
                    if df_curve is not None and isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
                        df_curve = df_curve.copy()
                        df_curve["Dia"] = pd.to_numeric(df_curve["Dia"], errors="coerce").astype(int)

                        if "Peso_pred_kg" in df_curve.columns:
                            ycol = "Peso_pred_kg"
                        elif "Peso_kg" in df_curve.columns:
                            ycol = "Peso_kg"
                        else:
                            ycol = None

                        if ycol:
                            df_curve[ycol] = pd.to_numeric(df_curve[ycol], errors="coerce")

                            if not (df_curve["Dia"] == edad_actual).any():
                                df_curve = pd.concat(
                                    [df_curve, pd.DataFrame({"Dia": [edad_actual], ycol: [np.nan]})],
                                    ignore_index=True
                                ).sort_values("Dia")

                            pred_en_hoy = df_curve.loc[df_curve["Dia"] == edad_actual, ycol].iloc[0]
                            if pd.isna(pred_en_hoy):
                                pred_en_hoy = peso_actual

                            delta = float(peso_actual) - float(pred_en_hoy)
                            m = df_curve["Dia"] >= edad_actual

                            df_curve.loc[m, ycol] = df_curve.loc[m, ycol].astype(float) + delta
                            df_curve.loc[m, ycol] = np.maximum(df_curve.loc[m, ycol].values, float(peso_actual))
                            df_curve.loc[m, ycol] = np.maximum.accumulate(df_curve.loc[m, ycol].values)

                            # recalcular peso_d40 después del shift (IMPORTANTE)
                            df40 = df_curve[df_curve["Dia"] == 40]
                            if not df40.empty:
                                peso_d40 = float(df40.iloc[0][ycol])

                    # KPIs
                    c1, c2 = st.columns(2)
                    with c1:
                        md(f'<div class="kpi-chip accent"><div class="kv">{peso_d40:.3f} kg</div><div class="kl">Peso Día 40</div></div>')
                    with c2:
                        md(f'<div class="kpi-chip"><div class="kv">{dias_rest} d</div><div class="kl">Días restantes</div></div>')

                    # Gráfico
                    fig_p = go.Figure()
                    fig_p.add_trace(go.Scatter(
                        x=hist_pred_guardado["Edad"], y=hist_pred_guardado["PesoFinal"],
                        mode="lines+markers", name="REAL",
                        line=dict(color=BLUE, width=3), marker=dict(size=7),
                        hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
                    ))

                    if df_curve is not None and isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
                        if "Peso_pred_kg" in df_curve.columns:
                            ycol = "Peso_pred_kg"
                        elif "Peso_kg" in df_curve.columns:
                            ycol = "Peso_kg"
                        else:
                            ycol = None

                        if ycol:
                            fig_p.add_trace(go.Scatter(
                                x=df_curve["Dia"], y=df_curve[ycol],
                                mode="lines", name="PROYECCIÓN D40",
                                line=dict(color=RED, width=3, dash="dash"),
                                hovertemplate="Día %{x}<br>PROY: %{y:.3f} kg<extra></extra>",
                            ))

                    fig_p.add_trace(go.Scatter(
                        x=[40], y=[peso_d40],
                        mode="markers", name="D40",
                        marker=dict(size=10, symbol="diamond", color=RED),
                        hovertemplate="Día 40<br>%{y:.3f} kg<extra></extra>",
                    ))

                    fig_p.update_layout(
                        template="plotly_white", paper_bgcolor=CARD, plot_bgcolor=CARD,
                        height=320, margin=dict(l=8, r=8, t=18, b=8),
                        font=dict(family="DM Sans", size=11, color=TEXT),
                        legend=dict(orientation="h", y=-0.15, x=0, bgcolor="rgba(0,0,0,0)"),
                        xaxis=dict(title="Edad (días)", gridcolor=BORDER, color=TEXT),
                        yaxis=dict(title="Peso (kg)", gridcolor=BORDER, color=TEXT),
                        hovermode="x unified",
                    )

                    st.plotly_chart(fig_p, width="stretch", key=f"chart_pred_{lote_sel}")

                    # Resumen
                    st.caption("**Resumen de la proyección:**")
                    m1, m2, m3 = st.columns(3)
                    with m1: st.metric("Edad actual",    f"{edad_actual} días")
                    with m2: st.metric("Peso actual",    f"{peso_actual:.3f} kg")
                    with m3: st.metric("Peso proy. D40", f"{peso_d40:.3f} kg")

                    with st.expander("📊 Ver tabla detallada de predicción"):
                        if df_curve is not None and isinstance(df_curve, pd.DataFrame):
                            st.dataframe(df_curve, width="stretch")
                        else:
                            st.info("El predictor no devolvió tabla df. Revisa model_predictor.")
# ──────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────
md(f"""
<div style="text-align:center;font-size:.72rem;color:{MUTED};
border-top:1px solid {BORDER};padding-top:10px;margin-top:20px">
PRONACA · Dashboard v15 ++ · ARREGLADO · {hoy:%d/%m/%Y %H:%M}
</div>
""")