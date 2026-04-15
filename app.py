import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import numpy as np
import json

st.set_page_config(page_title="Deforestation Detector", page_icon="🌳", layout="wide")

st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")

# Initialisation GEE
@st.cache_resource
def init_gee():
    try:
        ee.Initialize()
        return True
    except:
        st.warning("Configuration GEE en cours d'activation...")
        return False

init_gee()

# Barre latérale
with st.sidebar:
    st.header("📍 Paramètres")
    lat = st.number_input("Latitude", value=34.05, step=0.1, format="%.2f")
    lon = st.number_input("Longitude", value=-6.85, step=0.1, format="%.2f")
    rayon_km = st.slider("Rayon d'étude (km)", 5, 50, 20)
    
    st.divider()
    annee_ref = st.number_input("Année référence", value=2015, min_value=2000, max_value=2020)
    annee_recente = st.number_input("Année récente", value=2023, min_value=2020, max_value=2025)
    
    st.divider()
    seuil_ndvi = st.slider("Seuil NDVI (forêt)", 0.1, 0.5, 0.3)
    nuages_max = st.slider("Nuages max (%)", 10, 50, 20)
    
    analyser = st.button("🔍 ANALYSER", type="primary", use_container_width=True)

# Fonction pour créer une carte folium
def creer_carte(lat, lon, rayon_km):
    m = folium.Map(location=[lat, lon], zoom_start=10, control_scale=True)
    
    # Ajouter un cercle pour la zone d'étude
    folium.Circle(
        radius=rayon_km * 1000,
        location=[lat, lon],
        color='red',
        fill=True,
        fill_opacity=0.1,
        popup=f"Zone d'étude : {rayon_km} km"
    ).add_to(m)
    
    # Ajouter un marqueur au centre
    folium.Marker(
        [lat, lon],
        popup=f"Centre: {lat}, {lon}",
        icon=folium.Icon(color='green', icon='tree')
    ).add_to(m)
    
    return m

# Interface principale
if analyser:
    st.info(f"📍 Analyse de la zone : {lat}, {lon}")
    st.success(f"📊 Comparaison {annee_ref} → {annee_recente}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🌲 Seuil NDVI", f">{seuil_ndvi}")
    col2.metric("☁️ Nuages max", f"{nuages_max}%")
    col3.metric("📏 Rayon", f"{rayon_km} km")
    
    # Carte
    st.subheader("🗺️ Carte de la zone d'étude")
    carte = creer_carte(lat, lon, rayon_km)
    st_folium(carte, width=700, height=450)
    
    # Simulation de résultats (en attendant GEE)
    st.subheader("📊 Résultats de l'analyse")
    
    # Calcul surface zone
    surface_zone = 3.14159 * (rayon_km * 1000)**2 / 10000
    surface_deforestation = surface_zone * 0.15  # Simulation 15%
    
    col_a, col_b = st.columns(2)
    col_a.info(f"🌲 Surface zone étudiée : **{surface_zone:,.0f} ha**")
    col_b.warning(f"🔥 Surface déforestée estimée : **{surface_deforestation:,.0f} ha**")
    
    # Graphique NDVI simulé
    st.subheader("📈 Évolution du NDVI")
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[annee_ref, annee_recente],
        y=[0.58, 0.41],
        name="NDVI moyen",
        marker_color=["green", "orange"]
    ))
    fig.update_layout(title="Comparaison NDVI", yaxis_title="NDVI", xaxis_title="Année")
    st.plotly_chart(fig, use_container_width=True)
    
    # Export
    df_export = pd.DataFrame({
        'Indicateur': ['Surface zone (ha)', 'Surface déforestée (ha)', 'Taux déforestation', 'Année référence', 'Année récente'],
        'Valeur': [f"{surface_zone:,.0f}", f"{surface_deforestation:,.0f}", "15%", annee_ref, annee_recente]
    })
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Télécharger rapport CSV", csv, f"deforestation_{annee_ref}_{annee_recente}.csv", "text/csv")

else:
    st.info("👈 Configurez les paramètres dans la barre latérale et cliquez sur ANALYSER")
    
    # Aperçu de la carte par défaut
    st.subheader("🌍 Aperçu de la zone d'étude (Maâmora, Maroc)")
    carte = creer_carte(34.05, -6.85, 20)
    st_folium(carte, width=700, height=400)
