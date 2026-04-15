# app.py - Application de détection de déforestation

import streamlit as st
import ee
import geemap.foliumap as geemap
import pandas as pd
import plotly.express as px
import json
from datetime import datetime

# Configuration de la page
st.set_page_config(
    page_title="Deforestation Detector",
    page_icon="🌳",
    layout="wide"
)

st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")

# ---------------------------
# Initialisation GEE
# ---------------------------
@st.cache_resource
def init_gee():
    try:
        # Pour déploiement Streamlit Cloud
        import os
        if "GEE_SERVICE_ACCOUNT_KEY" in st.secrets:
            key_dict = json.loads(st.secrets["GEE_SERVICE_ACCOUNT_KEY"])
            credentials = ee.ServiceAccountCredentials(
                key_dict["client_email"],
                key_data=json.dumps(key_dict)
            )
            ee.Initialize(credentials)
        else:
            # Développement local
            ee.Initialize()
        return True
    except Exception as e:
        st.error(f"Erreur GEE: {e}")
        return False

init_gee()

# ---------------------------
# Sidebar - Paramètres
# ---------------------------
with st.sidebar:
    st.header("📍 Zone d'étude")
    
    # Option 1: Dessiner sur carte ou saisir coordonnées
    input_method = st.radio("Méthode", ["Coordonnées", "Polygone (à faire dans le code)"])
    
    if input_method == "Coordonnées":
        lat = st.number_input("Latitude", value=-10.0, step=0.5)
        lon = st.number_input("Longitude", value=-63.0, step=0.5)
        buffer_km = st.slider("Rayon (km)", 10, 100, 30)
        
        # Créer un buffer circulaire
        roi = ee.Geometry.Point([lon, lat]).buffer(buffer_km * 1000)
    else:
        # Exemple de polygone (Amazonie)
        roi = ee.Geometry.Polygon([
            [[-63.5, -10.5], [-62.5, -10.5], [-62.5, -9.5], [-63.5, -9.5]]
        ])
        st.info("Zone par défaut : Amazonie (peut être modifiée dans le code)")
    
    st.divider()
    st.header("📅 Périodes")
    
    col1, col2 = st.columns(2)
    with col1:
        year1 = st.number_input("Année référence", value=2015, min_value=1984, max_value=2024)
        month1_start = st.selectbox("Mois début (ref)", range(1,13), index=6)
        month1_end = st.selectbox("Mois fin (ref)", range(1,13), index=7)
    with col2:
        year2 = st.number_input("Année récente", value=2023, min_value=1984, max_value=2024)
        month2_start = st.selectbox("Mois début (récent)", range(1,13), index=6)
        month2_end = st.selectbox("Mois fin (récent)", range(1,13), index=7)
    
    cloud_threshold = st.slider("Couverture nuageuse max (%)", 10, 80, 20)
    ndvi_threshold = st.slider("Seuil NDVI (forêt)", 0.1, 0.5, 0.3, 0.05)
    
    analyze_btn = st.button("🔍 Lancer l'analyse", type="primary")

# ---------------------------
# Fonctions de traitement
# ---------------------------
def get_landsat_collection(start_date, end_date, roi, max_cloud):
    collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
        .filterDate(start_date, end_date) \
        .filterBounds(roi) \
        .filter(ee.Filter.lt('CLOUD_COVER', max_cloud))
    
    # Appliquer les facteurs d'échelle
    def scale_image(img):
        optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
        return img.addBands(optical, None, True)
    
    return collection.map(scale_image).median().clip(roi)

def calculate_ndvi(image):
    nir = image.select('SR_B5')
    red = image.select('SR_B4')
    return nir.subtract(red).divide(nir.add(red)).rename('NDVI')

def detect_deforestation(ndvi1, ndvi2, threshold):
    forest1 = ndvi1.gt(threshold)
    forest2 = ndvi2.gt(threshold)
    return forest1.and(forest2.not()).rename('deforestation')

def calculate_area_ha(image, scale=30):
    pixel_area_ha = (scale * scale) / 10000
    return image.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=scale,
        bestEffort=True
    )

