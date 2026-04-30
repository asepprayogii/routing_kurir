"""
Kurir Toko — Route Optimizer
============================
Fitur:
- Optimasi rute pengiriman berdasarkan lokasi
- Estimasi jarak dan waktu tempuh
- Export hasil ke CSV
- Input koordinat manual jika diperlukan
"""

import math
import re
import time
import requests
import streamlit as st
import pandas as pd
import folium
import polyline as polyline_lib
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# ──────────────────────────────────────────────────────
# KONFIGURASI INTERNAL (Tidak ditampilkan di UI)
# ──────────────────────────────────────────────────────

_ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImRjYTUxM2YwYWU1NzQwMDViNTU4M2VmZDA4NWRlNzFjIiwiaCI6Im11cm11cjY0In0="
_ORS_BASE = "https://api.openrouteservice.org/v2"
_ORS_MATRIX_BASE = "https://api.openrouteservice.org/v2/matrix"

_OSRM_BASE = "http://router.project-osrm.org/route/v1/driving"
_OSRM_TABLE = "http://router.project-osrm.org/table/v1/driving"

_LOCATIONIQ_API_KEY = "pk.99cc6a53008f844d73e5fd3a998fb888"
_LOCATIONIQ_BASE = "https://us1.locationiq.com/v1"

_GEOCODE_DELAY = 0.3
_KURIR_TOKO_KEYWORDS = ["kurir toko", "kurirtoko", "kurir_toko"]

# ──────────────────────────────────────────────────────
# DATA CABANG DEFAULT
# ──────────────────────────────────────────────────────

_BRANCHES_DEFAULT = [
    {"kode": "SUB", "nama": "Surabaya",   "lat": -7.317566, "lng": 112.764234},
    {"kode": "JKT", "nama": "Jakarta",    "lat": -6.208800, "lng": 106.845600},
    {"kode": "MLG", "nama": "Malang",     "lat": -7.979700, "lng": 112.630400},
    {"kode": "SMG", "nama": "Semarang",   "lat": -6.966700, "lng": 110.416700},
    {"kode": "JOG", "nama": "Yogyakarta", "lat": -7.795600, "lng": 110.369500},
    {"kode": "BLI", "nama": "Bali",       "lat": -8.340500, "lng": 115.092000},
]

_BRANCH_COLORS = {
    "SUB": "#C0392B", "JKT": "#1A5276", "MLG": "#1E8449",
    "SMG": "#D35400", "JOG": "#6C3483", "BLI": "#117A65",
}

_FOLIUM_COLORS = {
    "SUB": "red", "JKT": "blue", "MLG": "green",
    "SMG": "orange", "JOG": "purple", "BLI": "cadetblue",
}

_REGION_FALLBACK = {
    "rungkut industri": (-7.3280, 112.7590), "rungkut": (-7.3311, 112.7610),
    "tandes lor": (-7.2330, 112.7030), "tandes": (-7.2350, 112.7050),
    "raden wijaya": (-7.2820, 112.7380), "wonokromo": (-7.2850, 112.7350),
    "mulyorejo": (-7.2950, 112.7550), "manyar kertoadjo": (-7.2980, 112.7580),
    "manyar kertoarjo": (-7.2980, 112.7580), "sambikerep": (-7.3050, 112.6850),
    "citraland": (-7.3020, 112.6880), "citraland cbd": (-7.3030, 112.6890),
    "gubeng kertajaya": (-7.2680, 112.7520), "gubeng": (-7.2650, 112.7500),
    "gayungan": (-7.3150, 112.7280), "tegalsari": (-7.2750, 112.7450),
    "genteng": (-7.2620, 112.7420), "benowo": (-7.2450, 112.6650),
    "wiyung asri": (-7.3200, 112.6900), "wiyung": (-7.3180, 112.6920),
    "jemursari": (-7.3050, 112.7450), "ngagel jaya": (-7.2800, 112.7500),
    "ngagel": (-7.2780, 112.7480), "diponegoro": (-7.2600, 112.7400),
    "ahmad yani": (-7.2700, 112.7550), "darmo permai": (-7.2780, 112.7280),
    "darmo": (-7.2750, 112.7300), "hr muhammad": (-7.2680, 112.7450),
    "surabaya": (-7.2575, 112.7521),
    "lamongan": (-7.1196, 112.4115), "gresik": (-7.1560, 112.6508),
    "sidoarjo": (-7.4561, 112.7185), "mojokerto": (-7.4700, 112.4339),
    "pasuruan": (-7.6451, 112.9070), "probolinggo": (-7.7543, 113.2159),
    "jember": (-8.1724, 113.7020), "banyuwangi": (-8.2191, 114.3691),
    "kediri": (-7.8166, 112.0114), "blitar": (-8.0954, 112.1609),
    "tulungagung": (-8.0652, 111.9041), "madiun": (-7.6298, 111.5239),
    "bojonegoro": (-7.1507, 111.8817), "tuban": (-6.8918, 112.0508),
    "malang": (-7.9797, 112.6304), "semarang": (-6.9667, 110.4167),
    "yogyakarta": (-7.7956, 110.3695), "solo": (-7.5755, 110.8243),
    "jakarta": (-6.2088, 106.8456), "bandung": (-6.9175, 107.6191),
    "bekasi": (-6.2383, 106.9756), "tangerang": (-6.1702, 106.6402),
    "depok": (-6.4025, 106.7942), "bogor": (-6.5971, 106.8060),
    "denpasar": (-8.6705, 115.2126), "bali": (-8.3405, 115.0920),
}

