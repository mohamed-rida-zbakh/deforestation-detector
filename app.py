# app.py - Application de détection de déforestation
# Mohamed Rida Zbakh - Projet M2 TSIG
# Détection de déforestation par comparaison d'images Landsat

import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go
import json
import numpy as np

# Configuration de la page
st.set_page_config(
    page_title="Deforestation Detector - Mohamed Rida Zbakh",
    page_icon="🌳",
    layout="wide"
)

# Titre principal
st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")
st.markdown("---")

# ============================================
# INITIALISATION DE GOOGLE EARTH ENGINE
# ============================================

@st.cache_resource
def init_gee():
    """Initialise la connexion à Google Earth Engine"""
    try:
        # Vérifier si on est sur Streamlit Cloud avec secrets
        if st.secrets.get("GEE_SERVICE_ACCOUNT"):
            service_account_info = json.loads(st.secrets["GEE_SERVICE_ACCOUNT"])
            credentials = ee.ServiceAccountCredentials(
                service_account_info["client_email"],
                key_data=st.secrets["GEE_SERVICE_ACCOUNT"]
            )
            ee.Initialize(credentials)
            st.success("✅ Google Earth Engine connecté avec succès !")
        else:
            # Mode développement local
            ee.Initialize()
            st.info("🔧 Mode développement - GEE configuré localement")
        return True
    except Exception as e:
        st.error(f"❌ Erreur de connexion GEE : {e}")
        st.info("Vérifiez que les secrets Streamlit sont correctement configurés")
        return False

# Initialiser GEE
gee_ok = init_gee()

# ============================================
# BARRE LATÉRALE - PARAMÈTRES
# ============================================

with st.sidebar:
    st.header("📍 Zone d'étude")
    
    lat = st.number_input(
        "Latitude",
        value=34.05,
        step=0.1,
        format="%.2f",
        help="Exemple: 34.05 pour la Maâmora (Maroc)"
    )
    
    lon = st.number_input(
        "Longitude",
        value=-6.85,
        step=0.1,
        format="%.2f",
        help="Exemple: -6.85 pour la Maâmora (Maroc)"
    )
    
    rayon_km = st.slider(
        "Rayon d'étude (km)",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
        help="Rayon autour du point central"
    )
    
    st.divider()
    
    st.header("📅 Périodes")
    
    col1, col2 = st.columns(2)
    with col1:
        annee_ref = st.number_input(
            "Année référence",
            value=2015,
            min_value=2000,
            max_value=2020,
            help="Année de référence (avant déforestation)"
        )
    with col2:
        annee_recente = st.number_input(
            "Année récente",
            value=2023,
            min_value=2020,
            max_value=2025,
            help="Année récente (après déforestation potentielle)"
        )
    
    st.divider()
    
    st.header("⚙️ Paramètres NDVI")
    
    seuil_ndvi = st.slider(
        "Seuil NDVI (forêt)",
        min_value=0.1,
        max_value=0.5,
        value=0.3,
        step=0.05,
        help="NDVI > seuil = forêt, NDVI < seuil = sol nu/urbain"
    )
    
    nuages_max = st.slider(
        "Couverture nuageuse max (%)",
        min_value=10,
        max_value=50,
        value=20,
        step=5,
        help="Pourcentage maximal de nuages accepté"
    )
    
    st.divider()
    
    analyser = st.button(
        "🔍 ANALYSER LA DÉFORESTATION",
        type="primary",
        use_container_width=True
    )

# ============================================
# FONCTIONS DE TRAITEMENT GEE
# ============================================

def creer_carte_folium(lat, lon, rayon_km):
    """Crée une carte interactive avec folium"""
    m = folium.Map(
        location=[lat, lon],
        zoom_start=10,
        control_scale=True
    )
    
    # Ajouter un cercle pour la zone d'étude
    folium.Circle(
        radius=rayon_km * 1000,
        location=[lat, lon],
        color='red',
        weight=2,
        fill=True,
        fill_opacity=0.1,
        popup=f"Zone d'étude : {rayon_km} km"
    ).add_to(m)
    
    # Ajouter un marqueur au centre
    folium.Marker(
        [lat, lon],
        popup=f"Centre: {lat}, {lon}",
        icon=folium.Icon(color='green', icon='tree', prefix='fa')
    ).add_to(m)
    
    # Ajouter une échelle
    folium.LayerControl().add_to(m)
    
    return m

def calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max):
    """Calcule la surface déforestée en hectares"""
    
    # Créer la zone d'étude
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(rayon_km * 1000)
    
    def get_landsat(annee):
        """Charge et filtre les images Landsat pour une année donnée"""
        start = f"{annee}-06-01"
        end = f"{annee}-08-31"
        
        collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
            .filterDate(start, end) \
            .filterBounds(roi) \
            .filter(ee.Filter.lt('CLOUD_COVER', nuages_max))
        
        def scale_image(img):
            # Appliquer les facteurs d'échelle pour la réflectance
            optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
            return img.addBands(optical, None, True)
        
        # Composition médiane et clipping
        return collection.map(scale_image).median().clip(roi)
    
    def calculate_ndvi(img):
        """Calcule l'indice NDVI"""
        nir = img.select('SR_B5')
        red = img.select('SR_B4')
        return nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    
    # Charger les images
    landsat_ref = get_landsat(annee_ref)
    landsat_recent = get_landsat(annee_recente)
    
    # Calculer NDVI
    ndvi_ref = calculate_ndvi(landsat_ref)
    ndvi_recent = calculate_ndvi(landsat_recent)
    
    # Détection de la déforestation
    foret_ref = ndvi_ref.gt(seuil_ndvi)
    foret_recent = ndvi_recent.gt(seuil_ndvi)
    deforestation = foret_ref.And(foret_recent.Not()).rename('deforestation')
    
    # Calcul de la surface en hectares
    # Pixel Landsat = 30m x 30m = 900 m² = 0.09 hectare
    pixel_area_ha = (30 * 30) / 10000
    
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
    
    # Calculer aussi les NDVI moyens
    ndvi_ref_moyen = ndvi_ref.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=30,
        bestEffort=True
    )
    
    ndvi_recent_moyen = ndvi_recent.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=30,
        bestEffort=True
    )
    
    try:
        ndvi_ref_val = ndvi_ref_moyen.getInfo().get('NDVI', 0)
        ndvi_recent_val = ndvi_recent_moyen.getInfo().get('NDVI', 0)
    except:
        ndvi_ref_val = 0
        ndvi_recent_val = 0
    
    return {
        'surface_ha': surface_ha,
        'ndvi_ref': ndvi_ref_val,
        'ndvi_recent': ndvi_recent_val,
        'roi': roi
    }

# ============================================
# INTERFACE PRINCIPALE
# ============================================

