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
import matplotlib
import streamlit as st
from matplotlib import pyplot as plt
from shapely import simplify as shp_simplify
from shapely.geometry import Point
from streamlit_folium import st_folium

matplotlib.use("Agg")

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

# --- Pareto frontier plot configuration (ported from scripts/pareto_frontier_plots.py) ---
# Pixel area in hectares (29x29m raster cells).
PIXEL_AREA_HA = 0.0841

# Ecosystem services and their per-scenario field mappings.
SERVICES = {
    "Baseflow (mm)": {
        "b": "B_b_mean", "a": "B_a_mean", "r": "B_r_mean", "ar": "B_ar_mean",
        "p10": "B_p10_mean", "p25": "B_p25_mean", "p50": "B_p50_mean",
    },
    "Surface Runoff (mm)": {
        "b": "Q_b_mean", "a": "Q_a_mean", "r": "Q_r_mean", "ar": "Q_ar_mean",
        "p10": "Q_p10_mean", "p25": "Q_p25_mean", "p50": "Q_p50_mean",
    },
    "Sediments (t/ha/yr)": {
        "b": "S_b_mean", "a": "S_a_mean", "r": "S_r_mean", "ar": "S_ar_mean",
        "p10": "S_p10_mean", "p25": "S_p25_mean", "p50": "S_p50_mean",
    },
    "Nitrogen (kg/ha/yr)": {
        "b": "N_b_mean", "a": "N_a_mean", "r": "N_r_mean", "ar": "N_ar_mean",
        "p10": "N_p10_mean", "p25": "N_p25_mean", "p50": "N_p50_mean",
    },
}

# Mask (pixel-count) fields per scenario; baseline has no intervention.
MASK_FIELDS = {
    "b": None, "a": "Mask_a_cou", "r": "Mask_r_cou", "ar": "Mask_ar_co",
    "p10": "Mask_p10_c", "p25": "Mask_p25_c", "p50": "Mask_p50_c",
}

SCENARIO_KEYS = ["b", "a", "r", "ar", "p10", "p25", "p50"]

SCENARIO_COLORS = {
    "b": "#666666", "a": "#2196F3", "r": "#4CAF50", "ar": "#9C27B0",
    "p10": "#FF9800", "p25": "#F44336", "p50": "#00BCD4",
}

SCENARIO_MARKERS = {
    "b": "o", "a": "s", "r": "^", "ar": "D",
    "p10": "o", "p25": "o", "p50": "o",
}

SCENARIO_LABELS = {
    "b": "Baseline", "a": "APP", "r": "Legal Reserve", "ar": "APP + RL",
    "p10": "Priority 10%", "p25": "Priority 25%", "p50": "Priority 50%",
}

# Named watersheds for plot titles (from scripts/pareto_frontier_plots.py).
# Unlisted ws_id_nest values fall back to "WS <id>".
WATERSHED_NAMES = {
    238: "WS 238", 233: "WS 233", 235: "WS 235", 165: "Rio Macacu",
    236: "WS 236", 148: "WS 148", 53: "Rio Muriaé",
}


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


def find_clicked_serviceshed(lat: float, lng: float):
    """Return the ws_id_nest of the serviceshed polygon containing (lat, lng), or None."""
    gdf = load_servicesheds()
    point = Point(lng, lat)
    matches = gdf[gdf.geometry.contains(point)]
    if matches.empty:
        return None
    return int(matches.iloc[0]["ws_id_nest"])


@st.cache_data(ttl=3600)
def compute_pareto_data(ws_id_nest: int):
    """Compute per-service (area, yield) points for the 7 scenarios of a serviceshed.

    Returns {service_name: {"x": [...], "y": [...], "scenarios": [...]}} or None.
    """
    gdf = load_servicesheds()
    row = gdf[gdf["ws_id_nest"] == ws_id_nest]
    if row.empty:
        return None
    r = row.iloc[0]
    result = {}
    for service_name, fields in SERVICES.items():
        xs, ys, scs = [], [], []
        for sc in SCENARIO_KEYS:
            mask_field = MASK_FIELDS[sc]
            x = 0.0 if sc == "b" else float(r[mask_field]) * PIXEL_AREA_HA
            y = float(r[fields[sc]])
            xs.append(x)
            ys.append(y)
            scs.append(sc)
        result[service_name] = {"x": xs, "y": ys, "scenarios": scs}
    return result