# ---------------------------
# Exécution principale
# ---------------------------
if analyze_btn:
    with st.spinner("Chargement et traitement des images..."):
        # Formatage des dates
        start1 = f"{year1}-{month1_start:02d}-01"
        end1 = f"{year1}-{month1_end:02d}-28"
        start2 = f"{year2}-{month2_start:02d}-01"
        end2 = f"{year2}-{month2_end:02d}-28"
        
        # Chargement
        landsat1 = get_landsat_collection(start1, end1, roi, cloud_threshold)
        landsat2 = get_landsat_collection(start2, end2, roi, cloud_threshold)
        
        ndvi1 = calculate_ndvi(landsat1)
        ndvi2 = calculate_ndvi(landsat2)
        
        deforestation = detect_deforestation(ndvi1, ndvi2, ndvi_threshold)
        
        # Calcul des superficies
        area_data = calculate_area_ha(deforestation)
        
        # Récupération des valeurs
        try:
            area_ha = area_data.getInfo().get('deforestation', 0)
        except:
            area_ha = 0
    
    # ---------------------------
    # Affichage des résultats
    # ---------------------------
    
    # Métriques
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("🌲 Forêt référence", f"{year1}")
    col_m2.metric("🌳 Forêt récente", f"{year2}")
    col_m3.metric("🔴 Surface déforestée", f"{area_ha:,.0f} ha")
    
    # Carte interactive
    st.subheader("🗺️ Carte de déforestation")
    
    Map = geemap.Map(center=[lat if input_method == "Coordonnées" else -10.0,
                              lon if input_method == "Coordonnées" else -63.0],
                      zoom=9)
    
    # Paramètres visuels
    rgb_vis = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 0, "max": 0.3, "gamma": 1.2}
    ndvi_vis = {"min": -0.2, "max": 0.8, "palette": ["brown", "yellow", "green", "darkgreen"]}
    deforest_vis = {"min": 0, "max": 1, "palette": ["white", "red"]}
    
    Map.addLayer(landsat1, rgb_vis, f"Landsat {year1}")
    Map.addLayer(landsat2, rgb_vis, f"Landsat {year2}")
    Map.addLayer(deforestation, deforest_vis, "Déforestation")
    
    Map.to_streamlit(height=500)
    
    # Graphique NDVI comparatif
    st.subheader("📊 Évolution du NDVI")
    
    # Échantillonnage pour le graphique
    def sample_ndvi_profile(ndvi, roi, n_points=1000):
        points = ee.FeatureCollection.randomPoints(roi, n_points)
        samples = ndvi.sampleRegions(
            collection=points,
            scale=30,
            geometries=False
        )
        return samples
    
    # Création DataFrame pour visualisation
    try:
        samples1 = sample_ndvi_profile(ndvi1, roi, 500)
        samples2 = sample_ndvi_profile(ndvi2, roi, 500)
        
        # Extraction
        values1 = samples1.aggregate_array('NDVI').getInfo()
        values2 = samples2.aggregate_array('NDVI').getInfo()
        
        # Création du boxplot
        import plotly.graph_objects as go
        
        fig = go.Figure()
        fig.add_trace(go.Box(y=values1, name=f"NDVI {year1}", marker_color="green"))
        fig.add_trace(go.Box(y=values2, name=f"NDVI {year2}", marker_color="orange"))
        fig.update_layout(title="Distribution du NDVI - Comparaison temporelle",
                          yaxis_title="NDVI",
                          xaxis_title="Période")
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.warning(f"Graphique NDVI non disponible: {e}")
    
    # Tableau récapitulatif
    st.subheader("📋 Synthèse")
    summary_df = pd.DataFrame({
        "Indicateur": ["Surface déforestée (ha)", "Seuil NDVI", "Couverture nuageuse max"],
        "Valeur": [f"{area_ha:,.0f}", f">{ndvi_threshold}", f"{cloud_threshold}%"]
    })
    st.dataframe(summary_df, use_container_width=True)
    
    # Export
    st.subheader("⬇️ Export des résultats")
    csv_data = pd.DataFrame([{
        "Année_référence": year1,
        "Année_récente": year2,
        "Surface_deforestation_ha": area_ha,
        "Seuil_NDVI": ndvi_threshold
    }])
    st.download_button(
        label="Télécharger les statistiques (CSV)",
        data=csv_data.to_csv(index=False),
        file_name=f"deforestation_{year1}_{year2}.csv",
        mime="text/csv"
    )

else:
    st.info("👈 Configurez les paramètres dans la barre latérale et cliquez sur 'Lancer l'analyse'")
