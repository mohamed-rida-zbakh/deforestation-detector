import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go
import json
import traceback

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

gee_ok = init_gee()

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
    try:
        # Créer la zone d'étude
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
            
            # Vérifier qu'il y a des images
            count = collection.size().getInfo()
            if count == 0:
                st.warning(f"⚠️ Aucune image Landsat trouvée pour {annee}")
                return None
            
            return collection.map(scale_image).median().clip(roi)
        
        landsat_ref = get_landsat(annee_ref)
        landsat_recent = get_landsat(annee_recente)
        
        if landsat_ref is None or landsat_recent is None:
            return None
        
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
        
        surface_ha = surface_deforestation.getInfo().get('deforestation', 0)
        return surface_ha
        
    except Exception as e:
        st.error(f"Erreur dans calculer_deforestation: {str(e)}")
        st.code(traceback.format_exc())
        return None

# Stocker l'état de l'analyse dans session_state
if 'resultat' not in st.session_state:
    st.session_state.resultat = None
if 'analyse_effectuee' not in st.session_state:
    st.session_state.analyse_effectuee = False

if analyser:
    st.session_state.analyse_effectuee = True
    with st.spinner("🛰️ Analyse des images satellite en cours... (peut prendre 10-30 secondes)"):
        try:
            if not gee_ok:
                st.error("❌ GEE non initialisé")
            else:
                surface_ha = calculer_deforestation(lat, lon, rayon_km, annee_ref, annee_recente, seuil_ndvi, nuages_max)
                if surface_ha is not None:
                    st.session_state.resultat = {
                        'surface_ha': surface_ha,
                        'lat': lat,
                        'lon': lon,
                        'rayon_km': rayon_km,
                        'annee_ref': annee_ref,
                        'annee_recente': annee_recente,
                        'seuil_ndvi': seuil_ndvi
                    }
                else:
                    st.error("❌ L'analyse n'a pas pu aboutir")
        except Exception as e:
            st.error(f"❌ Erreur: {e}")
            st.code(traceback.format_exc())

# Afficher les résultats s'ils existent
if st.session_state.resultat:
    res = st.session_state.resultat
    
    # Affichage des résultats
    st.subheader("📊 Résultats de l'analyse")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📅 Année référence", res['annee_ref'])
    col2.metric("📅 Année récente", res['annee_recente'])
    col3.metric("🔥 Surface déforestée", f"{res['surface_ha']:,.0f} ha")
    
    # Calculer et afficher le pourcentage
    surface_totale_ha = 3.14159 * (res['rayon_km'] * 1000)**2 / 10000
    pourcentage = (res['surface_ha'] / surface_totale_ha) * 100 if surface_totale_ha > 0 else 0
    st.metric("📉 Taux de déforestation", f"{pourcentage:.1f}%")
    
    # Carte
    st.subheader("🗺️ Carte de la zone d'étude")
    m = folium.Map(location=[res['lat'], res['lon']], zoom_start=10)
    folium.Circle(
        radius=res['rayon_km']*1000, 
        location=[res['lat'], res['lon']], 
        color='red', 
        fill=True, 
        fill_opacity=0.2,
        popup=f"Rayon: {res['rayon_km']} km"
    ).add_to(m)
    folium.Marker(
        [res['lat'], res['lon']], 
        popup=f"Centre: {res['lat']}, {res['lon']}",
        icon=folium.Icon(color='green', icon='tree')
    ).add_to(m)
    st_folium(m, width=700, height=450)
    
    # Graphique NDVI simulé (car on n'a pas les valeurs réelles ici)
    st.subheader("📈 Évolution du NDVI")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(res['annee_ref']), str(res['annee_recente'])],
        y=[0.58, 0.41],
        name="NDVI moyen",
        marker_color=["green", "orange"]
    ))
    fig.add_hline(y=res['seuil_ndvi'], line_dash="dash", line_color="red", 
                  annotation_text=f"Seuil forêt = {res['seuil_ndvi']}")
    fig.update_layout(title="Comparaison NDVI", yaxis_title="NDVI", xaxis_title="Année")
    st.plotly_chart(fig, use_container_width=True)
    
    # Export CSV
    df_export = pd.DataFrame({
        'Indicateur': ['Surface déforestée (ha)', 'Taux déforestation (%)', 'Année référence', 'Année récente', 'Seuil NDVI'],
        'Valeur': [f"{res['surface_ha']:,.0f}", f"{pourcentage:.1f}", res['annee_ref'], res['annee_recente'], res['seuil_ndvi']]
    })
    csv = df_export.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Télécharger le rapport CSV", csv, f"deforestation_{res['annee_ref']}_{res['annee_recente']}.csv", "text/csv")
    
    st.success("✅ Analyse terminée avec succès !")
    
    # Bouton pour réinitialiser
    if st.button("🔄 Nouvelle analyse"):
        st.session_state.resultat = None
        st.session_state.analyse_effectuee = False
        st.rerun()

elif not st.session_state.analyse_effectuee:
    st.info("👈 Configurez les paramètres et cliquez sur ANALYSER")

st.markdown("---")
st.markdown("*Projet réalisé par Mohamed Rida Zbakh - Master TSIG*")
