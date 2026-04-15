import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go
import json

st.set_page_config(page_title="Deforestation Detector", page_icon="🌳", layout="wide")

st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")

# Initialisation GEE
@st.cache_resource
def init_gee():
    try:
        if st.secrets.get("GEE_SERVICE_ACCOUNT"):
            service_account_info = json.loads(st.secrets["GEE_SERVICE_ACCOUNT"])
            credentials = ee.ServiceAccountCredentials(
                service_account_info["client_email"],
                key_data=st.secrets["GEE_SERVICE_ACCOUNT"]
            )
            ee.Initialize(credentials)
            st.success("✅ Google Earth Engine connecté avec succès !")
        else:
            ee.Initialize()
            st.info("🔧 Mode développement")
        return True
    except Exception as e:
        st.error(f"❌ Erreur GEE : {e}")
        return False

init_gee()

# Barre latérale
with st.sidebar:
    st.header("📍 Paramètres")
    lat = st.number_input("Latitude", value=34.05, step=0.1, format="%.2f")
    lon = st.number_input("Longitude", value=-6.85, step=0.1, format="%.2f")
    rayon_km = st.slider("Rayon d'étude (km)", 5, 50, 20)
    
    st.divider()
    st.header("📅 Périodes")
    annee_ref = st.number_input("Année référence", value=2015, min_value=2000, max_value=2020)
    annee_recente = st.number_input("Année récente", value=2023, min_value=2020, max_value=2025)
    
    st.divider()
    st.header("⚙️ Paramètres NDVI")
    seuil_ndvi = st.slider("Seuil NDVI (forêt)", 0.1, 0.5, 0.3, 0.05)
    nuages_max = st.slider("Nuages max (%)", 10, 50, 20)
    
    analyser = st.button("🔍 ANALYSER", type="primary", use_container_width=True)

def calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max):
    """Calcule la déforestation réelle avec GEE"""
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(rayon_km * 1000)
    
    def get_landsat(annee):
        start = f"{annee}-06-01"
        end = f"{annee}-08-31"
        collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(roi) \
            .filter(ee.Filter.lt('CLOUD_COVER', nuages_max))
        
        def scale_image(img):
            optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
            return img.addBands(optical, None, True)
        
        return collection.map(scale_image).median().clip(roi)
    
    landsat_ref = get_landsat(annee_ref)
    landsat_recent = get_landsat(annee_recente)
    
    def ndvi(img):
        nir = img.select('SR_B5')
        red = img.select('SR_B4')
        return nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    
    ndvi_ref = ndvi(landsat_ref)
    ndvi_recent = ndvi(landsat_recent)
    
    foret_ref = ndvi_ref.gt(seuil_ndvi)
    foret_recent = ndvi_recent.gt(seuil_ndvi)
    deforestation = foret_ref.And(foret_recent.Not())
    
    pixel_area_ha = (30 * 30) / 10000
    surface_deforestation = deforestation.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=30,
        bestEffort=True
    )
    
    try:
        surface_ha = surface_deforestation.getInfo().get('deforestation', 0)
    except:
        surface_ha = 0
    
    return surface_ha

if analyser:
    with st.spinner("🛰️ Analyse des images satellite en cours..."):
        try:
            surface_ha = calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max)
            
            # Affichage des résultats
            col1, col2, col3 = st.columns(3)
            col1.metric("📅 Année référence", annee_ref)
            col2.metric("📅 Année récente", annee_recente)
            col3.metric("🔥 Surface déforestée", f"{surface_ha:,.0f} ha")
            
            # Carte
            st.subheader("🗺️ Carte de la zone d'étude")
            m = folium.Map(location=[lat, lon], zoom_start=10)
            folium.Circle(radius=rayon_km*1000, location=[lat, lon], color='red', fill=True, fill_opacity=0.1).add_to(m)
            st_folium(m, width=700, height=450)
            
            st.success("✅ Analyse terminée avec succès !")
            
        except Exception as e:
            st.error(f"Erreur : {e}")
else:
    st.info("👈 Configurez les paramètres et cliquez sur ANALYSER")

st.markdown("---")
st.markdown("*Projet réalisé par Mohamed Rida Zbakh - Master TSIG*")
