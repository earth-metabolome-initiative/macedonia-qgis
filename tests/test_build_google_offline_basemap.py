from pathlib import Path

import pytest

from scripts import build_google_offline_basemap as basemap


def test_zoom_18_tile_range_covers_buffered_aoi() -> None:
    x_min, x_max, y_min, y_max = basemap.tile_range()

    assert (x_min, x_max, y_min, y_max) == (146201, 146292, 97250, 97340)
    assert basemap.tile_count() == 8_372
    assert basemap.ZOOM == 18


def test_vrt_has_web_mercator_geometry_and_all_rgb_sources(tmp_path: Path) -> None:
    tile_directory = tmp_path / "tiles"
    tile_directory.mkdir()
    vrt = tmp_path / "mosaic.vrt"

    basemap.write_vrt(tile_directory, vrt)
    text = vrt.read_text(encoding="utf-8")

    assert "EPSG:3857" in text
    assert text.count("<VRTRasterBand") == 3
    assert text.count("<SimpleSource>") == basemap.tile_count() * 3
    assert 'rasterXSize="23552"' in text
    assert 'rasterYSize="23296"' in text


def test_commands_create_tiled_jpeg_geotiff_with_overviews(tmp_path: Path) -> None:
    vrt = tmp_path / "mosaic.vrt"
    output = tmp_path / "offline_satellite.tif"

    translate = basemap.translate_command(vrt, output)
    overviews = basemap.overview_command(output)

    assert translate[0] == "gdal_translate"
    assert "TILED=YES" in translate
    assert "COMPRESS=JPEG" in translate
    assert overviews[0] == "gdaladdo"
    assert "256" in overviews


def test_metadata_records_source_zoom_extent_and_tile_count() -> None:
    metadata = basemap.metadata_text()

    assert basemap.SOURCE_URL in metadata
    assert f"Zoom: {basemap.ZOOM}" in metadata
    assert f"Tile count: {basemap.tile_count()}" in metadata
    assert basemap.ATTRIBUTION in metadata


def test_build_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "offline_satellite.tif"
    output.touch()

    with pytest.raises(FileExistsError):
        basemap.build(output)
