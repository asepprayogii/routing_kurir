"""
Kurir Toko — Route Optimizer v18 (Updated with Manual Input)
============================================================
Multi-Vehicle Routing: Motor vs Mobil
Fitur: GraphHopper API + Segment Colors + Fallback Cerdas + Input Manual

LOGIKA KLASIFIKASI KENDARAAN
-----------------------------
Motor: 60x40x40 cm, 20 kg, 3 item → kapasitas fisik motor delivery standar
Mobil: Jika salah satu batas terlampaui → butuh kapasitas lebih besar

ROUTING ENGINE
--------------
Primary: GraphHopper (motorcycle/car) - lebih akurat untuk Indonesia
Fallback: ORS → OSRM → Haversine estimasi

SEGMENT COLORS
--------------
Setiap leg rute (gudang→paket1, paket1→paket2, dst) punya warna berbeda
untuk memudahkan visualisasi urutan dan identifikasi segment.
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
from typing import List, Tuple, Optional

# ══════════════════════════════════════════════════════════════════
# KONFIGURASI API & INTERNAL
# ══════════════════════════════════════════════════════════════════

# 🎯 GRAPHHOPPER API KEY (User Provided)
_GRAPHHOPPER_API_KEY = "fe0684a1-db7e-4808-bf88-b0da9795a51f"
_GRAPHHOPPER_BASE = "https://graphhopper.com/api/1"

# Fallback APIs
_ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImRjYTUxM2YwYWU1NzQwMDViNTU4M2VmZDA4NWRlNzFjIiwiaCI6Im11cm11cjY0In0="
_ORS_BASE = "https://api.openrouteservice.org/v2"
_OSRM_BASE = "http://router.project-osrm.org/route/v1"
_LOCATIONIQ_API_KEY = "pk.99cc6a53008f844d73e5fd3a998fb888"
_LOCATIONIQ_BASE = "https://us1.locationiq.com/v1"

_GEOCODE_DELAY = 0.3
_KURIR_TOKO_KEYWORDS = ["kurir toko", "kurirtoko", "kurir_toko"]

# ══════════════════════════════════════════════════════════════════
# KONFIGURASI KENDARAAN
# ══════════════════════════════════════════════════════════════════

VEHICLE_CONFIG = {
    "MOTOR": {
        "max_panjang": 60, "max_lebar": 40, "max_tinggi": 40,
        "max_berat": 20, "max_qty": 3,
        "max_radius": 20, "kecepatan": 40, "cost_per_km": 1_000,
        "gh_profile": "motorcycle",  # GraphHopper profile
        "ors_profile": "cycling-regular",
        "osrm_profile": "bicycle",
        "hex": "#27ae60", "hex_light": "#d4edda", "label": "Motor", "icon": "🛵",
    },
    "MOBIL": {
        "max_panjang": 9_999, "max_lebar": 9_999, "max_tinggi": 9_999,
        "max_berat": 500, "max_qty": 9_999,
        "max_radius": 20, "kecepatan": 35, "cost_per_km": 2_500,
        "gh_profile": "car",
        "ors_profile": "driving-car",
        "osrm_profile": "driving",
        "hex": "#2980b9", "hex_light": "#cfe2ff", "label": "Mobil", "icon": "🚐",
    },
}

# ══════════════════════════════════════════════════════════════════
# PALET WARNA UNTUK SEGMENT RUTE
# ══════════════════════════════════════════════════════════════════

# 12 warna berbeda untuk segment rute (cukup untuk ~12 stop)
_SEGMENT_COLORS = [
    "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c", "#3498db",
    "#9b59b6", "#34495e", "#16a085", "#27ae60", "#2980b9", "#8e44ad",
]

def _get_segment_color(segment_index: int, base_color: str) -> str:
    if segment_index < len(_SEGMENT_COLORS):
        return _SEGMENT_COLORS[segment_index]
    return base_color


# ══════════════════════════════════════════════════════════════════
# DATA CABANG / GUDANG
# ══════════════════════════════════════════════════════════════════

_BRANCHES_DEFAULT = [
    {"kode": "SUB", "nama": "Surabaya", "lat": -7.317566, "lng": 112.764234},
    {"kode": "JKT", "nama": "Jakarta", "lat": -6.208800, "lng": 106.845600},
    {"kode": "MLG", "nama": "Malang", "lat": -7.979700, "lng": 112.630400},
    {"kode": "SMG", "nama": "Semarang", "lat": -6.966700, "lng": 110.416700},
    {"kode": "JOG", "nama": "Yogyakarta", "lat": -7.795600, "lng": 110.369500},
    {"kode": "BLI", "nama": "Bali", "lat": -8.340500, "lng": 115.092000},
]

_BRANCH_COLORS = {"SUB": "#C0392B", "JKT": "#1A5276", "MLG": "#1E8449",
                  "SMG": "#D35400", "JOG": "#6C3483", "BLI": "#117A65"}
_FOLIUM_COLORS = {"SUB": "red", "JKT": "blue", "MLG": "green",
                  "SMG": "orange", "JOG": "purple", "BLI": "cadetblue"}

# ══════════════════════════════════════════════════════════════════
# FALLBACK KOORDINAT WILAYAH
# ══════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════
# ROUTING: GRAPHHOPPER (PRIMARY)
# ══════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=3600)
def _graphhopper_route(coords: Tuple[Tuple[float, float], ...], profile: str = "car") -> Optional[dict]:
    if len(coords) < 2:
        return None
    
    points_list = [f"{lat},{lng}" for lat, lng in coords]
    url = f"{_GRAPHHOPPER_BASE}/route"
    
    params = {
        "key": _GRAPHHOPPER_API_KEY,
        "profile": profile,
        "point": points_list,
        "instructions": False,
        "points_encoded": False,
        "locale": "id",
        "calc_points": True,
    }
    
    try:
        r = requests.get(url, params=params, timeout=20)
        
        if r.status_code == 429:
            print(f"[GraphHopper] Rate limited. Waiting...")
            time.sleep(2)
            return None
            
        if r.status_code == 200:
            data = r.json()
            if data.get("paths"):
                path = data["paths"][0]
                distance_km = round(path["distance"] / 1000, 2)
                duration_sec = path["time"] / 1000
                
                raw_coords = path.get("points", {}).get("coordinates", [])
                folium_geom = [[c[1], c[0]] for c in raw_coords] if raw_coords else []
                
                return {
                    "distance_km": distance_km,
                    "duration_min": round(duration_sec / 60, 1),
                    "duration_seconds": duration_sec,
                    "geometry": folium_geom,
                    "status": "graphhopper",
                    "provider": "GraphHopper"
                }
        elif r.status_code == 400:
            print(f"[GraphHopper] Bad Request: {r.text[:200]}")
    except requests.exceptions.Timeout:
        print("[GraphHopper] Timeout")
    except requests.exceptions.RequestException as e:
        print(f"[GraphHopper] Error: {e}")
    except Exception as e:
        print(f"[GraphHopper] Parse Error: {e}")
        
    return None


# ══════════════════════════════════════════════════════════════════
# ROUTING: FALLBACK (ORS & OSRM)
# ══════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=3600)
def _ors_route(coords: tuple, profile: str = "driving-car") -> Optional[dict]:
    if len(coords) < 2:
        return None
    headers = {
        "Accept": "application/json",
        "Authorization": _ORS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "coordinates": [[lng, lat] for lat, lng in coords],
        "instructions": False, "geometry": True, "format": "json", "units": "km",
    }
    try:
        url = f"{_ORS_BASE}/directions/{profile}"
        r = requests.post(url, json=payload, headers=headers, timeout=20)
        if r.status_code == 200:
            feat = r.json().get("features", [])
            if feat:
                route = feat[0]
                geom = [[c[1], c[0]] for c in route["geometry"]["coordinates"]]
                summary = route["properties"]["summary"]
                return {
                    "distance_km": round(summary["distance"], 2),
                    "duration_min": round(summary["duration"] / 60, 1),
                    "duration_seconds": summary["duration"],
                    "geometry": geom,
                    "status": "ors",
                    "provider": "OpenRouteService"
                }
    except Exception:
        pass
    return None


@st.cache_data(show_spinner=False, ttl=3600)
def _osrm_route(coords: tuple, profile: str = "driving") -> Optional[dict]:
    if len(coords) < 2:
        return None
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)
    try:
        url = f"{_OSRM_BASE}/{profile}/{coord_str}"
        r = requests.get(url, params={"overview": "full", "geometries": "polyline"}, timeout=15)
        data = r.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            decoded = polyline_lib.decode(route.get("geometry", "")) if route.get("geometry") else []
            return {
                "distance_km": round(route["distance"] / 1000, 2),
                "duration_min": round(route["duration"] / 60, 1),
                "duration_seconds": route["duration"],
                "geometry": decoded,
                "status": "osrm",
                "provider": "OSRM"
            }
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════
# SMART ROUTING WRAPPER + RATE LIMITING
# ══════════════════════════════════════════════════════════════════

def _safe_delay(min_interval: float = 1.1):
    now = time.time()
    last = st.session_state.get("gh_last_call", 0)
    elapsed = now - last
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed + 0.05)
    st.session_state.gh_last_call = time.time()


def _get_route(coords: tuple, vehicle_type: str = "MOBIL") -> dict:
    _safe_delay(1.1)
    
    vc = VEHICLE_CONFIG.get(vehicle_type, VEHICLE_CONFIG["MOBIL"])
    gh_profile = vc.get("gh_profile", "car")
    
    result = _graphhopper_route(coords, gh_profile)
    if result and result.get("geometry"):
        return result
    
    ors_prof = vc.get("ors_profile", "driving-car")
    result = _ors_route(coords, ors_prof)
    if result and result.get("geometry"):
        return result
    
    osrm_prof = vc.get("osrm_profile", "driving")
    result = _osrm_route(coords, osrm_prof)
    if result and result.get("geometry"):
        return result
    
    if len(coords) == 2:
        d = _haversine(coords[0][0], coords[0][1], coords[1][0], coords[1][1])
        factor = 1.15 if vehicle_type == "MOTOR" else 1.25
        vc_speed = vc["kecepatan"]
        return {
            "distance_km": round(d * factor, 2),
            "duration_min": round((d * factor) / (vc_speed / 60), 1),
            "duration_seconds": (d * factor) * 3600 / vc_speed,
            "geometry": [list(coords[0]), list(coords[1])],
            "status": "haversine_fallback",
            "provider": "Estimasi"
        }
    
    return {"distance_km": 0, "duration_min": 0, "duration_seconds": 0, "geometry": [], "status": "failed", "provider": "None"}


# ══════════════════════════════════════════════════════════════════
# GEOCODING
# ══════════════════════════════════════════════════════════════════

def _extract_coords(text: str):
    t = str(text)
    m = re.search(r"\(?(-[1-9]\d?\.\d{3,})\s*,\s*(1[0-2]\d\.\d{3,})\)?", t)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if -11 <= lat <= 6 and 94 <= lng <= 141:
            return lat, lng
    return None, None


@st.cache_data(show_spinner=False, ttl=7200)
def _locationiq(query: str):
    try:
        params = {"key": _LOCATIONIQ_API_KEY, "q": query, "format": "json",
                  "limit": 1, "countrycodes": "id", "accept-language": "id"}
        r = requests.get(f"{_LOCATIONIQ_BASE}/search.php", params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
                if -11 <= lat <= 6 and 94 <= lng <= 141:
                    return lat, lng
    except Exception:
        pass
    return None, None


@st.cache_data(show_spinner=False)
def _nominatim(query: str):
    try:
        loc = Nominatim(user_agent="kurir_toko_v18", timeout=10).geocode(query)
        if loc:
            return loc.latitude, loc.longitude
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    return None, None


@st.cache_data(show_spinner=False)
def _photon(query: str):
    try:
        r = requests.get("https://photon.komoot.io/api/",
                         params={"q": query, "limit": 1, "lang": "id"}, timeout=10)
        feats = r.json().get("features", [])
        if feats:
            c = feats[0]["geometry"]["coordinates"]
            return c[1], c[0]
    except Exception:
        pass
    return None, None


def _region_fallback(raw: str):
    text = raw.lower()
    for key in sorted(_REGION_FALLBACK, key=len, reverse=True):
        if key in text:
            return _REGION_FALLBACK[key]
    return None, None


_SINGKATAN = {
    r"\bJl\.?\b": "Jalan", r"\bJln\.?\b": "Jalan",
    r"\bNo\.?\s*": "Nomor ", r"\bKec\.?\b": "Kecamatan",
    r"\bKel\.?\b": "Kelurahan", r"\bKab\.?\b": "Kabupaten",
    r"\bRT\.?\s*\d+\s*[/,]?\s*RW\.?\s*\d+\b": "",
    r"\bRT\.?\s*\d+\b": "", r"\bRW\.?\s*\d+\b": "",
    r"\bGg\.?\b": "Gang", r"\bPerum\.?\b": "Perumahan",
}

def _clean_address(raw: str) -> str:
    addr = raw
    for pat, rep in _SINGKATAN.items():
        addr = re.sub(pat, rep, addr, flags=re.IGNORECASE)
    addr = re.sub(r"\bIndonesia\b", "", addr, flags=re.IGNORECASE)
    addr = re.sub(r"\b\d{5}\b", "", addr)
    addr = re.sub(r"\s{2,}", " ", addr).strip()
    parts = [p.strip() for p in addr.split(",") if len(p.strip()) > 2]
    seen, unique = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower()); unique.append(p)
    return ", ".join(unique[:6])


def _geocode(raw: str) -> tuple:
    lat, lng = _extract_coords(raw)
    if lat:
        return lat, lng, "Koordinat langsung", "tinggi"
    cleaned = _clean_address(raw)
    lat, lng = _locationiq(cleaned + ", Indonesia")
    if lat:
        return lat, lng, "LocationIQ", "tinggi"
    time.sleep(0.15)
    lat, lng = _nominatim(cleaned + ", Indonesia")
    if lat:
        return lat, lng, "Nominatim", "tinggi"
    time.sleep(_GEOCODE_DELAY)
    lat, lng = _photon(cleaned + " Indonesia")
    if lat:
        return lat, lng, "Photon", "tinggi"
    time.sleep(0.2)
    lat, lng = _region_fallback(raw)
    if lat:
        return lat, lng, "Estimasi wilayah", "sedang"
    return None, None, "Gagal", "gagal"


# ══════════════════════════════════════════════════════════════════
# HELPER UMUM
# ══════════════════════════════════════════════════════════════════

def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lng2 - lng1)
    a = (math.sin(dl / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dg / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fmt_dur(seconds: float) -> str:
    if seconds <= 0:
        return "0 mnt"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h} jam {m} mnt" if h > 0 else f"{m} mnt"


def _fmt_rp(val) -> str:
    try:
        return f"Rp {int(float(val)):,}".replace(",", ".")
    except Exception:
        return "-"


def _is_kurir_toko(val) -> bool:
    if pd.isna(val) or str(val).strip() == "":
        return False
    v = str(val).lower().replace(" ", "").replace("_", "")
    return any(kw.replace(" ", "") in v for kw in _KURIR_TOKO_KEYWORDS)


# ══════════════════════════════════════════════════════════════════
# BACA FILE EXCEL / CSV
# ══════════════════════════════════════════════════════════════════

def _load_excel(uploaded_file):
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)

        df.columns = [c.strip() for c in df.columns]
        cl = {c.lower(): c for c in df.columns}

        def gc(*names):
            for n in names:
                if n.lower() in cl:
                    return cl[n.lower()]
            return None

        col_addr = gc("Shipping Address", "alamat", "address")
        if not col_addr:
            return None, "Kolom 'Shipping Address' tidak ditemukan."

        r = pd.DataFrame()
        
        r["SO Number"] = df[gc("SO Number", "Invoice NO", "invoice_no")].fillna("-").astype(str) if gc("SO Number", "Invoice NO", "invoice_no") else "-"
        r["Order Date"] = df[gc("Order Date", "order_date")].fillna("-").astype(str) if gc("Order Date", "order_date") else "-"
        r["Channel"] = df[gc("Channel", "channel")].fillna("-").astype(str) if gc("Channel", "channel") else "-"
        r["Store"] = df[gc("Store", "store")].fillna("-").astype(str) if gc("Store", "store") else "-"
        r["Invoice NO"] = df[gc("Invoice NO", "invoice_no")].fillna("-").astype(str) if gc("Invoice NO", "invoice_no") else "-"
        r["Payment Status"] = df[gc("Payment Status", "payment_status")].fillna("-").astype(str) if gc("Payment Status", "payment_status") else "-"
        r["Fulfillment Status"] = df[gc("Fulfillment Status", "fulfillment_status")].fillna("-").astype(str) if gc("Fulfillment Status", "fulfillment_status") else "-"
        r["Payment Type"] = df[gc("Payment Type", "payment_type")].fillna("-").astype(str) if gc("Payment Type", "payment_type") else "-"
        r["Payment Date"] = df[gc("Payment Date", "payment_date")].fillna("-").astype(str) if gc("Payment Date", "payment_date") else "-"
        r["Printed Date"] = df[gc("Printed Date", "printed_date")].fillna("-").astype(str) if gc("Printed Date", "printed_date") else "-"
        r["Ready to Pack Date"] = df[gc("Ready to Pack Date", "ready_to_pack_date")].fillna("-").astype(str) if gc("Ready to Pack Date", "ready_to_pack_date") else "-"
        r["Ready to Ship Date"] = df[gc("Ready to Ship Date", "ready_to_ship_date")].fillna("-").astype(str) if gc("Ready to Ship Date", "ready_to_ship_date") else "-"
        r["Marketplace RTS Date"] = df[gc("Marketplace Ready to Ship Date", "marketplace_rts_date")].fillna("-").astype(str) if gc("Marketplace Ready to Ship Date", "marketplace_rts_date") else "-"
        r["Handover Date"] = df[gc("Handover Date", "handover_date")].fillna("-").astype(str) if gc("Handover Date", "handover_date") else "-"
        r["Shipped Date"] = df[gc("Shipped Date", "shipped_date")].fillna("-").astype(str) if gc("Shipped Date", "shipped_date") else "-"
        r["Delivered Date"] = df[gc("Delivered Date", "delivered_date")].fillna("-").astype(str) if gc("Delivered Date", "delivered_date") else "-"
        r["Completed Date"] = df[gc("Completed Date", "completed_date")].fillna("-").astype(str) if gc("Completed Date", "completed_date") else "-"
        r["Cancelled Date"] = df[gc("Cancelled Date", "cancelled_date")].fillna("-").astype(str) if gc("Cancelled Date", "cancelled_date") else "-"
        r["Return Date"] = df[gc("Return Date", "return_date")].fillna("-").astype(str) if gc("Return Date", "return_date") else "-"
        r["Unpacking Date"] = df[gc("Unpacking Date", "unpacking_date")].fillna("-").astype(str) if gc("Unpacking Date", "unpacking_date") else "-"
        r["Delete Nota Date"] = df[gc("Delete Nota Date", "delete_nota_date")].fillna("-").astype(str) if gc("Delete Nota Date", "delete_nota_date") else "-"
        r["Cancelled Reason"] = df[gc("Cancelled Reason", "cancelled_reason")].fillna("-").astype(str) if gc("Cancelled Reason", "cancelled_reason") else "-"
        r["Expiry Date"] = df[gc("Expiry Date", "expiry_date")].fillna("-").astype(str) if gc("Expiry Date", "expiry_date") else "-"
        
        r["Shipping Courier"] = df[gc("Shipping Courier", "kurir")].fillna("-").astype(str) if gc("Shipping Courier", "kurir") else "-"
        r["AWB"] = df[gc("AWB", "awb", "resi")].fillna("-").astype(str) if gc("AWB", "awb", "resi") else "-"
        r["Customer Name"] = df[gc("Customer Name", "recipient_name", "penerima")].fillna("-").astype(str) if gc("Customer Name", "recipient_name", "penerima") else "-"
        r["Recipient Name"] = r["Customer Name"]
        r["Recipient Phone"] = df[gc("Recipient Phone", "recipient_phone", "phone")].fillna("-").astype(str) if gc("Recipient Phone", "recipient_phone", "phone") else "-"
        r["Shipping Address"] = df[col_addr].fillna("").astype(str)
        r["Additional Info"] = df[gc("Additional Info", "additional_info", "notes")].fillna("-").astype(str) if gc("Additional Info", "additional_info", "notes") else "-"
        r["No Accurate"] = df[gc("No Accurate", "no_accurate")].fillna("-").astype(str) if gc("No Accurate", "no_accurate") else "-"
        
        r["Items SKU"] = df[gc("Items SKU", "items_sku", "sku")].fillna("-").astype(str) if gc("Items SKU", "items_sku", "sku") else "-"
        r["Items Name"] = df[gc("Items Name", "items_name", "nama_barang")].fillna("-").astype(str) if gc("Items Name", "items_name", "nama_barang") else "-"
        r["Warehouse"] = df[gc("Warehouse", "warehouse")].fillna("-").astype(str) if gc("Warehouse", "warehouse") else "-"
        r["Warehouse Code"] = df[gc("Warehouse Code", "warehouse_code")].fillna("-").astype(str) if gc("Warehouse Code", "warehouse_code") else "-"
        r["Items Quantity"] = pd.to_numeric(df[gc("Items Quantity", "items_quantity", "qty")], errors="coerce").fillna(1).astype(int) if gc("Items Quantity", "items_quantity", "qty") else 1
        r["Items Price"] = pd.to_numeric(df[gc("Items Price", "items_price", "harga")], errors="coerce").fillna(0) if gc("Items Price", "items_price", "harga") else 0
        r["Items Discount Price"] = pd.to_numeric(df[gc("Items Discount Price", "items_discount_price")], errors="coerce").fillna(0) if gc("Items Discount Price", "items_discount_price") else 0
        r["Subtotal"] = pd.to_numeric(df[gc("Subtotal", "subtotal")], errors="coerce").fillna(0) if gc("Subtotal", "subtotal") else 0
        r["Original Shipping"] = pd.to_numeric(df[gc("Original Shipping Price", "original_shipping")], errors="coerce").fillna(0) if gc("Original Shipping Price", "original_shipping") else 0
        r["Buyer Paid Shipping"] = pd.to_numeric(df[gc("Buyer Paid Shipping Price", "buyer_shipping")], errors="coerce").fillna(0) if gc("Buyer Paid Shipping Price", "buyer_shipping") else 0
        r["Shipping Rebate"] = pd.to_numeric(df[gc("Shipping Rebate", "shipping_rebate")], errors="coerce").fillna(0) if gc("Shipping Rebate", "shipping_rebate") else 0
        r["Seller Discount"] = pd.to_numeric(df[gc("Seller Discount", "seller_discount")], errors="coerce").fillna(0) if gc("Seller Discount", "seller_discount") else 0
        r["Rebate"] = pd.to_numeric(df[gc("Rebate", "rebate")], errors="coerce").fillna(0) if gc("Rebate", "rebate") else 0
        r["Voucher Seller"] = pd.to_numeric(df[gc("Voucher Seller", "voucher_seller")], errors="coerce").fillna(0) if gc("Voucher Seller", "voucher_seller") else 0
        r["Platform Service Fee"] = pd.to_numeric(df[gc("Platform Service Fee", "platform_service_fee")], errors="coerce").fillna(0) if gc("Platform Service Fee", "platform_service_fee") else 0
        r["Platform Commission"] = pd.to_numeric(df[gc("Platform Commission Fee", "platform_commission")], errors="coerce").fillna(0) if gc("Platform Commission Fee", "platform_commission") else 0
        r["Total Amount"] = pd.to_numeric(df[gc("Total Amount", "total_amount", "total")], errors="coerce").fillna(0) if gc("Total Amount", "total_amount", "total") else 0
        
        def _num(col_name, default=0.0):
            col = gc(col_name, col_name.lower(), col_name.replace(" (cm)", "").replace(" (kg)", ""))
            if col:
                return pd.to_numeric(df[col], errors="coerce").fillna(default)
            return pd.Series([default] * len(df))

        r["Panjang"] = _num("Panjang (cm)")
        r["Lebar"] = _num("Lebar (cm)")
        r["Tinggi"] = _num("Tinggi (cm)")
        r["Berat"] = _num("Berat (kg)")

        col_kend = gc("Kendaraan", "kendaraan", "Vehicle", "vehicle")
        r["Kendaraan_Override"] = df[col_kend].fillna("").astype(str).str.upper().str.strip() if col_kend else ""

        r = r[~r["Shipping Address"].str.strip().str.lower().isin(["", "indonesia", "-", "nan"])].reset_index(drop=True)
        n_kt = r["Shipping Courier"].apply(_is_kurir_toko).sum()
        return r, f"Berhasil memuat {len(r)} order. {n_kt} Kurir Toko, {len(r) - n_kt} kurir lain."

    except Exception as e:
        return None, f"Gagal membaca file: {e}"


# ══════════════════════════════════════════════════════════════════
# KLASIFIKASI KENDARAAN
# ══════════════════════════════════════════════════════════════════

def _classify(panjang, lebar, tinggi, berat, qty, override="") -> str:
    if override in ("MOTOR", "MOBIL"):
        return override
    mc = VEHICLE_CONFIG["MOTOR"]
    if panjang == 0 and lebar == 0 and tinggi == 0 and berat == 0:
        return "MOTOR"
    is_motor = (
        panjang <= mc["max_panjang"] and
        lebar <= mc["max_lebar"] and
        tinggi <= mc["max_tinggi"] and
        berat <= mc["max_berat"] and
        qty <= mc["max_qty"]
    )
    return "MOTOR" if is_motor else "MOBIL"


# ══════════════════════════════════════════════════════════════════
# FILTER JARAK & PEMBAGIAN MOTOR / MOBIL
# ══════════════════════════════════════════════════════════════════

def _split_by_vehicle(geocoded, wlat, wlng):
    motor, mobil, excluded = [], [], []
    for pkg in geocoded:
        if not (pkg.get("lat") and pkg.get("lng")):
            continue
        vtype = _classify(
            float(pkg.get("Panjang", 0)),
            float(pkg.get("Lebar", 0)),
            float(pkg.get("Tinggi", 0)),
            float(pkg.get("Berat", 0)),
            int(pkg.get("Items Quantity", 1)),
            str(pkg.get("Kendaraan_Override", "")),
        )
        dist_km = _haversine(wlat, wlng, pkg["lat"], pkg["lng"])
        max_r = VEHICLE_CONFIG[vtype]["max_radius"]
        pkg_copy = {**pkg, "Vehicle Type": vtype, "Jarak_km": round(dist_km, 2)}
        if dist_km <= max_r:
            (motor if vtype == "MOTOR" else mobil).append(pkg_copy)
        else:
            excluded.append({
                "Invoice": pkg.get("Invoice NO", "-"),
                "Penerima": pkg.get("Recipient Name", "-"),
                "Barang": str(pkg.get("Items Name", "-"))[:40],
                "Alamat": pkg.get("Shipping Address", "")[:60],
                "Jarak_km": round(dist_km, 2),
                "Max_Radius": max_r,
                "Vehicle Type": vtype,
                "lat": pkg["lat"], "lng": pkg["lng"],
            })
    return motor, mobil, excluded


# ══════════════════════════════════════════════════════════════════
# ALGORITMA RUTE
# ══════════════════════════════════════════════════════════════════

def _cluster(pkgs, n=None):
    if len(pkgs) <= 3:
        return [pkgs]
    n = n or max(2, min(len(pkgs) // 6, 8))
    n = min(n, len(pkgs))
    coords = [(p["lat"], p["lng"]) for p in pkgs]
    centers = [coords[0]]
    for _ in range(n - 1):
        best_c, best_d = None, -1
        for c in coords:
            d = min(_haversine(c[0], c[1], ce[0], ce[1]) for ce in centers)
            if d > best_d:
                best_d, best_c = d, c
        if best_c:
            centers.append(best_c)
    for _ in range(30):
        assign = [min(range(n), key=lambda ci: _haversine(c[0], c[1], centers[ci][0], centers[ci][1])) for c in coords]
        new_c = []
        for ci in range(n):
            pts = [coords[i] for i, a in enumerate(assign) if a == ci]
            if pts:
                new_c.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
            else:
                new_c.append(centers[ci])
        if new_c == centers:
            break
        centers = new_c
    clusters = [[] for _ in range(n)]
    for i, pkg in enumerate(pkgs):
        clusters[assign[i]].append(pkg)
    return [c for c in clusters if c]


def _order_clusters(slat, slng, clusters):
    remaining = list(range(len(clusters)))
    ordered, clat, clng = [], slat, slng
    while remaining:
        def centroid(cl):
            return (sum(p["lat"] for p in cl) / len(cl), sum(p["lng"] for p in cl) / len(cl))
        best_i, best_d = None, float("inf")
        for i in remaining:
            la, lo = centroid(clusters[i])
            d = _haversine(clat, clng, la, lo)
            if d < best_d:
                best_d, best_i = d, i
        ordered.append(clusters[best_i])
        clat, clng = centroid(clusters[best_i])
        remaining.remove(best_i)
    return ordered


def _nn_segment(slat, slng, pkgs, hlat, hlng, is_last, vehicle_type="MOBIL"):
    remaining = pkgs.copy()
    route, total_km, total_sec = [], 0.0, 0.0
    clat, clng = slat, slng

    while remaining:
        if is_last and 1 < len(remaining) <= 3:
            best_i, best_cost = 0, float("inf")
            for i, p in enumerate(remaining):
                cost = (_haversine(clat, clng, p["lat"], p["lng"]) * 1.3
                        + 0.8 * _haversine(p["lat"], p["lng"], hlat, hlng) * 1.3)
                if cost < best_cost:
                    best_cost, best_i = cost, i
        else:
            best_i = min(range(len(remaining)),
                         key=lambda i: _haversine(clat, clng, remaining[i]["lat"], remaining[i]["lng"]))

        chosen = remaining.pop(best_i).copy()
        seg = _get_route(((clat, clng), (chosen["lat"], chosen["lng"])), vehicle_type)
        d_km = seg["distance_km"] if seg["distance_km"] > 0 else _haversine(clat, clng, chosen["lat"], chosen["lng"]) * 1.3
        d_sec = seg["duration_seconds"] if seg["duration_seconds"] > 0 else d_km * 90

        chosen.update({
            "jarak_lurus_km": round(_haversine(clat, clng, chosen["lat"], chosen["lng"]), 2),
            "jarak_jalan_km": round(d_km, 2),
            "durasi_detik": d_sec,
            "durasi_menit": round(d_sec / 60, 1),
            "durasi_text": _fmt_dur(d_sec),
        })
        route.append(chosen)
        total_km += d_km
        total_sec += d_sec
        clat, clng = chosen["lat"], chosen["lng"]

    return route, round(total_km, 2), round(total_sec / 60, 1), total_sec


def _compute_route(slat, slng, pkgs, algo="cluster", vehicle_type="MOBIL"):
    if not pkgs:
        return [], 0, 0, 0
    if algo == "cluster" and len(pkgs) > 4:
        clusters = _cluster(pkgs)
        ordered = _order_clusters(slat, slng, clusters)
        full, km, sec = [], 0.0, 0.0
        clat, clng = slat, slng
        for idx, cl in enumerate(ordered):
            seg, km_s, _, sec_s = _nn_segment(clat, clng, cl, slat, slng, idx == len(ordered) - 1, vehicle_type)
            full.extend(seg); km += km_s; sec += sec_s
            if seg:
                clat, clng = seg[-1]["lat"], seg[-1]["lng"]
        return full, round(km, 2), round(sec / 60, 1), sec
    else:
        return _nn_segment(slat, slng, pkgs, slat, slng, True, vehicle_type)


# ══════════════════════════════════════════════════════════════════
# PETA FOLIUM - SEGMENT COLORS + RUTE PULANG YANG BENAR
# ══════════════════════════════════════════════════════════════════

def _build_single_map(branch, route, vehicle_type, excluded=None):
    vc = VEHICLE_CONFIG[vehicle_type]
    base_color = vc["hex"]
    
    if route:
        lats = [branch["lat"]] + [p["lat"] for p in route]
        lngs = [branch["lng"]] + [p["lng"] for p in route]
        center = [sum(lats)/len(lats), sum(lngs)/len(lngs)]
        padding_lat = (max(lats) - min(lats)) * 0.3 + 0.01
        padding_lng = (max(lngs) - min(lngs)) * 0.3 + 0.01
        bounds = [[min(lats) - padding_lat, min(lngs) - padding_lng], 
                  [max(lats) + padding_lat, max(lngs) + padding_lng]]
    else:
        center = [branch["lat"], branch["lng"]]
        bounds = None
    
    m = folium.Map(location=center, zoom_start=13, tiles="CartoDB Positron")
    if bounds:
        m.fit_bounds(bounds, padding=(20, 20))

    folium.Marker(
        [branch["lat"], branch["lng"]],
        tooltip=f"Gudang {branch['nama']}",
        popup=f"<b>Gudang {branch['nama']}</b><br>{branch['lat']:.6f}, {branch['lng']:.6f}",
        icon=folium.Icon(color=_FOLIUM_COLORS.get(branch["kode"], "gray"), icon="home", prefix="fa"),
    ).add_to(m)

    folium.Circle(
        [branch["lat"], branch["lng"]],
        radius=vc["max_radius"] * 1000,
        color=base_color,
        fill=True,
        fillOpacity=0.08,
        weight=2,
        dashArray="6 4",
        tooltip=f"Radius operasional: {vc['max_radius']} km"
    ).add_to(m)

    if route:
        waypoints = [(branch["lat"], branch["lng"])] + [(p["lat"], p["lng"]) for p in route]
        
        for seg_idx in range(len(waypoints) - 1):
            start, end = waypoints[seg_idx], waypoints[seg_idx + 1]
            seg = _get_route((start, end), vehicle_type)
            geom = seg["geometry"] if seg.get("geometry") and len(seg["geometry"]) > 1 else [list(start), list(end)]
            
            seg_color = _get_segment_color(seg_idx, base_color)
            
            if seg_idx == 0:
                tooltip_text = f"Gudang → Paket #{seg_idx+1}"
            elif seg_idx == len(waypoints) - 2:
                tooltip_text = f"Paket #{seg_idx} → Pulang"
            else:
                tooltip_text = f"Paket #{seg_idx} → #{seg_idx+1}"
            
            folium.PolyLine(
                geom, 
                color=seg_color, 
                weight=4, 
                opacity=0.9,
                tooltip=tooltip_text,
                popup=f"Segment {seg_idx+1}: {seg.get('distance_km', 0):.2f} km<br>Provider: {seg.get('provider', 'Estimasi')}"
            ).add_to(m)
        
        if route:
            last = route[-1]
            return_seg = _get_route(((last["lat"], last["lng"]), (branch["lat"], branch["lng"])), vehicle_type)
            return_geom = return_seg["geometry"] if return_seg.get("geometry") and len(return_seg["geometry"]) > 1 else [[last["lat"], last["lng"]], [branch["lat"], branch["lng"]]]
            folium.PolyLine(
                return_geom,
                color=base_color,
                weight=2,
                opacity=0.4,
                dash_array="6 4",
                tooltip=f"Rute pulang ke gudang"
            ).add_to(m)
        
        for idx, pkg in enumerate(route, 1):
            html = (f'<div style="color:white;background:{base_color};border-radius:50%;'
                    f'width:28px;height:28px;display:flex;align-items:center;'
                    f'justify-content:center;font-size:13px;font-weight:bold;'
                    f'border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,.4)">{idx}</div>')
            popup_html = (f"<b>#{idx} - {vc['label']}</b><hr style='margin:5px 0'>"
                         f"<b>Invoice:</b> {pkg.get('Invoice NO','-')}<br>"
                         f"<b>Penerima:</b> {pkg.get('Recipient Name','-')}<br>"
                         f"<b>Barang:</b> {str(pkg.get('Items Name','-'))[:40]}<br>"
                         f"<b>Dimensi:</b> {pkg.get('Panjang',0):.0f}×{pkg.get('Lebar',0):.0f}×{pkg.get('Tinggi',0):.0f} cm<br>"
                         f"<b>Berat:</b> {pkg.get('Berat',0):.1f} kg | <b>Qty:</b> {pkg.get('Items Quantity',1)}<br>"
                         f"<b>Jarak segment:</b> {pkg.get('jarak_jalan_km',0):.1f} km<br>"
                         f"<b>Est. Waktu:</b> {pkg.get('durasi_text','-')}<br>"
                         f"<small style='color:#666'>Provider: {pkg.get('route_provider', 'Estimasi')}</small>")
            folium.Marker([pkg["lat"], pkg["lng"]], popup=folium.Popup(popup_html, max_width=320),
                          tooltip=f"#{idx} - {pkg.get('Recipient Name','-')[:20]}",
                          icon=folium.DivIcon(html=html, icon_size=(28, 28), icon_anchor=(14, 14))).add_to(m)

    if excluded:
        for pkg in excluded:
            if pkg.get("lat") and pkg.get("lng"):
                folium.CircleMarker([pkg["lat"], pkg["lng"]], radius=7, color="#999", fill=True,
                                    fill_color="#bbb", fill_opacity=0.7,
                                    tooltip=f"Diluar radius: {pkg.get('Invoice','-')}",
                                    popup=f"<b>Diluar Jangkauan</b><br>Invoice: {pkg['Invoice']}<br>Jarak: {pkg['Jarak_km']} km").add_to(m)

    legend_html = f"""
    <div style="position:fixed;bottom:15px;left:15px;padding:12px 16px;
                background:white;border:1px solid #ddd;border-radius:8px;
                font-size:11px;z-index:9999;box-shadow:2px 2px 6px rgba(0,0,0,.2)">
      <b>{vc['label']}</b><br><hr style="margin:6px 0">
      <span style="color:{base_color}">&#9679;</span> Rute {vc['label']}<br>
      <span style="color:#e74c3c">&#9679;</span> Segment 1<br>
      <span style="color:#3498db">&#9679;</span> Segment 2+<br>
      <span style="color:#999">&#9679;</span> Diluar radius<br>
      <span style="color:#555">&#8212;&#8212;</span> Pulang gudang
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m