if analyser:
    if not gee_ok:
        st.error("❌ Google Earth Engine n'est pas configuré. Vérifiez les secrets.")
    else:
        with st.spinner("🛰️ Analyse des images satellite en cours..."):
            try:
                # Calculer la déforestation
                resultats = calculer_deforestation(
                    lat, lon, rayon_km,
                    annee_ref, annee_recente,
                    seuil_ndvi, nuages_max
                )
                
                surface_ha = resultats['surface_ha']
                ndvi_ref_val = resultats['ndvi_ref']
                ndvi_recent_val = resultats['ndvi_recent']
                
                # Calculer la surface totale de la zone
                surface_totale_ha = 3.14159 * (rayon_km * 1000)**2 / 10000
                pourcentage_deforestation = (surface_ha / surface_totale_ha) * 100 if surface_totale_ha > 0 else 0
                
                # ============================================
                # AFFICHAGE DES MÉTRIQUES
                # ============================================
                
                st.subheader("📊 Résultats de l'analyse")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("📅 Année référence", annee_ref)
                with col2:
                    st.metric("📅 Année récente", annee_recente)
                with col3:
                    st.metric("🌲 NDVI référence", f"{ndvi_ref_val:.3f}")
                with col4:
                    st.metric("🌳 NDVI récent", f"{ndvi_recent_val:.3f}", delta=f"{ndvi_recent_val - ndvi_ref_val:.3f}")
                
                col5, col6, col7 = st.columns(3)
                
                with col5:
                    st.metric("🔥 Surface déforestée", f"{surface_ha:,.0f} ha")
                with col6:
                    st.metric("📐 Surface totale zone", f"{surface_totale_ha:,.0f} ha")
                with col7:
                    if pourcentage_deforestation > 10:
                        st.metric("📉 Taux déforestation", f"{pourcentage_deforestation:.1f}%", delta="ALERTE !", delta_color="inverse")
                    else:
                        st.metric("📉 Taux déforestation", f"{pourcentage_deforestation:.1f}%")
                
                # ============================================
                # CARTE INTERACTIVE
                # ============================================
                
                st.subheader("🗺️ Carte de la zone d'étude")
                carte = creer_carte_folium(lat, lon, rayon_km)
                st_folium(carte, width=800, height=500)
                
                # ============================================
                # GRAPHIQUE NDVI
                # ============================================
                
                st.subheader("📈 Évolution du NDVI")
                
                fig = go.Figure()
                
                # Barres pour les valeurs NDVI
                fig.add_trace(go.Bar(
                    x=[str(annee_ref), str(annee_recente)],
                    y=[ndvi_ref_val, ndvi_recent_val],
                    name="NDVI moyen",
                    marker_color=["#228B22", "#FF8C00"],
                    text=[f"{ndvi_ref_val:.3f}", f"{ndvi_recent_val:.3f}"],
                    textposition="auto"
                ))
                
                # Ligne de seuil forêt
                fig.add_hline(
                    y=seuil_ndvi,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Seuil forêt = {seuil_ndvi}",
                    annotation_position="bottom right"
                )
                
                fig.update_layout(
                    title="Comparaison du NDVI entre les deux périodes",
                    xaxis_title="Année",
                    yaxis_title="NDVI (Normalized Difference Vegetation Index)",
                    yaxis_range=[-0.2, 0.9],
                    template="plotly_white",
                    height=450
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # ============================================
                # INTERPRÉTATION
                # ============================================
                
                st.subheader("📝 Interprétation des résultats")
                
                if surface_ha > 100:
                    st.error(f"🚨 **Alerte déforestation !** Une surface de **{surface_ha:,.0f} hectares** a été déforestée entre {annee_ref} et {annee_recente}.")
                elif surface_ha > 10:
                    st.warning(f"⚠️ **Déforestation modérée.** {surface_ha:,.0f} hectares ont été perdus sur la zone étudiée.")
                else:
                    st.success(f"✅ **Peu ou pas de déforestation** détectée sur la zone étudiée.")
                
                # Afficher l'évolution du NDVI
                variation_ndvi = ndvi_recent_val - ndvi_ref_val
                if variation_ndvi < -0.1:
                    st.warning(f"📉 Forte baisse du NDVI ({variation_ndvi:.3f}) → perte significative de végétation.")
                elif variation_ndvi < -0.05:
                    st.info(f"📉 Baisse modérée du NDVI ({variation_ndvi:.3f}) → perte de végétation observable.")
                else:
                    st.success(f"📈 NDVI stable ou en hausse → la végétation est préservée.")
                
                # ============================================
                # EXPORT DES RÉSULTATS
                # ============================================
                
                st.subheader("⬇️ Export des résultats")
                
                # Créer un DataFrame pour l'export
                df_export = pd.DataFrame({
                    'Indicateur': [
                        'Latitude',
                        'Longitude',
                        'Rayon (km)',
                        'Année référence',
                        'Année récente',
                        'Seuil NDVI',
                        'Nuages max (%)',
                        'NDVI référence',
                        'NDVI récent',
                        'Variation NDVI',
                        'Surface déforestée (ha)',
                        'Surface totale zone (ha)',
                        'Taux déforestation (%)'
                    ],
                    'Valeur': [
                        lat,
                        lon,
                        rayon_km,
                        annee_ref,
                        annee_recente,
                        seuil_ndvi,
                        nuages_max,
                        f"{ndvi_ref_val:.3f}",
                        f"{ndvi_recent_val:.3f}",
                        f"{variation_ndvi:.3f}",
                        f"{surface_ha:.0f}",
                        f"{surface_totale_ha:.0f}",
                        f"{pourcentage_deforestation:.1f}"
                    ]
                })
                
                # Bouton de téléchargement CSV
                csv = df_export.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger le rapport CSV",
                    data=csv,
                    file_name=f"deforestation_{annee_ref}_{annee_recente}_{lat}_{lon}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                st.success("✅ Analyse terminée avec succès !")
                
            except Exception as e:
                st.error(f"❌ Erreur lors de l'analyse : {e}")
                st.info("""
                **Causes possibles :**
                - Pas d'images disponibles pour cette période
                - Couverture nuageuse trop élevée
                - Problème de connexion à GEE
                
                **Solutions :**
                - Augmentez le seuil de nuages max
                - Changez la zone d'étude
                - Vérifiez que GEE est bien configuré
                """)

else:
    # ============================================
    # PAGE D'ACCUEIL (avant analyse)
    # ============================================
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.info("👈 **Configurez les paramètres dans la barre latérale et cliquez sur ANALYSER**")
        
        st.subheader("🌍 Comment ça fonctionne ?")
        
        st.markdown("""
        **📌 Principe :**
        1. Sélectionnez une zone d'intérêt (latitude, longitude, rayon)
        2. Choisissez deux dates (année référence et année récente)
        3. L'algorithme compare le NDVI (indice de végétation)
        4. Les pixels "verts" (forêt) en année référence qui deviennent "non-verts" sont comptés comme déforestés
        
        **🎯 Indice NDVI :**
        - NDVI > 0.3 = Forêt 🌲
        - NDVI < 0.3 = Sol nu / Urbain / Eau 🏙️
        
        **🛰️ Données utilisées :**
        - Satellite : Landsat 8/9 Collection 2
        - Résolution spatiale : 30 mètres
        - Période d'acquisition : Juin-Août (saison sèche)
        - Filtre nuages : paramétrable
        
        **📊 Surface calculée :**
        - 1 pixel Landsat = 30m x 30m = 900 m² = 0.09 hectare
        """)
    
    with col2:
        # Aperçu de la carte par défaut
        st.subheader("🗺️ Aperçu")
        carte_defaut = creer_carte_folium(34.05, -6.85, 20)
        st_folium(carte_defaut, width=400, height=350)
        
        st.caption("Zone par défaut : Forêt de la Maâmora, Maroc")

# ============================================
# PIED DE PAGE
# ============================================

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: gray; font-size: 12px;">
    🌳 Projet réalisé par <strong>Mohamed Rida Zbakh</strong> - Master TSIG - Détection de déforestation par satellite<br>
    Données : Landsat 8/9 (NASA/USGS) | Plateforme : Google Earth Engine & Streamlit Cloud
    </div>
    """,
    unsafe_allow_html=True
)
# Ajouter cette fonction dans votre app.py

from fpdf import FPDF
import tempfile
import os

def generer_pdf_rapport(lat, lon, rayon_km, annee_ref, annee_recente, 
                         surface_ha, ndvi_ref, ndvi_recent, seuil_ndvi):
    """Génère un rapport PDF des résultats"""
    
    # Créer le PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Titre
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(26, 77, 42)  # Vert forêt
    pdf.cell(0, 15, "RAPPORT DE DÉFORESTATION", ln=True, align="C")
    
    # Date
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(100, 100, 100)
    from datetime import datetime
    pdf.cell(0, 8, f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="R")
    
    # Ligne de séparation
    pdf.line(10, 45, 200, 45)
    
    # Zone d'étude
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 12, "📍 ZONE D'ÉTUDE", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Latitude : {lat}", ln=True)
    pdf.cell(0, 8, f"Longitude : {lon}", ln=True)
    pdf.cell(0, 8, f"Rayon : {rayon_km} km", ln=True)
    
    # Périodes
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 12, "📅 PÉRIODES ANALYSÉES", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Année référence : {annee_ref}", ln=True)
    pdf.cell(0, 8, f"Année récente : {annee_recente}", ln=True)
    pdf.cell(0, 8, f"Seuil NDVI : > {seuil_ndvi}", ln=True)
    
    # Résultats
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 12, "📊 RÉSULTATS", ln=True)
    
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"NDVI {annee_ref} : {ndvi_ref:.3f}", ln=True)
    pdf.cell(0, 8, f"NDVI {annee_recente} : {ndvi_recent:.3f}", ln=True)
    
    variation = ndvi_recent - ndvi_ref
    pourcentage_var = (variation / ndvi_ref) * 100
    pdf.cell(0, 8, f"Variation NDVI : {variation:.3f} ({pourcentage_var:.1f}%)", ln=True)
    
    pdf.set_text_color(220, 20, 60)  # Rouge
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 12, f"🔥 SURFACE DÉFORESTÉE : {surface_ha:,.0f} HECTARES", ln=True)
    
    # Interprétation
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 12, "📝 INTERPRÉTATION", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.multi_cell(0, 7, f"Nous observons une baisse significative du NDVI de {abs(pourcentage_var):.0f}%, correspondant à une perte de {surface_ha:,.0f} hectares de couvert forestier entre {annee_ref} et {annee_recente}.")
    
    # Sauvegarder
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf.output(temp_file.name)
    return temp_file.name
    # À la fin de la section des résultats (après l'export CSV)

st.subheader("⬇️ Export des résultats")

# Bouton CSV existant
csv = df_export.to_csv(index=False).encode('utf-8')
st.download_button("📥 Télécharger le rapport CSV", csv, ...)

# Ajouter ce bouton pour le PDF
if st.button("📄 Télécharger le rapport PDF", use_container_width=True):
    with st.spinner("Génération du PDF en cours..."):
        pdf_path = generer_pdf_rapport(
            lat, lon, rayon_km,
            annee_ref, annee_recente,
            surface_ha, ndvi_ref_val, ndvi_recent_val,
            seuil_ndvi
        )
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        st.download_button(
            label="✅ Télécharger le PDF",
            data=pdf_data,
            file_name=f"rapport_deforestation_{annee_ref}_{annee_recente}.pdf",
            mime="application/pdf"
        )
        os.unlink(pdf_path)  # Supprimer le fichier temporaire
