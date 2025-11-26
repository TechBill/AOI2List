#!/usr/bin/env python3
"""
AOI2List – USGS LiDAR AOI Tile Finder
Developed by: Bill Fleming (TechBill)
Contact: billyjackrootbeer (at sign) gmail (dot) com
Donations: 
https://www.paypal.com/paypalme/techbill
https://www.buymeacoffee.com/techbill

Description:
------------------------------------
Given a center latitude/longitude and a square area in square miles,
this script queries USGS ScienceBase for LiDAR (LAZ) tiles that intersect
that area of interest (AOI) and writes a download list file containing one
LAZ URL per line.

This module also exposes helper functions for use by the GUI:
- query_sciencebase_for_aoi(...)

Usage (CLI example):
------------------------------------
python aoi2list.py --lat 37.1 --lon -92.6 --sqmi 6 --out downloadlist.txt

License and usage:
------------------------------------
This software is provided free for personal and educational use.
If you find this tool helpful and would like to support ongoing development,
donations are appreciated at the link above.

Commercial / business use:
If you wish to use this software in a commercial product, website,
corporate workflow, or other revenue-producing environment, please
request permission from the developer first.

This software is provided “as-is” with no warranty of any kind.
Permission is granted to use, modify, and distribute this software
for non-commercial purposes, provided that credit to the original
developer (Bill Fleming) is retained in derivative works.

By using this software, you agree that the author is not liable
for any damages or loss of data that may occur from its use.

Requires: requests
    pip install requests
"""

import argparse
import math
import sys
from typing import List, Dict, Any, Tuple

import requests


SCIENCEBASE_SEARCH_URL = "https://www.sciencebase.gov/catalog/items"

# USGS Lidar Point Cloud collection parent ID on ScienceBase
LPC_PARENT_ID = "4f70ab64e4b058caae3f8def"


# -----------------------------
# Argument parsing
# -----------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build LAZ download list from ScienceBase for an AOI."
    )
    parser.add_argument(
        "--lat",
        type=float,
        required=True,
        help="Center latitude in decimal degrees (positive north).",
    )
    parser.add_argument(
        "--lon",
        type=float,
        required=True,
        help="Center longitude in decimal degrees (negative west).",
    )
    parser.add_argument(
        "--sqmi",
        type=float,
        required=True,
        help="Square area size in square miles (AOI is a square of this area).",
    )
    parser.add_argument(
        "--out",
        default="downloadlist.txt",
        help="Output file path for list of LAZ URLs (default: downloadlist.txt).",
    )
    return parser.parse_args()


# -----------------------------
# Geometry helpers
# -----------------------------

def aoi_square_bbox(lat: float, lon: float, sqmi: float) -> Tuple[float, float, float, float]:
    """
    Compute a bounding box (min_lon, min_lat, max_lon, max_lat)
    for a square (in miles^2) centered at (lat, lon).

    Uses approximations:
      - ~69 miles per degree of latitude
      - ~69 * cos(lat) miles per degree of longitude
    """
    if sqmi <= 0:
        raise ValueError("sqmi must be > 0")

    side_miles = math.sqrt(sqmi)
    half_side = side_miles / 2.0

    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.0 * math.cos(math.radians(lat))

    if miles_per_deg_lon == 0:
        raise ValueError("Longitude scaling is zero at the poles; choose a different latitude.")

    dlat = half_side / miles_per_deg_lat
    dlon = half_side / miles_per_deg_lon

    min_lat = lat - dlat
    max_lat = lat + dlat
    min_lon = lon - dlon
    max_lon = lon + dlon

    return min_lon, min_lat, max_lon, max_lat


def bbox_to_wkt_polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> str:
    """
    Convert a bounding box to a WKT POLYGON string.
    ScienceBase expects coordinates as lon lat (x y).
    """
    coords = [
        (min_lon, min_lat),
        (min_lon, max_lat),
        (max_lon, max_lat),
        (max_lon, min_lat),
        (min_lon, min_lat),
    ]
    coord_str = ",".join(f"{x} {y}" for x, y in coords)
    return f"POLYGON(({coord_str}))"


def build_spatial_query_filter(wkt_polygon: str) -> str:
    """
    Build the spatialQuery filter string in the ad-hoc format used by ScienceBase:
        spatialQuery={wkt:"POLYGON(...)",relation:intersects}
    """
    return f'spatialQuery={{wkt:"{wkt_polygon}",relation:intersects}}'


def bbox_intersects(a_min_lon: float, a_min_lat: float, a_max_lon: float, a_max_lat: float,
                    b_min_lon: float, b_min_lat: float, b_max_lon: float, b_max_lat: float) -> bool:
    """Return True if two axis-aligned bboxes intersect."""
    return not (
        a_max_lon < b_min_lon or
        a_min_lon > b_max_lon or
        a_max_lat < b_min_lat or
        a_min_lat > b_max_lat
    )


# -----------------------------
# ScienceBase access
# -----------------------------

