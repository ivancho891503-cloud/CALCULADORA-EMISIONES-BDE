import streamlit as st
import pandas as pd
import os
import glob
import numpy as np
from datetime import datetime
import altair as alt
from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Calculadora GEI BDE", layout="wide", page_icon="📊")

# --- 1. CARGA DE BIBLIOTECA MAESTRA ---
@st.cache_data
def cargar_biblioteca_ghg():
    posibles = glob.glob("*.csv")
    filtro = [f for f in posibles if "biblioteca" in f.lower() or "factores" in f.lower()]
    ruta = filtro[0] if filtro else (posibles[0] if posibles else None)
    
    if ruta:
        try:
            df = pd.read_csv(ruta, skiprows=5, header=None, encoding='latin-1')
            df.columns = ["ID", "Alcance", "Nivel 1", "Nivel 2", "Nivel 3", "Nivel 4", 
                         "TextoColumna", "Unidad", "GEI_Unidad", "Factor"]
            df = df.dropna(subset=[1, 4, 9]) 
            for col in df.columns:
                if df[col].dtype == 'object': df[col] = df[col].str.strip()
            df['Factor'] = pd.to_numeric(df['Factor'], errors='coerce')
            return df.dropna(subset=['Factor']), ruta
        except Exception as e:
            return None, str(e)
    return None, "Archivo CSV no detectado en la raíz"

df_ghg, status_msg = cargar_biblioteca_ghg()

# --- 2. FUNCIÓN GENERAR PDF ---
def generar_pdf(df_final, t_costo, t_gei, t_int):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 15, "REPORTE DE HUELLA DE CARBONO - BDE", ln=True, align="C")
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 10, f"Costo Total: ${t_costo:,.2f} | GEI: {t_gei:,.2f} kg", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", "B", 8)
    pdf.cell(100, 8, " Rubro", 1); pdf.cell(45, 8, " Costo ($)", 1); pdf.cell(45, 8, " GEI (kg)", 1, 1)
    pdf.set_font("Arial", "", 7)
    for _, row in df_final.iterrows():
        pdf.cell(100, 7, str(row['Nivel 3'])[:60], 1)
        pdf.cell(45, 7, f"{row['Costo ($)']:,.2f}", 1)
        pdf.cell(45, 7, f"{row['Total GEI (kgCO2e)']:,.2f}", 1, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- 3. INICIALIZACIÓN ---
if 'tabla_proyecto' not in st.session_state:
    st.session_state.tabla_proyecto = pd.DataFrame(columns=['Grupo', 'Alcance', 'Nivel 1', 'Nivel 3', 'Unidad', 'Cantidad', 'Factor', 'Total GEI (kgCO2e)', 'Costo ($)', 'Intensidad'])

# --- 4. INTERFAZ ---
st.title("📊 Proyecto de Infraestructura - BDE")

if df_ghg is not None:
    with st.expander("➕ Registro de Rubros", expanded=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            alc = st.selectbox("1. Alcance", df_ghg['Alcance'].unique())
            n1 = st.selectbox("2. Categoría", df_ghg[df_ghg['Alcance'] == alc]['Nivel 1'].unique())
            n3 = st.selectbox("3. Ítem", df_ghg[df_ghg['Nivel 1'] == n1]['Nivel 3'].unique())
            df_f = df_ghg[df_ghg['Nivel 3'] == n3]
            uni = st.selectbox("4. Unidad", df_f['Unidad'].unique())
            f_val = float(df_f[df_f['Unidad'] == uni].iloc[0]['Factor'])
        with c2:
            cant = st.number_input("Cantidad", min_value=0.0)
            c_u = st.number_input("Costo Unitario ($)", min_value=0.0)
            st.metric("GEI Estimado", f"{cant * f_val:,.2f} kg")

        if st.button("✅ Registrar Rubro", use_container_width=True):
            if cant > 0:
                costo_t = cant * c_u
                nuevo = pd.DataFrame([{'Grupo': 'Gral', 'Alcance': alc, 'Nivel 1': n1, 'Nivel 3': n3, 'Unidad': uni, 
                                       'Cantidad': cant, 'Factor': f_val, 'Total GEI (kgCO2e)': cant * f_val, 
                                       'Costo ($)': costo_t, 'Intensidad': (cant * f_val)/costo_t if costo_t > 0 else 0}])
                st.session_state.tabla_proyecto = pd.concat([st.session_state.tabla_proyecto, nuevo], ignore_index=True)
                st.rerun()

# --- 5. RESULTADOS Y GESTIÓN (SINCRONIZACIÓN TOTAL) ---
# Definimos df_edit fuera de cualquier bloque de cálculo para que siempre sea accesible
df_edit = st.session_state.tabla_proyecto 

if not st.session_state.tabla_proyecto.empty:
    st.markdown("---")
    # Editor de datos que actualiza la variable central
    df_edit = st.data_editor(st.session_state.tabla_proyecto, num_rows="dynamic", use_container_width=True, key="main_editor")
    
    # Sincronización inmediata con la sesión
    if not df_edit.equals(st.session_state.tabla_proyecto):
        st.session_state.tabla_proyecto = df_edit
        st.rerun()

    # Cálculos y KPIs
    tc, tg = df_edit['Costo ($)'].sum(), df_edit['Total GEI (kgCO2e)'].sum()
    ti = tg / tc if tc > 0 else 0

    k1, k2, k3, k4 = st.columns([1, 1, 1, 1.5])
    k1.metric("PRESUPUESTO", f"${tc:,.2f}")
    k2.metric("TOTAL GEI", f"{tg:,.2f} kg")
    k3.metric("INTENSIDAD", f"{ti:.4f} kg/$")
    
    with k4:
        # Generar reporte usando la variable sincronizada
        pdf_bytes = generar_pdf(df_edit, tc, tg, ti)
        st.download_button("📄 Reporte PDF", pdf_bytes, "Reporte_BDE.pdf", "application/pdf", use_container_width=True)

    # Gráficos
    g1, g2 = st.columns(2)
    with g1:
        st.altair_chart(alt.Chart(df_edit).mark_bar().encode(x='sum(Total GEI (kgCO2e))', y='Nivel 1', color='Alcance'), use_container_width=True)
    with g2:
        st.altair_chart(alt.Chart(df_edit).mark_bar(color='gold').encode(x='Intensidad', y=alt.Y('Nivel 3', sort='-x')), use_container_width=True)
else:
    st.info(f"Sistema listo. Biblioteca: {status_msg}")