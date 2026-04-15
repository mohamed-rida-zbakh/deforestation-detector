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
import traceback  # 🔥 AJOUT

# Configuration de la page
st.set_page_config(
    page_title="Deforestation Detector - Mohamed Rida Zbakh",
    page_icon="🌳",
    layout="wide"
)

# 🔥 AJOUT - Initialiser session_state pour garder les résultats
if 'resultats' not in st.session_state:
    st.session_state.resultats = None
if 'analyse_effectuee' not in st.session_state:
    st.session_state.analyse_effectuee = False

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
            st.info("🔧 Mode développement - GEE configuré localement")
        return True
    except Exception as e:
        st.error(f"❌ Erreur de connexion GEE : {e}")
        return False

gee_ok = init_gee()

# ============================================
# BARRE LATÉRALE - PARAMÈTRES
# ============================================

with st.sidebar:
    st.header("📍 Zone d'étude")
    
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
    nuages_max = st.slider("Couverture nuageuse max (%)", 10, 50, 20)
    
    st.divider()
    
    analyser = st.button("🔍 ANALYSER LA DÉFORESTATION", type="primary", use_container_width=True)
    
    # 🔥 AJOUT - Bouton pour réinitialiser
    if st.button("🔄 Nouvelle analyse", use_container_width=True):
        st.session_state.resultats = None
        st.session_state.analyse_effectuee = False
        st.rerun()

# ============================================
# FONCTIONS DE TRAITEMENT GEE
# ============================================

def creer_carte_folium(lat, lon, rayon_km):
    m = folium.Map(location=[lat, lon], zoom_start=10, control_scale=True)
    folium.Circle(radius=rayon_km * 1000, location=[lat, lon], color='red', weight=2, fill=True, fill_opacity=0.1, popup=f"Zone d'étude : {rayon_km} km").add_to(m)
    folium.Marker([lat, lon], popup=f"Centre: {lat}, {lon}", icon=folium.Icon(color='green', icon='tree', prefix='fa')).add_to(m)
    folium.LayerControl().add_to(m)
    return m

def calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max):
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
    
    def calculate_ndvi(img):
        nir = img.select('SR_B5')
        red = img.select('SR_B4')
        return nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    
    landsat_ref = get_landsat(annee_ref)
    landsat_recent = get_landsat(annee_recente)
    
    ndvi_ref = calculate_ndvi(landsat_ref)
    ndvi_recent = calculate_ndvi(landsat_recent)
    
    foret_ref = ndvi_ref.gt(seuil_ndvi)
    foret_recent = ndvi_recent.gt(seuil_ndvi)
    deforestation = foret_ref.And(foret_recent.Not()).rename('deforestation')
    
    pixel_area_ha = (30 * 30) / 10000
    
    surface_deforestation = deforestation.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale=30,
        bestEffort=True,
        maxPixels=1e9  # 🔥 AJOUT
    )
    
    ndvi_ref_moyen = ndvi_ref.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, bestEffort=True)
    ndvi_recent_moyen = ndvi_recent.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=30, bestEffort=True)
    
    try:
        surface_ha = surface_deforestation.getInfo().get('deforestation', 0)
        ndvi_ref_val = ndvi_ref_moyen.getInfo().get('NDVI', 0)
        ndvi_recent_val = ndvi_recent_moyen.getInfo().get('NDVI', 0)
        return {'surface_ha': surface_ha, 'ndvi_ref': ndvi_ref_val, 'ndvi_recent': ndvi_recent_val}
    except Exception as e:
        st.error(f"Erreur GEE: {e}")
        return None

# ============================================
# LANCEMENT DE L'ANALYSE
# ============================================

if analyser:
    st.session_state.analyse_effectuee = True
    with st.spinner("🛰️ Analyse des images satellite en cours... (20-40 secondes)"):
        if not gee_ok:
            st.error("❌ Google Earth Engine n'est pas configuré.")
        else:
            try:
                resultats = calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max)
                if resultats:
                    st.session_state.resultats = {
                        'surface_ha': resultats['surface_ha'],
                        'ndvi_ref': resultats['ndvi_ref'],
                        'ndvi_recent': resultats['ndvi_recent'],
                        'lat': lat, 'lon': lon, 'rayon_km': rayon_km,
                        'annee_ref': annee_ref, 'annee_recente': annee_recente,
                        'seuil_ndvi': seuil_ndvi, 'nuages_max': nuages_max
                    }
                    st.success("✅ Analyse terminée avec succès !")
                else:
                    st.error("❌ L'analyse n'a pas pu aboutir")
            except Exception as e:
                st.error(f"❌ Erreur: {e}")
                st.code(traceback.format_exc())

# ============================================
# AFFICHAGE DES RÉSULTATS (s'ils existent)
# ============================================

