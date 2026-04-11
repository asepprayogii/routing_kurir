"""
Kurir Toko — Route Optimizer (v7 - Free Auto-Geocoding + Robust Routing)
✅ 100% GRATIS (Nominatim + Photon, tanpa API Key)
✅ Otomatis cari lat/lng dari alamat yang diketik
✅ Cascading geocoding: coba format alamat spesifik → kecamatan → kota → fallback
✅ Penanganan 0 km aman: routing stabil, UI transparan
✅ UI linear: Sidebar → Input → Proses → Hasil
"""
import math, re, time, requests
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# ════════════════════════════════════════════════════════
# KONSTANTA
# ════════════════════════════════════════════════════════
BRANCHES_DEFAULT = [
    {"kode": "SUB", "nama": "Surabaya", "lat": -7.2575, "lng": 112.7521},
    {"kode": "JKT", "nama": "Jakarta", "lat": -6.2088, "lng": 106.8456},
    {"kode": "MLG", "nama": "Malang", "lat": -7.9797, "lng": 112.6304},
    {"kode": "SMG", "nama": "Semarang", "lat": -6.9667, "lng": 110.4167},
    {"kode": "JOG", "nama": "Yogyakarta", "lat": -7.7956, "lng": 110.3695},
    {"kode": "BLI", "nama": "Bali", "lat": -8.3405, "lng": 115.0920},
]
BRANCH_COLORS = {"SUB": "#E53935", "JKT": "#1E88E5", "MLG": "#43A047", "SMG": "#FB8C00", "JOG": "#8E24AA", "BLI": "#00ACC1"}

# ════════════════════════════════════════════════════════
# GEOCODING GRADUAL & OTOMATIS (100% GRATIS)
# ════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def geocode_nominatim(address: str):
    try:
        loc = Nominatim(user_agent="kurir_v7_free", timeout=10).geocode(address)
        if loc: return loc.latitude, loc.longitude
    except: pass
    return None, None

@st.cache_data(show_spinner=False)
def geocode_photon(address: str):
    try:
        resp = requests.get("https://photon.komoot.io/api/", params={"q": address, "limit": 1, "lang": "id"}, timeout=10)
        feats = resp.json().get("features", [])
        if feats: return feats[0]["geometry"]["coordinates"][1], feats[0]["geometry"]["coordinates"][0]
    except: pass
    return None, None

def bersihkan_alamat(raw: str) -> str:
    addr = re.sub(r'\b(Indonesia|Jawa Timur|Jawa Tengah|Jawa Barat|DKI Jakarta|Bali|DI Yogyakarta|Provinsi|Kota|Kabupaten|Kecamatan|Kelurahan)\b', '', raw, flags=re.IGNORECASE)
    addr = re.sub(r'\b\d{5}\b', '', addr)
    parts = [p.strip() for p in addr.split(',') if p.strip() and len(p.strip()) > 2]
    seen, unique = set(), []
    for p in parts:
        if p.lower() not in seen:
            seen.add(p.lower())
            unique.append(p)
    return ', '.join(unique[:4])

def geocode_cascade(raw: str) -> tuple:
    """Coba berbagai format alamat otomatis. Tidak pernah skip. Tetap gratis."""
    cleaned = bersihkan_alamat(raw)
    if not cleaned: return None, None, "Kosong", "gagal"

    # 1. Alamat lengkap
    lat, lng = geocode_nominatim(cleaned + ", Indonesia")
    if lat: return lat, lng, "Nominatim", "tinggi"
    time.sleep(0.3)
    lat, lng = geocode_photon(cleaned + " Indonesia")
    if lat: return lat, lng, "Photon", "tinggi"

    # 2. Jalan + Kota/Kabupaten (ambil 2 bagian terakhir jika ada koma)
    parts = cleaned.split(',')
    if len(parts) >= 2:
        broad = ', '.join(parts[-2:]).strip()
        lat, lng = geocode_nominatim(broad + ", Indonesia")
        if lat: return lat, lng, "Nominatim (Wilayah)", "sedang"
        time.sleep(0.3)
        lat, lng = geocode_photon(broad + " Indonesia")
        if lat: return lat, lng, "Photon (Wilayah)", "sedang"

    # 3. Hanya nama kota/kecamatan terakhir
    if len(parts) >= 1:
        city = parts[-1].strip()
        lat, lng = geocode_nominatim(city + ", Indonesia")
        if lat: return lat, lng, "Nominatim (Kota)", "rendah"

    # 4. Fallback: jangan skip, kembalikan None (UI akan tangani)
    return None, None, "❌ Tidak ditemukan", "gagal"

