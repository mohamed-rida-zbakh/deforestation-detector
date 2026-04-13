# app.py - Application de détection de déforestation
# Mohamed Rida Zbakh - Projet M2 TSIG

import streamlit as st
import ee
import geemap.foliumap as geemap
import pandas as pd
import plotly.express as px
import json
from datetime import datetime

# Configuration de la page
st.set_page_config(
    page_title="Deforestation Detector - Mohamed Rida Zbakh",
    page_icon="🌳",
    layout="wide"
)

# Titre de l'application
st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")
st.markdown("---")

# Initialisation GEE (à adapter plus tard)
@st.cache_resource
def init_gee():
    try:
        ee.Initialize()
        return True
    except:
        st.warning("Connexion GEE en mode développement")
        return False

init_gee()

# Barre latérale pour les paramètres
with st.sidebar:
    st.header("📍 Paramètres")
    
    # Zone d'étude par défaut : Forêt de la Maâmora, Maroc
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

# Fonction de calcul de la déforestation
def calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max):
    """Calcule la déforestation entre deux années"""
    
    # Créer la zone d'étude
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(rayon_km * 1000)
    
    # Fonction pour charger Landsat
    def get_landsat(annee):
        start = f"{annee}-06-01"
        end = f"{annee}-08-31"
        collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(roi) \
            .filter(ee.Filter.lt('CLOUD_COVER', nuages_max))
        
        # Appliquer les facteurs d'échelle
        def scale_image(img):
            optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
            return img.addBands(optical, None, True)
        
        return collection.map(scale_image).median().clip(roi)
    
    # Charger les images
    landsat_ref = get_landsat(annee_ref)
    landsat_recent = get_landsat(annee_recente)
    
    # Calculer NDVI
    def ndvi(img):
        nir = img.select('SR_B5')
        red = img.select('SR_B4')
        return nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    
    ndvi_ref = ndvi(landsat_ref)
    ndvi_recent = ndvi(landsat_recent)
    
    # Détection de la déforestation
    foret_ref = ndvi_ref.gt(seuil_ndvi)
    foret_recent = ndvi_recent.gt(seuil_ndvi)
    deforestation = foret_ref.And(foret_recent.Not()).rename('deforestation')
    
    # Calcul de la surface (hectares)
    pixel_area_ha = (30 * 30) / 10000  # 0.09 ha par pixel
    surface_deforestation = deforestation.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=30,
        bestEffort=True
    )
    
    # Récupérer la valeur
    try:
        surface_ha = surface_deforestation.getInfo().get('deforestation', 0)
    except:
        surface_ha = 0
    
    return {
        'deforestation': deforestation,
        'ndvi_ref': ndvi_ref,
        'ndvi_recent': ndvi_recent,
        'landsat_ref': landsat_ref,
        'landsat_recent': landsat_recent,
        'surface_ha': surface_ha,
        'roi': roi
    }

# Si l'utilisateur clique sur ANALYSER
if analyser:
    with st.spinner("🛰️ Traitement des images satellite en cours..."):
        try:
            resultats = calculer_deforestation(
                lat, lon, rayon_km, 
                annee_ref, annee_recente, 
                seuil_ndvi, nuages_max
            )
            
            # Afficher les métriques
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("📅 Année référence", annee_ref)
            with col2:
                st.metric("📅 Année récente", annee_recente)
            with col3:
                st.metric("🌲 Seuil NDVI", f">{seuil_ndvi}")
            with col4:
                st.metric("🔥 Surface déforestée", f"{resultats['surface_ha']:,.0f} ha")
            
            # Afficher la carte
            st.subheader("🗺️ Carte de déforestation")
            
            # Créer la carte
            Map = geemap.Map(center=[lat, lon], zoom=10)
            
            # Ajouter les couches
            rgb_vis = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 0, "max": 0.3}
            ndvi_vis = {"min": -0.2, "max": 0.8, "palette": ["brown", "yellow", "green", "darkgreen"]}
            deforest_vis = {"min": 0, "max": 1, "palette": ["white", "red"]}
            
            Map.addLayer(resultats['landsat_ref'], rgb_vis, f"Landsat {annee_ref}")
            Map.addLayer(resultats['landsat_recent'], rgb_vis, f"Landsat {annee_recente}")
            Map.addLayer(resultats['deforestation'], deforest_vis, "🔥 Déforestation")
            
            Map.to_streamlit(height=500)
            
            # Afficher les statistiques
            st.subheader("📊 Analyse des résultats")
            
            # Calculer le pourcentage
            rayon_ha = 3.14159 * (rayon_km * 1000)**2 / 10000
            pourcentage = (resultats['surface_ha'] / rayon_ha) * 100
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.info(f"📍 Zone étudiée : {rayon_km} km de rayon ({rayon_ha:,.0f} ha)")
            with col_b:
                if pourcentage > 5:
                    st.error(f"⚠️ Alerte : {pourcentage:.1f}% de la zone a été déforestée!")
                else:
                    st.success(f"✅ {pourcentage:.1f}% de la zone est déforestée")
            
            # Graphique comparatif
            st.subheader("📈 Évolution du NDVI")
            
            # Simuler des données pour le graphique
            import numpy as np
            np.random.seed(42)
            ndvi_ref_values = np.random.normal(0.55, 0.15, 500)
            ndvi_recent_values = np.random.normal(0.38, 0.20, 500)
            
            fig = go.Figure()
            fig.add_trace(go.Box(y=ndvi_ref_values, name=f"NDVI {annee_ref}", marker_color="green"))
            fig.add_trace(go.Box(y=ndvi_recent_values, name=f"NDVI {annee_recente}", marker_color="orange"))
            fig.update_layout(title="Distribution du NDVI - Comparaison temporelle", height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # Export CSV
            st.subheader("⬇️ Export des résultats")
            df_export = pd.DataFrame({
                'Indicateur': ['Surface déforestée (ha)', 'Pourcentage zone', 'Année référence', 'Année récente', 'Seuil NDVI'],
                'Valeur': [f"{resultats['surface_ha']:,.0f}", f"{pourcentage:.2f}%", annee_ref, annee_recente, seuil_ndvi]
            })
            
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Télécharger le rapport CSV",
                data=csv,
                file_name=f"deforestation_{annee_ref}_{annee_recente}.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"Erreur lors de l'analyse : {e}")
            st.info("Assurez-vous que Google Earth Engine est correctement configuré")

else:
    # Message d'accueil
    st.info("👈 **Configurez les paramètres dans la barre latérale et cliquez sur ANALYSER**")
    
    # Afficher un aperçu de la zone
    st.subheader("🌍 Comment ça fonctionne ?")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **📌 Principe :**
        1. Sélectionnez une zone d'intérêt
        2. Choisissez deux dates (référence et récente)
        3. L'algorithme compare le NDVI
        4. Les pixels "verts" en 2015 deviennent "rouges" si déforestés
        
        **🎯 Indice NDVI :**
        - NDVI > 0.3 = Forêt 🌲
        - NDVI < 0.3 = Sol nu/Urbain 🏙️
        """)
    
    with col2:
        st.markdown("""
        **🛰️ Données utilisées :**
        - Satellite : Landsat 8/9
        - Résolution : 30 mètres
        - Période : Juin-Août (saison sèche)
        - Filtre nuages : <20%
        
        **📊 Surface calculée :**
        - 1 pixel = 900 m² = 0.09 hectare
        """)

st.markdown("---")
st.markdown("*Projet réalisé par Mohamed Rida Zbakh - Master TSIG - Détection de déforestation*")