def render_pareto_figure(ws_id_nest: int, data: dict):
    """Build a 2x2 matplotlib figure with the 4 Pareto frontier scatter plots."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    axes = axes.flatten()

    # Indices of the two endpoints for the reference segment.
    baseline_i = SCENARIO_KEYS.index("b")
    app_rl_i = SCENARIO_KEYS.index("ar")

    for idx, (service_name, sd) in enumerate(data.items()):
        ax = axes[idx]
        xs, ys, scs = sd["x"], sd["y"], sd["scenarios"]

        # Simple red segment from baseline to APP+RL (not a fit).
        ax.plot(
            [xs[baseline_i], xs[app_rl_i]],
            [ys[baseline_i], ys[app_rl_i]],
            linestyle=":", color="red", alpha=0.6, linewidth=2.6, zorder=4,
        )

        for i, sc in enumerate(scs):
            ax.scatter(
                xs[i], ys[i],
                color=SCENARIO_COLORS[sc],
                marker=SCENARIO_MARKERS[sc],
                s=263, edgecolors="white", linewidth=2.6, zorder=5,
            )

        ax.set_title(service_name, fontsize=21, fontweight="bold")
        ax.set_xlabel("Intervened Area (ha)", fontsize=18)
        ax.set_ylabel(service_name, fontsize=18)
        ax.tick_params(axis="both", labelsize=14)
        ax.grid(True, alpha=0.3)

    ws_name = WATERSHED_NAMES.get(ws_id_nest, f"WS {ws_id_nest}")
    fig.suptitle(f"Pareto Frontier — {ws_name}",
                 fontsize=25, fontweight="bold", y=0.98)

    handles = [
        plt.Line2D([0], [0], marker=SCENARIO_MARKERS[sc], color="w",
                   markerfacecolor=SCENARIO_COLORS[sc], markersize=18,
                   markeredgecolor="white", markeredgewidth=2.6)
        for sc in SCENARIO_KEYS
    ]
    fig.legend(handles, [SCENARIO_LABELS[sc] for sc in SCENARIO_KEYS],
               loc="lower center", ncol=7, fontsize=16,
               bbox_to_anchor=(0.5, -0.02), frameon=True)

    plt.tight_layout(rect=[0, 0.06, 1, 0.94])
    return fig


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


def build_map(servicesheds_geojson, streams_geojson, selected_ws_id=None):
    """Build a folium map with basemaps, servicesheds, and stream network.

    When selected_ws_id is set, the map fits bounds to that feature and
    highlights it with a thick blue outline.
    """
    gdf = load_servicesheds()

    if selected_ws_id is not None:
        sel = gdf[gdf["ws_id_nest"] == selected_ws_id]
        bounds = sel.total_bounds if not sel.empty else gdf.total_bounds
    else:
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
        feat_ws = feature.get("properties", {}).get("ws_id_nest")
        is_selected = (
            selected_ws_id is not None
            and feat_ws is not None
            and int(feat_ws) == int(selected_ws_id)
        )
        return {
            "fillColor": serviceshed_fill_color(value),
            "color": "#0000ff" if is_selected else "#67000d",
            "weight": 3 if is_selected else 0.5,
            "fillOpacity": 0.85 if is_selected else 0.7,
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
    folium.LayerControl(collapsed=True).add_to(m)

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

    # Session state: selected watershed + map-remount token.
    if "selected_ws_id" not in st.session_state:
        st.session_state.selected_ws_id = None
    if "map_view_token" not in st.session_state:
        st.session_state.map_view_token = 0

    _, btn_col, _ = st.columns([1, 1, 1])
    with btn_col:
        if st.button("Restaurar zoom", use_container_width=True):
            st.session_state.selected_ws_id = None
            st.session_state.map_view_token += 1
            st.rerun()

    # --- Instruction line above the map (only when nothing is selected) ---
    if st.session_state.selected_ws_id is None:
        st.info(
            "Clique em uma bacia abastecedora no mapa para visualizar "
            "os gráficos de fronteira de Pareto."
        )

    with st.spinner("Carregando mapa..."):
        m = build_map(
            servicesheds_geojson,
            streams_geojson,
            selected_ws_id=st.session_state.selected_ws_id,
        )

    map_output = st_folium(
        m,
        width="100%",
        height=450,
        returned_objects=["last_clicked"],
        key=f"map_{st.session_state.map_view_token}",
    )

    # --- Process map clicks: select the clicked serviceshed ---
    if map_output and map_output.get("last_clicked"):
        click = map_output["last_clicked"]
        clicked_ws = find_clicked_serviceshed(click["lat"], click["lng"])
        if clicked_ws is not None and clicked_ws != st.session_state.selected_ws_id:
            st.session_state.selected_ws_id = clicked_ws
            st.rerun()

    # --- Pareto frontier plots below the map ---
    st.markdown("---")
    selected_ws_id = st.session_state.selected_ws_id
    if selected_ws_id is not None:
        ws_name = WATERSHED_NAMES.get(selected_ws_id, f"WS {selected_ws_id}")
        st.markdown(
            f"<h3 style='text-align:center; margin-bottom:0.4rem;'>"
            f"Fronteira de Pareto — {ws_name}"
            f"</h3>",
            unsafe_allow_html=True,
        )
        pareto_data = compute_pareto_data(selected_ws_id)
        if pareto_data is None:
            st.warning(f"Sem dados de cenário para a bacia {selected_ws_id}.")
        else:
            fig = render_pareto_figure(selected_ws_id, pareto_data)
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)


if __name__ == "__main__":
    main()