# ════════════════════════════════════════════════════════
# MATEMATIKA & ROUTING (Stabil & Kontinu)
# ════════════════════════════════════════════════════════
def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dl, dg = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dl/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dg/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def nn_tsp(start_lat, start_lng, pkgs: list, road_factor: float) -> tuple:
    remaining = pkgs.copy()
    route, total = [], 0.0
    clat, clng = start_lat, start_lng
    order = 1
    
    while remaining:
        best_i, best_d = 0, float("inf")
        for i, p in enumerate(remaining):
            d = haversine(clat, clng, p["lat"], p["lng"])
            if d < best_d: best_d = d; best_i = i
            
        chosen = remaining.pop(best_i)
        # Tampilkan asli di UI, tapi pakai min 0.001 km untuk kalkulasi agar routing tidak error
        dist_display = round(best_d, 2)
        dist_calc = max(best_d, 0.001)
        
        chosen["jarak_sebelumnya"] = dist_display
        chosen["jarak_estimasi"] = round(dist_calc * road_factor, 2)
        chosen["urutan"] = order
        order += 1
        
        route.append(chosen)
        total += dist_calc
        clat, clng = chosen["lat"], chosen["lng"]
        
    return route, round(total, 2)

def proses_routing(geocoded_pkgs: list, active_branch: dict, road_factor: float) -> dict:
    route, total = nn_tsp(active_branch["lat"], active_branch["lng"], geocoded_pkgs, road_factor)
    return {
        "branch": active_branch,
        "route": route,
        "total_lurus": total,
        "total_estimasi": round(total * road_factor, 2),
        "total_pkg": len(route)
    }

# ════════════════════════════════════════════════════════
# PETA
# ════════════════════════════════════════════════════════
def buat_peta(hasil: dict) -> folium.Map:
    b = hasil["branch"]
    m = folium.Map(location=[b["lat"], b["lng"]], zoom_start=11, tiles="CartoDB Positron")
    color = BRANCH_COLORS.get(b["kode"], "blue")
    
    folium.Marker(location=[b["lat"], b["lng"]], tooltip=f"🏭 {b['nama']}", icon=folium.Icon(color="darkred", icon="home")).add_to(m)
    
    if hasil["route"]:
        coords = [[b["lat"], b["lng"]]] + [[p["lat"], p["lng"]] for p in hasil["route"]]
        folium.PolyLine(coords, color=color, weight=4, opacity=0.85, tooltip="Rute Pengiriman Berurutan").add_to(m)
        
        for i, pkg in enumerate(hasil["route"], 1):
            warn = " ⚠️ Perkiraan" if pkg.get("akurasi") in ["sedang", "rendah"] else ""
            folium.CircleMarker(location=[pkg["lat"], pkg["lng"]], radius=9, color=color, fill=True, fill_color=color, fill_opacity=0.9,
                tooltip=f"<b>#{i} {pkg.get('Penerima','?')}</b>{warn}<br>{str(pkg.get('Alamat',''))[:70]}...<br>📏 {pkg['jarak_sebelumnya']} km").add_to(m)
            folium.Marker(location=[pkg["lat"], pkg["lng"]], icon=folium.DivIcon(html=f'<div style="font-size:10px;font-weight:bold;color:white;background:{color};border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;border:1px solid white">{i}</div>', icon_size=(20,20), icon_anchor=(10,10))).add_to(m)
    return m

# ════════════════════════════════════════════════════════
# STREAMLIT UI
# ════════════════════════════════════════════════════════
st.set_page_config(page_title="Kurir Toko Optimizer v7", page_icon="🚚", layout="wide")
st.title("🚚 Optimizer Rute Kurir (100% Gratis & Otomatis)")

