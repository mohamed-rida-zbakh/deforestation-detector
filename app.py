import streamlit as st
import ee
import geemap.foliumap as geemap
import pandas as pd
import plotly.express as px
import json
import numpy as np

st.set_page_config(page_title="Deforestation Detector", page_icon="🌳", layout="wide")

st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")

@st.cache_resource
def init_gee():
    try:
        ee.Initialize()
        return True
    except:
        st.warning("Configuration GEE en cours...")
        return False

init_gee()

with st.sidebar:
    st.header("📍 Paramètres")
    lat = st.number_input("Latitude", value=34.05, step=0.1)
    lon = st.number_input("Longitude", value=-6.85, step=0.1)
    rayon_km = st.slider("Rayon d'étude (km)", 5, 50, 20)
    
    st.divider()
    annee_ref = st.number_input("Année référence", value=2015, min_value=2000, max_value=2020)
    annee_recente = st.number_input("Année récente", value=2023, min_value=2020, max_value=2025)
    
    st.divider()
    seuil_ndvi = st.slider("Seuil NDVI (forêt)", 0.1, 0.5, 0.3)
    nuages_max = st.slider("Nuages max (%)", 10, 50, 20)
    
    analyser = st.button("🔍 ANALYSER", type="primary", use_container_width=True)

if analyser:
    st.info(f"📍 Analyse de la zone : {lat}, {lon}")
    st.success(f"📊 Comparaison {annee_ref} → {annee_recente}")
    st.metric("🌲 Seuil NDVI", f">{seuil_ndvi}")
    
    # Carte de démonstration (sans GEE pour le test)
    st.subheader("🗺️ Carte de la zone d'étude")
    Map = geemap.Map(center=[lat, lon], zoom=10)
    Map.to_streamlit(height=450)
    
    st.info("✅ Application prête - Configuration GEE en cours d'activation")

else:
    st.info("👈 Configurez les paramètres et cliquez sur ANALYSER")
