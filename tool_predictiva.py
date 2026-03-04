# tool_predictiva.py
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from textwrap import dedent

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
MODEL_FILE = "modelo_rf_avicola.joblib"
MODEL_FALLBACK = os.path.join("artifacts_modelo", "modelo_rf_avicola.joblib")


def md(html: str):
    st.markdown(dedent(html), unsafe_allow_html=True)


def _file_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


@st.cache_resource(show_spinner=False)
def _load_predictor_cached(model_path: str, model_mtime: float):
    # Se recarga si cambia el mtime
    from model_predictor import cargar_predictor
    return cargar_predictor(model_path)


def load_predictor():
    model_path = MODEL_FILE
    if not os.path.exists(model_path) and os.path.exists(MODEL_FALLBACK):
        model_path = MODEL_FALLBACK

    if not os.path.exists(model_path):
        return None, f"No se encontró **{MODEL_FILE}** (ni fallback **{MODEL_FALLBACK}**) en la carpeta del app."

    try:
        mtime = _file_mtime(model_path)
        pred = _load_predictor_cached(model_path, mtime)
        ok = pred is not None and getattr(pred, "model", None) is not None
        return (pred if ok else None), (None if ok else "El predictor cargó pero `predictor.model` está vacío.")
    except Exception as e:
        return None, str(e)


def _model_features(model):
    feats = getattr(model, "feature_names_in_", None)
    if feats is None:
        return None
    return list(feats)


def _parse_num_value(x) -> float:
    # Soporta "450,00" / "$ 1.234,50" / "1234.5"
    try:
        if x is None:
            return np.nan
        s = str(x).strip()
        if s == "":
            return np.nan
        s = s.replace("\u00A0", "").replace(" ", "").replace("$", "")
        # deja solo dígitos, coma, punto y -
        s = "".join(ch for ch in s if (ch.isdigit() or ch in [",", ".", "-"]))
        has_dot = "." in s
        has_comma = "," in s
        if has_dot and has_comma:
            # asume 1.234,56 -> 1234.56
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return np.nan


def _get_bundle_like_fields(predictor):
    """
    Intenta obtener lo necesario desde el predictor (si lo expone) sin romper.
    Esperamos (ideal):
      predictor.features
      predictor.feature_defaults
      predictor.alim_by_edad  (DataFrame con min/median/max por edad)
      predictor.perfil_alimento_mediana (Series por edad)
      predictor.max_edad
    """
    features = getattr(predictor, "features", None)
    defaults = getattr(predictor, "feature_defaults", None)
    alim_by_edad = getattr(predictor, "alim_by_edad", None)
    perfil_alimento = getattr(predictor, "perfil_alimento_mediana", None)
    max_edad = getattr(predictor, "max_edad", None)

    if isinstance(max_edad, (np.integer, int, float)) and not pd.isna(max_edad):
        max_edad = int(max_edad)
    else:
        max_edad = None

    if not isinstance(defaults, dict):
        defaults = {}

    return features, defaults, alim_by_edad, perfil_alimento, max_edad


def _suggest_alimento_for_age(edad: int, alim_by_edad, perfil_alimento):
    edad = int(edad)
    if isinstance(alim_by_edad, pd.DataFrame) and "median" in alim_by_edad.columns:
        if edad in alim_by_edad.index and pd.notna(alim_by_edad.loc[edad, "median"]):
            return float(alim_by_edad.loc[edad, "median"])
    if isinstance(perfil_alimento, pd.Series):
        try:
            if edad in perfil_alimento.index and pd.notna(perfil_alimento.loc[edad]):
                return float(perfil_alimento.loc[edad])
        except Exception:
            pass
    return None