# ══════════════════════════════════════════════════════════════════
# EXPORT CSV
# ══════════════════════════════════════════════════════════════════

def _export_route_to_csv(route, branch, vehicle_type, jp, sp):
    rows = []
    cum_dist, cum_time = 0, 0
    rows.append({"Urutan": "START", "Lokasi": f"GUDANG - {branch['nama']}", "Alamat": "-",
                 "Koordinat": f"{branch['lat']},{branch['lng']}", "Jarak_Segment_km": 0,
                 "Jarak_Kumulatif_km": 0, "Est_Waktu_Segment": "0 mnt", "Est_Waktu_Kumulatif": "0 mnt",
                 "Invoice": "-", "Penerima": "-", "Barang": "-", "Dimensi": "-", "Berat_kg": 0,
                 "Qty": 0, "Phone": "-", "Kendaraan": vehicle_type})
    for idx, pkg in enumerate(route, 1):
        cum_dist += pkg.get("jarak_jalan_km", 0)
        cum_time += pkg.get("durasi_detik", 0)
        rows.append({"Urutan": idx, "Lokasi": f"STOP #{idx}",
                     "Alamat": pkg.get("Shipping Address", "")[:100],
                     "Koordinat": f"{pkg['lat']},{pkg['lng']}",
                     "Jarak_Segment_km": pkg.get("jarak_jalan_km", 0),
                     "Jarak_Kumulatif_km": round(cum_dist, 2),
                     "Est_Waktu_Segment": pkg.get("durasi_text", "-"),
                     "Est_Waktu_Kumulatif": _fmt_dur(cum_time),
                     "Invoice": pkg.get("Invoice NO", "-"),
                     "Penerima": pkg.get("Recipient Name", "-"),
                     "Barang": str(pkg.get("Items Name", "-"))[:50],
                     "Dimensi": f"{pkg.get('Panjang',0):.0f}x{pkg.get('Lebar',0):.0f}x{pkg.get('Tinggi',0):.0f} cm",
                     "Berat_kg": pkg.get("Berat", 0), "Qty": pkg.get("Items Quantity", 1),
                     "Phone": pkg.get("Recipient Phone", "-"), "Kendaraan": vehicle_type})
    if jp > 0:
        cum_dist += jp
        cum_time += sp
        rows.append({"Urutan": "END", "Lokasi": f"KEMBALI KE GUDANG - {branch['nama']}", "Alamat": "-",
                     "Koordinat": f"{branch['lat']},{branch['lng']}", "Jarak_Segment_km": round(jp, 2),
                     "Jarak_Kumulatif_km": round(cum_dist, 2), "Est_Waktu_Segment": _fmt_dur(sp),
                     "Est_Waktu_Kumulatif": _fmt_dur(cum_time), "Invoice": "-", "Penerima": "-",
                     "Barang": "-", "Dimensi": "-", "Berat_kg": 0, "Qty": 0, "Phone": "-",
                     "Kendaraan": vehicle_type})
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════
# SESSION STATE & CSS
# ══════════════════════════════════════════════════════════════════

