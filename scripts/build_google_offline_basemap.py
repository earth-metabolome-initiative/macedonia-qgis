from __future__ import annotations

import argparse
import concurrent.futures
import math
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ZOOM = 18
TILE_SIZE = 256
BOUNDS = (20.777, 41.971, 20.902, 42.063)
SOURCE_URL = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
ATTRIBUTION = "Satellite imagery served by Google Maps"
OVERVIEW_LEVELS = (2, 4, 8, 16, 32, 64, 128, 256)
WEB_MERCATOR_HALF_WORLD = 20037508.342789244


def longitude_to_tile_x(longitude: float, zoom: int = ZOOM) -> float:
    return (longitude + 180.0) / 360.0 * 2**zoom


def latitude_to_tile_y(latitude: float, zoom: int = ZOOM) -> float:
    latitude_radians = math.radians(latitude)
    return (
        1.0 - math.asinh(math.tan(latitude_radians)) / math.pi
    ) / 2.0 * 2**zoom


def tile_range(
    bounds: tuple[float, float, float, float] = BOUNDS,
    zoom: int = ZOOM,
) -> tuple[int, int, int, int]:
    west, south, east, north = bounds
    return (
        math.floor(longitude_to_tile_x(west, zoom)),
        math.floor(longitude_to_tile_x(east, zoom)),
        math.floor(latitude_to_tile_y(north, zoom)),
        math.floor(latitude_to_tile_y(south, zoom)),
    )


def tile_count(bounds: tuple[float, float, float, float] = BOUNDS, zoom: int = ZOOM) -> int:
    x_min, x_max, y_min, y_max = tile_range(bounds, zoom)
    return (x_max - x_min + 1) * (y_max - y_min + 1)


