"""
Kurir Toko — Route Optimizer v11
=================================
Disesuaikan dengan struktur file orders.xlsx dari sistem marketplace.

Kolom yang dibaca dari orders.xlsx:
  Invoice NO, Order Date, SO Number, Recipient Name, Recipient Phone,
  Shipping Address (geocoding), Items Name, Items SKU, Items Quantity,
  Items Price, Subtotal, Total Amount, Payment Status, Fulfillment Status,
  Shipping Courier (filter Kurir Toko), Warehouse, No Accurate

Filter otomatis: hanya order dengan Shipping Courier mengandung "kurir toko"

Install:
    pip install streamlit pandas folium streamlit-folium geopy requests openpyxl

Jalankan:
    streamlit run kurir_toko_optimizer.py
"""

import math
import re
import time
import requests
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# ──────────────────────────────────────────────────────
# KONSTANTA GLOBAL
# ──────────────────────────────────────────────────────

GEOCODE_DELAY = 1.1  # Rate limit Nominatim — JANGAN dikurangi

KURIR_TOKO_KEYWORDS = ["kurir toko", "kurirtoko", "kurir_toko"]

# ──────────────────────────────────────────────────────
# DATA CABANG DEFAULT
# ──────────────────────────────────────────────────────

BRANCHES_DEFAULT = [
    {"kode": "SUB", "nama": "Surabaya",   "lat": -7.317566, "lng": 112.764234},
    {"kode": "JKT", "nama": "Jakarta",    "lat": -6.208800, "lng": 106.845600},
    {"kode": "MLG", "nama": "Malang",     "lat": -7.979700, "lng": 112.630400},
    {"kode": "SMG", "nama": "Semarang",   "lat": -6.966700, "lng": 110.416700},
    {"kode": "JOG", "nama": "Yogyakarta", "lat": -7.795600, "lng": 110.369500},
    {"kode": "BLI", "nama": "Bali",       "lat": -8.340500, "lng": 115.092000},
]

BRANCH_COLORS = {
    "SUB": "#C0392B", "JKT": "#1A5276", "MLG": "#1E8449",
    "SMG": "#D35400", "JOG": "#6C3483", "BLI": "#117A65",
}

FOLIUM_COLORS = {
    "SUB": "red",    "JKT": "blue",  "MLG": "green",
    "SMG": "orange", "JOG": "purple","BLI": "cadetblue",
}

REGION_FALLBACK = {
    "lamongan":    (-7.1196, 112.4115), "gresik":      (-7.1560, 112.6508),
    "sidoarjo":    (-7.4561, 112.7185), "mojokerto":   (-7.4700, 112.4339),
    "pasuruan":    (-7.6451, 112.9070), "probolinggo": (-7.7543, 113.2159),
    "jember":      (-8.1724, 113.7020), "banyuwangi":  (-8.2191, 114.3691),
    "kediri":      (-7.8166, 112.0114), "blitar":      (-8.0954, 112.1609),
    "tulungagung": (-8.0652, 111.9041), "madiun":      (-7.6298, 111.5239),
    "bojonegoro":  (-7.1507, 111.8817), "tuban":       (-6.8918, 112.0508),
    "surabaya":    (-7.3176, 112.7642), "malang":      (-7.9797, 112.6304),
    "semarang":    (-6.9667, 110.4167), "yogyakarta":  (-7.7956, 110.3695),
    "jakarta":     (-6.2088, 106.8456), "bandung":     (-6.9175, 107.6191),
    "bekasi":      (-6.2383, 106.9756), "tangerang":   (-6.1702, 106.6402),
    "depok":       (-6.4025, 106.7942), "bogor":       (-6.5971, 106.8060),
    "denpasar":    (-8.6705, 115.2126), "badung":      (-8.5692, 115.1880),
    "bali":        (-8.3405, 115.0920), "solo":        (-7.5755, 110.8243),
    "salatiga":    (-7.3306, 110.5080), "pekalongan":  (-6.8886, 109.6753),
    "tegal":       (-6.8797, 109.1256), "purwokerto":  (-7.4153, 109.2350),
    "jawa timur":  (-7.5360, 112.2384), "jawa tengah": (-7.1500, 110.1403),
    "jawa barat":  (-6.9175, 107.6191), "dki jakarta": (-6.2088, 106.8456),
    "simokerto":   (-7.2436, 112.7378), "tambaksari":  (-7.2617, 112.7669),
    "rungkut":     (-7.3311, 112.7610), "waru":        (-7.3632, 112.7204),
    "paciran":     (-6.8660, 112.3160),
}

# ──────────────────────────────────────────────────────
# EXPAND SINGKATAN INDONESIA
# ──────────────────────────────────────────────────────