def _validate_alimento_vs_age(edad: int, alim_acum: float, alim_by_edad):
    """
    Reglas simples:
    - Si tenemos min/median/max por edad, evitamos valores absurdamente bajos.
    - Permitimos 0 en edades muy bajas o si el histórico realmente tiene 0.
    """
    if not isinstance(alim_by_edad, pd.DataFrame):
        return True, None

    if not {"min", "median", "max"}.issubset(set(alim_by_edad.columns)):
        return True, None

    edad = int(edad)
    if edad not in alim_by_edad.index:
        return True, None

    a_min = float(alim_by_edad.loc[edad, "min"])
    a_med = float(alim_by_edad.loc[edad, "median"])
    a_max = float(alim_by_edad.loc[edad, "max"])

    info = (a_min, a_med, a_max)

    # Si el histórico en esa edad tiene min>0, entonces 0 o muy bajo es OOD.
    if a_min > 0 and float(alim_acum) < (a_min * 0.7):
        return False, info

    # También si es exageradamente alto
    if a_max > 0 and float(alim_acum) > (a_max * 1.5):
        # no bloqueamos, pero avisamos con warning (lo manejará el caller)
        return True, info

    return True, info


def _build_single_row_inputs(
    edad_obj: int,
    alim_acum: float,
    quintil_num: float,
    extra: dict,
    model_feats: list[str] | None,
    defaults: dict | None = None,
):
    """
    ✅ Corrección clave:
    - Antes: faltantes -> 0 (te aplana todo y permite escenarios absurdos)
    - Ahora: faltantes -> defaults (mediana de entrenamiento) y 0 como último fallback.
    """
    defaults = defaults or {}

    row = dict(defaults)  # base con defaults
    row.update({
        "X4=Edad": int(edad_obj),
        "Edad^2": float(edad_obj) ** 2,
        "alimento acumulado": float(alim_acum),
        "Quintil_num": float(quintil_num),
    })
    row.update(extra or {})

    X = pd.DataFrame([row])

    if model_feats:
        for f in model_feats:
            if f not in X.columns:
                X[f] = defaults.get(f, 0.0)
        X = X[model_feats]
    return X


def _predict_single(predictor, X: pd.DataFrame) -> float:
    y = predictor.model.predict(X)[0]
    return float(y)


def _parse_num_series(s: pd.Series) -> pd.Series:
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


def _limpiar_historial_para_modelo(hist: pd.DataFrame) -> pd.DataFrame:
    h = hist.copy()

    h["Edad"] = pd.to_numeric(h.get("Edad"), errors="coerce")
    h = h[h["Edad"].notna()].copy()
    h["Edad"] = h["Edad"].astype(int)

    h["PesoFinal"] = pd.to_numeric(h.get("PesoFinal"), errors="coerce")
    h = h[h["PesoFinal"].notna()].copy()
    h = h[h["PesoFinal"] > 0].copy()

    h = h.sort_values("Edad").copy()

    estado = str(h.get("EstadoLote").iloc[-1] if "EstadoLote" in h.columns and len(h) else "ABIERTO").upper()
    if estado != "CERRADO":
        h7 = h[h["Edad"] % 7 == 0].copy()
        last_row = h.iloc[[-1]].copy()
        if not h7.empty:
            h = pd.concat([h7, last_row], ignore_index=True)
        else:
            h = last_row
        h = h.drop_duplicates(subset=["Edad"], keep="last").copy()

    h = h.drop_duplicates(subset=["Edad"], keep="last").copy()
    return h