# ──────────────────────────────────────────────────────
# ROUTING ENGINES (Internal)
# ──────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def _ors_route(coords: tuple, api_key: str = _ORS_API_KEY) -> dict:
    if len(coords) < 2:
        return {"distance_km": 0, "duration_min": 0, "duration_seconds": 0, "geometry": []}
    ors_coords = [[lng, lat] for lat, lng in coords]
    headers = {"Accept": "application/json", "Authorization": api_key, "Content-Type": "application/json"}
    payload = {"coordinates": ors_coords, "instructions": False, "geometry": True, "format": "json", "units": "km"}
    try:
        response = requests.post(f"{_ORS_BASE}/directions/driving-car", json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("features"):
                route = data["features"][0]
                geometry = [[coord[1], coord[0]] for coord in route["geometry"]["coordinates"]]
                summary = route["properties"]["summary"]
                return {"distance_km": round(summary["distance"], 2), "duration_min": round(summary["duration"] / 60, 1), "duration_seconds": summary["duration"], "geometry": geometry}
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def _ors_matrix(coords: tuple, api_key: str = _ORS_API_KEY) -> tuple:
    if len(coords) < 2:
        return None, None
    ors_coords = [[lng, lat] for lat, lng in coords]
    headers = {"Accept": "application/json", "Authorization": api_key, "Content-Type": "application/json"}
    payload = {"locations": ors_coords, "metrics": ["distance", "duration"], "units": "km"}
    try:
        response = requests.post(f"{_ORS_MATRIX_BASE}/driving-car", json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            distances = data.get("distances", [])
            durations = data.get("durations", [])
            if distances and durations:
                dist_matrix = [[round(d, 2) if d else 0 for d in row] for row in distances]
                dur_matrix = [[round(d, 1) if d else 0 for d in row] for row in durations]
                return dist_matrix, dur_matrix
    except Exception:
        pass
    return None, None

@st.cache_data(show_spinner=False, ttl=3600)
def _osrm_route(coords: tuple) -> dict:
    if len(coords) < 2:
        return {"distance_km": 0, "duration_min": 0, "duration_seconds": 0, "geometry": []}
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)
    try:
        r = requests.get(f"{_OSRM_BASE}/{coord_str}", params={"overview": "full", "geometries": "polyline"}, timeout=15)
        data = r.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            decoded = polyline_lib.decode(route.get("geometry", "")) if route.get("geometry") else []
            return {"distance_km": round(route["distance"] / 1000, 2), "duration_min": round(route["duration"] / 60, 1), "duration_seconds": route["duration"], "geometry": decoded}
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def _osrm_table(coords: tuple) -> tuple:
    if len(coords) < 2:
        return None, None
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)
    try:
        r = requests.get(f"{_OSRM_TABLE}/{coord_str}", params={"annotations": "distance,duration"}, timeout=30)
        data = r.json()
        if data.get("code") == "Ok":
            distances = [[round(v / 1000, 2) if v else 0 for v in row] for row in data.get("distances", [])]
            durations = [[round(v, 1) if v else 0 for v in row] for row in data.get("durations", [])]
            return distances, durations
    except Exception:
        pass
    return None, None

def _get_route_with_fallback(coords: tuple) -> dict:
    route = _ors_route(coords)
    if route:
        return route
    route = _osrm_route(coords)
    if route:
        return route
    return {"distance_km": 0, "duration_min": 0, "duration_seconds": 0, "geometry": []}

def _get_matrix_with_fallback(coords: tuple) -> tuple:
    dist, dur = _ors_matrix(coords)
    if dist and dur:
        return dist, dur
    return _osrm_table(coords)

# ──────────────────────────────────────────────────────
# GEOCODING (Internal)
# ──────────────────────────────────────────────────────

def _extract_coords_from_text(text: str):
    if not text or str(text).strip() in ("", "-", "nan"):
        return None, None
    t = str(text)
    m = re.search(r"lat[:\s=]+(-?\d{1,3}\.?\d*)[,\s]+lng[:\s=]+(\d{2,3}\.?\d*)", t, re.IGNORECASE)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"\(?(-[1-9]\d?\.\d{3,})\s*,\s*(1[0-2]\d\.\d{3,})\)?", t)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -11.0 <= lat <= 6.0 and 94.0 <= lng <= 141.0:
            return lat, lng
    m = re.search(r"(-[0-9]{1,2}\.[0-9]{4,})[,\s]+([0-9]{3}\.[0-9]{4,})", t)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -11.0 <= lat <= 6.0 and 94.0 <= lng <= 141.0:
            return lat, lng
    return None, None