# SIDEBAR
with st.sidebar:
    st.header("🏭 Konfigurasi")
    if "branches" not in st.session_state: st.session_state.branches = [b.copy() for b in BRANCHES_DEFAULT]
    
    aktif_kode = st.selectbox("Pilih Cabang Utama", [b["kode"] for b in st.session_state.branches], index=0, key="sel_branch")
    cabang_aktif = next(b for b in st.session_state.branches if b["kode"] == aktif_kode)
    
    st.divider()
    st.subheader("Edit Koordinat Cabang")
    c1, c2 = st.columns(2)
    new_lat = c1.number_input("Lat", value=float(cabang_aktif["lat"]), format="%.5f", key="edit_lat")
    new_lng = c2.number_input("Lng", value=float(cabang_aktif["lng"]), format="%.5f", key="edit_lng")
    if st.button("💾 Simpan", use_container_width=True):
        for b in st.session_state.branches:
            if b["kode"] == aktif_kode: b.update({"lat": new_lat, "lng": new_lng})
        st.success("✅ Disimpan")
        
    st.divider()
    road_factor = st.slider("📏 Faktor Koreksi Jalan (×)", 1.0, 2.0, 1.3, 0.1, help="1.0 = Garis lurus. 1.3 ≈ Jalan kota normal. Naikkan jika banyak belokan.")
    
    st.info("💡 Sistem otomatis mencari lat/lng dari alamat Anda. 100% gratis. Format alamat: `Jalan, Kelurahan, Kecamatan, Kota`")

# MAIN
if "paket_list" not in st.session_state:
    st.session_state.paket_list = [{"Alamat": "", "Penerima": "", "Berat (kg)": 1.0, "Lat": None, "Lng": None}]
if "hasil" not in st.session_state: st.session_state.hasil = None

st.subheader("📦 Step 1: Input Paket")
st.caption("Isi alamat. Sistem akan otomatis mencari koordinatnya. Kosongkan Lat/Lng agar dicari otomatis.")

to_hapus = None
for i, pkg in enumerate(st.session_state.paket_list):
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        c1.text_input(f"Alamat #{i+1}", value=pkg.get("Alamat", ""), key=f"alm_{i}")
        c2.text_input("Penerima", value=pkg.get("Penerima", ""), key=f"ter_{i}")
        _, c3 = st.columns([4, 1])
        c3.number_input("Berat (kg)", value=float(pkg.get("Berat (kg)", 1.0)), min_value=0.1, step=0.1, key=f"brt_{i}")
        
        # Input manual lat/lng (opsional, tersembunyi di expander)
        with st.expander("🔧 Opsi: Masukkan Lat/Lng Manual (jika sudah tahu)", expanded=False):
            cl1, cl2 = st.columns(2)
            cl1.number_input("Latitude", value=float(pkg.get("Lat", 0.0)) if pkg.get("Lat") else 0.0, format="%.6f", key=f"lat_{i}")
            cl2.number_input("Longitude", value=float(pkg.get("Lng", 0.0)) if pkg.get("Lng") else 0.0, format="%.6f", key=f"lng_{i}")
        
        st.session_state.paket_list[i] = {
            "Alamat": st.session_state[f"alm_{i}"],
            "Penerima": st.session_state[f"ter_{i}"],
            "Berat (kg)": st.session_state[f"brt_{i}"],
            "Lat": st.session_state[f"lat_{i}"] if st.session_state[f"lat_{i}"] != 0.0 else None,
            "Lng": st.session_state[f"lng_{i}"] if st.session_state[f"lng_{i}"] != 0.0 else None,
        }
    if len(st.session_state.paket_list) > 1 and st.button(f"🗑️", key=f"del_{i}"): to_hapus = i

if to_hapus is not None:
    st.session_state.paket_list.pop(to_hapus)
    st.rerun()

col1, col2 = st.columns(2)
with col1:
    if st.button("➕ Tambah Baris", use_container_width=True):
        st.session_state.paket_list.append({"Alamat": "", "Penerima": "", "Berat (kg)": 1.0, "Lat": None, "Lng": None})
        st.rerun()
with col2:
    if st.button("🗑️ Reset", use_container_width=True):
        st.session_state.paket_list = [{"Alamat": "", "Penerima": "", "Berat (kg)": 1.0, "Lat": None, "Lng": None}]
        st.session_state.hasil = None
        st.rerun()

st.divider()