def _imputar_alimento_en_historial(h: pd.DataFrame, perfil_alimento: pd.Series | None):
    """
    ✅ Corrección clave:
    - Antes: si no había AlimAcumKg -> alimento acumulado = 0.0 (irreal)
    - Ahora: si no hay, usamos perfil mediano por edad (si existe).
      Si hay algunos valores, escalamos el perfil para calzar con el último valor conocido.
    """
    if perfil_alimento is None or not isinstance(perfil_alimento, pd.Series):
        # fallback: si no tenemos perfil, dejamos 0 (pero avisaremos en UI)
        h["alimento acumulado"] = 0.0
        return h

    h = h.copy()
    h["Edad"] = h["Edad"].astype(int)

    # base perfil por edad
    edades = h["Edad"].values
    base = pd.Series(index=h.index, dtype=float)
    for i, ed in enumerate(edades):
        if ed in perfil_alimento.index and pd.notna(perfil_alimento.loc[ed]):
            base.iloc[i] = float(perfil_alimento.loc[ed])
        else:
            base.iloc[i] = np.nan

    base = base.interpolate().ffill().bfill()

    # si el usuario dio algunos alimentos, usamos factor de escala
    if "AlimAcumKg" in h.columns and h["AlimAcumKg"].notna().any():
        # último conocido (edad, alim)
        sub = h[h["AlimAcumKg"].notna()].sort_values("Edad")
        last_ed = int(sub.iloc[-1]["Edad"])
        last_al = float(sub.iloc[-1]["AlimAcumKg"])
        denom = float(perfil_alimento.loc[last_ed]) if (last_ed in perfil_alimento.index and pd.notna(perfil_alimento.loc[last_ed])) else None
        factor = (last_al / denom) if (denom is not None and denom > 0) else 1.0

        alim_est = base.astype(float) * float(factor)

        # override donde sí hay dato real del usuario
        alim_est.loc[h["AlimAcumKg"].notna()] = h.loc[h["AlimAcumKg"].notna(), "AlimAcumKg"].astype(float)
        h["alimento acumulado"] = alim_est.astype(float).ffill().bfill()
    else:
        h["alimento acumulado"] = base.astype(float)

    return h


def _anchor_curve_to_last_real(df_curve: pd.DataFrame, edad_actual: int, peso_actual: float):
    if df_curve is None or df_curve.empty:
        return df_curve, None

    df_curve = df_curve.copy()
    df_curve["Dia"] = pd.to_numeric(df_curve["Dia"], errors="coerce").astype(int)

    if "Peso_pred_kg" in df_curve.columns:
        ycol = "Peso_pred_kg"
    elif "Peso_kg" in df_curve.columns:
        ycol = "Peso_kg"
    else:
        return df_curve, None

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

    return df_curve, ycol