@st.cache_data(show_spinner=False, ttl=7200)
def _locationiq(query: str, api_key: str):
    if not api_key:
        return None, None
    try:
        params = {"key": api_key, "q": query, "format": "json", "limit": 1, "countrycodes": "id", "accept-language": "id"}
        r = requests.get(f"{_LOCATIONIQ_BASE}/search.php", params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
                if -11.0 <= lat <= 6.0 and 94.0 <= lng <= 141.0:
                    return lat, lng
    except Exception:
        pass
    return None, None

@st.cache_data(show_spinner=False)
def _nominatim(query: str):
    try:
        loc = Nominatim(user_agent="kurir_toko_app", timeout=10).geocode(query)
        if loc:
            return loc.latitude, loc.longitude
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    return None, None

@st.cache_data(show_spinner=False)
def _photon(query: str):
    try:
        r = requests.get("https://photon.komoot.io/api/", params={"q": query, "limit": 1, "lang": "id"}, timeout=10)
        feats = r.json().get("features", [])
        if feats:
            c = feats[0]["geometry"]["coordinates"]
            return c[1], c[0]
    except Exception:
        pass
    return None, None

def _region_fallback(raw: str):
    text = raw.lower()
    specific_areas = ["rungkut industri", "rungkut", "tandes lor", "tandes", "wonokromo", "raden wijaya", 
                      "mulyorejo", "manyar kertoarjo", "manyar kertoadjo", "sambikerep", "citraland", 
                      "citraland cbd", "gubeng kertajaya", "gubeng", "gayungan", "tegalsari", "genteng", 
                      "benowo", "wiyung asri", "wiyung", "jemursari", "ngagel jaya", "ngagel", "diponegoro", 
                      "ahmad yani", "darmo permai", "darmo", "hr muhammad"]
    for area in specific_areas:
        if area in text and area in _REGION_FALLBACK:
            return _REGION_FALLBACK[area]
    for region, coords in sorted(_REGION_FALLBACK.items(), key=lambda x: -len(x[0])):
        if region in text and region not in specific_areas and region != "surabaya":
            return coords
    if "surabaya" in text and "surabaya" in _REGION_FALLBACK:
        return _REGION_FALLBACK["surabaya"]
    return None, None

def _geocode(raw: str, api_key: str = "") -> tuple:
    lat_ext, lng_ext = _extract_coords_from_text(raw)
    if lat_ext is not None:
        return lat_ext, lng_ext, "Koordinat dari teks", "tinggi"
    cleaned = _clean_address(raw)
    if api_key:
        lat, lng = _locationiq(cleaned + ", Indonesia", api_key)
        if lat:
            return lat, lng, "Layanan eksternal", "tinggi"
        time.sleep(0.15)
    lat, lng = _nominatim(cleaned + ", Indonesia")
    if lat:
        return lat, lng, "Layanan eksternal", "tinggi"
    time.sleep(_GEOCODE_DELAY)
    lat, lng = _photon(cleaned + " Indonesia")
    if lat:
        return lat, lng, "Layanan eksternal", "tinggi"
    time.sleep(0.2)
    lat, lng = _region_fallback(raw)
    if lat:
        is_kecamatan = any(ka in raw.lower() for ka in _REGION_FALLBACK.keys() if ka != "surabaya")
        return lat, lng, "Estimasi wilayah", "sedang" if is_kecamatan else "rendah"
    return None, None, "Gagal", "gagal"

# ──────────────────────────────────────────────────────
# ADDRESS PROCESSING
# ──────────────────────────────────────────────────────

_SINGKATAN_MAP = {
    r"\bJl\.?\b": "Jalan", r"\bJln\.?\b": "Jalan", r"\bNo\.?\s*": "Nomor ",
    r"\bNO\.?\s*": "Nomor ", r"\bLT\.?\s*(\d)": r"Lantai \1", r"\bLt\.?\s*(\d)": r"Lantai \1",
    r"\bBLOK\b": "Blok", r"\bBlk\.?\b": "Blok", r"\bKec\.?\b": "Kecamatan",
    r"\bKel\.?\b": "Kelurahan", r"\bKab\.?\b": "Kabupaten",
    r"\bRT\.?\s*\d+\s*[/,]?\s*RW\.?\s*\d+\b": "", r"\bRT\.?\s*\d+\b": "", r"\bRW\.?\s*\d+\b": "",
    r"\bGg\.?\b": "Gang", r"\bPerum\.?\b": "Perumahan", r"\bKomp\.?\b": "Komplek",
}

def _expand_abbreviations(raw: str) -> str:
    result = raw
    for pattern, replacement in _SINGKATAN_MAP.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", result).strip()

def _clean_address(raw: str) -> str:
    addr = _expand_abbreviations(raw)
    addr = re.sub(r"\bIndonesia\b", "", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\b\d{5}\b", "", addr)
    parts = [p.strip() for p in addr.split(",") if p.strip() and len(p.strip()) > 2]
    unique, seen = [], set()
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return ", ".join([p for p in unique if len(p) > 2][:6])

# ──────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────

def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0 menit"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours} jam {minutes} menit"
    return f"{minutes} menit"

def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dl, dg = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dl / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dg / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _validate_geocoding_results(geocoded: list, threshold_km: float = 0.5) -> dict:
    if len(geocoded) < 3:
        return {"is_valid": True, "warning": None}
    coords = [(p["lat"], p["lng"]) for p in geocoded if p.get("lat")]
    if len(coords) < 3:
        return {"is_valid": True, "warning": None}
    fallback_count = sum(1 for p in geocoded if p.get("geocode_sumber") == "Estimasi wilayah")
    same_count = 0
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            if _haversine(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) < threshold_km:
                same_count += 1
    total_pairs = len(coords) * (len(coords) - 1) // 2
    if total_pairs > 0 and (same_count / total_pairs > 0.6 and fallback_count > len(geocoded) * 0.5):
        return {"is_valid": False, "warning": "Beberapa alamat memiliki lokasi yang serupa. Periksa koordinat manual jika diperlukan."}
    return {"is_valid": True, "warning": None}

def _is_kurir_toko(val) -> bool:
    if pd.isna(val) or str(val).strip() == "":
        return False
    v = str(val).lower().replace(" ", "").replace("_", "")
    return any(kw.replace(" ", "") in v for kw in _KURIR_TOKO_KEYWORDS)

def _format_currency(val) -> str:
    try:
        return f"Rp {int(float(val)):,}".replace(",", ".")
    except:
        return "-"

def _format_date(val) -> str:
    try:
        if pd.isna(val) or str(val).strip() in ("", "NaT", "nan", "-"):
            return "-"
        ts = pd.to_datetime(str(val), errors="coerce")
        return ts.strftime("%d/%m/%Y %H:%M") if not pd.isna(ts) else str(val)[:16]
    except:
        return str(val)[:16] if val else "-"

def _load_orders_excel(uploaded_file):
    try:
        df_raw = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.lower().endswith(".csv") else pd.read_excel(uploaded_file, dtype=str)
        df_raw.columns = [c.strip() for c in df_raw.columns]
        cl = {c.lower(): c for c in df_raw.columns}
        def gc(names):
            for n in names:
                if n.lower() in cl:
                    return cl[n.lower()]
            return None
        col_addr = gc(["Shipping Address", "shipping_address", "Alamat"])
        if not col_addr:
            return None, "Kolom 'Shipping Address' tidak ditemukan."
        r = pd.DataFrame()
        r["Shipping Address"] = df_raw[col_addr].fillna("").astype(str)
        r["Invoice NO"] = df_raw[gc(["Invoice NO", "Invoice No"])].fillna("-").astype(str) if gc(["Invoice NO", "Invoice No"]) else "-"
        r["SO Number"] = df_raw[gc(["SO Number", "so_number"])].fillna("-").astype(str) if gc(["SO Number"]) else "-"
        r["Order Date"] = df_raw[gc(["Order Date", "order_date"])].fillna("-").astype(str) if gc(["Order Date"]) else "-"
        r["Recipient Name"] = df_raw[gc(["Recipient Name", "recipient_name", "Penerima"])].fillna("-").astype(str) if gc(["Recipient Name", "Penerima"]) else "-"
        r["Recipient Phone"] = df_raw[gc(["Recipient Phone", "recipient_phone"])].fillna("-").astype(str) if gc(["Recipient Phone"]) else "-"
        r["Items Name"] = df_raw[gc(["Items Name", "items_name", "Nama Barang"])].fillna("-").astype(str) if gc(["Items Name", "Nama Barang"]) else "-"
        r["Items SKU"] = df_raw[gc(["Items SKU", "items_sku", "SKU"])].fillna("-").astype(str) if gc(["Items SKU", "SKU"]) else "-"
        r["Items Quantity"] = pd.to_numeric(df_raw[gc(["Items Quantity", "items_quantity", "Qty"])], errors="coerce").fillna(1).astype(int) if gc(["Items Quantity", "Qty"]) else 1
        r["Total Amount"] = pd.to_numeric(df_raw[gc(["Total Amount", "total_amount", "Total"])], errors="coerce").fillna(0) if gc(["Total Amount", "Total"]) else 0
        r["Payment Status"] = df_raw[gc(["Payment Status", "payment_status"])].fillna("-").astype(str) if gc(["Payment Status"]) else "-"
        r["Fulfillment Status"] = df_raw[gc(["Fulfillment Status", "fulfillment_status"])].fillna("-").astype(str) if gc(["Fulfillment Status"]) else "-"
        r["Shipping Courier"] = df_raw[gc(["Shipping Courier", "shipping_courier", "Kurir"])].fillna("-").astype(str) if gc(["Shipping Courier", "Kurir"]) else "-"
        r = r[~r["Shipping Address"].str.strip().str.lower().isin(["", "indonesia", "-", "nan"])].reset_index(drop=True)
        n_kt = r["Shipping Courier"].apply(_is_kurir_toko).sum()
        return r, f"{len(r)} order dimuat. {n_kt} Kurir Toko, {len(r) - n_kt} kurir lain."
    except Exception as e:
        return None, f"Gagal membaca file: {e}"

# ──────────────────────────────────────────────────────
# ROUTING OPTIMIZATION
# ──────────────────────────────────────────────────────

def _nn_tsp_with_duration(start_lat, start_lng, pkgs: list) -> tuple:
    if not pkgs:
        return [], 0, 0
    all_coords = [(start_lat, start_lng)] + [(p["lat"], p["lng"]) for p in pkgs]
    dist_matrix, dur_matrix = _get_matrix_with_fallback(tuple(all_coords))
    if dist_matrix and dur_matrix:
        remaining_idx = list(range(1, len(pkgs) + 1))
        route, total_km, total_sec, current_idx = [], 0.0, 0.0, 0
        while remaining_idx:
            best_i, best_d, best_t, best_mi = None, float("inf"), float("inf"), None
            for mi in remaining_idx:
                d = dist_matrix[current_idx][mi]
                t = dur_matrix[current_idx][mi]
                if d < best_d:
                    best_d, best_t, best_i, best_mi = d, t, remaining_idx.index(mi), mi
            chosen = pkgs[best_mi - 1].copy()
            chosen["jarak_lurus_km"] = round(_haversine(all_coords[current_idx][0], all_coords[current_idx][1], all_coords[best_mi][0], all_coords[best_mi][1]), 2)
            chosen["jarak_jalan_km"] = round(best_d, 2)
            chosen["durasi_detik"] = best_t
            chosen["durasi_menit"] = round(best_t / 60, 1)
            chosen["durasi_text"] = _format_duration(best_t)
            route.append(chosen)
            total_km += best_d
            total_sec += best_t
            current_idx = best_mi
            remaining_idx.pop(best_i)
        return route, round(total_km, 2), round(total_sec / 60, 1), total_sec
    else:
        remaining, route, total_km, total_min, clat, clng = pkgs.copy(), [], 0.0, 0.0, start_lat, start_lng
        while remaining:
            best_i, best_d = 0, float("inf")
            for i, p in enumerate(remaining):
                d = _haversine(clat, clng, p["lat"], p["lng"])
                if d < best_d:
                    best_d, best_i = d, i
            chosen = remaining.pop(best_i)
            estimated_duration_sec = best_d * 120
            chosen["jarak_lurus_km"] = round(best_d, 2)
            chosen["jarak_jalan_km"] = round(max(best_d, 0.001) * 1.3, 2)
            chosen["durasi_detik"] = estimated_duration_sec * 1.3
            chosen["durasi_menit"] = round(estimated_duration_sec * 1.3 / 60, 1)
            chosen["durasi_text"] = _format_duration(estimated_duration_sec * 1.3)
            route.append(chosen)
            total_km += max(best_d, 0.001) * 1.3
            total_min += estimated_duration_sec * 1.3 / 60
            clat, clng = chosen["lat"], chosen["lng"]
        return route, round(total_km, 2), round(total_min, 1), total_min * 60

# ──────────────────────────────────────────────────────
# MAP VISUALIZATION
# ──────────────────────────────────────────────────────

_SEGMENT_PALETTE = ["#E6194B", "#3CB44B", "#4363D8", "#F58231", "#911EB4", "#42D4F4", "#F032E6", "#BFEF45", 
                   "#FABED4", "#469990", "#DCBEFF", "#9A6324", "#FFFAC8", "#800000", "#AAFFC3", "#808000", 
                   "#FFD8B1", "#000075", "#A9A9A9", "#E6BEFF"]

def _get_segment_color(idx: int) -> str:
    return _SEGMENT_PALETTE[idx % len(_SEGMENT_PALETTE)]

def _buat_peta(cabang: dict, route: list) -> folium.Map:
    m = folium.Map(location=[cabang["lat"], cabang["lng"]], zoom_start=10, tiles="CartoDB Positron")
    folium.Marker([cabang["lat"], cabang["lng"]], tooltip=f"Gudang {cabang['nama']}", 
                  icon=folium.Icon(color=_FOLIUM_COLORS.get(cabang["kode"], "gray"), icon="home", prefix="fa")).add_to(m)
    if not route:
        return m
    all_points = [(cabang["lat"], cabang["lng"])] + [(p["lat"], p["lng"]) for p in route]
    for i in range(len(all_points) - 1):
        seg = _get_route_with_fallback((all_points[i], all_points[i + 1]))
        color = _get_segment_color(i)
        if seg and seg.get("geometry"):
            coords = seg["geometry"]
            tooltip = f"#{i + 1} -> #{i + 2} ({seg['distance_km']} km, {_format_duration(seg['duration_seconds'])})"
        else:
            coords = [list(all_points[i]), list(all_points[i + 1])]
            tooltip = f"#{i + 1} -> #{i + 2} (Estimasi)"
        folium.PolyLine(coords, color=color, weight=5 if seg else 3, opacity=0.85, tooltip=tooltip).add_to(m)
    for i, pkg in enumerate(route, 1):
        color = _get_segment_color(i - 1)
        tip = f"<b>#{i} - {pkg.get('Invoice NO', '-')}</b><br>{pkg.get('Recipient Name', '-')}<br>{str(pkg.get('Items Name', '-'))[:40]}<br>Jarak: {pkg['jarak_jalan_km']} km<br>Waktu: {pkg.get('durasi_text', '-')}"
        folium.CircleMarker([pkg["lat"], pkg["lng"]], radius=8, color=color, fill=True, fill_color=color, tooltip=tip).add_to(m)
        folium.Marker([pkg["lat"], pkg["lng"]], 
                      icon=folium.DivIcon(html=f'<div style="color:white;background:{color};border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:bold;border:2px solid white">{i}</div>')).add_to(m)
    return m

# ──────────────────────────────────────────────────────
# STATE & UI SETUP
# ──────────────────────────────────────────────────────

def _init_state():
    defs = {"branches": [b.copy() for b in _BRANCHES_DEFAULT], "selected_branch_kode": _BRANCHES_DEFAULT[0]["kode"],
            "hasil": None, "orders_df": None, "pkg_df": None, "_last_geocoded": [], "filter_kt": True, "manual_coords": {}}
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

_CUSTOM_CSS = """<style>
#MainMenu, footer { visibility: hidden; }
[data-testid="metric-container"] { background:#f8f9fa; border:1px solid #e9ecef; border-radius:8px; padding:12px 16px; }
thead tr th { background-color:#f1f3f5!important; font-weight:600!important; font-size:13px!important; color:#343a40!important; }
.stButton > button[kind="primary"] { background-color:#1a3a5c; border-color:#1a3a5c; font-weight:600; }
.section-header { font-size:12px; font-weight:700; color:#6c757d; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }
.info-card { background:#f8f9fa; border-left:4px solid #1a3a5c; padding:10px 16px; border-radius:0 6px 6px 0; margin-bottom:10px; font-size:13px; }
</style>"""

# ──────────────────────────────────────────────────────
# MAIN APPLICATION
# ──────────────────────────────────────────────────────

st.set_page_config(page_title="Kurir Toko - Route Optimizer", layout="wide")
st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
_init_state()

# Sidebar
with st.sidebar:
    st.markdown("## Kurir Toko")
    st.caption("Route Optimizer")
    st.divider()
    
    branches = st.session_state.branches
    branch_options = {b["kode"]: f"{b['nama']} ({b['kode']})" for b in branches}
    selected_kode = st.radio("Cabang", list(branch_options.keys()), 
                             format_func=lambda k: branch_options[k], 
                             index=list(branch_options.keys()).index(st.session_state.selected_branch_kode), 
                             label_visibility="collapsed")
    if selected_kode != st.session_state.selected_branch_kode:
        st.session_state.selected_branch_kode = selected_kode
        st.session_state.hasil = None
        st.rerun()
    
    cabang_aktif = next(b for b in branches if b["kode"] == selected_kode)
    st.markdown(f'<div style="background:#f8f9fa;border-left:4px solid {_BRANCH_COLORS.get(cabang_aktif["kode"], "#555")};padding:10px;border-radius:4px;margin:8px 0"><strong>{cabang_aktif["nama"]}</strong><br><span style="font-size:12px;color:#666">Lat: {cabang_aktif["lat"]:.6f} | Lng: {cabang_aktif["lng"]:.6f}</span></div>', unsafe_allow_html=True)
    st.divider()
    
    if st.button("Reset", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# Header
st.title("Kurir Toko - Route Optimizer")
st.caption("Optimasi rute pengiriman dengan estimasi jarak dan waktu")
st.divider()

# 1. UPLOAD FILE
st.subheader("Upload File Orders")
uploaded = st.file_uploader("Upload file orders (xlsx/csv)", type=["xlsx", "xls", "csv"])

if uploaded:
    df_orders, msg = _load_orders_excel(uploaded)
    if df_orders is None:
        st.error(msg)
    else:
        st.session_state.orders_df = df_orders
        st.success(msg)
        n_kt = df_orders["Shipping Courier"].apply(_is_kurir_toko).sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Order", len(df_orders))
        m2.metric("Kurir Toko", int(n_kt))
        m3.metric("Total Nilai", _format_currency(df_orders["Total Amount"].sum()))
        
        st.session_state.filter_kt = st.toggle("Filter hanya Kurir Toko", value=st.session_state.filter_kt)
        df_view = df_orders[df_orders["Shipping Courier"].apply(_is_kurir_toko)] if st.session_state.filter_kt else df_orders
        
        if df_view.empty:
            st.warning("Tidak ada order Kurir Toko.")
        else:
            st.markdown(f"#### Preview ({len(df_view)} baris)")
            cols_show = {"Invoice NO": "Invoice", "Order Date": "Tgl", "Recipient Name": "Penerima", 
                         "Items Name": "Barang", "Total Amount": "Total", "Shipping Address": "Alamat"}
            avail = [c for c in cols_show if c in df_view.columns]
            df_disp = df_view[avail].copy()
            df_disp.columns = [cols_show[c] for c in avail]
            if "Tgl" in df_disp.columns:
                df_disp["Tgl"] = df_disp["Tgl"].apply(_format_date)
            st.dataframe(df_disp, use_container_width=True, height=250, hide_index=True)
            
            if st.button(f"Gunakan {len(df_view)} Order Ini", type="primary", use_container_width=True):
                st.session_state.pkg_df = df_view.reset_index(drop=True)
                st.session_state.hasil = None
                st.session_state.manual_coords = {}
                st.success("Siap untuk menghitung rute")

# 2. INPUT KOORDINAT MANUAL
if st.session_state.pkg_df is not None and not st.session_state.pkg_df.empty:
    st.divider()
    st.subheader("Koreksi Koordinat (Opsional)")
    
    pkg_df = st.session_state.pkg_df
    
    if st.session_state._last_geocoded:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("Isi Otomatis", use_container_width=True):
                for item in st.session_state._last_geocoded:
                    idx = item.get("_original_idx")
                    if idx is not None and item.get("lat"):
                        st.session_state.manual_coords[idx] = {"lat": item["lat"], "lng": item["lng"]}
                st.success(f"Koordinat telah diisi otomatis")
                st.rerun()
    
    with st.expander("Panel Input Manual", expanded=False):
        for i, row in pkg_df.iterrows():
            inv = row.get("Invoice NO", f"#{i + 1}")
            addr = str(row.get("Shipping Address", ""))[:60]
            
            geocoded_item = None
            if st.session_state._last_geocoded:
                for item in st.session_state._last_geocoded:
                    if item.get("_original_idx") == i:
                        geocoded_item = item
                        break
            
            col1, col2, col3, col4 = st.columns([2.5, 1.2, 1.2, 1])
            
            with col1:
                st.markdown(f"**{inv}**<br><span style='font-size:10px;color:#666'>{addr}</span>", unsafe_allow_html=True)
            
            saved = st.session_state.manual_coords.get(i, {})
            default_lat = saved.get("lat", geocoded_item.get("lat", 0.0) if geocoded_item else 0.0)
            default_lng = saved.get("lng", geocoded_item.get("lng", 0.0) if geocoded_item else 0.0)
            
            with col2:
                nl = st.number_input("Latitude", value=float(default_lat), format="%.6f", 
                                     key=f"mlat_{i}", label_visibility="collapsed")
            with col3:
                ng = st.number_input("Longitude", value=float(default_lng), format="%.6f", 
                                     key=f"mlng_{i}", label_visibility="collapsed")
            with col4:
                if nl != 0.0 and ng != 0.0:
                    if st.button("Simpan", key=f"save_{i}"):
                        st.session_state.manual_coords[i] = {"lat": nl, "lng": ng}
            
            if nl != 0.0 and ng != 0.0 and (saved.get("lat") != nl or saved.get("lng") != ng):
                st.session_state.manual_coords[i] = {"lat": nl, "lng": ng}

# 3. HITUNG RUTE
st.divider()
st.subheader("Hitung Rute Optimal")
run = st.button("Hitung Rute", type="primary", use_container_width=True)

if run:
    if st.session_state.pkg_df is None:
        st.error("Silakan upload dan pilih order terlebih dahulu.")
        st.stop()
    
    pkg_list = [{**p, "_idx": i, "_original_idx": i} for i, p in enumerate(st.session_state.pkg_df.to_dict("records")) 
                if str(p.get("Shipping Address", "")).strip().lower() not in ("", "-", "nan")]
    if not pkg_list:
        st.error("Tidak ada alamat valid untuk diproses.")
        st.stop()
    
    bar = st.progress(0, text="Memproses alamat...")
    geocoded, failed = [], []
    api_key = _LOCATIONIQ_API_KEY
    
    for i, pkg in enumerate(pkg_list):
        raw = str(pkg.get("Shipping Address", ""))
        bar.progress((i + 1) / len(pkg_list), text=f"[{i + 1}/{len(pkg_list)}] {raw[:40]}...")
        idx = pkg.get("_idx", i)
        
        if idx in st.session_state.manual_coords and st.session_state.manual_coords[idx].get("lat", 0) != 0:
            lat = st.session_state.manual_coords[idx]["lat"]
            lng = st.session_state.manual_coords[idx]["lng"]
            src, akr = "Manual", "tinggi"
        else:
            lat, lng, src, akr = _geocode(raw, api_key=api_key)
        
        if lat is None or lat == 0:
            failed.append({"Invoice NO": pkg.get("Invoice NO", "-"), "Alamat": raw})
        else:
            out = {k: v for k, v in pkg.items() if k not in ["_idx", "_original_idx"]}
            out["_original_idx"] = pkg.get("_original_idx", i)
            geocoded.append({**out, "lat": lat, "lng": lng, "geocode_sumber": src, "akurasi": akr})
    
    bar.empty()
    st.session_state._last_geocoded = geocoded
    
    if failed:
        with st.expander(f"Alamat yang tidak dapat diproses ({len(failed)})", expanded=False):
            for f in failed[:5]:
                st.caption(f"- {f['Invoice NO']}: {f['Alamat'][:50]}...")
    
    paket_ok = [p for p in geocoded if p.get("akurasi") != "gagal" and p.get("lat")]
    if not paket_ok:
        st.error("Semua alamat gagal diproses.")
        st.stop()
    
    methods = {}
    for p in geocoded:
        methods[p["geocode_sumber"]] = methods.get(p["geocode_sumber"], 0) + 1
    st.info(f"{len(geocoded)} alamat berhasil diproses")
    
    val = _validate_geocoding_results(geocoded)
    if val["warning"]:
        st.warning(val["warning"])
    
    b = cabang_aktif
    st.info("Menghitung rute optimal...")
    
    route, total_km, total_min, total_sec = _nn_tsp_with_duration(b["lat"], b["lng"], paket_ok)
    
    st.success(f"Rute selesai: {len(route)} paket | {total_km:.1f} km | Estimasi waktu: {_format_duration(total_sec)}")
    
    st.session_state.hasil = {
        "branch": b, 
        "route": route, 
        "total_km": total_km, 
        "total_min": total_min,
        "total_sec": total_sec,
        "total_paket": len(route), 
        "total_nilai": sum(p.get("Total Amount", 0) for p in route),
    }

# 4. HASIL
if st.session_state.hasil:
    hasil = st.session_state.hasil
    b = hasil["branch"]
    route = hasil["route"]
    
    st.divider()
    st.subheader("Hasil Rute Pengiriman")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Paket", hasil["total_paket"])
    col2.metric("Total Jarak", f"{hasil['total_km']:.1f} km")
    col3.metric("Estimasi Waktu", _format_duration(hasil["total_sec"]))
    col4.metric("Total Nilai", _format_currency(hasil["total_nilai"]))
    
    if hasil["total_paket"] > 0:
        avg_time_per_pkg = hasil["total_sec"] / hasil["total_paket"]
        st.caption(f"Rata-rata: {_format_duration(avg_time_per_pkg)} per paket")
    
    tab_rute, tab_peta = st.tabs(["Urutan Pengiriman", "Peta Rute"])
    
    with tab_rute:
        rows = []
        cumulative_time = 0
        cumulative_km = 0
        
        for i, pkg in enumerate(route, 1):
            cumulative_time += pkg.get("durasi_detik", 0)
            cumulative_km += pkg.get("jarak_jalan_km", 0)
            
            rows.append({
                "No": i,
                "Invoice": pkg.get("Invoice NO", "-"),
                "Penerima": pkg.get("Recipient Name", "-"),
                "Barang": str(pkg.get("Items Name", "-"))[:35],
                "Jarak(km)": pkg["jarak_jalan_km"],
                "Durasi": pkg.get("durasi_text", "-"),
                "Kumulatif Waktu": _format_duration(cumulative_time),
                "Alamat": str(pkg.get("Shipping Address", "-"))[:50]
            })
        
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=450)
        
        csv_data = pd.DataFrame([{
            "No": i,
            "Invoice NO": pkg.get("Invoice NO", "-"),
            "Recipient Name": pkg.get("Recipient Name", "-"),
            "Items Name": pkg.get("Items Name", "-"),
            "Total Amount": pkg.get("Total Amount", 0),
            "Latitude": pkg["lat"],
            "Longitude": pkg["lng"],
            "Jarak_Jalan_km": pkg["jarak_jalan_km"],
            "Durasi_menit": pkg.get("durasi_menit", 0),
            "Durasi_text": pkg.get("durasi_text", "-")
        } for i, pkg in enumerate(route, 1)]).to_csv(index=False).encode("utf-8")
        
        st.download_button("Download Hasil (.csv)", csv_data, f"rute_{b['kode']}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv")
    
    with tab_peta:
        st.caption("Garis menunjukkan rute jalan. Angka menunjukkan urutan pengiriman.")
        with st.spinner("Memuat peta..."):
            st_folium(_buat_peta(b, route), use_container_width=True, height=600)