"""
Model Predictor para PRONACA Dashboard v13
============================================

Responsabilidades:
  1. Cargar modelo Random Forest entrenado desde joblib
  2. Extraer features dinámicamente del historial del lote
  3. Proyectar iterativamente día a día (no solo peso)
  4. Aplicar restricción de monotonía
  5. Retornar curva completa para visualización

Uso:
  from model_predictor import cargar_predictor
  
  predictor = cargar_predictor("modelo_rf_avicola.joblib")
  
  res = predictor.proyectar_curva(
      hist_lote=hist_df,
      target_edad=40,
      enforce_monotonic="isotonic"
  )
  
  if not res.get("error"):
      df_prediccion = res["df"]
      peso_d40 = res["peso_d40"]
      edad_actual = res["edad_actual"]
"""

import os
import numpy as np
import pandas as pd
import joblib
from typing import Dict, Optional, Any
from sklearn.isotonic import IsotonicRegression


class Predictor:
    """
    Encapsulador del modelo RandomForest para proyecciones avícolas
    
    Attributes:
        model_path (str): Ruta al archivo joblib
        model: Modelo RandomForest cargado (None si no existe)
        features (list): Lista de features que el modelo espera
        max_edad (int): Edad máxima de predicción (generalmente 40)
        perfil_alimento (pd.Series): Perfil mediana de alimento por día
    """
    
    def __init__(self, model_path: str):
        """
        Carga el modelo y metadatos desde joblib
        
        Args:
            model_path (str): Ruta a modelo_rf_avicola.joblib
        """
        self.model_path = model_path
        self.model = None
        self.features = []
        self.max_edad = 40
        self.perfil_alimento = None
        
        if os.path.exists(model_path):
            try:
                bundle = joblib.load(model_path)
                self.model = bundle.get("model")
                self.features = bundle.get("features", [])
                self.max_edad = bundle.get("max_edad", 40)
                self.perfil_alimento = bundle.get("perfil_alimento_mediana")
                print(f"✅ Modelo cargado exitosamente: {len(self.features)} features")
                print(f"   Features: {', '.join(self.features[:5])}{'...' if len(self.features) > 5 else ''}")
            except Exception as e:
                print(f"❌ Error cargando modelo: {e}")
                self.model = None
        else:
            print(f"⚠️ Archivo no encontrado: {model_path}")
    
    def _get_snapshot_features(self, hist_lote: pd.DataFrame) -> Dict[str, float]:
        """
        Extrae TODAS las variables necesarias del último registro del lote
        
        El modelo fue entrenado con múltiples features (no solo peso):
        - X4=Edad
        - Edad^2
        - alimento acumulado
        - conversión alimenticia
        - mortalidad
        - zona
        - tipo granja
        - quintil
        - etc.
        
        Args:
            hist_lote (pd.DataFrame): DataFrame histórico del lote (ordenado por Edad)
        
        Returns:
            Dict[str, float]: Diccionario con todos los features mapeados
        """
        # Tomar el último registro válido (más reciente)
        ultimo = hist_lote.iloc[-1]
        
        snapshot = {}
        
        # Iterar sobre TODOS los features que el modelo espera
        for feat in self.features:
            if feat in hist_lote.columns:
                val = ultimo[feat]
                # Convertir a float, manejo de NaN
                try:
                    snapshot[feat] = float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    snapshot[feat] = 0.0
            else:
                # Feature no presente en los datos → usar 0.0
                snapshot[feat] = 0.0
        
        return snapshot
    
    def _ensure_columns_for_model(self, hist_lote: pd.DataFrame) -> pd.DataFrame:
        """
        Asegura que existan las columnas que el modelo espera (self.features),
        creando derivados comunes si vienen con otros nombres o en texto.
        """
        h = hist_lote.copy()

        # ─────────────────────────────────────────
        # 1) QUINTIL_num (si el modelo lo usa)
        # ─────────────────────────────────────────
        if "Quintil_num" in self.features and "Quintil_num" not in h.columns:
            src = None
            for c in ("Quintil", "quintil", "Quintil_Area_Crianza"):
                if c in h.columns:
                    src = c
                    break

            if src is not None:
                q = (
                    h[src].astype(str).str.upper().str.strip()
                    .str.extract(r"(Q[1-5])", expand=False)
                    .fillna("Q5")
                )
                h["Quintil_num"] = q.map({"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Q5": 5}).astype(float)
            else:
                # default seguro
                h["Quintil_num"] = 5.0

        # ─────────────────────────────────────────
        # 2) ZONA (si el modelo la usa)
        #   Ajusta el mapeo si en tu entrenamiento fue distinto.
        # ─────────────────────────────────────────
        if "Zona" in self.features and "Zona" not in h.columns:
            if "ZonaNombre" in h.columns:
                zn = h["ZonaNombre"].astype(str).str.upper()
                # ejemplo: 1=BUCAY, 2=SANTO DOMINGO
                h["Zona"] = np.where(zn.str.contains("BUC"), 1.0,
                            np.where(zn.str.contains("SANTO"), 2.0, 0.0))
            elif "LoteCompleto" in h.columns:
                pref = h["LoteCompleto"].astype(str).str[:3].str.upper()
                h["Zona"] = pref.map({"BUC": 1.0, "STO": 2.0}).fillna(0.0).astype(float)
            else:
                h["Zona"] = 0.0

        # ─────────────────────────────────────────
        # 3) X4=Edad y Edad^2 (si el modelo las usa)
        # ─────────────────────────────────────────
        if "X4=Edad" in self.features and "X4=Edad" not in h.columns and "Edad" in h.columns:
            h["X4=Edad"] = pd.to_numeric(h["Edad"], errors="coerce")

        if "Edad^2" in self.features and "Edad^2" not in h.columns:
            base = "X4=Edad" if "X4=Edad" in h.columns else ("Edad" if "Edad" in h.columns else None)
            if base is not None:
                h["Edad^2"] = pd.to_numeric(h[base], errors="coerce") ** 2

        # ─────────────────────────────────────────
        # 4) alimento acumulado (si el modelo lo usa)
        # ─────────────────────────────────────────
        if "alimento acumulado" in self.features and "alimento acumulado" not in h.columns:
            for c in ("AlimAcumKg", "Alimento_acumulado_kg", "AlimAcum", "alim_acum"):
                if c in h.columns:
                    h["alimento acumulado"] = pd.to_numeric(h[c], errors="coerce")
                    break
            if "alimento acumulado" not in h.columns:
                h["alimento acumulado"] = 0.0

        # ─────────────────────────────────────────
        # 5) Forzar numéricos para TODO lo que el modelo espera
        # ─────────────────────────────────────────
        for f in self.features:
            if f in h.columns:
                h[f] = pd.to_numeric(h[f], errors="coerce").fillna(0.0)

        return h
        
    def _interpolar_alimento(self, dia: int, alim_hoy: float, edad_hoy: int) -> float:
        """
        Estima alimento acumulado para un día futuro
        basándose en el perfil histórico
        
        Estrategia:
          - Si hay perfil_alimento (mediana por día) → usar ese
          - Si no → extrapolación lineal simple
        
        Args:
            dia (int): Día futuro (28, 29, 30, ..., 40)
            alim_hoy (float): Alimento acumulado al día actual (ej: 1250 kg)
            edad_hoy (int): Edad actual (ej: 28)
        
        Returns:
            float: Alimento acumulado estimado para el día futuro
        """
        if self.perfil_alimento is None or alim_hoy is None or alim_hoy == 0:
            # Estrategia simple: asumir consumo lineal
            consumo_diario = alim_hoy / max(edad_hoy, 1)
            return alim_hoy + consumo_diario * (dia - edad_hoy)
        
        # Usar perfil si está disponible
        try:
            if dia in self.perfil_alimento.index:
                perfil_dia = float(self.perfil_alimento.loc[dia])
                perfil_hoy = float(self.perfil_alimento.loc[edad_hoy])
                if perfil_hoy > 0:
                    factor = alim_hoy / perfil_hoy
                    return perfil_dia * factor
        except Exception:
            pass
        
        # Fallback: consumo diario lineal
        consumo_diario = alim_hoy / max(edad_hoy, 1)
        return alim_hoy + consumo_diario * (dia - edad_hoy)
    
    def _aplicar_restricciones(self, pesos: np.ndarray, metodo: str = "isotonic") -> np.ndarray:
        """
        Asegura que los pesos predichos sean monótonamente crecientes
        
        Un pollo NO pierde peso en crianza normal
        
        Args:
            pesos (np.ndarray): Array de pesos predichos [2.10, 2.25, 2.48, 2.41, 2.55, ...]
            metodo (str): "cummax" = máximo acumulado
                         "isotonic" = regresión isotónica (más suave)
        
        Returns:
            np.ndarray: Array ajustado [2.10, 2.25, 2.48, 2.48, 2.55, ...]
        """
        if metodo == "cummax":
            return np.maximum.accumulate(pesos)
        
        elif metodo == "isotonic":
            # Isotonic Regression: ajusta para que sea monótonamente creciente
            dias = np.arange(len(pesos), dtype=float)
            iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
            return iso.fit_transform(dias, pesos)
        
        else:
            return pesos
    
    def proyectar_curva(
        self,
        hist_lote: pd.DataFrame,
        target_edad: int = 40,
        enforce_monotonic: str = "isotonic",
    ) -> Dict[str, Any]:
        """
        FUNCIÓN PRINCIPAL: Proyecta la curva de crecimiento hasta target_edad
        
        Flujo:
          1. Extrae snapshot (TODAS las variables) del último día del lote
          2. Para cada día de hoy hasta target_edad:
             a. Actualiza variables (edad, edad^2, alimento estimado)
             b. Pasa al modelo RandomForest → obtiene peso predicho
             c. Almacena en lista
          3. Aplica restricción de monotonía
          4. Retorna DataFrame con curva completa
        
        Args:
            hist_lote (pd.DataFrame): DataFrame del lote (debe tener PesoFinal ordenado por Edad)
            target_edad (int): Día final de proyección (ej: 40)
            enforce_monotonic (str): "isotonic", "cummax", o None
        
        Returns:
            Dict[str, Any]: Diccionario con:
              - "error" (str o None): Mensaje de error si hay problema
              - "df" (pd.DataFrame): DataFrame con [Dia, Peso_pred_kg, Peso_pred_g]
              - "edad_actual" (int): Última edad en historial
              - "peso_d40" (float): Peso predicho para target_edad
        """
        try:
            # ────────────────────────────────────────────────────────────
            # VALIDACIONES BÁSICAS
            # ────────────────────────────────────────────────────────────
            if self.model is None:
                return {
                    "error": "Modelo no cargado",
                    "df": None,
                    "edad_actual": None,
                    "peso_d40": None
                }
            
            if hist_lote.empty:
                return {
                    "error": "Historial vacío",
                    "df": None,
                    "edad_actual": None,
                    "peso_d40": None
                }
            
            # ────────────────────────────────────────────────────────────
            # PREPARAR DATOS
            # ────────────────────────────────────────────────────────────
            
            # ✅ asegurar columnas que el modelo necesita (Quintil_num, Zona, etc.)
            hist_lote = self._ensure_columns_for_model(hist_lote)
            
            # Último registro disponible
            ultimo_registro = hist_lote.iloc[-1]
            edad_actual = int(ultimo_registro["Edad"])
            
            # Extraer SNAPSHOT de variables
            snapshot = self._get_snapshot_features(hist_lote)
            print("[DEBUG] snapshot Quintil_num =", snapshot.get("Quintil_num", None))
            print("[DEBUG] snapshot Zona       =", snapshot.get("Zona", None))
            
            # Obtener alimento acumulado del último registro
            alim_hoy = None
            for col in ["AlimAcumKg", "alimento acumulado", "Alimento_acumulado_kg", 
                        "AlimAcum", "alim_acum"]:
                if col in hist_lote.columns:
                    try:
                        alim_hoy = float(ultimo_registro[col])
                        if pd.notna(alim_hoy) and alim_hoy > 0:
                            break
                    except (ValueError, TypeError):
                        pass
            
            # ────────────────────────────────────────────────────────────
            # PROYECTAR DÍA A DÍA
            # ────────────────────────────────────────────────────────────
            
            pesos_predichos = []
            filas_resultado = []
            
            for dia in range(edad_actual, min(target_edad + 1, self.max_edad + 1)):
                # Copiar snapshot y actualizar variables
                fila_pred = dict(snapshot)
                
                # ⭐ ACTUALIZAR EDAD (variable continua)
                fila_pred["X4=Edad"] = float(dia)
                
                # ⭐ ACTUALIZAR EDAD^2 (variable derivada)
                if "Edad^2" in self.features:
                    fila_pred["Edad^2"] = float(dia ** 2)
                
                # ⭐ ESTIMAR ALIMENTO ACUMULADO
                if "alimento acumulado" in self.features and alim_hoy is not None:
                    fila_pred["alimento acumulado"] = self._interpolar_alimento(
                        dia, alim_hoy, edad_actual
                    )
                
                # Preparar DataFrame para predicción (solo features del modelo)
                X_pred = pd.DataFrame([{f: fila_pred.get(f, 0.0) for f in self.features}])
                
                # Predicción del modelo
                peso_kg = float(self.model.predict(X_pred)[0])
                pesos_predichos.append(peso_kg)
                
                filas_resultado.append({
                    "Dia": int(dia),
                    "Edad": int(dia),
                    "Peso_pred_kg_raw": float(peso_kg),
                    "Peso_pred_g_raw": float(peso_kg * 1000),
                })
            
            # ────────────────────────────────────────────────────────────
            # CREAR DATAFRAME
            # ────────────────────────────────────────────────────────────
            
            df_curve = pd.DataFrame(filas_resultado)
            
            # ────────────────────────────────────────────────────────────
            # APLICAR RESTRICCIÓN DE MONOTONÍA
            # ────────────────────────────────────────────────────────────
            
            if enforce_monotonic and len(pesos_predichos) > 0:
                pesos_ajustados = self._aplicar_restricciones(
                    np.array(pesos_predichos),
                    metodo=enforce_monotonic
                )
                df_curve["Peso_pred_kg"] = pesos_ajustados
                df_curve["Peso_pred_g"] = (pesos_ajustados * 1000).round(0).astype(int)
            else:
                df_curve["Peso_pred_kg"] = df_curve["Peso_pred_kg_raw"]
                df_curve["Peso_pred_g"] = df_curve["Peso_pred_g_raw"].round(0).astype(int)
            
            # ────────────────────────────────────────────────────────────
            # EXTRAER PESO PARA target_edad
            # ────────────────────────────────────────────────────────────
            
            df_target = df_curve[df_curve["Dia"] == target_edad]
            if not df_target.empty:
                peso_d40 = float(df_target.iloc[0]["Peso_pred_kg"])
            else:
                # Si target_edad está fuera de rango, tomar el último
                peso_d40 = float(df_curve.iloc[-1]["Peso_pred_kg"])
            
            # ────────────────────────────────────────────────────────────
            # RETORNAR RESULTADO
            # ────────────────────────────────────────────────────────────
            
            return {
                "error": None,
                "df": df_curve[["Dia", "Peso_pred_kg", "Peso_pred_g"]],
                "edad_actual": int(edad_actual),
                "peso_d40": float(peso_d40),
            }
        
        except Exception as e:
            import traceback
            error_msg = f"Excepción en proyección: {str(e)}\n{traceback.format_exc()}"
            print(f"❌ {error_msg}")
            return {
                "error": error_msg,
                "df": None,
                "edad_actual": None,
                "peso_d40": None,
            }


def cargar_predictor(ruta: str = "modelo_rf_avicola.joblib") -> Predictor:
    import os

    # Obtener ruta absoluta del archivo actual
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ruta_absoluta = os.path.join(base_dir, ruta)

    print("📁 Buscando modelo en:", ruta_absoluta)

    return Predictor(ruta_absoluta)


# ─────────────────────────────────────────────────────────────────────────────
# TEST (ejecutar si se corre este archivo directamente)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing model_predictor.py...")
    print("=" * 80)
    
    # Intentar cargar el predictor
    predictor = cargar_predictor("modelo_rf_avicola.joblib")
    
    if predictor.model is None:
        print("⚠️ El modelo no está disponible.")
        print("   Asegúrate de que 'modelo_rf_avicola.joblib' existe en la carpeta.")
    else:
        print(f"✅ Predictor cargado correctamente")
        print(f"   Features esperados: {len(predictor.features)}")
        print(f"   Max edad: {predictor.max_edad}")