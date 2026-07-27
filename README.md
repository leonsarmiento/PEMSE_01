# PEMSE — Web Map Dashboard

Interactive web map dashboard for identifying critical areas for ecosystem
service provision in the water-supply watersheds of the state of Rio de
Janeiro, Brazil. Built with Streamlit + Folium.

## What it does

- Banner with project logos, Portuguese title, authors and affiliations.
- Folium map rendering the **Bacias Abastecedoras** (servicesheds) as a
  choropleth on `% passivas APP & RL` (5-stop Reds ramp, bins 0-20-40-60-80),
  overlaid with the stream network (`Rede de Drenagem`).
- Basemap switcher (OpenStreetMap / Esri satellite) and layer toggle.
- Hover tooltip on each serviceshed showing `Porcentagem passivo APP & RL`.
- **Restaurar zoom** button to snap the view back to the initial extent.
- Click a serviceshed to:
  - Fit the map to that feature and outline it in blue.
  - Render a 2x2 Pareto frontier figure below the map (Baseflow, Surface
    Runoff, Sediments, Nitrogen), with one point per restoration scenario
    (Baseline, APP, RL, APP+RL, Priority 10/25/50%) and a reference segment
    from Baseline to APP+RL.

## Data

All geospatial inputs live under `GIS_data/` and are self-contained — the
dashboard reads only from that folder (no external shapefile dependency).

- `GIS_data/Servicesheds.shp` — servicesheds (EPSG:32723), attributes drive
  both the choropleth (`prc_passiv`) and the Pareto plots (`B_*`, `Q_*`,
  `S_*`, `N_*`, `Mask_*` fields).
- `GIS_data/streams.shp` — drainage network (EPSG:32723).
- `Banner/Logos.png` — top banner image.

Both vector layers are reprojected to EPSG:4326 and simplified
(Douglas-Peucker, tolerance 0.001 deg ~ 100 m) before serialization to
GeoJSON, to keep the payload small enough for the Folium component.

## Requirements

```
streamlit>=1.30
folium>=0.15
streamlit-folium>=0.18
geopandas>=0.14
matplotlib>=3.5
shapely>=2.0
```

Python 3.10+ is required (Streamlit 1.48+ uses `@dataclass` on
`typing.Protocol`, which fails silently on Python 3.9).

## Run

```bash
conda activate <env with the packages above>
streamlit run app.py
```

The app is served at http://localhost:8501.

## Project layout

```
web_app/
├── app.py                # dashboard entry point
├── requirements.txt
├── Banner/
│   └── Logos.png
└── GIS_data/
    ├── Servicesheds.*    # servicesheds + scenario attributes
    └── streams.*         # drainage network
```