SINGKATAN_MAP = {
    r"\bJl\.?\b": "Jalan",   r"\bJln\.?\b": "Jalan",
    r"\bNo\.?\s*": "Nomor ", r"\bNO\.?\s*": "Nomor ",
    r"\bLT\.?\s*(\d)": r"Lantai \1", r"\bLt\.?\s*(\d)": r"Lantai \1",
    r"\bBLOK\b": "Blok",    r"\bBlk\.?\b": "Blok",
    r"\bKec\.?\b": "Kecamatan", r"\bKel\.?\b": "Kelurahan",
    r"\bKab\.?\b": "Kabupaten",
    r"\bRT\.?\s*\d+\s*[/,]?\s*RW\.?\s*\d+\b": "",
    r"\bRT\.?\s*\d+\b": "", r"\bRW\.?\s*\d+\b": "",
    r"\bGg\.?\b": "Gang",
    r"\bPerum\.?\b": "Perumahan", r"\bKomp\.?\b": "Komplek",
}


def expand_abbreviations(raw: str) -> str:
    result = raw
    for pattern, replacement in SINGKATAN_MAP.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", result).strip()


def clean_address(raw: str) -> str:
    addr = expand_abbreviations(raw)
    for w in ["Indonesia", "Java", r"\d{5}"]:
        addr = re.sub(r"\b" + w + r"\b", "", addr, flags=re.IGNORECASE)
    parts = [p.strip() for p in addr.split(",") if p.strip() and len(p.strip()) > 2]
    seen, unique = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return ", ".join([p for p in unique if len(p) > 2][:4])


def extract_city_province(raw: str) -> str:
    km = re.search(r"(Kota|Kabupaten)\s+([A-Za-z ]+?)(?:,|$)", raw, re.IGNORECASE)
    pm = re.search(
        r"(Jawa Timur|Jawa Tengah|Jawa Barat|DKI Jakarta|Daerah Istimewa Yogyakarta"
        r"|DIY|Bali|Surabaya|Jakarta|Malang|Semarang|Yogyakarta|Denpasar"
        r"|Bandung|Bekasi|Tangerang|Bojonegoro|Lamongan|Gresik|Sidoarjo)",
        raw, re.IGNORECASE,
    )
    parts = []
    if km:
        parts.append(km.group(0).strip())
    if pm and (not km or pm.group(0).lower() not in km.group(0).lower()):
        parts.append(pm.group(0).strip())
    return ", ".join(parts)


# ──────────────────────────────────────────────────────
# GEOCODING
# ──────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _nominatim(query: str):
    try:
        loc = Nominatim(user_agent="kurir_toko_magang_v11_2025", timeout=10).geocode(query)
        if loc:
            return loc.latitude, loc.longitude
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    return None, None


@st.cache_data(show_spinner=False)
def _photon(query: str):
    try:
        r = requests.get(
            "https://photon.komoot.io/api/",
            params={"q": query, "limit": 1, "lang": "id"},
            timeout=10,
        )
        feats = r.json().get("features", [])
        if feats:
            c = feats[0]["geometry"]["coordinates"]
            return c[1], c[0]
    except Exception:
        pass
    return None, None


def _region_fallback(raw: str):
    text = raw.lower()
    for region, coords in sorted(REGION_FALLBACK.items(), key=lambda x: -len(x[0])):
        if region in text:
            return coords
    return None, None


def geocode(raw: str) -> tuple:
    cleaned = clean_address(raw)
    city_pv = extract_city_province(raw)

    lat, lng = _nominatim(cleaned + ", Indonesia")
    if lat:
        return lat, lng, "Nominatim", "tinggi"
    time.sleep(GEOCODE_DELAY)

    lat, lng = _photon(expand_abbreviations(raw) + " Indonesia")
    if lat:
        return lat, lng, "Photon", "tinggi"
    time.sleep(0.5)

    if city_pv:
        lat, lng = _nominatim(city_pv + ", Indonesia")
        if lat:
            return lat, lng, "Nominatim (kota)", "sedang"
        time.sleep(GEOCODE_DELAY)
        lat, lng = _photon(city_pv + " Indonesia")
        if lat:
            return lat, lng, "Photon (kota)", "sedang"
        time.sleep(0.5)

    lat, lng = _region_fallback(raw)
    if lat:
        return lat, lng, "Region fallback", "rendah"

    return None, None, "Gagal", "gagal"


# ──────────────────────────────────────────────────────
# PARSE FILE ORDERS
# ──────────────────────────────────────────────────────

def is_kurir_toko(val) -> bool:
    if pd.isna(val) or str(val).strip() == "":
        return False
    v = str(val).lower().replace(" ", "").replace("_", "")
    return any(kw.replace(" ", "") in v for kw in KURIR_TOKO_KEYWORDS)


def format_currency(val) -> str:
    try:
        return f"Rp {int(float(val)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "-"


def format_date(val) -> str:
    try:
        if pd.isna(val) or str(val).strip() in ("", "NaT", "nan", "-"):
            return "-"
        ts = pd.to_datetime(str(val), errors="coerce")
        return ts.strftime("%d/%m/%Y %H:%M") if not pd.isna(ts) else str(val)[:16]
    except Exception:
        return str(val)[:16] if val else "-"