def download_tile(x: int, y: int, destination: Path, zoom: int = ZOOM) -> None:
    request = urllib.request.Request(
        SOURCE_URL.format(x=x, y=y, z=zoom),
        headers={"User-Agent": "macedonia-qgis-offline-map/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if len(data) < 1_000:
                raise RuntimeError(f"Tile {zoom}/{x}/{y} returned only {len(data)} bytes")
            destination.write_bytes(data)
            return
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"Could not download tile {zoom}/{x}/{y}") from last_error


def write_vrt(
    tile_directory: Path,
    vrt_path: Path,
    bounds: tuple[float, float, float, float] = BOUNDS,
    zoom: int = ZOOM,
) -> None:
    x_min, x_max, y_min, y_max = tile_range(bounds, zoom)
    tile_columns = x_max - x_min + 1
    tile_rows = y_max - y_min + 1
    resolution = 2 * WEB_MERCATOR_HALF_WORLD / (TILE_SIZE * 2**zoom)
    origin_x = -WEB_MERCATOR_HALF_WORLD + x_min * TILE_SIZE * resolution
    origin_y = WEB_MERCATOR_HALF_WORLD - y_min * TILE_SIZE * resolution

    root = ET.Element(
        "VRTDataset",
        rasterXSize=str(tile_columns * TILE_SIZE),
        rasterYSize=str(tile_rows * TILE_SIZE),
    )
    ET.SubElement(root, "SRS").text = "EPSG:3857"
    ET.SubElement(root, "GeoTransform").text = (
        f"{origin_x:.12f}, {resolution:.12f}, 0, "
        f"{origin_y:.12f}, 0, {-resolution:.12f}"
    )
    for band_number in range(1, 4):
        band = ET.SubElement(
            root, "VRTRasterBand", dataType="Byte", band=str(band_number)
        )
        ET.SubElement(band, "ColorInterp").text = (
            "Red" if band_number == 1 else "Green" if band_number == 2 else "Blue"
        )
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                source = ET.SubElement(band, "SimpleSource")
                ET.SubElement(source, "SourceFilename", relativeToVRT="1").text = (
                    f"tiles/{x}_{y}.jpg"
                )
                ET.SubElement(source, "SourceBand").text = str(band_number)
                ET.SubElement(
                    source,
                    "SourceProperties",
                    RasterXSize=str(TILE_SIZE),
                    RasterYSize=str(TILE_SIZE),
                    DataType="Byte",
                    BlockXSize=str(TILE_SIZE),
                    BlockYSize=str(TILE_SIZE),
                )
                ET.SubElement(
                    source,
                    "SrcRect",
                    xOff="0",
                    yOff="0",
                    xSize=str(TILE_SIZE),
                    ySize=str(TILE_SIZE),
                )
                ET.SubElement(
                    source,
                    "DstRect",
                    xOff=str((x - x_min) * TILE_SIZE),
                    yOff=str((y - y_min) * TILE_SIZE),
                    xSize=str(TILE_SIZE),
                    ySize=str(TILE_SIZE),
                )
    ET.indent(root)
    ET.ElementTree(root).write(vrt_path, encoding="utf-8", xml_declaration=True)


def translate_command(vrt: Path, output: Path) -> list[str]:
    return [
        "gdal_translate",
        "-of",
        "GTiff",
        "-co",
        "TILED=YES",
        "-co",
        "COMPRESS=JPEG",
        "-co",
        "JPEG_QUALITY=88",
        "-co",
        "PHOTOMETRIC=YCBCR",
        "-co",
        "BIGTIFF=IF_SAFER",
        str(vrt),
        str(output),
    ]


def overview_command(output: Path) -> list[str]:
    return [
        "gdaladdo",
        "--config",
        "COMPRESS_OVERVIEW",
        "JPEG",
        "--config",
        "JPEG_QUALITY_OVERVIEW",
        "85",
        "-r",
        "average",
        str(output),
        *(str(level) for level in OVERVIEW_LEVELS),
    ]


def metadata_text(
    bounds: tuple[float, float, float, float] = BOUNDS,
    zoom: int = ZOOM,
) -> str:
    west, south, east, north = bounds
    x_min, x_max, y_min, y_max = tile_range(bounds, zoom)
    resolution = 2 * WEB_MERCATOR_HALF_WORLD / (TILE_SIZE * 2**zoom)
    return f"""# Macedonia offline satellite basemap provenance

Source: Google Maps satellite XYZ tiles
Tile endpoint: {SOURCE_URL}
Zoom: {zoom}
Nominal Web Mercator pixel size: {resolution:.3f} metres
Buffered requested bounds (west, south, east, north): {west}, {south}, {east}, {north}
Tile range (x_min, x_max, y_min, y_max): {x_min}, {x_max}, {y_min}, {y_max}
Tile count: {tile_count(bounds, zoom)}
Output CRS: EPSG:3857
Attribution: {ATTRIBUTION}
Build note: rebuilds require network access and the provider may change its tiles or endpoint.
Terms: https://www.google.com/help/terms_maps/
"""


def build(
    output: Path,
    *,
    bounds: tuple[float, float, float, float] = BOUNDS,
    zoom: int = ZOOM,
    force: bool = False,
    workers: int = 8,
) -> None:
    for executable in ("gdal_translate", "gdaladdo"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required executable is not available: {executable}")
    if output.exists() and not force:
        raise FileExistsError(f"Output already exists: {output}; pass --force to replace it")

    output.parent.mkdir(parents=True, exist_ok=True)
    x_min, x_max, y_min, y_max = tile_range(bounds, zoom)
    with tempfile.TemporaryDirectory(prefix="macedonia-google-tiles-") as temporary:
        temporary_path = Path(temporary)
        tile_directory = temporary_path / "tiles"
        tile_directory.mkdir()
        jobs = [
            (x, y, tile_directory / f"{x}_{y}.jpg")
            for y in range(y_min, y_max + 1)
            for x in range(x_min, x_max + 1)
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_tile, *job, zoom) for job in jobs]
            for completed, future in enumerate(
                concurrent.futures.as_completed(futures), start=1
            ):
                future.result()
                if completed % 100 == 0 or completed == len(futures):
                    print(f"Downloaded {completed}/{len(futures)} tiles", flush=True)

        vrt = temporary_path / "mosaic.vrt"
        write_vrt(tile_directory, vrt, bounds, zoom)
        temporary_output = output.with_name(f".{output.name}.building")
        subprocess.run(translate_command(vrt, temporary_output), check=True)
        subprocess.run(overview_command(temporary_output), check=True)
        temporary_output.replace(output)

    output.with_suffix(".metadata.txt").write_text(
        metadata_text(bounds, zoom), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the zoom-18 Google satellite offline map for Macedonia."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(args.output, force=args.force, workers=args.workers)


if __name__ == "__main__":
    main()
