import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go
import json
import traceback

# Configuration de la page
st.set_page_config(page_title="Deforestation Detector", page_icon="🌳", layout="wide")

st.title("🌳 Détection de Déforestation par Satellite")
st.markdown("*Comparaison d'images Landsat pour quantifier la perte de couvert forestier*")

# ============================================
# INITIALISATION DE GOOGLE EARTH ENGINE
# ============================================
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
            st.info("🔧 Mode développement - GEE configuré localement")
        return True
    except Exception as e:
        st.error(f"❌ Erreur GEE : {e}")
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
    nuages_max = st.slider("Nuages max (%)", 10, 50, 20)
    
    analyser = st.button("🔍 ANALYSER", type="primary", use_container_width=True)

# ============================================
# FONCTION DE CALCUL (CORRIGÉE)
# ============================================
def calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max):
    """Calcule la déforestation réelle avec GEE - Version corrigée"""
    
    # Créer la zone d'étude (cercle de rayon donné)
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
            optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
            return img.addBands(optical, None, True)
        
        return collection.map(scale_image).median().clip(roi)
    
    def calculate_ndvi(img):
        """Calcule l'indice NDVI"""
        nir = img.select('SR_B5')
        red = img.select('SR_B4')
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        return ndvi
    
    # Charger les images
    landsat_ref = get_landsat(annee_ref)
    landsat_recent = get_landsat(annee_recente)
    
    # Calculer NDVI
    ndvi_ref = calculate_ndvi(landsat_ref)
    ndvi_recent = calculate_ndvi(landsat_recent)
    
    # Détection forêt (NDVI > seuil)
    foret_ref = ndvi_ref.gt(seuil_ndvi)
    foret_recent = ndvi_recent.gt(seuil_ndvi)
    
    # Déforestation = était forêt en référence ET n'est plus forêt en récent
    deforestation = foret_ref.And(foret_recent.Not()).rename('deforestation')
    
    # Reforestation = n'était pas forêt en référence ET est devenu forêt en récent
    reforestation = foret_ref.Not().And(foret_recent).rename('reforestation')
    
    # Surface par pixel (Landsat: 30m x 30m = 900 m² = 0.09 ha)
    pixel_area_ha = (30 * 30) / 10000  # 0.09 ha/pixel
    
    # Calculer surface déforestée
    surface_deforestation = deforestation.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale: 30,
        bestEffort: True,
        maxPixels: 1e9
    )
    
    # Calculer surface reforestée
    surface_reforestation = reforestation.multiply(pixel_area_ha).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi,
        scale: 30,
        bestEffort: True,
        maxPixels: 1e9
    )
    
    # Calculer NDVI moyen
    ndvi_ref_moyen = ndvi_ref.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale: 30,
        bestEffort: True
    )
    
    ndvi_recent_moyen = ndvi_recent.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale: 30,
        bestEffort: True
    )
    
    try:
        # Récupérer les valeurs
        surface_def = surface_deforestation.getInfo().get('deforestation', 0)
        surface_ref = surface_reforestation.getInfo().get('reforestation', 0)
        ndvi_ref_val = ndvi_ref_moyen.getInfo().get('NDVI', 0)
        ndvi_recent_val = ndvi_recent_moyen.getInfo().get('NDVI', 0)
        
        return {
            'deforestation_ha': surface_def,
            'reforestation_ha': surface_ref,
            'ndvi_ref': ndvi_ref_val,
            'ndvi_recent': ndvi_recent_val,
            'roi': roi
        }
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données: {e}")
        return None

# ============================================
# AFFICHAGE DES RÉSULTATS
# ============================================

# Stocker les résultats dans session_state pour qu'ils persistent
if 'resultats' not in st.session_state:
    st.session_state.resultats = None

if analyser:
    if not gee_ok:
        st.error("❌ Google Earth Engine n'est pas configuré correctement.")
    else:
        with st.spinner("🛰️ Analyse des images satellite en cours... (20-40 secondes)"):
            try:
                resultats = calculer_deforestation(
                    lat, lon, rayon_km,
                    annee_ref, annee_recente,
                    seuil_ndvi, nuages_max
                )
                
                if resultats:
                    st.session_state.resultats = {
                        'deforestation_ha': resultats['deforestation_ha'],
                        'reforestation_ha': resultats['reforestation_ha'],
                        'ndvi_ref': resultats['ndvi_ref'],
                        'ndvi_recent': resultats['ndvi_recent'],
                        'lat': lat,
                        'lon': lon,
                        'rayon_km': rayon_km,
                        'annee_ref': annee_ref,
                        'annee_recente': annee_recente,
                        'seuil_ndvi': seuil_ndvi,
                        'nuages_max': nuages_max
                    }
                    st.success("✅ Analyse terminée avec succès !")
                else:
                    st.error("❌ L'analyse n'a pas pu aboutir. Vérifiez les paramètres.")
                    
            except Exception as e:
                st.error(f"❌ Erreur inattendue: {e}")
                st.code(traceback.format_exc())