if st.session_state.resultats:
    res = st.session_state.resultats
    
    surface_totale_ha = 3.14159 * (res['rayon_km'] * 1000)**2 / 10000
    pourcentage = (res['surface_ha'] / surface_totale_ha) * 100 if surface_totale_ha > 0 else 0
    variation_ndvi = res['ndvi_recent'] - res['ndvi_ref']
    
    st.subheader("📊 Résultats de l'analyse")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Année référence", res['annee_ref'])
    col2.metric("📅 Année récente", res['annee_recente'])
    col3.metric("🌲 NDVI référence", f"{res['ndvi_ref']:.3f}")
    col4.metric("🌳 NDVI récent", f"{res['ndvi_recent']:.3f}", delta=f"{variation_ndvi:.3f}")
    
    col5, col6, col7 = st.columns(3)
    col5.metric("🔥 Surface déforestée", f"{res['surface_ha']:,.0f} ha")
    col6.metric("📐 Surface totale zone", f"{surface_totale_ha:,.0f} ha")
    
    if pourcentage > 10:
        col7.metric("📉 Taux déforestation", f"{pourcentage:.1f}%", delta="ALERTE !", delta_color="inverse")
    else:
        col7.metric("📉 Taux déforestation", f"{pourcentage:.1f}%")
    
    st.subheader("🗺️ Carte de la zone d'étude")
    carte = creer_carte_folium(res['lat'], res['lon'], res['rayon_km'])
    st_folium(carte, width=800, height=500)
    
    st.subheader("📈 Évolution du NDVI")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[str(res['annee_ref']), str(res['annee_recente'])], y=[res['ndvi_ref'], res['ndvi_recent']], marker_color=["#228B22", "#FF8C00"], text=[f"{res['ndvi_ref']:.3f}", f"{res['ndvi_recent']:.3f}"], textposition="auto"))
    fig.add_hline(y=res['seuil_ndvi'], line_dash="dash", line_color="red", annotation_text=f"Seuil forêt = {res['seuil_ndvi']}")
    fig.update_layout(title="Comparaison du NDVI", xaxis_title="Année", yaxis_title="NDVI", yaxis_range=[-0.2, 0.9], height=450)
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("📝 Interprétation")
    if res['surface_ha'] > 100:
        st.error(f"🚨 **Alerte !** {res['surface_ha']:,.0f} hectares déforestés.")
    elif res['surface_ha'] > 10:
        st.warning(f"⚠️ **Déforestation modérée.** {res['surface_ha']:,.0f} hectares perdus.")
    else:
        st.success(f"✅ **Peu ou pas de déforestation** détectée.")
    
    if variation_ndvi < -0.1:
        st.warning(f"📉 Forte baisse du NDVI ({variation_ndvi:.3f})")
    elif variation_ndvi < -0.05:
        st.info(f"📉 Baisse modérée du NDVI ({variation_ndvi:.3f})")
    else:
        st.success(f"📈 NDVI stable ou en hausse ({variation_ndvi:.3f})")
    
    st.subheader("⬇️ Export des résultats")
    df_export = pd.DataFrame({
        'Indicateur': ['Latitude', 'Longitude', 'Rayon (km)', 'Année référence', 'Année récente', 'Seuil NDVI', 'NDVI référence', 'NDVI récent', 'Surface déforestée (ha)', 'Taux déforestation (%)'],
        'Valeur': [res['lat'], res['lon'], res['rayon_km'], res['annee_ref'], res['annee_recente'], res['seuil_ndvi'], f"{res['ndvi_ref']:.3f}", f"{res['ndvi_recent']:.3f}", f"{res['surface_ha']:.0f}", f"{pourcentage:.1f}"]
    })
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Télécharger le rapport CSV", csv, f"deforestation_{res['annee_ref']}_{res['annee_recente']}.csv", "text/csv")

elif not st.session_state.analyse_effectuee:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info("👈 **Configurez les paramètres dans la barre latérale et cliquez sur ANALYSER**")
        st.subheader("🌍 Comment ça fonctionne ?")
        st.markdown("""
        **📌 Principe :** Comparaison du NDVI entre deux dates
        - NDVI > seuil = Forêt 🌲
        - NDVI < seuil = Sol nu/Urbain 🏙️
        - Déforestation = Forêt en année référence ET non-forêt en année récente
        """)
    with col2:
        st.subheader("🗺️ Aperçu")
        st_folium(creer_carte_folium(34.05, -6.85, 20), width=400, height=350)

# Pied de page
st.markdown("---")
st.markdown("""<div style="text-align: center; color: gray; font-size: 12px;">🌳 Projet réalisé par <strong>Mohamed Rida Zbakh</strong> - Master TSIG</div>""", unsafe_allow_html=True)