def load_orders_excel(uploaded_file):
    try:
        fname = uploaded_file.name.lower()
        if fname.endswith(".csv"):
            df_raw = pd.read_csv(uploaded_file, dtype=str)
        else:
            df_raw = pd.read_excel(uploaded_file, dtype=str)

        df_raw.columns = [c.strip() for c in df_raw.columns]
        cl = {c.lower(): c for c in df_raw.columns}

        def gc(names):
            for n in names:
                if n.lower() in cl:
                    return cl[n.lower()]
            return None

        col_addr = gc(["Shipping Address", "shipping_address", "Alamat"])
        if not col_addr:
            return None, f"Kolom 'Shipping Address' tidak ditemukan. Kolom ada: {', '.join(df_raw.columns.tolist())}"

        r = pd.DataFrame()
        r["Shipping Address"]    = df_raw[col_addr].fillna("").astype(str)
        r["Invoice NO"]          = df_raw[gc(["Invoice NO","Invoice No"])].fillna("-").astype(str) if gc(["Invoice NO","Invoice No"]) else "-"
        r["SO Number"]           = df_raw[gc(["SO Number","so_number"])].fillna("-").astype(str) if gc(["SO Number"]) else "-"
        r["Order Date"]          = df_raw[gc(["Order Date","order_date"])].fillna("-").astype(str) if gc(["Order Date"]) else "-"
        r["Recipient Name"]      = df_raw[gc(["Recipient Name","recipient_name","Penerima"])].fillna("-").astype(str) if gc(["Recipient Name","Penerima"]) else "-"
        r["Recipient Phone"]     = df_raw[gc(["Recipient Phone","recipient_phone"])].fillna("-").astype(str) if gc(["Recipient Phone"]) else "-"
        r["Items Name"]          = df_raw[gc(["Items Name","items_name","Nama Barang"])].fillna("-").astype(str) if gc(["Items Name","Nama Barang"]) else "-"
        r["Items SKU"]           = df_raw[gc(["Items SKU","items_sku","SKU"])].fillna("-").astype(str) if gc(["Items SKU","SKU"]) else "-"
        r["Items Quantity"]      = pd.to_numeric(df_raw[gc(["Items Quantity","items_quantity","Qty"])], errors="coerce").fillna(1).astype(int) if gc(["Items Quantity","Qty"]) else 1
        r["Items Price"]         = pd.to_numeric(df_raw[gc(["Items Price","items_price"])], errors="coerce").fillna(0) if gc(["Items Price"]) else 0
        r["Subtotal"]            = pd.to_numeric(df_raw[gc(["Subtotal"])], errors="coerce").fillna(0) if gc(["Subtotal"]) else 0
        r["Total Amount"]        = pd.to_numeric(df_raw[gc(["Total Amount","total_amount","Total"])], errors="coerce").fillna(0) if gc(["Total Amount","Total"]) else 0
        r["Payment Status"]      = df_raw[gc(["Payment Status","payment_status"])].fillna("-").astype(str) if gc(["Payment Status"]) else "-"
        r["Fulfillment Status"]  = df_raw[gc(["Fulfillment Status","fulfillment_status"])].fillna("-").astype(str) if gc(["Fulfillment Status"]) else "-"
        r["Shipping Courier"]    = df_raw[gc(["Shipping Courier","shipping_courier","Kurir"])].fillna("-").astype(str) if gc(["Shipping Courier","Kurir"]) else "-"
        r["Warehouse"]           = df_raw[gc(["Warehouse","warehouse","Gudang"])].fillna("-").astype(str) if gc(["Warehouse","Gudang"]) else "-"
        r["No Accurate"]         = df_raw[gc(["No Accurate","no_accurate"])].fillna("-").astype(str) if gc(["No Accurate"]) else "-"
        r["Additional Info"]     = df_raw[gc(["Additional Info","additional_info","Catatan"])].fillna("-").astype(str) if gc(["Additional Info","Catatan"]) else "-"

        # Buang baris alamat tidak berguna
        r = r[~r["Shipping Address"].str.strip().str.lower().isin(["", "indonesia", "-", "nan"])].reset_index(drop=True)

        n_kt = r["Shipping Courier"].apply(is_kurir_toko).sum()
        return r, f"{len(r)} order dimuat. {n_kt} Kurir Toko, {len(r)-n_kt} kurir lain."

    except Exception as e:
        return None, f"Gagal membaca file: {e}"


# ──────────────────────────────────────────────────────
# LAPORAN AKURASI
# ──────────────────────────────────────────────────────

def buat_laporan_akurasi(geocoded: list, failed: list) -> dict:
    total = len(geocoded) + len(failed)
    if total == 0:
        return {}
    per_sumber  = {}
    per_akurasi = {"tinggi": 0, "sedang": 0, "rendah": 0}
    for p in geocoded:
        src = p.get("geocode_sumber", "?")
        per_sumber[src] = per_sumber.get(src, 0) + 1
        akr = p.get("akurasi", "")
        if akr in per_akurasi:
            per_akurasi[akr] += 1
    return {
        "total": total, "berhasil": len(geocoded), "gagal": len(failed),
        "pct_berhasil": round(len(geocoded) / total * 100, 1),
        "per_sumber": per_sumber, "per_akurasi": per_akurasi,
    }