def _init():
    defaults = {
        "branches": [b.copy() for b in _BRANCHES_DEFAULT],
        "selected_branch": _BRANCHES_DEFAULT[0]["kode"],
        "orders_df": None, "pkg_df": None, "hasil": None,
        "filter_kt": True, "algo_mode": "cluster",
        "gh_last_call": 0,
        "is_manual_input": False,  # Added for manual input tracking
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_CSS = """
<style>
#MainMenu, footer { visibility: hidden; }
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
    border: 1px solid #e9ecef; border-radius: 10px; padding: 14px 18px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.vehicle-summary { border-radius: 8px; padding: 14px 18px; margin-bottom: 12px; font-size: 13px; border-left: 4px solid; }
.vehicle-summary.motor { background: #d4edda; border-left-color: #27ae60; }
.vehicle-summary.mobil { background: #cfe2ff; border-left-color: #2980b9; }
.excluded-card { background: #fff5f5; border-left: 4px solid #e74c3c; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 8px; font-size: 12px; }
.info-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; font-size: 13px; margin-bottom: 14px; }
.dim-chip { display: inline-block; background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 10px; font-size: 11px; margin: 2px 4px 2px 0; font-family: monospace; color: #475569; }
.section-header { font-size: 18px; font-weight: 600; color: #1e293b; margin: 20px 0 12px 0; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] { padding: 10px 20px; border-radius: 8px 8px 0 0; }
</style>
"""


# ══════════════════════════════════════════════════════════════════
# APLIKASI UTAMA
# ══════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Kurir Toko v18", layout="wide", page_icon="🚚")
st.markdown(_CSS, unsafe_allow_html=True)
_init()

# ── SIDEBAR ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Kurir Toko")
    st.caption("Route Optimizer v18 - GraphHopper + Segment Colors")
    st.divider()
    
    branches = st.session_state.branches
    branch_map = {b["kode"]: f"{b['nama']} ({b['kode']})" for b in branches}
    sel_kode = st.radio("Pilih Gudang/Cabang", list(branch_map.keys()), 
                        format_func=lambda k: branch_map[k],
                        index=list(branch_map.keys()).index(st.session_state.selected_branch), 
                        label_visibility="collapsed")
    if sel_kode != st.session_state.selected_branch:
        st.session_state.selected_branch = sel_kode
        st.session_state.hasil = None
        st.rerun()
    
    cab = next(b for b in branches if b["kode"] == sel_kode)
    mc, bc = VEHICLE_CONFIG["MOTOR"], VEHICLE_CONFIG["MOBIL"]
    
    st.markdown(f'''<div style="background:#f8f9fa;border-left:4px solid {_BRANCH_COLORS.get(cab["kode"],"#555")};padding:12px;border-radius:4px;margin:8px 0">
        <strong>{cab["nama"]} ({cab["kode"]})</strong><br>
        <span style="font-size:11px;color:#666">{cab["lat"]:.6f}, {cab["lng"]:.6f}</span><br>
        <span style="color:{mc["hex"]};font-size:11px;font-weight:600">● Radius: {mc["max_radius"]} km</span>
        </div>''', unsafe_allow_html=True)
    
    st.divider()
    st.markdown("**Kriteria Kendaraan**")
    st.markdown(f'''<div class="info-box">
        <b style="color:{mc["hex"]}">Motor</b>: P≤{mc["max_panjang"]}cm · L≤{mc["max_lebar"]}cm · T≤{mc["max_tinggi"]}cm<br>
        Berat ≤{mc["max_berat"]}kg · Qty ≤{mc["max_qty"]}<br><br>
        <b style="color:{bc["hex"]}">Mobil</b>: Jika salah satu kriteria di atas terlampaui<br>
        Berat maks {bc["max_berat"]}kg<br><br>
        <small><i>Radius operasional: {mc["max_radius"]} km dari gudang</i></small>
        </div>''', unsafe_allow_html=True)
    
    st.divider()
    st.markdown("**Routing Engine**")
    st.caption("Primary: GraphHopper (motorcycle/car) • Fallback: ORS/OSRM")
    
    st.divider()
    algo = st.radio("Algoritma Rute", ["cluster", "nn"], 
                    format_func=lambda x: "Cluster + NN (rekomendasi)" if x == "cluster" else "Nearest Neighbor", 
                    index=0 if st.session_state.algo_mode == "cluster" else 1, 
                    label_visibility="collapsed")
    st.session_state.algo_mode = algo
    
    st.divider()
    if st.button("Reset Semua", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ── HEADER ───────────────────────────────────────────────────────
st.title("Kurir Toko - Multi-Vehicle Route Optimizer")
st.caption("v18 - GraphHopper API | Segment Colors | Radius 20 km | Peta terpisah")
st.divider()

# ════════════════════════════════════════════════════════════════
# STEP 1 — UPLOAD FILE / INPUT MANUAL
# ════════════════════════════════════════════════════════════════
st.subheader("Step 1 - Input Data Order")
input_mode = st.radio("Pilih Metode Input", ["Upload File Excel/CSV", "Input Manual Alamat"], horizontal=True)

# Reset state if input mode changes to avoid data mismatch
if "prev_input_mode" not in st.session_state:
    st.session_state.prev_input_mode = input_mode
if st.session_state.prev_input_mode != input_mode:
    st.session_state.prev_input_mode = input_mode
    st.session_state.pkg_df = None
    st.session_state.orders_df = None
    st.session_state.hasil = None
    st.session_state.is_manual_input = False

if input_mode == "Upload File Excel/CSV":
    st.caption("Upload file order dari marketplace (Excel/CSV). Pastikan kolom 'Shipping Address' tersedia.")
    uploaded = st.file_uploader("Pilih file Excel atau CSV", type=["xlsx", "xls", "csv"], label_visibility="collapsed")

    if uploaded:
        df_orders, msg = _load_excel(uploaded)
        if df_orders is None:
            st.error(msg)
        else:
            st.session_state.orders_df = df_orders
            st.success(msg)
            n_kt = df_orders["Shipping Courier"].apply(_is_kurir_toko).sum()
            total_val = df_orders["Total Amount"].sum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Order", len(df_orders)); c2.metric("Kurir Toko", int(n_kt))
            c3.metric("Kurir Lain", int(len(df_orders) - n_kt)); c4.metric("Total Nilai", _fmt_rp(total_val))
            
            st.session_state.filter_kt = st.toggle("Tampilkan hanya order Kurir Toko", value=st.session_state.filter_kt)
            df_view = (df_orders[df_orders["Shipping Courier"].apply(_is_kurir_toko)] if st.session_state.filter_kt else df_orders)
            
            if df_view.empty:
                st.warning("Tidak ada order Kurir Toko ditemukan.")
            else:
                has_dim = any(df_orders[c].sum() > 0 for c in ["Panjang", "Lebar", "Tinggi", "Berat"])
                if not has_dim and st.session_state.filter_kt:
                    st.warning("Kolom dimensi kosong. Semua paket akan diklasifikasikan sebagai Motor.")
                
                cols_show = {"SO Number": "SO No", "Invoice NO": "Invoice", "Order Date": "Tgl Order", 
                            "Recipient Name": "Penerima", "Items Name": "Barang", "Items Quantity": "Qty",
                            "Panjang": "P(cm)", "Lebar": "L(cm)", "Tinggi": "T(cm)", "Berat": "W(kg)",
                            "Kendaraan_Override": "Override", "Total Amount": "Total", 
                            "Shipping Address": "Alamat", "Shipping Courier": "Kurir"}
                avail = [c for c in cols_show if c in df_view.columns]
                df_disp = df_view[avail].copy().rename(columns=cols_show)
                st.markdown(f"#### Preview Data ({len(df_view)} baris)")
                st.dataframe(df_disp, use_container_width=True, height=260, hide_index=True)
                
                if st.button(f"Gunakan {len(df_view)} Order Ini", type="primary", use_container_width=True):
                    st.session_state.pkg_df = df_view.reset_index(drop=True)
                    st.session_state.hasil = None
                    st.success("Order siap. Lanjut ke Step 2 untuk hitung rute.")
else:
    st.caption("Masukkan alamat tujuan pengiriman secara manual untuk simulasi / testing. Gudang dan rute pulang akan mengikuti pilihan di sidebar.")
    
    if st.session_state.get("is_manual_input") and st.session_state.pkg_df is not None:
        df_view = st.session_state.pkg_df
        st.success(f"Data manual aktif: {len(df_view)} alamat siap diproses.")
        
        cols_show = {"SO Number": "SO No", "Invoice NO": "Invoice", "Order Date": "Tgl Order", 
                    "Recipient Name": "Penerima", "Items Name": "Barang", "Items Quantity": "Qty",
                    "Panjang": "P(cm)", "Lebar": "L(cm)", "Tinggi": "T(cm)", "Berat": "W(kg)",
                    "Kendaraan_Override": "Override", "Total Amount": "Total", 
                    "Shipping Address": "Alamat", "Shipping Courier": "Kurir"}
        avail = [c for c in cols_show if c in df_view.columns]
        df_disp = df_view[avail].copy().rename(columns=cols_show)
        st.markdown(f"#### Preview Data Manual ({len(df_view)} baris)")
        st.dataframe(df_disp, use_container_width=True, height=260, hide_index=True)
        
        if st.button("Reset & Input Ulang", use_container_width=True):
            st.session_state.is_manual_input = False
            st.session_state.pkg_df = None
            st.session_state.orders_df = None
            st.session_state.hasil = None
            st.rerun()
            
    else:
        num_addr = st.number_input("Jumlah alamat yang ingin diinput", min_value=1, max_value=15, value=2, step=1)
        
        manual_data = []
        for i in range(int(num_addr)):
            with st.expander(f"📍 Alamat {i+1}", expanded=(i==0)):
                c1, c2 = st.columns([2, 1])
                with c1:
                    addr = st.text_input(f"Alamat Lengkap", key=f"addr_{i}", placeholder="Jl. Sudirman No. 1, Surabaya")
                with c2:
                    recipient = st.text_input(f"Nama Penerima", value=f"Penerima {i+1}", key=f"rec_{i}")
                    
                c3, c4, c5 = st.columns(3)
                with c3:
                    item_name = st.text_input(f"Nama Barang", value=f"Paket {i+1}", key=f"item_{i}")
                with c4:
                    qty = st.number_input(f"Qty", min_value=1, value=1, step=1, key=f"qty_{i}")
                with c5:
                    vehicle_override = st.selectbox(f"Override Kendaraan", ["", "MOTOR", "MOBIL"], key=f"veh_{i}")
                    
                with st.expander(f"Detail Dimensi & Berat (Opsional)"):
                    c6, c7, c8, c9 = st.columns(4)
                    with c6: panjang = st.number_input(f"P (cm)", min_value=0, value=0, key=f"p_{i}")
                    with c7: lebar = st.number_input(f"L (cm)", min_value=0, value=0, key=f"l_{i}")
                    with c8: tinggi = st.number_input(f"T (cm)", min_value=0, value=0, key=f"t_{i}")
                    with c9: berat = st.number_input(f"Berat (kg)", min_value=0.0, value=0.0, step=0.1, key=f"w_{i}")
                
                if addr.strip():
                    manual_data.append({
                        "SO Number": f"MAN-{i+1:03d}", "Order Date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                        "Channel": "Manual", "Store": "Manual", "Invoice NO": f"INV-MAN-{i+1:03d}",
                        "Payment Status": "Paid", "Fulfillment Status": "Ready", "Payment Type": "Manual",
                        "Payment Date": "-", "Printed Date": "-", "Ready to Pack Date": "-",
                        "Ready to Ship Date": "-", "Marketplace RTS Date": "-", "Handover Date": "-",
                        "Shipped Date": "-", "Delivered Date": "-", "Completed Date": "-",
                        "Cancelled Date": "-", "Return Date": "-", "Unpacking Date": "-",
                        "Delete Nota Date": "-", "Cancelled Reason": "-", "Expiry Date": "-",
                        "Shipping Courier": "Kurir Toko", 
                        "AWB": f"AWB-MAN-{i+1:03d}",
                        "Customer Name": recipient, "Recipient Name": recipient, "Recipient Phone": "-",
                        "Shipping Address": addr, "Additional Info": "-", "No Accurate": "-",
                        "Items SKU": f"SKU-MAN-{i+1:03d}", "Items Name": item_name,
                        "Warehouse": cab["nama"], "Warehouse Code": cab["kode"],
                        "Items Quantity": qty, "Items Price": 0, "Items Discount Price": 0, "Subtotal": 0,
                        "Original Shipping": 0, "Buyer Paid Shipping": 0, "Shipping Rebate": 0,
                        "Seller Discount": 0, "Rebate": 0, "Voucher Seller": 0,
                        "Platform Service Fee": 0, "Platform Commission": 0, "Total Amount": 0,
                        "Panjang": panjang, "Lebar": lebar, "Tinggi": tinggi, "Berat": berat,
                        "Kendaraan_Override": vehicle_override,
                    })
                    
        if st.button("Gunakan Data Manual Ini", type="primary", use_container_width=True):
            if not manual_data:
                st.warning("Harap isi minimal satu alamat lengkap.")
            else:
                df_manual = pd.DataFrame(manual_data)
                st.session_state.orders_df = df_manual
                st.session_state.pkg_df = df_manual
                st.session_state.is_manual_input = True
                st.session_state.hasil = None
                st.success(f"Berhasil memuat {len(df_manual)} order manual.")
                st.rerun()

st.divider()

# ════════════════════════════════════════════════════════════════
# STEP 2 — HITUNG RUTE
# ════════════════════════════════════════════════════════════════
st.subheader("Step 2 - Hitung Rute Optimal")
if st.session_state.pkg_df is None:
    st.info("Upload atau input alamat terlebih dahulu di Step 1.")
else:
    n_order = len(st.session_state.pkg_df)
    algo_label = "Cluster + NN" if st.session_state.algo_mode == "cluster" else "Nearest Neighbor"
    st.markdown(f"**{n_order} order siap diproses** · Algoritma: {algo_label} · Radius: 20 km")
    
    run = st.button(f"Hitung Rute Multi-Vehicle", type="primary", use_container_width=True)
    
    if run:
        pkg_list = [{**p, "_idx": i} for i, p in enumerate(st.session_state.pkg_df.to_dict("records")) 
                    if str(p.get("Shipping Address", "")).strip().lower() not in ("", "-", "nan")]
        if not pkg_list:
            st.error("Tidak ada alamat valid untuk diproses."); st.stop()
        
        bar = st.progress(0, text="Memulai geocoding...")
        geocoded, failed = [], []
        
        for i, pkg in enumerate(pkg_list):
            raw = str(pkg.get("Shipping Address", ""))
            bar.progress((i + 1) / len(pkg_list), text=f"Geocoding [{i+1}/{len(pkg_list)}]: {raw[:40]}...")
            lat, lng, src, akr = _geocode(raw)
            if lat:
                geocoded.append({**pkg, "lat": lat, "lng": lng, "geocode_sumber": src, "akurasi": akr})
            else:
                failed.append({"Invoice": pkg.get("Invoice NO", "-"), "Alamat": raw})
        
        bar.empty()
        
        if failed:
            with st.expander(f"{len(failed)} alamat gagal diproses", expanded=False):
                for f in failed[:20]: st.caption(f"• {f['Invoice']}: {f['Alamat'][:70]}")
        
        paket_ok = [p for p in geocoded if p.get("akurasi") != "gagal" and p.get("lat")]
        if not paket_ok:
            st.error("Semua alamat gagal diproses. Periksa koneksi atau format alamat."); st.stop()
        
        motor_pkgs, mobil_pkgs, excluded = _split_by_vehicle(paket_ok, cab["lat"], cab["lng"])
        st.info(f"Klasifikasi: {len(motor_pkgs)} paket Motor | {len(mobil_pkgs)} paket Mobil | {len(excluded)} diluar radius 20 km")
        
        if excluded:
            with st.expander(f"{len(excluded)} paket diluar jangkauan", expanded=False):
                for ex in excluded:
                    st.markdown(f'''<div class="excluded-card">
                        <b>{ex["Invoice"]}</b> · {ex["Penerima"]}<br>
                        {ex["Barang"]}<br>
                        {ex["Alamat"][:60]}<br>
                        Jarak {ex["Jarak_km"]} km > radius {ex["Max_Radius"]} km ({ex["Vehicle Type"]})
                        </div>''', unsafe_allow_html=True)
        
        if not motor_pkgs and not mobil_pkgs:
            st.error("Semua paket di luar jangkauan. Periksa koordinat gudang."); st.stop()
        
        with st.spinner("Menghitung rute Motor..."):
            r_motor, km_motor, _, sec_motor = _compute_route(cab["lat"], cab["lng"], motor_pkgs, st.session_state.algo_mode, "MOTOR")
        with st.spinner("Menghitung rute Mobil..."):
            r_mobil, km_mobil, _, sec_mobil = _compute_route(cab["lat"], cab["lng"], mobil_pkgs, st.session_state.algo_mode, "MOBIL")
        
        def _pulang(route, vtype):
            if not route: return 0, 0
            last = route[-1]
            seg = _get_route(((last["lat"], last["lng"]), (cab["lat"], cab["lng"])), vtype)
            if seg and seg["distance_km"] > 0: return seg["distance_km"], seg["duration_seconds"]
            d = _haversine(last["lat"], last["lng"], cab["lat"], cab["lng"]) * (1.15 if vtype=="MOTOR" else 1.25)
            return round(d, 2), d * 90
        
        jp_motor, sp_motor = _pulang(r_motor, "MOTOR")
        jp_mobil, sp_mobil = _pulang(r_mobil, "MOBIL")
        
        km_motor_full = round(km_motor + jp_motor, 2); sec_motor_full = sec_motor + sp_motor
        km_mobil_full = round(km_mobil + jp_mobil, 2); sec_mobil_full = sec_mobil + sp_mobil
        cost_motor = round(km_motor_full * mc["cost_per_km"]); cost_mobil = round(km_mobil_full * bc["cost_per_km"])
        
        st.session_state.hasil = {
            "branch": cab, "route_motor": r_motor, "route_mobil": r_mobil,
            "km_motor_full": km_motor_full, "sec_motor_full": sec_motor_full, "cost_motor": cost_motor,
            "km_mobil_full": km_mobil_full, "sec_mobil_full": sec_mobil_full, "cost_mobil": cost_mobil,
            "total_cost": cost_motor + cost_mobil,
            "jp_motor": jp_motor, "sp_motor": sp_motor, "jp_mobil": jp_mobil, "sp_mobil": sp_mobil,
            "excluded": excluded,
        }
        st.success(f"Rute selesai! Motor: {len(r_motor)} paket · Mobil: {len(r_mobil)} paket")

# ════════════════════════════════════════════════════════════════
# STEP 3 — HASIL (PETA TERPISAH + SEGMENT COLORS)
# ════════════════════════════════════════════════════════════════
if st.session_state.hasil:
    hasil = st.session_state.hasil; b = hasil["branch"]
    
    st.divider(); st.subheader("Step 3 - Hasil & Peta Rute")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"##### Rute Motor")
        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Paket", len(hasil["route_motor"])); cm2.metric("Jarak", f"{hasil['km_motor_full']:.1f} km")
        cm3.metric("Waktu", _fmt_dur(hasil["sec_motor_full"])); cm4.metric("Biaya", _fmt_rp(hasil["cost_motor"]))
        st.markdown(f'''<div class="vehicle-summary motor">
            <b>Ringkasan Motor:</b> {len(hasil["route_motor"])} paket | {hasil["km_motor_full"]:.1f} km | 
            {_fmt_dur(hasil["sec_motor_full"])} | {_fmt_rp(hasil["cost_motor"])}
            </div>''', unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"##### Rute Mobil")
        cb1, cb2, cb3, cb4 = st.columns(4)
        cb1.metric("Paket", len(hasil["route_mobil"])); cb2.metric("Jarak", f"{hasil['km_mobil_full']:.1f} km")
        cb3.metric("Waktu", _fmt_dur(hasil["sec_mobil_full"])); cb4.metric("Biaya", _fmt_rp(hasil["cost_mobil"]))
        st.markdown(f'''<div class="vehicle-summary mobil">
            <b>Ringkasan Mobil:</b> {len(hasil["route_mobil"])} paket | {hasil["km_mobil_full"]:.1f} km | 
            {_fmt_dur(hasil["sec_mobil_full"])} | {_fmt_rp(hasil["cost_mobil"])}
            </div>''', unsafe_allow_html=True)
    
    st.divider()
    
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("Total Paket", len(hasil["route_motor"]) + len(hasil["route_mobil"]))
    cs2.metric("Total Jarak", f"{hasil['km_motor_full'] + hasil['km_mobil_full']:.1f} km")
    cs3.metric("Total Waktu", _fmt_dur(hasil["sec_motor_full"] + hasil["sec_mobil_full"]))
    cs4.metric("Total Biaya", _fmt_rp(hasil["total_cost"]))
    
    st.divider()
    
    tab_order_motor, tab_order_mobil, tab_map_motor, tab_map_mobil, tab_export = st.tabs([
        "Urutan Motor", "Urutan Mobil", "Peta Motor", "Peta Mobil", "Export Data"
    ])
    
    def _build_rows(route, vtype, jp, sp):
        rows, cum_t = [], 0
        for i, pkg in enumerate(route, 1):
            cum_t += pkg.get("durasi_detik", 0)
            rows.append({
                "No": i, "Invoice": pkg.get("Invoice NO", "-"), "Penerima": pkg.get("Recipient Name", "-"),
                "Barang": str(pkg.get("Items Name", "-"))[:35], 
                "Dimensi": f"{pkg.get('Panjang',0):.0f}×{pkg.get('Lebar',0):.0f}×{pkg.get('Tinggi',0):.0f} cm",
                "Berat": f"{pkg.get('Berat',0):.1f} kg", "Qty": pkg.get("Items Quantity", 1),
                "Jarak": f"{pkg['jarak_jalan_km']:.1f} km", "Durasi": pkg.get("durasi_text", "-"), 
                "Kumulatif": _fmt_dur(cum_t),
            })
        if jp > 0:
            cum_t += sp
            rows.append({"No": "Pulang", "Invoice": "PULANG", "Penerima": f"Gudang {b['nama']}",
                        "Barang": "-", "Dimensi": "-", "Berat": "-", "Qty": "-",
                        "Jarak": f"{jp:.1f} km", "Durasi": _fmt_dur(sp), "Kumulatif": _fmt_dur(cum_t)})
        return pd.DataFrame(rows)
    
    with tab_order_motor:
        if hasil["route_motor"]:
            df_m = _build_rows(hasil["route_motor"], "MOTOR", hasil["jp_motor"], hasil["sp_motor"])
            st.dataframe(df_m, use_container_width=True, hide_index=True, height=400)
        else: st.info("Tidak ada paket untuk rute Motor.")
    
    with tab_order_mobil:
        if hasil["route_mobil"]:
            df_b = _build_rows(hasil["route_mobil"], "MOBIL", hasil["jp_mobil"], hasil["sp_mobil"])
            st.dataframe(df_b, use_container_width=True, hide_index=True, height=400)
        else: st.info("Tidak ada paket untuk rute Mobil.")
    
    with tab_map_motor:
        st.caption(f"Peta Rute Motor - Setiap segmen warna berbeda untuk visualisasi urutan")
        with st.spinner("Memuat peta Motor..."):
            peta_motor = _build_single_map(b, hasil["route_motor"], "MOTOR", hasil.get("excluded"))
            st_folium(peta_motor, use_container_width=True, height=600, returned_objects=[])
    
    with tab_map_mobil:
        st.caption(f"Peta Rute Mobil - Setiap segmen warna berbeda untuk visualisasi urutan")
        with st.spinner("Memuat peta Mobil..."):
            peta_mobil = _build_single_map(b, hasil["route_mobil"], "MOBIL", hasil.get("excluded"))
            st_folium(peta_mobil, use_container_width=True, height=600, returned_objects=[])
    
    with tab_export:
        st.markdown("##### Export Rute ke CSV"); st.caption("File CSV dapat digunakan driver untuk panduan pengiriman")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            if hasil["route_motor"]:
                csv_motor = _export_route_to_csv(hasil["route_motor"], b, "MOTOR", hasil["jp_motor"], hasil["sp_motor"])
                csv_motor_str = csv_motor.to_csv(index=False, sep=";")
                st.download_button(label="Download Rute Motor (.csv)", data=csv_motor_str, 
                                  file_name=f"rute_motor_{b['kode']}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv", 
                                  mime="text/csv", use_container_width=True)
            else: st.info("Tidak ada data Motor untuk diexport.")
        with col_exp2:
            if hasil["route_mobil"]:
                csv_mobil = _export_route_to_csv(hasil["route_mobil"], b, "MOBIL", hasil["jp_mobil"], hasil["sp_mobil"])
                csv_mobil_str = csv_mobil.to_csv(index=False, sep=";")
                st.download_button(label="Download Rute Mobil (.csv)", data=csv_mobil_str, 
                                  file_name=f"rute_mobil_{b['kode']}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv", 
                                  mime="text/csv", use_container_width=True)
            else: st.info("Tidak ada data Mobil untuk diexport.")