"""
PEMSE — Web Map Dashboard
Identificacao de areas criticas para provisao de servicos ecossistemicos
nas bacias de abastecimento do Estado do Rio de Janeiro, Brasil.

Deploy: streamlit run app.py
"""

import base64
from pathlib import Path

import folium
import geopandas as gpd
import streamlit as st
from shapely import simplify as shp_simplify
from streamlit_folium import st_folium

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
BANNER_PATH = BASE_DIR / "Banner" / "Logos.png"
SERVICESHEDS_PATH = BASE_DIR / "GIS_data" / "Servicesheds.shp"
STREAMS_PATH = BASE_DIR / "GIS_data" / "streams.shp"

TITLE = (
    "Uso da Abordagem de Capital Natural para identifica&ccedil;&atilde;o de "
    "&aacute;reas cr&iacute;ticas para provis&atilde;o de servi&ccedil;os "
    "ecossist&ecirc;micos nas bacias de abastecimento do Estado do Rio de "
    "Janeiro, Brasil"
)

AUTHORS = "Jorge Leon Sarmiento<sup>(1)</sup>, Claudia Moster<sup>(2)</sup>"

AFFILIATIONS = (
    "<sup>(1)</sup> Natural Capital Insights / UFRRJ / Laborat&oacute;rio de "
    "Modelagem de Bacias Hidrogr&aacute;ficas (LMBH) Grupo de Pesquisa PEMSE, "
    "Serop&eacute;dica-RJ, Brasil;<br>"
    "<sup>(2)</sup> UFRRJ / Laborat&oacute;rio de Modelagem de Bacias "
    "Hidrogr&aacute;ficas (LMBH) / Comite de Bacia GUANDU, Serop&eacute;dica-RJ, "
    "Brasil."
)

# Geometry simplification tolerance (in WGS84 degrees).
# 0.001 ≈ 100m. Reduces GeoJSON payload while preserving recognizable shapes.
SIMPLIFICATION_TOLERANCE = 0.001

# Choropleth graduation on servicesheds, based on prc_passiv (% passivas).
# 5 stops sampled from the ColorBrewer "Reds" scheme (#fff5f0 -> #67000d).
SERVICESHED_BREAKS = [0, 20, 40, 60, 80, float("inf")]
SERVICESHED_COLORS = ["#fff5f0", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"]
SERVICESHED_NODATA_COLOR = "#cccccc"
SERVICESHED_FIELD = "prc_passiv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_json_serializable(value):
    """Recursively convert pandas/numpy types to native Python types."""
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_make_json_serializable(v) for v in value]
    if isinstance(value, dict):
        return {k: _make_json_serializable(v) for k, v in value.items()}
    return value


def gdf_to_geojson_serializable(gdf: gpd.GeoDataFrame) -> dict:
    """Convert a GeoDataFrame to a JSON-serializable GeoJSON dict.

    Handles pandas Timestamps, numpy ints/floats, etc.
    """
    geometries = [g.__geo_interface__ for g in gdf.geometry]
    props_list = gdf.drop(columns=["geometry"]).to_dict("records")
    props_list = [_make_json_serializable(p) for p in props_list]
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": geom, "properties": props}
            for geom, props in zip(geometries, props_list)
        ],
    }


def simplify_gdf(gdf: gpd.GeoDataFrame, tolerance: float) -> gpd.GeoDataFrame:
    """Simplify geometries using Douglas-Peucker.

    Args:
        gdf: Input GeoDataFrame (not modified in-place).
        tolerance: Tolerance in CRS units (degrees for WGS84).
    """
    gdf_simplified = gdf.copy()
    gdf_simplified["geometry"] = gdf_simplified.geometry.apply(
        lambda geom: shp_simplify(geom, tolerance=tolerance)
    )
    gdf_simplified = gdf_simplified[~gdf_simplified.geometry.is_empty]
    return gdf_simplified