def render(go_dashboard=None):
    st.title("🔮 Herramienta predictiva")

    if go_dashboard:
        if st.button("⬅️ Volver al dashboard", use_container_width=True):
            go_dashboard()

    predictor, err = load_predictor()
    if predictor is None:
        st.error(f"⚠️ Modelo no disponible.\n\n{err}")
        st.stop()

    # info desde predictor (si existe)
    pred_feats, pred_defaults, alim_by_edad, perfil_alimento, max_edad_pred = _get_bundle_like_fields(predictor)

    model_feats = _model_features(predictor.model)
    # max edad real del modelo (prioridad: predictor.max_edad -> si no, 40 por seguridad)
    MAX_EDAD_MODELO = int(max_edad_pred) if isinstance(max_edad_pred, int) and max_edad_pred > 0 else 40

    with st.expander("Ver variables que espera el modelo (features)"):
        if model_feats:
            st.write(model_feats)
        elif isinstance(pred_feats, list) and pred_feats:
            st.write(pred_feats)
        else:
            st.info("No hay `feature_names_in_` ni `predictor.features`. Se usará lo que armes en inputs (ojo).")

        if pred_defaults:
            st.caption("✅ Este predictor trae `feature_defaults`: faltantes NO se llenan con 0, se llenan con valores típicos.")
        else:
            st.warning("⚠️ Este predictor NO expone `feature_defaults`. Se llenarán faltantes con 0 como último recurso (menos fiable).")

    tab1, tab2 = st.tabs(["1) Predicción puntual (un día)", "2) Proyección desde historial → curva"])

    # ─────────────────────────────────────────────
    # TAB 1: Predicción puntual
    # ─────────────────────────────────────────────
    with tab1:
        st.subheader("Predice el peso para un día objetivo")

        # Nota: usamos text_input para permitir "450,00"
        with st.form("form_puntual"):
            c1, c2, c3 = st.columns(3)
            with c1:
                edad_obj = st.number_input(
                    "Edad objetivo (días)",
                    min_value=1,
                    max_value=MAX_EDAD_MODELO,
                    value=min(30, MAX_EDAD_MODELO),
                    step=1
                )
            with c2:
                quintil = st.selectbox("Quintil", ["Q1", "Q2", "Q3", "Q4", "Q5"], index=4)
            with c3:
                sug = _suggest_alimento_for_age(int(edad_obj), alim_by_edad, perfil_alimento)
                alim_acum_txt = st.text_input(
                    "Alimento acumulado (kg)",
                    value=(f"{sug:.0f}" if isinstance(sug, (int, float)) else "0"),
                    help="Acepta coma o punto: 450,00 / 450.00"
                )

            # Si tu modelo tiene más features, aquí puedes agregarlas como inputs extra:
            extra = {}

            do = st.form_submit_button("Predecir peso", use_container_width=True)

        if do:
            quintil_num = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Q5": 5}[quintil]
            alim_acum = _parse_num_value(alim_acum_txt)

            if pd.isna(alim_acum):
                st.error("Alimento acumulado inválido.")
                st.stop()

            ok_alim, info = _validate_alimento_vs_age(int(edad_obj), float(alim_acum), alim_by_edad)
            if info:
                a_min, a_med, a_max = info
                st.caption(f"Rango histórico alimento (día {int(edad_obj)}): min={a_min:,.0f} · mediana={a_med:,.0f} · max={a_max:,.0f}")

            if not ok_alim:
                st.error("Alimento acumulado demasiado bajo para esa edad (fuera de distribución). Ajusta el valor.")
                st.stop()

            # ⚠️ si está exageradamente alto, solo warning
            if info:
                a_min, a_med, a_max = info
                if a_max > 0 and float(alim_acum) > (a_max * 1.5):
                    st.warning("Alimento acumulado muy alto vs histórico para esa edad. La predicción puede ser poco confiable.")

            # defaults (si no existen, dict vacío)
            defaults = pred_defaults or {}

            # model_feats manda, si no, usamos predictor.features, si no, None
            feats_for_build = model_feats or (pred_feats if isinstance(pred_feats, list) else None)

            X = _build_single_row_inputs(
                edad_obj=int(edad_obj),
                alim_acum=float(alim_acum),
                quintil_num=float(quintil_num),
                extra=extra,
                model_feats=feats_for_build,
                defaults=defaults,
            )

            # por estabilidad (si tu modelo entrenó en float32)
            try:
                X = X.astype(np.float32)
            except Exception:
                pass

            try:
                y = _predict_single(predictor, X)
                st.success("Listo ✅")
                st.metric("Peso predicho", f"{y:.3f} kg")
            except Exception as e:
                st.error(f"No se pudo predecir: {e}")

    # ─────────────────────────────────────────────
    # TAB 2: Proyección desde historial
    # ─────────────────────────────────────────────
    with tab2:
        st.subheader("Ingresa historial (Edad + PesoFinal) y proyecta al día objetivo")
        st.caption("Mínimo: Edad, PesoFinal. Si no tienes alimento, se imputará con un perfil típico (si el modelo lo trae).")

        cA, cB, cC = st.columns(3)
        with cA:
            target_edad = st.number_input("Proyectar hasta (días)", min_value=1, max_value=120, value=40, step=1)
        with cB:
            quintil2 = st.selectbox("Quintil (para la proyección)", ["Q1", "Q2", "Q3", "Q4", "Q5"], index=4, key="q2")
        with cC:
            estado = st.selectbox("Estado (si está abierto/cerrado)", ["ABIERTO", "CERRADO"], index=0)

        if int(target_edad) > int(MAX_EDAD_MODELO):
            st.warning(f"Tu modelo fue entrenado hasta {MAX_EDAD_MODELO} días. La proyección se recortará o perderá confiabilidad.")

        df_default = pd.DataFrame({
            "Edad": [7, 14, 21, 28, 35],
            "PesoFinal": [np.nan, np.nan, np.nan, np.nan, np.nan],
            "AlimAcumKg": [np.nan, np.nan, np.nan, np.nan, np.nan],
        })

        df_in = st.data_editor(
            df_default,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )

        if st.button("Proyectar curva", use_container_width=True):
            try:
                h = df_in.copy()

                # parseo robusto
                h["Edad"] = _parse_num_series(h["Edad"])
                h["PesoFinal"] = _parse_num_series(h["PesoFinal"])
                if "AlimAcumKg" in h.columns:
                    h["AlimAcumKg"] = _parse_num_series(h["AlimAcumKg"])

                h = h.dropna(subset=["Edad", "PesoFinal"]).copy()
                h["EstadoLote"] = estado

                # features mínimas
                h["Edad"] = h["Edad"].astype(int)
                h["X4=Edad"] = h["Edad"]
                h["Edad^2"] = (h["Edad"].astype(float) ** 2)

                # ✅ alimento: si no hay, imputamos con perfil típico (si existe)
                h = _imputar_alimento_en_historial(h, perfil_alimento)

                if (h.get("alimento acumulado") is not None) and (h["alimento acumulado"].astype(float).max() == 0.0):
                    st.warning("No hay alimento real ni perfil de alimento en el predictor. Se usará 0, la proyección puede ser poco realista.")

                qn = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Q5": 5}[quintil2]
                h["Quintil_num"] = float(qn)
                h["Quintil"] = quintil2

                # limpia (tu regla)
                h2 = _limpiar_historial_para_modelo(h)

                if h2.empty:
                    st.error("Historial vacío (no hay PesoFinal válido > 0).")
                    st.stop()

                # Ejecuta proyección del predictor
                res = predictor.proyectar_curva(
                    hist_lote=h2,
                    target_edad=int(target_edad),
                    enforce_monotonic="isotonic",
                )
                if res.get("error"):
                    st.error(f"Error del predictor: {res['error']}")
                    st.stop()

                df_curve = res.get("df")
                edad_actual = int(res.get("edad_actual", int(h2.iloc[-1]["Edad"])))
                peso_actual = float(h2.iloc[-1]["PesoFinal"])

                df_curve, ycol = _anchor_curve_to_last_real(df_curve, edad_actual, peso_actual)

                peso_target = None
                if df_curve is not None and ycol:
                    row_t = df_curve[df_curve["Dia"] == int(target_edad)]
                    if not row_t.empty:
                        peso_target = float(row_t.iloc[0][ycol])

                if peso_target is None:
                    peso_target = float(res.get("peso_d40", np.nan))

                st.success("Proyección generada ✅")
                st.metric(f"Peso proyectado día {int(target_edad)}", f"{peso_target:.3f} kg")

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=h2["Edad"], y=h2["PesoFinal"],
                    mode="lines+markers", name="REAL",
                    hovertemplate="Día %{x}<br>REAL: %{y:.3f} kg<extra></extra>",
                ))

                if df_curve is not None and ycol:
                    fig.add_trace(go.Scatter(
                        x=df_curve["Dia"], y=df_curve[ycol],
                        mode="lines", name=f"PROYECCIÓN D{int(target_edad)}",
                        line=dict(dash="dash"),
                        hovertemplate="Día %{x}<br>PROY: %{y:.3f} kg<extra></extra>",
                    ))

                fig.add_trace(go.Scatter(
                    x=[int(target_edad)], y=[peso_target],
                    mode="markers", name="TARGET",
                    marker=dict(size=10, symbol="diamond"),
                    hovertemplate=f"Día {int(target_edad)}<br>%{{y:.3f}} kg<extra></extra>",
                ))

                fig.update_layout(
                    height=380,
                    margin=dict(l=10, r=10, t=10, b=10),
                    xaxis_title="Edad (días)",
                    yaxis_title="Peso (kg)",
                    hovermode="x unified",
                )
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("Ver tabla de proyección"):
                    if df_curve is not None:
                        st.dataframe(df_curve, use_container_width=True)

            except Exception as e:
                st.error(f"No se pudo proyectar: {e}")