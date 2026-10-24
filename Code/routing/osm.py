"""
OpenStreetMap road data for Phase 11 routing: fetch the pinned Geofabrik India zone shapefiles' roads layer and read it.

Source: Geofabrik "free" shapefiles, © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright).
Only the roads members (gis_osm_roads_free_1.*) are downloaded, each with one HTTP range request on the dated,
immutable file name (e.g. western-zone-261022-free.shp.zip), inflated on the fly and checked against the zip CRC-32.
The raw files live outside the repository (BDA_OSM_DIR, default <user>/bda-env/osm); the repository keeps only the
snapshot record (Processed_Data/routing/osm_snapshot.csv) and the derived routing outputs.

Run:  python -B -m Code.routing.osm fetch          (roads, about 1.8 GB; resumable per member)
      python -B -m Code.routing.osm fetch-storage  (storage candidates, about 0.33 GB)
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import struct
import sys
import urllib.request
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SNAPSHOT = "261022"                      # Geofabrik build date (YYMMDD) of the pinned extracts: data up to 2026-10-22
ZONES = ["central", "eastern", "northern", "southern", "western"]   # the zones holding the 46 points (none in north-east)
BASE = "https://download.geofabrik.de/asia/india/{zone}-zone-{snap}-free.shp.zip"
MEMBERS = ["gis_osm_roads_free_1.shp", "gis_osm_roads_free_1.dbf", "gis_osm_roads_free_1.prj"]
# Storage-facility candidates (Code/routing/storage.py); recorded in their own snapshot file.
STORAGE_MEMBERS = [f"gis_osm_{l}_free_1.{e}" for l in ("pois", "pois_a", "landuse_a") for e in ("shp", "dbf")] + ["gis_osm_buildings_a_free_1.dbf"]
UA = {"User-Agent": "BDA-course-project/1.0 (academic, non-commercial routing study)"}
OSM_DIR = Path(os.environ.get("BDA_OSM_DIR", Path.home() / "bda-env" / "osm"))
SNAPSHOT_FILE = Path("Processed_Data/routing/osm_snapshot.csv")
STORAGE_SNAPSHOT_FILE = Path("Processed_Data/routing/osm_snapshot_storage.csv")
LICENCE = "OpenStreetMap contributors, ODbL 1.0; extracts by Geofabrik GmbH"


def zone_dir(zone: str) -> Path:
    return OSM_DIR / f"{zone}-zone-{SNAPSHOT}"


class _Range:
    """Minimal seekable reader over HTTP range requests, enough for zipfile to read the central directory."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA), timeout=60)
        self.size, self.last_modified = int(head.headers["Content-Length"]), head.headers.get("Last-Modified", "")

    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        end = self.size if n < 0 else min(self.size, self.pos + n)
        if end <= self.pos:
            return b""
        b = self.get(self.pos, end).read()
        self.pos += len(b)
        return b

    def get(self, start: int, end: int):
        return urllib.request.urlopen(urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={start}-{end - 1}"}), timeout=120)


def _fetch_member(src: _Range, info: zipfile.ZipInfo, out: Path) -> str:
    """Stream one deflated member to disk, verify its CRC-32, return its SHA-256."""
    hdr = src.get(info.header_offset, info.header_offset + 30).read()
    name_len, extra_len = struct.unpack("<HH", hdr[26:30])
    start = info.header_offset + 30 + name_len + extra_len
    body = src.get(start, start + info.compress_size)
    inflate = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
    crc, sha, tmp = 0, hashlib.sha256(), out.with_suffix(out.suffix + ".part")
    with open(tmp, "wb") as f:
        while chunk := body.read(1 << 20):
            data = inflate.decompress(chunk) if inflate else chunk
            crc, _ = zlib.crc32(data, crc), sha.update(data)
            f.write(data)
        if inflate:
            data = inflate.flush()
            crc, _ = zlib.crc32(data, crc), sha.update(data)
            f.write(data)
    if crc != info.CRC or tmp.stat().st_size != info.file_size:
        tmp.unlink()
        raise IOError(f"{out.name}: CRC or size mismatch, download corrupt")
    tmp.replace(out)
    return sha.hexdigest()


def fetch(zones=ZONES, members=MEMBERS, record=SNAPSHOT_FILE) -> None:
    rows = {(r["zone"], r["member"]): r for r in read_snapshot(record)} if record.exists() else {}
    for zone in zones:
        url = BASE.format(zone=zone, snap=SNAPSHOT)
        src = _Range(url)
        zf = zipfile.ZipFile(src)
        zone_dir(zone).mkdir(parents=True, exist_ok=True)
        for m in members:
            out, info = zone_dir(zone) / m, zf.getinfo(m)
            done = rows.get((zone, m))
            if done and out.exists() and out.stat().st_size == info.file_size:
                print(f"{zone}/{m}: already fetched")
                continue
            print(f"{zone}/{m}: {info.compress_size / 1e6:.0f} MB ...", flush=True)
            sha = _fetch_member(src, info, out)
            rows[(zone, m)] = {"zone": zone, "member": m, "url": url, "zip_bytes": src.size, "zip_last_modified": src.last_modified,
                               "member_bytes": info.file_size, "member_crc32": f"{info.CRC:08x}", "member_sha256": sha,
                               "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "licence": LICENCE}
            _write_snapshot(rows, record)


def read_snapshot(record: Path = SNAPSHOT_FILE) -> list[dict]:
    with open(record, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_snapshot(rows: dict, record: Path) -> None:
    record.parent.mkdir(parents=True, exist_ok=True)
    out = sorted(rows.values(), key=lambda r: (r["zone"], r["member"]))
    with open(record, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), lineterminator="\n")
        w.writeheader(), w.writerows(out)


def verify_snapshot(record: Path = SNAPSHOT_FILE) -> None:
    """Every fetched member still matches its recorded SHA-256 (the pinned input)."""
    for r in read_snapshot(record):
        if r["member"] == f"{BUILDINGS}.shp":                       # streamed, not stored: its subset is pinned instead
            continue
        p = zone_dir(r["zone"]) / r["member"]
        if _sha(p) != r["member_sha256"]:
            raise ValueError(f"{p} no longer matches the snapshot record")
    if record == STORAGE_SNAPSHOT_FILE:
        with open(SUBSET_MANIFEST, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if _sha(zone_dir(r["zone"]) / r["file"]) != r["sha256"]:
                    raise ValueError(f"{r['zone']} buildings subset no longer matches its record")


BUILDINGS = "gis_osm_buildings_a_free_1"
# Broad pre-filter for the 1 GB buildings geometry: a superset of every storage rule in Code/routing/storage.py.
BROAD_STORAGE_NAME = re.compile(r"cold|ware\s*hous|godown|\bfci\b|\bcwc\b|swc\b|food\s+corp|silo", re.I)


SUBSET_MANIFEST = Path("Processed_Data/routing/osm_buildings_subset_manifest.csv")


def buildings_subset_path(zone: str) -> Path:
    return zone_dir(zone) / f"{BUILDINGS}.subset.csv"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 24):
            h.update(b)
    return h.hexdigest()


def record_subsets() -> None:
    """Pin the streamed building subsets (the .shp itself is not stored) by row count and SHA-256."""
    rows = [{"zone": z, "file": buildings_subset_path(z).name, "records": sum(1 for _ in open(buildings_subset_path(z))) - 1,
             "sha256": _sha(buildings_subset_path(z))} for z in ZONES if buildings_subset_path(z).exists()]
    with open(SUBSET_MANIFEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["zone", "file", "records", "sha256"], lineterminator=chr(10))
        w.writeheader(), w.writerows(rows)


def fetch_buildings_subset(zones=ZONES) -> None:
    """Stream each zone's buildings .shp (not stored), keep the outer-ring centroid of records whose name matches
    BROAD_STORAGE_NAME, and verify the stream's CRC-32 and size. Needs the buildings .dbf (fetch-storage) first."""
    rows = {(r["zone"], r["member"]): r for r in read_snapshot(STORAGE_SNAPSHOT_FILE)}
    for zone in zones:
        if (zone, f"{BUILDINGS}.shp") in rows and buildings_subset_path(zone).exists():
            print(f"{zone}: buildings subset already built")
            continue
        names = read_dbf(zone_dir(zone) / f"{BUILDINGS}.dbf", ["name"])["name"]
        keep = np.array([bool(BROAD_STORAGE_NAME.search(n)) for n in names])
        url = BASE.format(zone=zone, snap=SNAPSHOT)
        src = _Range(url)
        info = zipfile.ZipFile(src).getinfo(f"{BUILDINGS}.shp")
        hdr = src.get(info.header_offset, info.header_offset + 30).read()
        start = info.header_offset + 30 + sum(struct.unpack("<HH", hdr[26:30]))
        body, inflate = src.get(start, start + info.compress_size), zlib.decompressobj(-15)
        crc, sha, size, buf, pos, i, out = 0, hashlib.sha256(), 0, b"", 100, 0, []
        print(f"{zone}: streaming {info.compress_size / 1e6:.0f} MB of building geometry ({keep.sum()} named candidates)", flush=True)
        while True:
            chunk = body.read(1 << 20)
            data = inflate.decompress(chunk) if chunk else inflate.flush()
            crc, size = zlib.crc32(data, crc), size + len(data)
            sha.update(data)
            buf += data
            while len(buf) >= pos + 8:                                  # parse every complete record in the buffer
                clen = struct.unpack(">i", buf[pos + 4:pos + 8])[0] * 2
                if len(buf) < pos + 8 + clen:
                    break
                rec = buf[pos + 8:pos + 8 + clen]
                if keep[i] and struct.unpack("<i", rec[:4])[0] == 5:
                    nparts, npts = struct.unpack("<ii", rec[36:44])
                    parts = np.frombuffer(rec, "<i4", nparts, 44)
                    end = parts[1] if nparts > 1 else npts
                    ring = np.frombuffer(rec, "<f8", npts * 2, 44 + 4 * nparts).reshape(npts, 2)[:end]
                    out.append((i, round(float(ring[:, 1].mean()), 6), round(float(ring[:, 0].mean()), 6)))
                pos, i = pos + 8 + clen, i + 1
            buf, pos = buf[pos:], 0
            if not chunk:
                break
        if crc != info.CRC or size != info.file_size or i != len(keep):
            raise IOError(f"{zone} buildings stream: CRC, size or record count mismatch")
        with open(buildings_subset_path(zone), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["record", "latitude", "longitude"]), w.writerows(out)
        rows[(zone, f"{BUILDINGS}.shp")] = {
            "zone": zone, "member": f"{BUILDINGS}.shp", "url": url, "zip_bytes": src.size, "zip_last_modified": src.last_modified,
            "member_bytes": info.file_size, "member_crc32": f"{info.CRC:08x}", "member_sha256": sha.hexdigest(),
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "licence": LICENCE + "; streamed, only ring-vertex means of name-matched records kept"}
        _write_snapshot(rows, STORAGE_SNAPSHOT_FILE)
    record_subsets()


# ---------------------------------------------------------------- shapefile reading (standard library + numpy)
def read_dbf(path: Path, fields: list[str]) -> dict[str, np.ndarray]:
    """Read selected columns of a dBASE III file as stripped strings."""
    with open(path, "rb") as f:
        n, hlen, rlen = struct.unpack("<xxxxIHH20x", f.read(32))
        specs, off = [], 1                                     # byte 0 of each record is the deletion flag
        while (d := f.read(32))[0] != 0x0D:
            name = d[:11].split(b"\0")[0].decode()
            specs.append((name, off, d[16]))
            off += d[16]
        f.seek(hlen)
        raw = np.frombuffer(f.read(n * rlen), dtype=np.uint8).reshape(n, rlen)
    out = {}
    for name, o, ln in specs:
        if name in fields:
            col = raw[:, o:o + ln].copy().view(f"S{ln}").ravel()
            out[name] = np.char.strip(np.char.decode(col, "utf-8", errors="replace"))
    missing = set(fields) - set(out)
    if missing:
        raise KeyError(f"{path.name}: missing fields {missing}")
    return out


def read_polylines(path: Path, keep: np.ndarray, types=(3,)):
    """Yield (record_index, points[n,2] lon/lat) per part of the records in `keep` (boolean mask).
    Shape type 3 = PolyLine; 5 = Polygon (same layout; parts are rings, the first is the outer ring); 1 = Point."""
    with open(path, "rb") as f:
        if struct.unpack(">i", f.read(4))[0] != 9994:
            raise ValueError(f"{path.name}: not a shapefile")
        f.seek(100)
        i = 0
        while hdr := f.read(8):
            _, clen = struct.unpack(">ii", hdr)
            body = f.read(clen * 2)
            kind = struct.unpack("<i", body[:4])[0] if keep[i] else 0
            if kind == 1 and kind in types:
                yield i, np.frombuffer(body, "<f8", 2, 4).reshape(1, 2)
            elif kind in (3, 5) and kind in types:
                nparts, npts = struct.unpack("<ii", body[36:44])
                parts = np.frombuffer(body, "<i4", nparts, 44)
                pts = np.frombuffer(body, "<f8", npts * 2, 44 + 4 * nparts).reshape(npts, 2)
                bounds = list(parts) + [npts]
                for a, b in zip(bounds[:-1], bounds[1:]):
                    yield i, pts[a:b]
            i += 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        fetch(sys.argv[2:] or ZONES)
    elif cmd == "fetch-storage":
        fetch(sys.argv[2:] or ZONES, STORAGE_MEMBERS, STORAGE_SNAPSHOT_FILE)
    elif cmd == "fetch-buildings":
        fetch_buildings_subset(sys.argv[2:] or ZONES)
    elif cmd == "verify":
        verify_snapshot(); verify_snapshot(STORAGE_SNAPSHOT_FILE); print("snapshot OK")
    else:
        sys.exit("usage: python -B -m Code.routing.osm fetch [zone ...] | fetch-storage [zone ...] | fetch-buildings [zone ...] | verify")