def fetch_sciencebase_items(spatial_filter: str, max_items: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch ScienceBase items that match the spatial filter from the
    USGS Lidar Point Cloud collection.
    """
    params = {
        "q": "",
        "format": "json",
        "parentId": LPC_PARENT_ID,         # restrict to LiDAR Point Cloud collection
        "filter": spatial_filter,          # spatialQuery={...}
        # Only ask for fields we actually use
        "fields": "webLinks,spatial,dates",
        "max": str(max_items),
    }

    resp = requests.get(SCIENCEBASE_SEARCH_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict) and "items" in data:
        return data["items"]
    elif isinstance(data, list):
        return data

    raise RuntimeError("Unexpected ScienceBase response structure; no 'items' key found.")


def filter_items_to_aoi(items: List[Dict[str, Any]],
                        min_lon: float, min_lat: float,
                        max_lon: float, max_lat: float) -> List[Dict[str, Any]]:
    """Keep only ScienceBase items whose own bbox intersects our AOI."""
    filtered: List[Dict[str, Any]] = []
    for item in items:
        spatial = item.get("spatial") or {}
        bb = spatial.get("boundingBox") or {}
        try:
            b_min_lon = bb["minX"]
            b_max_lon = bb["maxX"]
            b_min_lat = bb["minY"]
            b_max_lat = bb["maxY"]
        except KeyError:
            continue  # skip items without bbox

        if bbox_intersects(min_lon, min_lat, max_lon, max_lat,
                           b_min_lon, b_min_lat, b_max_lon, b_max_lat):
            filtered.append(item)

    return filtered


# -----------------------------
# Tile metadata extraction
# -----------------------------

def _guess_flight_date_from_item(item: Dict[str, Any]) -> str:
    """
    Try to get an acquisition/flight date from the 'dates' field.
    Returns a string like '2018-03-15' or '2018' or '' if unknown.
    """
    dates = item.get("dates") or []
    candidates = []
    for d in dates:
        label = (d.get("dateType") or d.get("type") or d.get("label") or "").lower()
        ds = (d.get("dateString") or "").strip()
        if not ds:
            continue
        if any(word in label for word in ["acquisition", "ground", "flight"]):
            candidates.append(ds)

    if candidates:
        return candidates[0]

    # Fallback: any dateString at all
    for d in dates:
        ds = (d.get("dateString") or "").strip()
        if ds:
            return ds

    return ""


def extract_laz_tiles_with_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    From ScienceBase items, build a flat list of tiles with minimal metadata.

    Each entry in the returned list is a dict:
      {
        "tile_id": str,       # derived from filename
        "url": str,           # direct LAZ URL
        "min_lon": float or None,
        "min_lat": float or None,
        "max_lon": float or None,
        "max_lat": float or None,
        "flight_date": str,   # free-text date, may be ''
      }
    """
    tiles: List[Dict[str, Any]] = []

    for item in items:
        web_links = item.get("webLinks") or []
        spatial = item.get("spatial") or {}
        bb = spatial.get("boundingBox") or {}

        min_lon = bb.get("minX")
        max_lon = bb.get("maxX")
        min_lat = bb.get("minY")
        max_lat = bb.get("maxY")

        flight_date = _guess_flight_date_from_item(item)

        for link in web_links:
            uri = link.get("uri")
            if not uri:
                continue
            if not uri.lower().endswith(".laz"):
                continue

            # Derive tile_id from filename
            tile_id = uri.rsplit("/", 1)[-1]
            if tile_id.lower().endswith(".laz"):
                tile_id = tile_id[:-4]

            tiles.append(
                {
                    "tile_id": tile_id,
                    "url": uri,
                    "min_lon": min_lon,
                    "min_lat": min_lat,
                    "max_lon": max_lon,
                    "max_lat": max_lat,
                    "flight_date": flight_date,
                }
            )

    # Deduplicate by URL while preserving first occurrence
    seen = set()
    unique_tiles: List[Dict[str, Any]] = []
    for t in tiles:
        url = t["url"]
        if url not in seen:
            seen.add(url)
            unique_tiles.append(t)

    # Sort by tile_id (tile name) for stable, human-friendly output
    unique_tiles.sort(key=lambda t: t.get("tile_id", ""))

    return unique_tiles


def collect_laz_urls_from_tiles(tiles: List[Dict[str, Any]]) -> List[str]:
    """Return list of LAZ URLs in the same order as tiles."""
    return [t["url"] for t in tiles]


# -----------------------------
# High-level query function for GUI
# -----------------------------

def query_sciencebase_for_aoi(lat: float, lon: float, sqmi: float) -> Tuple[List[Dict[str, Any]], str]:
    """
    High-level helper used by the GUI.

    Returns (tiles, info_message_string).

    tiles is a list of tile dicts as produced by extract_laz_tiles_with_metadata().
    """
    min_lon, min_lat, max_lon, max_lat = aoi_square_bbox(lat, lon, sqmi)

    wkt = bbox_to_wkt_polygon(min_lon, min_lat, max_lon, max_lat)
    spatial_filter = build_spatial_query_filter(wkt)

    items = fetch_sciencebase_items(spatial_filter)
    items_in_aoi = filter_items_to_aoi(items, min_lon, min_lat, max_lon, max_lat)
    tiles = extract_laz_tiles_with_metadata(items_in_aoi)

    msg = (
        f"AOI bbox:\n"
        f"  min_lon: {min_lon:.6f}, min_lat: {min_lat:.6f}\n"
        f"  max_lon: {max_lon:.6f}, max_lat: {max_lat:.6f}\n"
        f"Tiles found: {len(tiles)}"
    )
    return tiles, msg


# -----------------------------
# Output helper
# -----------------------------

def write_download_list(urls: List[str], out_path: str) -> None:
    """Write a plain-text list of URLs to the given file path."""
    with open(out_path, "w", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")


# -----------------------------
# CLI main
# -----------------------------

def main():
    args = parse_args()

    try:
        tiles, info = query_sciencebase_for_aoi(args.lat, args.lon, args.sqmi)
    except ValueError as e:
        print(f"Error computing AOI: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error querying ScienceBase: {e}", file=sys.stderr)
        sys.exit(2)

    print(info)
    print(f"Using ScienceBase. Total tiles: {len(tiles)}")

    if not tiles:
        print("No LAZ URLs found for this AOI.")
        sys.exit(0)

    urls = collect_laz_urls_from_tiles(tiles)
    write_download_list(urls, args.out)
    print(f"\nWrote LAZ URL list to: {args.out}")


if __name__ == "__main__":
    main()