def tampilkan_laporan_akurasi(laporan: dict):
    if not laporan:
        return
    st.markdown("#### Laporan Akurasi Geocoding")
    st.caption("Tunjukkan ke pembimbing sebagai bukti pengujian Minggu 1.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", laporan["total"])
    c2.metric("Berhasil", laporan["berhasil"])
    c3.metric("Gagal", laporan["gagal"])
    c4.metric("Sukses", f"{laporan['pct_berhasil']}%")
    col_src, col_akr = st.columns(2)
    with col_src:
        st.markdown("**Sumber geocoding:**")
        for src, count in laporan["per_sumber"].items():
            pct = round(count / laporan["berhasil"] * 100) if laporan["berhasil"] else 0
            st.markdown(f"- {src}: **{count}** ({pct}%)")
    with col_akr:
        st.markdown("**Tingkat akurasi:**")
        labels = {"tinggi": "Spesifik", "sedang": "Perkiraan wilayah", "rendah": "Perkiraan kota"}
        for akr, count in laporan["per_akurasi"].items():
            st.markdown(f"- {labels.get(akr, akr)}: **{count}**")
    rows = [{
        "Invoice NO": p.get("Invoice NO",""), "Penerima": p.get("Recipient Name",""),
        "Alamat": p.get("Shipping Address",""), "Geocoder": p.get("geocode_sumber",""),
        "Akurasi": p.get("akurasi",""), "Lat": p.get("lat",""), "Lng": p.get("lng",""),
    } for p in st.session_state.get("_last_geocoded", [])]
    if rows:
        st.download_button("Download laporan akurasi (.csv)",
                           data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8"),
                           file_name="laporan_akurasi_geocoding.csv", mime="text/csv")


