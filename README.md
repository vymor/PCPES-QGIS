# Potential Coastal Protection Ecosystem Service of Seagrasses (PCPES)

This QGIS processing plugin evaluates the coastal protective capacity of seagrass meadows, providing indicative levels of their coastal protection ecosystem service. More details and scientific backround of this tool can be found in Moraitis et al. (2026) (a link will be available after acceptance).

## Key Spatial Data Prerequisites
To maintain calculation validity and avoid silent indexing errors, please ensure **All metric calculation layers** (Coastline, Land, Seagrass polygons) are projected in the **exact same metric Coordinate Reference System (CRS)** appropriate for your local study area. The **REI Point Layer** can alternatively be delivered in standard global geographic coordinates (**WGS 84 / EPSG:4326**), as the tool will automatically handle the cross-datum translation grid transformations in memory.

## Local Installation Layout
To manually test this tool on your machine:
1. Download this repository as a `.zip` archive.
2. Extract the folder into your local QGIS 3 profile Python plugins directory:
   `C:\Users\<YOUR_NAME>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
3. Restart QGIS, navigate to the **Plugin Manager**, and enable the extension.