# Afficher les résultats s'ils existent
if st.session_state.resultats:
    res = st.session_state.resultats
    
    # Métriques principales
    st.subheader("📊 Résultats de l'analyse")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Année référence", res['annee_ref'])
    col2.metric("📅 Année récente", res['annee_recente'])
    col3.metric("🌿 NDVI référence", f"{res['ndvi_ref']:.3f}")
    col4.metric("🌿 NDVI récent", f"{res['ndvi_recent']:.3f}", 
                delta=f"{res['ndvi_recent'] - res['ndvi_ref']:.3f}")
    
    col5, col6, col7 = st.columns(3)
    col5.metric("🔥 Déforestation", f"{res['deforestation_ha']:,.0f} ha")
    col6.metric("🌱 Reforestation", f"{res['reforestation_ha']:,.0f} ha")
    
    # Calcul du bilan net
    bilan_net = res['deforestation_ha'] - res['reforestation_ha']
    col7.metric("📉 Bilan net", f"{bilan_net:,.0f} ha", 
                delta="Perte nette" if bilan_net > 0 else "Gain net")
    
    # Calcul du pourcentage par rapport à la zone totale
    surface_totale_ha = 3.14159 * (res['rayon_km'] * 1000)**2 / 10000
    pourcentage_def = (res['deforestation_ha'] / surface_totale_ha) * 100 if surface_totale_ha > 0 else 0
    
    st.metric("📐 Taux de déforestation", f"{pourcentage_def:.1f}% de la zone")
    
    # Carte interactive
    st.subheader("🗺️ Carte de la zone d'étude")
    m = folium.Map(location=[res['lat'], res['lon']], zoom_start=10, control_scale=True)
    
    # Cercle zone d'étude
    folium.Circle(
        radius=res['rayon_km'] * 1000,
        location=[res['lat'], res['lon']],
        color='red',
        weight=2,
        fill=True,
        fill_opacity=0.1,
        popup=f"Zone d'étude: {res['rayon_km']} km"
    ).add_to(m)
    
    # Marqueur central
    folium.Marker(
        [res['lat'], res['lon']],
        popup=f"Centre: {res['lat']}, {res['lon']}",
        icon=folium.Icon(color='green', icon='tree', prefix='fa')
    ).add_to(m)
    
    st_folium(m, width=800, height=500)
    
    # Graphique NDVI
    st.subheader("📈 Évolution du NDVI")
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=[str(res['annee_ref']), str(res['annee_recente'])],
        y=[res['ndvi_ref'], res['ndvi_recent']],
        name="NDVI moyen",
        marker_color=["#228B22", "#FF8C00"],
        text=[f"{res['ndvi_ref']:.3f}", f"{res['ndvi_recent']:.3f}"],
        textposition="auto"
    ))
    
    # Ligne de seuil forêt
    fig.add_hline(
        y=res['seuil_ndvi'],
        line_dash="dash",
        line_color="red",
        annotation_text=f"Seuil forêt = {res['seuil_ndvi']}",
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
    
    # Interprétation
    st.subheader("📝 Interprétation")
    
    variation_ndvi = res['ndvi_recent'] - res['ndvi_ref']
    
    if variation_ndvi < -0.1:
        st.warning(f"📉 Forte baisse du NDVI ({variation_ndvi:.3f}) → perte significative de végétation.")
    elif variation_ndvi < -0.05:
        st.info(f"📉 Baisse modérée du NDVI ({variation_ndvi:.3f}) → perte de végétation observable.")
    else:
        st.success(f"📈 NDVI stable ou en hausse ({variation_ndvi:.3f}) → la végétation est préservée.")
    
    if res['deforestation_ha'] > 100:
        st.error(f"🚨 **Alerte déforestation !** {res['deforestation_ha']:,.0f} hectares ont été perdus.")
    elif res['deforestation_ha'] > 10:
        st.warning(f"⚠️ **Déforestation modérée.** {res['deforestation_ha']:,.0f} hectares perdus.")
    else:
        st.success(f"✅ **Peu ou pas de déforestation** détectée.")
    
    # Export CSV
    st.subheader("⬇️ Export des résultats")
    
    df_export = pd.DataFrame({
        'Indicateur': [
            'Latitude', 'Longitude', 'Rayon (km)',
            'Année référence', 'Année récente',
            'Seuil NDVI', 'Nuages max (%)',
            'NDVI référence', 'NDVI récent', 'Variation NDVI',
            'Déforestation (ha)', 'Reforestation (ha)', 'Bilan net (ha)',
            'Surface zone (ha)', 'Taux déforestation (%)'
        ],
        'Valeur': [
            res['lat'], res['lon'], res['rayon_km'],
            res['annee_ref'], res['annee_recente'],
            res['seuil_ndvi'], res['nuages_max'],
            f"{res['ndvi_ref']:.3f}", f"{res['ndvi_recent']:.3f}", f"{variation_ndvi:.3f}",
            f"{res['deforestation_ha']:.0f}", f"{res['reforestation_ha']:.0f}", f"{bilan_net:.0f}",
            f"{surface_totale_ha:.0f}", f"{pourcentage_def:.1f}"
        ]
    })
    
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Télécharger le rapport CSV",
        data=csv,
        file_name=f"deforestation_{res['annee_ref']}_{res['annee_recente']}.csv",
        mime="text/csv",
        use_container_width=True
    )
    
    # Bouton pour nouvelle analyse
    if st.button("🔄 Nouvelle analyse", use_container_width=True):
        st.session_state.resultats = None
        st.rerun()

elif not analyser:
    st.info("👈 Configurez les paramètres dans la barre latérale et cliquez sur ANALYSER")

# Pied de page
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: gray; font-size: 12px;">
    🌳 Projet réalisé par <strong>Mohamed Rida Zbakh</strong> - Master TSIG<br>
    Données : Landsat 8/9 (NASA/USGS) | Plateforme : Google Earth Engine & Streamlit Cloud
    </div>
    """,
    unsafe_allow_html=True
)