def serviceshed_fill_color(value) -> str:
    """Map a prc_passiv value to one of 5 choropleth colors by bin.

    Bins: [0,20), [20,40), [40,60), [60,80), [80, inf). Values that are
    missing, NaN, or negative fall back to the no-data color.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return SERVICESHED_NODATA_COLOR
    if v != v or v < 0:  # NaN or negative
        return SERVICESHED_NODATA_COLOR
    for i in range(len(SERVICESHED_BREAKS) - 1):
        if SERVICESHED_BREAKS[i] <= v < SERVICESHED_BREAKS[i + 1]:
            return SERVICESHED_COLORS[i]
    return SERVICESHED_COLORS[-1]


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------


@st.cache_data(ttl=86400)
def get_banner_data_uri() -> str:
    """Read the banner PNG once and embed as base64 data URI."""
    with open(BANNER_PATH, "rb") as f:
        data = f.read()
    return f"data:image/png;base64,{base64.b64encode(data).decode('utf-8')}"


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def load_servicesheds():
    """Load servicesheds, reproject to WGS84, simplify."""
    gdf = gpd.read_file(str(SERVICESHEDS_PATH))
    if gdf.crs is not None and str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf = simplify_gdf(gdf, tolerance=SIMPLIFICATION_TOLERANCE)
    # Pre-formatted label for the hover tooltip (folium has no suffix option).
    gdf["prc_passiv_label"] = gdf["prc_passiv"].map(
        lambda v: f"{v:.2f}%" if v is not None and v == v else "N/A"
    )
    return gdf


@st.cache_data(ttl=3600)
def load_streams():
    """Load streams, reproject to WGS84, simplify."""
    gdf = gpd.read_file(str(STREAMS_PATH))
    if gdf.crs is not None and str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf = simplify_gdf(gdf, tolerance=SIMPLIFICATION_TOLERANCE)
    return gdf


@st.cache_data(ttl=3600)
def get_servicesheds_geojson():
    """Pre-serialized serviceshed GeoJSON (cached)."""
    return gdf_to_geojson_serializable(load_servicesheds())


@st.cache_data(ttl=3600)
def get_streams_geojson():
    """Pre-serialized streams GeoJSON (cached)."""
    return gdf_to_geojson_serializable(load_streams())


# ---------------------------------------------------------------------------
# Map building
# ---------------------------------------------------------------------------


def build_map(servicesheds_geojson, streams_geojson):
    """Build a folium map with basemaps, servicesheds, and stream network."""
    gdf = load_servicesheds()
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy] in lon/lat
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    m = folium.Map(location=center, zoom_start=9, tiles=None)

    # --- Basemap layers ---
    folium.TileLayer(
        tiles="OpenStreetMap",
        attr="OpenStreetMap",
        name="OpenStreetMap",
        overlay=False,
        control=True,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satelite (Esri)",
        overlay=False,
        control=True,
    ).add_to(m)

    # --- Servicesheds: choropleth on prc_passiv (% passivas) ---
    def style_serviceshed(feature):
        value = feature.get("properties", {}).get(SERVICESHED_FIELD)
        return {
            "fillColor": serviceshed_fill_color(value),
            "color": "#67000d",
            "weight": 0.5,
            "fillOpacity": 0.7,
        }

    folium.GeoJson(
        servicesheds_geojson,
        name="Bacias Abastecedoras",
        style_function=style_serviceshed,
        tooltip=folium.GeoJsonTooltip(
            fields=["prc_passiv_label"],
            aliases=["Percentagem passivo APP &amp; RL:"],
            labels=True,
        ),
        highlight_function=lambda feature: {
            "weight": 2,
            "color": "#000000",
            "fillOpacity": 0.85,
        },
    ).add_to(m)

    # --- Stream network (overlay) ---
    folium.GeoJson(
        streams_geojson,
        name="Rede de Drenagem",
        style_function=lambda feature: {
            "color": "#1f78b4",
            "weight": 1.2,
            "opacity": 0.9,
        },
    ).add_to(m)

    # --- Layer control ---
    folium.LayerControl(collapsed=False).add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return m


# ---------------------------------------------------------------------------
# Streamlit app
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(
        page_title="PEMSE - Web Map Dashboard",
        layout="wide",
    )

    # --- Banner ---
    banner_uri = get_banner_data_uri()
    st.markdown(
        f'<img src="{banner_uri}" '
        f'style="width:100%; max-height:120px; object-fit:cover; display:block;">',
        unsafe_allow_html=True,
    )

    # --- Title ---
    st.markdown(
        f"<h1 style='text-align:center; margin-top:0.4rem; margin-bottom:0.2em; "
        f"font-size:1.4rem; line-height:1.3;'>{TITLE}</h1>",
        unsafe_allow_html=True,
    )

    # --- Authors ---
    st.markdown(
        f"<p style='text-align:center; font-size:1.05rem; margin:0.1rem 0;'>"
        f"{AUTHORS}</p>",
        unsafe_allow_html=True,
    )

    # --- Affiliations ---
    st.markdown(
        f"<p style='text-align:center; font-size:0.8rem; color:#555; "
        f"margin-top:0.3rem;'>{AFFILIATIONS}</p>",
        unsafe_allow_html=True,
    )

    # --- Map ---
    servicesheds_geojson = get_servicesheds_geojson()
    streams_geojson = get_streams_geojson()

    # Session token bumped by the "Restaurar zoom" button. Changing the
    # st_folium key forces the component to remount and re-apply the map's
    # fit_bounds, snapping the view back to the initial extent.
    if "map_view_token" not in st.session_state:
        st.session_state.map_view_token = 0

    _, btn_col, _ = st.columns([1, 1, 1])
    with btn_col:
        if st.button("Restaurar zoom", use_container_width=True):
            st.session_state.map_view_token += 1
            st.rerun()

    with st.spinner("Carregando mapa..."):
        m = build_map(servicesheds_geojson, streams_geojson)

    st_folium(
        m,
        width="100%",
        height=600,
        returned_objects=[],
        key=f"map_{st.session_state.map_view_token}",
    )


if __name__ == "__main__":
    main()