# ──────────────────────────────────────────────────────
# ROUTING
# ──────────────────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2) -> float:
    R  = 6371
    dl = math.radians(lat2 - lat1)
    dg = math.radians(lng2 - lng1)
    a  = (math.sin(dl/2)**2 + math.cos(math.radians(lat1))
          * math.cos(math.radians(lat2)) * math.sin(dg/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nn_tsp(start_lat, start_lng, pkgs: list, road_factor: float) -> tuple:
    remaining    = pkgs.copy()
    route, total = [], 0.0
    clat, clng   = start_lat, start_lng
    while remaining:
        best_i, best_d = 0, float("inf")
        for i, p in enumerate(remaining):
            d = haversine(clat, clng, p["lat"], p["lng"])
            if d < best_d:
                best_d, best_i = d, i
        chosen = remaining.pop(best_i)
        chosen["jarak_lurus_km"] = round(best_d, 2)
        chosen["jarak_jalan_km"] = round(max(best_d, 0.001) * road_factor, 2)
        route.append(chosen)
        total += max(best_d, 0.001)
        clat, clng = chosen["lat"], chosen["lng"]
    return route, round(total, 2)


# ──────────────────────────────────────────────────────
# PETA FOLIUM
# ──────────────────────────────────────────────────────

def buat_peta(cabang: dict, route: list) -> folium.Map:
    kode  = cabang["kode"]
    color = BRANCH_COLORS.get(kode, "#555")
    fcol  = FOLIUM_COLORS.get(kode, "gray")
    m = folium.Map(location=[cabang["lat"], cabang["lng"]], zoom_start=10, tiles="CartoDB Positron")
    folium.Marker([cabang["lat"], cabang["lng"]],
                  tooltip=f"Gudang {cabang['nama']} ({kode})",
                  icon=folium.Icon(color=fcol, icon="home", prefix="fa")).add_to(m)
    if not route:
        return m
    coords = [[cabang["lat"], cabang["lng"]]] + [[p["lat"], p["lng"]] for p in route]
    folium.PolyLine(coords, color=color, weight=3, opacity=0.85).add_to(m)
    for i, pkg in enumerate(route, 1):
        warn = " ⚠ perkiraan" if pkg.get("akurasi") in ("sedang","rendah") else ""
        tip  = (f"<b>#{i} — {pkg.get('Invoice NO','-')}</b>{warn}<br>"
                f"Penerima: {pkg.get('Recipient Name','-')}<br>"
                f"Barang: {str(pkg.get('Items Name','-'))[:50]}<br>"
                f"Qty: {pkg.get('Items Quantity','-')} | Total: {format_currency(pkg.get('Total Amount',0))}<br>"
                f"Jarak: {pkg['jarak_lurus_km']} km")
        folium.CircleMarker([pkg["lat"], pkg["lng"]], radius=9, color=color,
                            fill=True, fill_color=color, fill_opacity=0.9,
                            tooltip=folium.Tooltip(tip, sticky=True)).add_to(m)
        folium.Marker([pkg["lat"], pkg["lng"]],
                      icon=folium.DivIcon(
                          html=(f'<div style="font-size:10px;font-weight:700;color:white;'
                                f'background:{color};border-radius:50%;width:20px;height:20px;'
                                f'display:flex;align-items:center;justify-content:center;'
                                f'border:1.5px solid white">{i}</div>'),
                          icon_size=(20,20), icon_anchor=(10,10))).add_to(m)
    return m


# ──────────────────────────────────────────────────────
# HELPER & STATE
# ──────────────────────────────────────────────────────

def badge_akurasi(v: str) -> str:
    return {"tinggi":"Spesifik","sedang":"Perkiraan wilayah",
            "rendah":"Perkiraan kota","gagal":"Gagal"}.get(v, v)


def init_state():
    defs = {
        "branches":             [b.copy() for b in BRANCHES_DEFAULT],
        "selected_branch_kode": BRANCHES_DEFAULT[0]["kode"],
        "hasil":                None,
        "orders_df":            None,
        "pkg_df":               None,
        "laporan_akurasi":      None,
        "_last_geocoded":       [],
        "filter_kt":            True,
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v


CUSTOM_CSS = """
<style>
#MainMenu, footer { visibility: hidden; }
[data-testid="metric-container"] {
    background:#f8f9fa;border:1px solid #e9ecef;border-radius:8px;padding:12px 16px;
}
thead tr th { background-color:#f1f3f5!important;font-weight:600!important;font-size:13px!important;color:#343a40!important; }
.stButton > button[kind="primary"] { background-color:#1a3a5c;border-color:#1a3a5c;font-weight:600; }
.stButton > button[kind="primary"]:hover { background-color:#14304f; }
.section-header { font-size:12px;font-weight:700;color:#6c757d;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px; }
.info-card { background:#f8f9fa;border-left:4px solid #1a3a5c;padding:10px 16px;border-radius:0 6px 6px 0;margin-bottom:10px;font-size:13px; }
</style>
"""

# ──────────────────────────────────────────────────────
# MAIN APP
# ──────────────────────────────────────────────────────

st.set_page_config(page_title="Kurir Toko — Route Optimizer", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
init_state()

# ════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## Kurir Toko")
    st.caption("Route Optimizer v11")
    st.divider()

    branches = st.session_state.branches
    st.markdown('<p class="section-header">Pilih Cabang Pengirim</p>', unsafe_allow_html=True)
    branch_options = {b["kode"]: f"{b['nama']}  ({b['kode']})" for b in branches}
    if st.session_state.selected_branch_kode not in branch_options:
        st.session_state.selected_branch_kode = branches[0]["kode"]

    selected_kode = st.radio("Cabang", options=list(branch_options.keys()),
                             format_func=lambda k: branch_options[k],
                             index=list(branch_options.keys()).index(st.session_state.selected_branch_kode),
                             label_visibility="collapsed", key="radio_cabang")
    if selected_kode != st.session_state.selected_branch_kode:
        st.session_state.selected_branch_kode = selected_kode
        st.session_state.hasil = None
        st.rerun()

    cabang_aktif = next(b for b in branches if b["kode"] == selected_kode)
    color_aktif  = BRANCH_COLORS.get(selected_kode, "#555")
    st.markdown(
        f'<div style="background:#f8f9fa;border-left:4px solid {color_aktif};'
        f'padding:10px 14px;border-radius:0 6px 6px 0;margin:8px 0 4px">'
        f'<strong>{cabang_aktif["nama"]}</strong><br>'
        f'<span style="font-size:12px;color:#6c757d">'
        f'Lat: {cabang_aktif["lat"]:.6f}<br>Lng: {cabang_aktif["lng"]:.6f}</span></div>',
        unsafe_allow_html=True)
    st.divider()

    road_factor = st.slider("Faktor koreksi jalan", 1.0, 2.0, 1.3, 0.05,
                            help="1.0 = garis lurus. 1.3 = estimasi jalan kota normal.")
    st.divider()

    st.markdown('<p class="section-header">Kelola Cabang</p>', unsafe_allow_html=True)
    to_delete = None
    for i, b in enumerate(branches):
        with st.expander(f"{b['nama']} ({b['kode']})", expanded=False):
            ca, cb = st.columns(2)
            b["kode"] = ca.text_input("Kode", value=b["kode"], max_chars=5, key=f"kode_{i}").strip().upper()
            b["nama"] = cb.text_input("Nama", value=b["nama"], key=f"nama_{i}")
            cc, cd   = st.columns(2)
            b["lat"]  = cc.number_input("Latitude",  value=float(b["lat"]), format="%.6f", key=f"lat_{i}")
            b["lng"]  = cd.number_input("Longitude", value=float(b["lng"]), format="%.6f", key=f"lng_{i}")
            if st.button("Hapus", key=f"del_{i}") and len(branches) > 1:
                to_delete = i
    if to_delete is not None:
        st.session_state.branches.pop(to_delete)
        st.session_state.selected_branch_kode = st.session_state.branches[0]["kode"]
        st.rerun()

    st.divider()
    with st.expander("+ Tambah cabang baru"):
        nk = st.text_input("Kode*", placeholder="SBY2", key="new_kode")
        nn = st.text_input("Nama*", placeholder="Surabaya Timur", key="new_nama")
        nc, nd = st.columns(2)
        nl = nc.number_input("Latitude",  value=-7.0, format="%.6f", key="new_lat")
        ng = nd.number_input("Longitude", value=112.0, format="%.6f", key="new_lng")
        if st.button("Tambahkan", use_container_width=True, type="primary"):
            if not nk or not nn:
                st.error("Kode dan Nama wajib diisi.")
            elif nk.upper() in [b["kode"] for b in branches]:
                st.error(f"Kode '{nk.upper()}' sudah ada.")
            else:
                st.session_state.branches.append({"kode": nk.strip().upper(), "nama": nn, "lat": nl, "lng": ng})
                st.rerun()

    if st.button("Reset ke default", use_container_width=True):
        st.session_state.branches              = [b.copy() for b in BRANCHES_DEFAULT]
        st.session_state.selected_branch_kode = BRANCHES_DEFAULT[0]["kode"]
        st.session_state.hasil                 = None
        st.rerun()


# ════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════

st.title("Kurir Toko — Route Optimizer")
st.caption("Pengurutan rute pengiriman otomatis dari file orders marketplace.")
st.divider()

color_aktif = BRANCH_COLORS.get(cabang_aktif["kode"], "#555")
st.markdown(
    f'<div style="background:#f0f4f8;border-left:5px solid {color_aktif};'
    f'padding:12px 18px;border-radius:0 8px 8px 0;margin-bottom:16px">'
    f'Mengatur rute dari cabang '
    f'<strong style="color:{color_aktif}">{cabang_aktif["nama"]} ({cabang_aktif["kode"]})</strong>. '
    f'Ganti cabang lewat panel kiri.</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════
# BAGIAN 1: UPLOAD FILE
# ════════════════════════════════════════════════════════

st.subheader("Upload File Orders")

col_up, col_info = st.columns([3, 2])
with col_up:
    uploaded = st.file_uploader(
        "Upload orders.xlsx dari sistem marketplace",
        type=["xlsx", "xls", "csv"],
        help="Kolom wajib: Shipping Address. Kolom lain opsional.",
    )
with col_info:
    st.markdown(
        '<div class="info-card">'
        '<b>Kolom yang dibaca:</b><br>'
        'Invoice NO &nbsp;·&nbsp; Order Date &nbsp;·&nbsp; SO Number<br>'
        'Recipient Name &nbsp;·&nbsp; Recipient Phone<br>'
        'Items Name &nbsp;·&nbsp; Items SKU &nbsp;·&nbsp; Qty &nbsp;·&nbsp; Harga<br>'
        'Total Amount &nbsp;·&nbsp; Payment Status<br>'
        'Fulfillment Status &nbsp;·&nbsp; Shipping Courier<br>'
        '<i>Filter otomatis: Kurir Toko</i>'
        '</div>', unsafe_allow_html=True)

if uploaded:
    df_orders, pesan = load_orders_excel(uploaded)
    if df_orders is None:
        st.error(pesan)
    else:
        st.session_state.orders_df = df_orders
        st.success(pesan)

        # ── Ringkasan 5 metrik ──
        n_kt       = df_orders["Shipping Courier"].apply(is_kurir_toko).sum()
        n_paid     = (df_orders["Payment Status"].str.lower() == "paid").sum()
        n_delivered= df_orders["Fulfillment Status"].str.lower().str.contains("delivered").sum()
        total_val  = df_orders["Total Amount"].sum()

        st.markdown("#### Ringkasan File")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Order",   len(df_orders))
        m2.metric("Kurir Toko",    int(n_kt))
        m3.metric("Sudah Bayar",   int(n_paid))
        m4.metric("Delivered",     int(n_delivered))
        m5.metric("Total Nilai",   format_currency(total_val))

        # ── Filter toggle ──
        st.session_state.filter_kt = st.toggle(
            "Tampilkan hanya Kurir Toko",
            value=st.session_state.filter_kt,
            help="Filter otomatis berdasarkan kolom Shipping Courier",
        )

        df_view = df_orders[df_orders["Shipping Courier"].apply(is_kurir_toko)] \
                  if st.session_state.filter_kt else df_orders

        if df_view.empty:
            st.warning("Tidak ada order Kurir Toko. Matikan toggle filter untuk lihat semua.")
        else:
            st.markdown(f"#### Daftar Order ({len(df_view)} baris)")

            # Kolom tampilan tabel — sesuai data orders.xlsx
            SHOW_COLS = {
                "Invoice NO":        "Invoice",
                "Order Date":        "Tgl Order",
                "SO Number":         "SO Number",
                "Recipient Name":    "Penerima",
                "Items Name":        "Barang",
                "Items SKU":         "SKU",
                "Items Quantity":    "Qty",
                "Total Amount":      "Total (Rp)",
                "Payment Status":    "Bayar",
                "Fulfillment Status":"Status",
                "Shipping Courier":  "Kurir",
                "Shipping Address":  "Alamat Tujuan",
            }
            avail   = [c for c in SHOW_COLS if c in df_view.columns]
            df_disp = df_view[avail].copy()
            df_disp.columns = [SHOW_COLS[c] for c in avail]
            if "Tgl Order" in df_disp.columns:
                df_disp["Tgl Order"] = df_disp["Tgl Order"].apply(format_date)
            if "Total (Rp)" in df_disp.columns:
                df_disp["Total (Rp)"] = df_disp["Total (Rp)"].apply(
                    lambda x: format_currency(x) if str(x).replace(".", "").replace(",","").isdigit() else x)

            st.dataframe(df_disp, use_container_width=True, height=320, hide_index=True,
                         column_config={
                             "Barang":       st.column_config.TextColumn(width="large"),
                             "Alamat Tujuan":st.column_config.TextColumn(width="large"),
                         })

            if st.button(f"Gunakan {len(df_view)} order ini untuk routing →",
                         type="primary", use_container_width=True):
                st.session_state.pkg_df = df_view.reset_index(drop=True)
                st.session_state.hasil  = None
                st.success(f"{len(df_view)} order siap. Klik 'Hitung Rute Optimal' di bawah.")

if st.session_state.orders_df is None:
    st.info("Upload file orders.xlsx dari sistem marketplace di atas.")
    with st.expander("Lihat format kolom yang dikenali"):
        st.markdown("""
| Kolom di file | Fungsi | Wajib? |
|---|---|---|
| `Shipping Address` | Alamat tujuan untuk geocoding | ✅ Ya |
| `Invoice NO` | Nomor invoice ditampilkan di hasil | Disarankan |
| `Order Date` | Tanggal pemesanan | Disarankan |
| `SO Number` | Nomor SO | Opsional |
| `Recipient Name` | Nama penerima | Opsional |
| `Recipient Phone` | No. HP penerima | Opsional |
| `Items Name` | Nama barang (tampil di tabel & peta) | Opsional |
| `Items SKU` | Kode SKU | Opsional |
| `Items Quantity` | Jumlah barang | Opsional |
| `Items Price` | Harga satuan | Opsional |
| `Total Amount` | Total nilai order | Opsional |
| `Payment Status` | Status pembayaran | Opsional |
| `Fulfillment Status` | Status pengiriman | Opsional |
| `Shipping Courier` | Filter Kurir Toko otomatis | Opsional |
        """)


# ════════════════════════════════════════════════════════
# BAGIAN 2: HITUNG RUTE
# ════════════════════════════════════════════════════════

st.divider()
col_hitung, col_reset = st.columns([4, 1])
with col_hitung:
    run = st.button("Hitung Rute Optimal", type="primary", use_container_width=True)
with col_reset:
    if st.button("Reset hasil", use_container_width=True):
        st.session_state.hasil = None
        st.session_state.laporan_akurasi = None
        st.rerun()

if run:
    if st.session_state.pkg_df is None or len(st.session_state.pkg_df) == 0:
        st.error("Upload file dan klik 'Gunakan untuk routing' dulu.")
        st.stop()

    pkg_list = st.session_state.pkg_df.to_dict("records")
    pkg_list = [p for p in pkg_list
                if str(p.get("Shipping Address", "")).strip().lower()
                not in ("", "indonesia", "-", "nan")]

    if not pkg_list:
        st.error("Tidak ada alamat yang bisa diproses.")
        st.stop()

    bar = st.progress(0, text="Geocoding alamat...")
    geocoded, failed = [], []

    for i, pkg in enumerate(pkg_list):
        raw = str(pkg.get("Shipping Address", ""))
        bar.progress((i+1)/len(pkg_list),
                     text=f"Geocoding [{i+1}/{len(pkg_list)}]: {raw[:55]}...")
        lat, lng, sumber, akurasi = geocode(raw)
        if lat is None:
            failed.append({"Invoice NO": pkg.get("Invoice NO","-"), "Alamat": raw})
        else:
            geocoded.append({**pkg, "lat": lat, "lng": lng,
                             "geocode_sumber": sumber, "akurasi": akurasi})
    bar.empty()

    st.session_state["_last_geocoded"] = geocoded
    st.session_state.laporan_akurasi   = buat_laporan_akurasi(geocoded, failed)

    if failed:
        with st.expander(f"⚠ {len(failed)} alamat gagal di-geocode (dilewati)", expanded=True):
            st.warning("Coba sederhanakan: hapus lantai/blok, cukup nama jalan + kota.")
            for f in failed:
                st.code(f"{f.get('Invoice NO','-')} | {f.get('Alamat','')}")

    paket_ok = [p for p in geocoded if p.get("akurasi") != "gagal"]
    if not paket_ok:
        st.error("Tidak ada alamat yang berhasil diproses.")
        st.stop()

    methods = {}
    for p in geocoded:
        m = p["geocode_sumber"]
        methods[m] = methods.get(m, 0) + 1
    st.info(f"{len(geocoded)} berhasil — " + ", ".join(f"{v} via {k}" for k,v in methods.items()))

    b = cabang_aktif
    route, total_lurus = nn_tsp(b["lat"], b["lng"], paket_ok, road_factor)

    st.session_state.hasil = {
        "branch":       b,
        "route":        route,
        "total_lurus":  total_lurus,
        "total_jalan":  round(total_lurus * road_factor, 2),
        "total_paket":  len(route),
        "total_nilai":  sum(p.get("Total Amount", 0) for p in route),
    }
    st.success(f"Rute selesai — {len(route)} paket dari cabang {b['nama']}.")


# ════════════════════════════════════════════════════════
# BAGIAN 3: HASIL RUTE
# ════════════════════════════════════════════════════════

if st.session_state.hasil:
    hasil = st.session_state.hasil
    b     = hasil["branch"]
    route = hasil["route"]
    color = BRANCH_COLORS.get(b["kode"], "#555")

    st.divider()
    st.subheader("Hasil Rute Pengiriman")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total paket",       hasil["total_paket"])
    m2.metric("Estimasi jarak",    f"{hasil['total_jalan']:.1f} km")
    m3.metric("Total nilai order", format_currency(hasil["total_nilai"]))
    m4.metric("Cabang",            f"{b['nama']} ({b['kode']})")

    st.divider()
    tab_rute, tab_peta, tab_laporan = st.tabs(["Urutan Pengiriman", "Peta Rute", "Laporan Akurasi"])

    with tab_rute:
        st.markdown(
            f'<div style="border-left:4px solid {color};padding:10px 16px;'
            f'background:#f8f9fa;border-radius:0 6px 6px 0;margin-bottom:14px">'
            f'<strong>Cabang {b["nama"]} ({b["kode"]})</strong>'
            f'<span style="color:#6c757d;font-size:13px;margin-left:16px">'
            f'{hasil["total_paket"]} paket &nbsp;·&nbsp; ~{hasil["total_jalan"]} km</span></div>',
            unsafe_allow_html=True)

        rows = []
        for i, pkg in enumerate(route, 1):
            rows.append({
                "No.":             i,
                "Invoice NO":      pkg.get("Invoice NO", "-"),
                "Tgl Order":       format_date(pkg.get("Order Date", "-")),
                "SO Number":       pkg.get("SO Number", "-"),
                "Penerima":        pkg.get("Recipient Name", "-"),
                "No. HP":          str(pkg.get("Recipient Phone", "-"))[:15],
                "Barang":          str(pkg.get("Items Name", "-"))[:60],
                "SKU":             pkg.get("Items SKU", "-"),
                "Qty":             pkg.get("Items Quantity", "-"),
                "Total (Rp)":      format_currency(pkg.get("Total Amount", 0)),
                "Bayar":           pkg.get("Payment Status", "-"),
                "Status":          pkg.get("Fulfillment Status", "-"),
                "Jarak (km)":      pkg["jarak_lurus_km"],
                "Est. Jalan (km)": pkg["jarak_jalan_km"],
                "Akurasi":         badge_akurasi(pkg.get("akurasi", "")),
                "Alamat Tujuan":   str(pkg.get("Shipping Address", "-"))[:80],
            })

        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True, height=440,
            column_config={
                "No.":           st.column_config.NumberColumn(width="small"),
                "Barang":        st.column_config.TextColumn(width="large"),
                "Alamat Tujuan": st.column_config.TextColumn(width="large"),
                "Akurasi":       st.column_config.TextColumn(width="medium"),
            })

        if any(p.get("akurasi") in ("sedang","rendah") for p in route):
            st.warning("Beberapa koordinat adalah perkiraan wilayah/kota. Urutan tetap dioptimalkan.")

    with tab_peta:
        st.caption("Ikon rumah = gudang cabang. Hover marker untuk detail paket.")
        st_folium(buat_peta(b, route), use_container_width=True, height=540)

    with tab_laporan:
        if st.session_state.laporan_akurasi:
            tampilkan_laporan_akurasi(st.session_state.laporan_akurasi)
        else:
            st.info("Laporan muncul setelah geocoding selesai.")

    # ── Download CSV hasil rute ──
    st.divider()
    all_rows = []
    for i, pkg in enumerate(route, 1):
        all_rows.append({
            "No. Urutan":         i,
            "Invoice NO":         pkg.get("Invoice NO", ""),
            "SO Number":          pkg.get("SO Number", ""),
            "Tgl Order":          format_date(pkg.get("Order Date", "")),
            "Penerima":           pkg.get("Recipient Name", ""),
            "No. HP":             pkg.get("Recipient Phone", ""),
            "Barang":             pkg.get("Items Name", ""),
            "SKU":                pkg.get("Items SKU", ""),
            "Qty":                pkg.get("Items Quantity", ""),
            "Total Amount (Rp)":  pkg.get("Total Amount", ""),
            "Payment Status":     pkg.get("Payment Status", ""),
            "Fulfillment Status": pkg.get("Fulfillment Status", ""),
            "Alamat Tujuan":      pkg.get("Shipping Address", ""),
            "Jarak Lurus (km)":   pkg["jarak_lurus_km"],
            "Est. Jalan (km)":    pkg["jarak_jalan_km"],
            "Lat":                round(pkg["lat"], 6),
            "Lng":                round(pkg["lng"], 6),
            "Akurasi Lokasi":     badge_akurasi(pkg.get("akurasi", "")),
            "Geocoder":           pkg.get("geocode_sumber", ""),
            "Cabang":             b["nama"],
            "Kode Cabang":        b["kode"],
        })

    csv = pd.DataFrame(all_rows).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download hasil rute (.csv)",
        data=csv,
        file_name=f"rute_{b['kode']}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )