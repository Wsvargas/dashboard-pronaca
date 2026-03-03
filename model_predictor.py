import numpy as np
import pandas as pd
import joblib
from dataclasses import dataclass

from sklearn.isotonic import IsotonicRegression


@dataclass
class Predictor:
    model: object
    features: list
    max_edad: int = 40
    perfil_alimento: pd.Series | None = None

    def _armar_fila_features(self, row: dict) -> pd.DataFrame:
        # arma 1 fila con TODAS las features que el modelo espera
        data = {f: row.get(f, 0) for f in self.features}
        return pd.DataFrame([data])

    def proyectar_curva(self, hist_lote: pd.DataFrame, target_edad: int = 40, enforce_monotonic: str = "isotonic"):
        """
        hist_lote: historial del lote (como el 'hist' que ya tienes en Sec 03)
        target_edad: hasta qué día proyectar (40)
        Retorna: df con Dia, Peso_predicho_kg
        """

        if hist_lote is None or hist_lote.empty:
            return {"error": "Historial vacío", "df": None}

        # Tomamos el último registro disponible del lote (snapshot actual)
        hist_lote = hist_lote.sort_values("Edad").copy()
        snap = hist_lote.iloc[-1].to_dict()

        # --- Mapeos para que coincida con el modelo entrenado ---
        # El modelo se entrenó con X4=Edad y Edad^2
        edad_actual = int(float(snap.get("Edad", np.nan)))
        if not np.isfinite(edad_actual) or edad_actual <= 0:
            return {"error": "No se pudo leer Edad del lote", "df": None}

        # alimento acumulado: tu dashboard maneja AlimAcumKg (kg). El modelo entrenado usó "alimento acumulado" (normalmente g)
        # Regla: si existe AlimAcumKg, lo pasamos a gramos.
        alim_acum_g_hoy = None
        if "AlimAcumKg" in hist_lote.columns and pd.notna(hist_lote.iloc[-1]["AlimAcumKg"]):
            try:
                alim_acum_g_hoy = float(hist_lote.iloc[-1]["AlimAcumKg"]) * 1000.0
            except Exception:
                alim_acum_g_hoy = None

        # Construimos snapshot base (sin el target)
        snapshot_base = dict(snap)

        # Normalizamos nombres que el modelo suele esperar
        snapshot_base["X4=Edad"] = edad_actual
        snapshot_base["Edad^2"] = float(edad_actual) ** 2

        # Si el modelo espera 'alimento acumulado', lo seteamos en gramos
        if "alimento acumulado" in self.features:
            if alim_acum_g_hoy is not None:
                snapshot_base["alimento acumulado"] = alim_acum_g_hoy
            else:
                # si no hay alimento, dejamos 0 (pero el modelo puede bajar confiabilidad)
                snapshot_base["alimento acumulado"] = snapshot_base.get("alimento acumulado", 0)

        # --- Proyección día a día ---
        target_edad = int(min(target_edad, self.max_edad))
        if target_edad < edad_actual:
            target_edad = edad_actual

        rows = []
        for dia in range(edad_actual, target_edad + 1):
            fila = dict(snapshot_base)
            fila["X4=Edad"] = dia
            fila["Edad^2"] = float(dia) ** 2

            # si existe perfil de alimento: reconstruimos alimento acumulado estimado por día
            if "alimento acumulado" in self.features and self.perfil_alimento is not None:
                try:
                    base = float(self.perfil_alimento.loc[dia])
                    if alim_acum_g_hoy is not None:
                        denom = float(self.perfil_alimento.loc[edad_actual])
                        factor = (alim_acum_g_hoy / denom) if denom > 0 else 1.0
                        fila["alimento acumulado"] = base * factor
                    else:
                        fila["alimento acumulado"] = base
                except Exception:
                    pass

            Xp = self._armar_fila_features(fila)
            pred = float(self.model.predict(Xp)[0])

            rows.append({"Dia": dia, "Peso_pred_raw": pred})

        out = pd.DataFrame(rows)

        # --- Forzar curva sin “saltos hacia abajo” ---
        if enforce_monotonic == "cummax":
            out["Peso_pred_kg"] = out["Peso_pred_raw"].cummax()
        elif enforce_monotonic == "isotonic":
            x = out["Dia"].values.astype(float)
            y = out["Peso_pred_raw"].values.astype(float)
            iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
            out["Peso_pred_kg"] = iso.fit_transform(x, y)
        else:
            out["Peso_pred_kg"] = out["Peso_pred_raw"]

        return {
            "error": None,
            "edad_actual": edad_actual,
            "peso_actual": float(hist_lote.iloc[-1]["PesoFinal"]) if "PesoFinal" in hist_lote.columns and pd.notna(hist_lote.iloc[-1]["PesoFinal"]) else None,
            "peso_d40": float(out.iloc[-1]["Peso_pred_kg"]),
            "df": out[["Dia", "Peso_pred_kg"]]
        }


def cargar_predictor(model_path: str) -> Predictor:
    bundle = joblib.load(model_path)

    # bundle esperado:
    # { "model": rf, "features": [...], "max_edad": 40, "perfil_alimento_mediana": Series, ... }
    model = bundle.get("model", None)
    features = bundle.get("features", [])
    max_edad = int(bundle.get("max_edad", 40))
    perfil = bundle.get("perfil_alimento_mediana", None)

    return Predictor(
        model=model,
        features=features,
        max_edad=max_edad,
        perfil_alimento=perfil
    )