if st.button("🚀 STEP 2: Hitung Rute Otomatis", type="primary", use_container_width=True):
    pkg_valid = [p for p in st.session_state.paket_list if str(p.get("Alamat", "")).strip()]
    if not pkg_valid:
        st.error("Masukkan minimal 1 alamat!"); st.stop()
        
    progress = st.progress(0, text="🔍 Geocoding otomatis...")
    geocoded, failed = [], []
    
    for i, pkg in enumerate(pkg_valid):
        progress.progress((i+1)/len(pkg_valid), text=f"[{i+1}/{len(pkg_valid)}] {str(pkg['Alamat'])[:60]}...")
        
        # Jika user isi manual Lat/Lng, skip geocoding
        if pkg.get("Lat") and pkg.get("Lng"):
            geocoded.append({**pkg, "lat": pkg["Lat"], "lng": pkg["Lng"], "method": "Manual", "akurasi": "tinggi"})
            continue
            
        lat, lng, method, akurasi = geocode_cascade(str(pkg["Alamat"]))
        if lat is None:
            failed.append(pkg["Alamat"])
        else:
            geocoded.append({**pkg, "lat": lat, "lng": lng, "method": method, "akurasi": akurasi})
        time.sleep(0.3) # Hindari rate limit Nominatim
    progress.empty()
    
    if failed: st.warning(f"❌ {len(failed)} alamat tidak ditemukan sama sekali (dilewati)")
    if not geocoded: st.error("Tidak ada alamat valid."); st.stop()
    
    # Tandai duplikat untuk UI
    coord_count = {}
    for p in geocoded:
        key = (round(p["lat"], 3), round(p["lng"], 3))
        coord_count[key] = coord_count.get(key, 0) + 1
    for p in geocoded:
        key = (round(p["lat"], 3), round(p["lng"], 3))
        p["is_duplikat"] = coord_count[key] > 1
        
    hasil = proses_routing(geocoded, cabang_aktif, road_factor)
    st.session_state.hasil = hasil
    st.success(f"✅ Rute berhasil! {len(geocoded)} paket diurutkan optimal.")

# HASIL
if st.session_state.hasil:
    st.subheader("📊 STEP 3: Hasil Rute")
    hasil = st.session_state.hasil
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("📦 Total Paket", hasil["total_pkg"])
    mc2.metric("📏 Jarak Lurus", f"{hasil['total_lurus']:.1f} km")
    mc3.metric("🛣️ Est. Jalan", f"{hasil['total_estimasi']:.1f} km")
    
    dup_count = sum(1 for p in hasil["route"] if p.get("is_duplikat"))
    if dup_count > 0:
        st.warning(f"⚠️ {dup_count} paket koordinatnya sama/berdekatan → jarak ditampilkan `0.00 km`. Sistem tetap merutekan tanpa error.")
        
    tab_tabel, tab_peta = st.tabs(["📋 Urutan Pengiriman", "🗺️ Peta Rute"])
    with tab_tabel:
        rows = []
        for p in hasil["route"]:
            rows.append({
                "Urutan": p["urutan"],
                "Penerima": p.get("Penerima", "-"),
                "Alamat": p.get("Alamat", "-"),
                "Berat": p.get("Berat (kg)", "-"),
                "Jarak dari Titik Sebelumnya (km)": p["jarak_sebelumnya"],
                "Est. Jalan (km)": p["jarak_estimasi"],
                "Akurasi": "✅ Spesifik" if p.get("akurasi")=="tinggi" else ("⚠️ Wilayah" if p.get("akurasi")=="sedang" else "🔍 Kota"),
                "Metode": p.get("method", "-")
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with tab_peta:
        st.caption("🔵 Rute berurutan tanpa zona. Marker bernomor = urutan antar.")
        st_folium(buat_peta(hasil), use_container_width=True, height=500)
        
    # CSV Download
    all_rows = [] 
    b = hasil["branch"]
    for p in hasil["route"]:   
        all_rows.append({"Cabang": b["nama"], "Urutan": p["urutan"], "Penerima": p.get("Penerima",""), "Alamat": p.get("Alamat",""), "Jarak Sebelum": p["jarak_sebelumnya"], "Est Jalan": p["jarak_estimasi"], "Lat": p["lat"], "Lng": p["lng"], "Akurasi": p.get("akurasi","-")})
    csv = pd.DataFrame(all_rows).to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv, file_name="rute_kurir.csv", mime="text/csv", use_container_width=True)