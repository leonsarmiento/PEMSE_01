from pathlib import Path

import folium
import geopandas as gpd
import streamlit as st
from streamlit_folium import st_folium

APP_DIR = Path(__file__).parent
BANNER_PATH = APP_DIR / "Banner" / "Logos.png"
SERVICESHEDS_PATH = APP_DIR / "GIS_data" / "Servicesheds.shp"
STREAMS_PATH = APP_DIR / "GIS_data" / "streams.shp"

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


@st.cache_data
def load_layer(path: str, layer_name: str) -> gpd.GeoDataFrame:
    """Load a shapefile and reproject to WGS84 for display in folium."""
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs("EPSG:32723", inplace=True)
    gdf = gdf.to_crs("EPSG:4326")
    gdf.attrs["layer_name"] = layer_name
    return gdf


def style_serviceshed(_feature) -> dict:
    return {
        "fillColor": "#2ca25f",
        "color": "#006d2c",
        "weight": 1,
        "fillOpacity": 0.5,
    }


def style_stream(_feature) -> dict:
    return {
        "color": "#1f78b4",
        "weight": 1.2,
        "opacity": 0.9,
    }


def build_map(servicesheds: gpd.GeoDataFrame, streams: gpd.GeoDataFrame) -> folium.Map:
    bounds = servicesheds.total_bounds  # [minx, miny, maxx, maxy]
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")
    folium.LayerControl(collapsed=False).add_to(m)

    folium.GeoJson(
        data=servicesheds.to_json(),
        name="Servicesheds",
        style_function=style_serviceshed,
        tooltip=folium.GeoJsonTooltip(
            fields=["Km2", "prc_passiv"],
            aliases=["&Aacute;rea (km&sup2;):", "% passivas:"],
            localize=True,
        ),
        highlight_function=lambda _f: {
            "weight": 2,
            "color": "#000000",
            "fillOpacity": 0.7,
        },
    ).add_to(m)

    folium.GeoJson(
        data=streams.to_json(),
        name="Streams",
        style_function=style_stream,
        tooltip=folium.GeoJsonTooltip(fields=["grid_code"], aliases=["Ordem:"]),
    ).add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    return m


def render_header() -> None:
    if BANNER_PATH.exists():
        st.image(str(BANNER_PATH), use_container_width=True)

    st.markdown(
        f"<div style='text-align:center; margin-top:0.5rem;'>"
        f"<h1 style='font-size:1.4rem; line-height:1.3; margin-bottom:0.25rem;'>{TITLE}</h1>"
        f"<p style='font-size:1.05rem; margin:0.1rem 0;'>{AUTHORS}</p>"
        f"<p style='font-size:0.8rem; color:#555; margin-top:0.3rem;'>{AFFILIATIONS}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")


def main() -> None:
    st.set_page_config(page_title="PEMSE - Web Map Dashboard", layout="wide")

    render_header()

    servicesheds = load_layer(str(SERVICESHEDS_PATH), "servicesheds")
    streams = load_layer(str(STREAMS_PATH), "streams")

    st.subheader("Mapa de Servicsheds e Rede de Drenagem")
    m = build_map(servicesheds, streams)
    st_folium(m, width=None, height=650, returned_objects=[])


if __name__ == "__main__":
    main()
