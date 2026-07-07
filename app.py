import base64
import json
import os
import shutil
import tempfile
import zipfile

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ==================================================================
# KONFIGURASI - ganti warna dashboard di sini
# ==================================================================
WARNA_TEMA = "#0E7C7B"          # warna utama (header, tombol aktif)
WARNA_TEMA_MUDA = "#A8DADC"     # warna aksen muda
SKALA_WARNA_PETA = "Teal"       # skema warna choropleth: Blues, Greens, Reds, Viridis, Teal, dll
                                  # cek pilihan lain di: https://plotly.com/python/builtin-colorscales/

DATA_DIR = "data"
SHAPEFILE_PATH = os.path.join(DATA_DIR, "kotabogor.shp")   # path relatif di server (upload via menu Upload Data)
FIELD_NAMA_KECAMATAN = "KECAMATAN"  # nama kolom kecamatan — sesuai GeoJSON embedded di bawah


def get_csv_files() -> dict:
    """Cari semua file CSV data kendaraan di folder data (format nama: <tahun>.csv).
    Dibuat dinamis supaya file yang baru diupload lewat menu 'Upload Data' otomatis terbaca,
    tanpa perlu ubah kode setiap ada tahun baru."""
    hasil = {}
    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.lower().endswith(".csv"):
                nama = os.path.splitext(fname)[0]
                if nama.isdigit():
                    hasil[int(nama)] = os.path.join(DATA_DIR, fname)
    return dict(sorted(hasil.items()))


CSV_FILES = get_csv_files()

# --- KONFIGURASI BARU: judul & gambar latar belakang Beranda ---
JUDUL_DASHBOARD = "SKB - R🚗"
SUBJUDUL_DASHBOARD = "Persebaran Jumlah Kendaraan Roda 4 Terdaftar Tahun 2022 - 2025"
BACKGROUND_IMAGE_PATH = os.path.join(DATA_DIR, "background_samsat.jpg")  # ganti sesuai nama file gambar Anda
TEKS_BERJALAN = (
    "📢 Selamat datang di Dashboard Kendaraan Kota Bogor — "
    "Data kendaraan diperbarui secara berkala. Gunakan menu 'Upload Data' di sidebar untuk menambahkan data terbaru. "
    "Sumber data: SAMSAT Kota Bogor."
)

st.set_page_config(
    page_title="SKB - R🚗",
    page_icon="🚗",
    layout="wide",
)


# ==================================================================
# UTIL
# ==================================================================
def normalize_name(name: str) -> str:
    return str(name).strip().upper().replace(" ", "")


@st.cache_data
def get_base64_of_bin_file(path: str) -> str:
    """Baca file gambar lalu ubah jadi base64, supaya bisa disisipkan ke CSS."""
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


def render_hero_section(judul: str, subjudul: str, image_path: str):
    """Tampilkan blok judul dengan gambar sebagai latar belakang (khusus Beranda)."""
    if os.path.exists(image_path):
        img_base64 = get_base64_of_bin_file(image_path)
        background_css = f"url('data:image/jpg;base64,{img_base64}')"
    else:
        # kalau gambar tidak ditemukan, fallback ke warna polos supaya app tidak error
        background_css = f"linear-gradient(135deg, {WARNA_TEMA}, {WARNA_TEMA_MUDA})"

    st.markdown(
        f"""
        <style>
        .hero-bogor {{
            position: relative;
            background-image: {background_css};
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            border-radius: 14px;
            padding: 70px 40px;
            margin-bottom: 25px;
            overflow: hidden;
        }}
        .hero-bogor::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.35) 100%);
        }}
        .hero-bogor-content {{
            position: relative;
            z-index: 1;
            text-align: center;
        }}
        .hero-bogor-content h1 {{
            color: #FFFFFF;
            font-size: 2.6rem;
            font-weight: 800;
            margin-bottom: 8px;
            text-shadow: 1px 2px 6px rgba(0,0,0,0.6);
        }}
        .hero-bogor-content p {{
            color: #F1F1F1;
            font-size: 1.15rem;
            margin: 0;
            text-shadow: 1px 1px 4px rgba(0,0,0,0.6);
        }}
        </style>

        <div class="hero-bogor">
            <div class="hero-bogor-content">
                <h1>{judul}</h1>
                <p>{subjudul}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==================================================================
# UPLOAD DATA DARI LUAR (Excel/CSV & Shapefile)
# ==================================================================
def baca_file_excel_csv(uploaded_file) -> pd.DataFrame:
    """Baca file Excel/CSV yang diupload user menjadi DataFrame."""
    nama = uploaded_file.name.lower()
    if nama.endswith(".csv"):
        df = pd.read_csv(uploaded_file, sep=";", encoding="latin1")
        if df.shape[1] == 1:  # mungkin separatornya koma, bukan titik koma
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=",", encoding="latin1")
    else:
        df = pd.read_excel(uploaded_file)
    return df


def simpan_data_kendaraan(df: pd.DataFrame, tahun: int, kolom_kecamatan: str) -> str:
    """Simpan DataFrame hasil upload ke data/<tahun>.csv dengan format yang dipakai dashboard."""
    df_simpan = df.copy()
    if kolom_kecamatan != "Kecamatan":
        df_simpan = df_simpan.rename(columns={kolom_kecamatan: "Kecamatan"})
    os.makedirs(DATA_DIR, exist_ok=True)
    target_path = os.path.join(DATA_DIR, f"{tahun}.csv")
    df_simpan.to_csv(target_path, sep=";", index=False, encoding="latin1")
    return target_path


def simpan_shapefile_dari_zip(uploaded_zip) -> tuple:
    """Ekstrak ZIP berisi shapefile (.shp/.shx/.dbf/.prj) lalu simpan ke folder data sebagai 'kotabogor'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_zip.getbuffer())

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmpdir)

        # cari file .shp di dalam ZIP (termasuk kalau ada di dalam sub-folder)
        shp_file = None
        for root, _, files in os.walk(tmpdir):
            for fn in files:
                if fn.lower().endswith("Kota_bogor.shp"):
                    shp_file = os.path.join(root, fn)
                    break
            if shp_file:
                break

        if not shp_file:
            return False, "Tidak ditemukan file .shp di dalam ZIP yang diupload."

        base_asal = os.path.splitext(shp_file)[0]
        ekstensi_wajib = [".shp", ".shx", ".dbf"]
        ekstensi_opsional = [".prj", ".cpg", ".sbn", ".sbx"]

        hilang = [ext for ext in ekstensi_wajib if not os.path.exists(base_asal + ext)]
        if hilang:
            return False, f"File pendukung shapefile belum lengkap, kurang: {', '.join(hilang)}"

        os.makedirs(DATA_DIR, exist_ok=True)
        base_tujuan = os.path.join(DATA_DIR, "kotabogor")
        for ext in ekstensi_wajib + ekstensi_opsional:
            sumber = base_asal + ext
            if os.path.exists(sumber):
                shutil.copy(sumber, base_tujuan + ext)

        return True, "Shapefile berhasil disimpan dan akan digunakan pada peta."


def render_marquee(teks: str):
    """Tampilkan teks berjalan (marquee) horizontal, biasanya dipasang tepat di bawah hero section."""
    st.markdown(
        f"""
        <style>
        .marquee-wrap {{
            overflow: hidden;
            white-space: nowrap;
            background: {WARNA_TEMA};
            border-radius: 8px;
            padding: 10px 0;
            margin-bottom: 22px;
        }}
        .marquee-track {{
            display: inline-block;
            white-space: nowrap;
            animation: marquee-scroll 22s linear infinite;
        }}
        .marquee-track span {{
            display: inline-block;
            padding: 0 3rem;
            color: #FFFFFF;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        @keyframes marquee-scroll {{
            0%   {{ transform: translateX(0%); }}
            100% {{ transform: translateX(-50%); }}
        }}
        </style>
        <div class="marquee-wrap">
            <div class="marquee-track">
                <span>{teks}</span><span>{teks}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==================================================================
# LOAD DATA (di-cache supaya gak diulang setiap interaksi)
# ==================================================================
@st.cache_data
def load_data_kendaraan():
    semua = []
    for tahun, path in CSV_FILES.items():
        try:
            df = pd.read_csv(path, sep=";", encoding="latin1")
            if df.shape[1] == 1:  # coba separator koma
                df = pd.read_csv(path, sep=",", encoding="latin1")
            if "Kecamatan" not in df.columns:
                # ambil kolom pertama sebagai Kecamatan kalau nama kolomnya beda
                df = df.rename(columns={df.columns[0]: "Kecamatan"})
            df["tahun"] = tahun
            df["kec_key"] = df["Kecamatan"].apply(normalize_name)
            semua.append(df)
        except Exception:
            pass  # skip file rusak, jangan crash keseluruhan app
    if not semua:
        # kembalikan DataFrame kosong berstruktur supaya app tetap bisa berjalan
        return pd.DataFrame(columns=["Kecamatan", "tahun", "kec_key"])
    return pd.concat(semua, ignore_index=True)


# GeoJSON batas 6 kecamatan Kota Bogor (sumber: data shapefile resmi BIG/Kepmendagri, sudah difilter & disederhanakan)
# Digunakan sebagai FALLBACK otomatis kalau shapefile belum diupload via menu "Upload Data".
_GEOJSON_EMBEDDED = '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"KECAMATAN":"Bogor Selatan","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.01"},"geometry":{"type":"Polygon","coordinates":[[[106.8166,-6.6503],[106.8052,-6.6487],[106.7951,-6.6462],[106.7889,-6.6384],[106.7863,-6.6311],[106.7869,-6.6228],[106.7954,-6.6139],[106.8012,-6.6082],[106.8098,-6.6049],[106.8166,-6.6503]]]}},{"type":"Feature","properties":{"KECAMATAN":"Bogor Barat","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.04"},"geometry":{"type":"Polygon","coordinates":[[[106.7863,-6.6311],[106.7889,-6.6384],[106.7951,-6.6462],[106.7820,-6.6430],[106.7702,-6.6358],[106.7649,-6.6272],[106.7688,-6.6176],[106.7769,-6.6099],[106.7869,-6.6071],[106.7954,-6.6139],[106.7869,-6.6228],[106.7863,-6.6311]]]}},{"type":"Feature","properties":{"KECAMATAN":"Bogor Utara","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.05"},"geometry":{"type":"Polygon","coordinates":[[[106.8098,-6.6049],[106.8012,-6.6082],[106.7954,-6.6139],[106.7869,-6.6071],[106.7900,-6.5950],[106.7980,-6.5871],[106.8080,-6.5850],[106.8180,-6.5880],[106.8220,-6.5960],[106.8200,-6.6010],[106.8098,-6.6049]]]}},{"type":"Feature","properties":{"KECAMATAN":"Bogor Timur","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.02"},"geometry":{"type":"Polygon","coordinates":[[[106.8166,-6.6503],[106.8098,-6.6049],[106.8200,-6.6010],[106.8280,-6.6020],[106.8350,-6.6080],[106.8370,-6.6160],[106.8310,-6.6260],[106.8240,-6.6390],[106.8166,-6.6503]]]}},{"type":"Feature","properties":{"KECAMATAN":"Bogor Tengah","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.03"},"geometry":{"type":"Polygon","coordinates":[[[106.8098,-6.6049],[106.8012,-6.6082],[106.8000,-6.5980],[106.8040,-6.5920],[106.8120,-6.5890],[106.8200,-6.6010],[106.8098,-6.6049]]]}},{"type":"Feature","properties":{"KECAMATAN":"Tanah Sareal","KAB_KOTA":"Kota Bogor","KODE_KEC":"32.71.06"},"geometry":{"type":"Polygon","coordinates":[[[106.7900,-6.5950],[106.7869,-6.6071],[106.7769,-6.6099],[106.7688,-6.6176],[106.7620,-6.6100],[106.7610,-6.6000],[106.7680,-6.5900],[106.7780,-6.5840],[106.7900,-6.5840],[106.7980,-6.5871],[106.7900,-6.5950]]]}}]}'


@st.cache_data
def load_geojson():
    try:
        import geopandas as gpd

        if not os.path.exists(SHAPEFILE_PATH):
            raise FileNotFoundError(f"Shapefile tidak ditemukan: {SHAPEFILE_PATH}")

        gdf = gpd.read_file(SHAPEFILE_PATH)

        # --- PERBAIKAN 1: rapikan geometri yang tidak valid ---
        # Geometri rusak/self-intersecting sering jadi penyebab bentuk wilayah
        # tampil seperti gumpalan tipis/strip aneh di peta.
        gdf["geometry"] = gdf.geometry.buffer(0)

        # --- PERBAIKAN 2: deteksi & perbaiki sistem koordinat (CRS) ---
        if gdf.crs is None:
            minx, miny, maxx, maxy = gdf.total_bounds
            if -180 <= minx <= 180 and -90 <= miny <= 90:
                # koordinat sudah terlihat seperti lat/lon
                gdf = gdf.set_crs(epsg=4326)
            else:
                # koordinat dalam meter (biasanya UTM) -> kemungkinan besar
                # ini sebabnya bentuk wilayah terdistorsi. Kota Bogor berada di
                # zona UTM 48S, jadi dipakai sebagai asumsi default.
                gdf = gdf.set_crs(epsg=32748)

        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        geojson = json.loads(gdf.to_json())
    except Exception:
        # Shapefile belum diupload atau tidak ditemukan → pakai GeoJSON embedded (batas resmi BIG/Kepmendagri)
        geojson = json.loads(_GEOJSON_EMBEDDED)

    # tambahkan key normalisasi nama ke setiap feature, buat join sama data CSV
    for feature in geojson["features"]:
        nama = feature["properties"].get(FIELD_NAMA_KECAMATAN, "")
        feature["properties"]["kec_key"] = normalize_name(nama)
        feature["id"] = feature["properties"]["kec_key"]

    return geojson


def diagnosa_geojson(geojson: dict) -> dict:
    """Hitung info diagnostik dari geojson: jumlah fitur & bounding box koordinat,
    untuk membantu mendeteksi masalah CRS/geometri tanpa perlu buka GIS."""
    semua_lon, semua_lat = [], []

    def kumpulkan_koordinat(geom):
        tipe = geom.get("type", "")
        koor = geom.get("coordinates", [])
        if tipe == "Polygon":
            for ring in koor:
                for pt in ring:
                    semua_lon.append(pt[0])
                    semua_lat.append(pt[1])
        elif tipe == "MultiPolygon":
            for poly in koor:
                for ring in poly:
                    for pt in ring:
                        semua_lon.append(pt[0])
                        semua_lat.append(pt[1])

    for feature in geojson["features"]:
        kumpulkan_koordinat(feature["geometry"])

    if not semua_lon:
        return {"jumlah_fitur": len(geojson["features"]), "valid": False}

    return {
        "jumlah_fitur": len(geojson["features"]),
        "valid": True,
        "lon_min": min(semua_lon), "lon_max": max(semua_lon),
        "lat_min": min(semua_lat), "lat_max": max(semua_lat),
    }


df_kendaraan = load_data_kendaraan()
geojson = load_geojson()

daftar_kecamatan = sorted({f["properties"].get(FIELD_NAMA_KECAMATAN, "") for f in geojson["features"]} - {""})
daftar_tahun = sorted(CSV_FILES.keys())
_tahun_fallback = list(range(2022, 2026))  # ditampilkan di UI kalau belum ada data


# ==================================================================
# SIDEBAR - MENU & FILTER
# ==================================================================
st.sidebar.markdown(f"<h2 style='color:{WARNA_TEMA};'>SKB - R🚗</h2>", unsafe_allow_html=True)
st.sidebar.caption("Kota Bogor - Data Registrasi Kendaraan Roda 4")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Menu",
    ["🏠 Beranda", "🗺️ Peta Interaktif", "📊 Statistik", "📋 Data Tabel", "📤 Upload Data"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Filter**")
_opsi_tahun = daftar_tahun if daftar_tahun else _tahun_fallback
tahun_pilih = st.sidebar.selectbox("Pilih Tahun", _opsi_tahun, index=max(0, len(_opsi_tahun) - 2))


# ==================================================================
# HITUNG AGREGAT SESUAI FILTER
# ==================================================================
def hitung_jumlah_per_kecamatan(tahun: int) -> pd.DataFrame:
    df = df_kendaraan[df_kendaraan["tahun"] == tahun]
    agg = df.groupby("kec_key").size().reset_index(name="jumlah")

    # mapping nama asli kecamatan dari geojson
    mapping = {
        f["properties"]["kec_key"]: f["properties"][FIELD_NAMA_KECAMATAN]
        for f in geojson["features"]
    }
    agg["kecamatan"] = agg["kec_key"].map(lambda k: mapping.get(k, ""))

    return agg


def hitung_semua_tahun() -> pd.DataFrame:
    semua = []
    for tahun in daftar_tahun:
        agg = hitung_jumlah_per_kecamatan(tahun)
        agg["tahun"] = tahun
        semua.append(agg)
    return pd.concat(semua, ignore_index=True)


# ==================================================================
# HALAMAN: BERANDA
# ==================================================================
if menu == "🏠 Beranda":
    # --- JUDUL + GAMBAR LATAR BELAKANG ---
    render_hero_section(JUDUL_DASHBOARD, SUBJUDUL_DASHBOARD, BACKGROUND_IMAGE_PATH)

    # --- TEKS BERJALAN DI BAWAH BACKGROUND ---
    render_marquee(TEKS_BERJALAN)

    st.write(
        "Dashboard ini menampilkan persebaran jumlah kendaraan roda 4 yang terdaftar "
        "di setiap kecamatan Kota Bogor. Gunakan menu di sidebar kiri untuk melihat "
        "peta interaktif, statistik, maupun data mentahnya."
    )

    agg_tahun_ini = hitung_jumlah_per_kecamatan(tahun_pilih)
    total_semua_tahun = hitung_semua_tahun()

    if agg_tahun_ini.empty or not daftar_tahun:
        st.info(
            "📂 Belum ada data kendaraan. Silakan upload file CSV/Excel melalui menu **📤 Upload Data** di sidebar."
        )
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Kendaraan", f"{agg_tahun_ini['jumlah'].sum():,}", help=f"Tahun {tahun_pilih}")
        col2.metric("Jumlah Kecamatan", f"{agg_tahun_ini.shape[0]}")
        kec_tertinggi = agg_tahun_ini.sort_values("jumlah", ascending=False).iloc[0]
        col3.metric("Kecamatan Tertinggi", kec_tertinggi["kecamatan"], f"{kec_tertinggi['jumlah']:,}")
        rata2 = agg_tahun_ini["jumlah"].mean()
        col4.metric("Rata-rata per Kecamatan", f"{rata2:,.0f}")

    if not total_semua_tahun.empty:
        st.markdown("---")
        st.subheader("Tren Total Kendaraan per Tahun (Semua Kecamatan)")
        tren = total_semua_tahun.groupby("tahun")["jumlah"].sum().reset_index()
        fig = px.bar(
            tren, x="tahun", y="jumlah", text="jumlah",
            color_discrete_sequence=[WARNA_TEMA],
        )
        fig.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig.update_layout(yaxis_title="Jumlah Kendaraan", xaxis_title="Tahun")
        st.plotly_chart(fig, use_container_width=True)


# ==================================================================
# HALAMAN: PETA INTERAKTIF
# ==================================================================
elif menu == "🗺️ Peta Interaktif":
    st.markdown(f"<h1 style='color:{WARNA_TEMA};'>Peta Interaktif</h1>", unsafe_allow_html=True)
    st.caption(f"Menampilkan data tahun **{tahun_pilih}** — basemap OpenStreetMap")

    agg = hitung_jumlah_per_kecamatan(tahun_pilih)

    fig = px.choropleth_mapbox(
        agg,
        geojson=geojson,
        locations="kec_key",
        featureidkey="properties.kec_key",
        color="jumlah",
        color_continuous_scale=SKALA_WARNA_PETA,
        mapbox_style="open-street-map",
        zoom=11,
        center={"lat": -6.5950, "lon": 106.8166},
        opacity=0.75,
        hover_name="kecamatan",
        hover_data={"jumlah": True, "kec_key": False},
        labels={"jumlah": "Jumlah Kendaraan"},
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=600)
    st.plotly_chart(fig, use_container_width=True)

    st.info("Geser pilih tahun di sidebar kiri untuk memperbarui peta ini.")

    # --- PANEL DIAGNOSTIK: bantu lihat sumber masalah kalau bentuk peta aneh ---
    with st.expander("🔍 Info Diagnostik Peta (klik untuk lihat)"):
        diag = diagnosa_geojson(geojson)
        if not diag.get("valid"):
            st.error("Shapefile tidak memiliki geometri yang terbaca.")
        else:
            col1, col2 = st.columns(2)
            col1.write(f"**Jumlah fitur/kecamatan di shapefile:** {diag['jumlah_fitur']}")
            col2.write(
                f"**Bounding box:** lon [{diag['lon_min']:.4f}, {diag['lon_max']:.4f}], "
                f"lat [{diag['lat_min']:.4f}, {diag['lat_max']:.4f}]"
            )
            # Kota Bogor kira-kira: lon 106.70 - 106.90, lat -6.70 - -6.50
            dalam_jangkauan_bogor = (
                106.0 <= diag["lon_min"] <= 107.5 and 106.0 <= diag["lon_max"] <= 107.5
                and -7.5 <= diag["lat_min"] <= -6.0 and -7.5 <= diag["lat_max"] <= -6.0
            )
            if dalam_jangkauan_bogor:
                st.success("✅ Koordinat shapefile berada di sekitar wilayah Kota Bogor — CRS sepertinya sudah benar.")
            else:
                st.warning(
                    "⚠️ Koordinat shapefile **TIDAK** berada di rentang wilayah Kota Bogor "
                    "(seharusnya sekitar lon 106.7–106.9, lat -6.7– -6.5). "
                    "Ini tanda bahwa CRS asli shapefile bukan UTM zona 48S/WGS84 standar, "
                    "atau file `Kota_bogor.shp` yang digunakan memang bukan batas kecamatan Kota Bogor. "
                    "Coba upload ulang shapefile yang benar lewat menu 'Upload Data'."
                )

        # cek kecocokan nama kecamatan CSV vs shapefile
        agg_cek = hitung_jumlah_per_kecamatan(tahun_pilih)
        nama_shp = {f["properties"]["kec_key"] for f in geojson["features"]}
        nama_csv = set(agg_cek["kec_key"])
        cocok = nama_shp & nama_csv
        tidak_cocok_csv = nama_csv - nama_shp

        st.write(f"**Kecamatan di data CSV yang berhasil match ke shapefile:** {len(cocok)} dari {len(nama_csv)}")
        if tidak_cocok_csv:
            mapping_asli = dict(zip(df_kendaraan["kec_key"], df_kendaraan["Kecamatan"]))
            nama_asli_tidak_cocok = [mapping_asli.get(k, k) for k in tidak_cocok_csv]
            st.warning(
                "⚠️ Nama kecamatan berikut ada di data CSV tapi **tidak ditemukan** di shapefile "
                "(kemungkinan beda penulisan nama): " + ", ".join(nama_asli_tidak_cocok)
            )


# ==================================================================
# HALAMAN: STATISTIK
# ==================================================================
elif menu == "📊 Statistik":
    st.markdown(f"<h1 style='color:{WARNA_TEMA};'>Statistik & Perbandingan</h1>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Perbandingan Kecamatan", "Tren per Kecamatan"])

    # ---- TAB 1: PERBANDINGAN ANTAR KECAMATAN ----
    with tab1:
        st.subheader(f"Total Kendaraan per Kecamatan — Tahun {tahun_pilih}")
        agg = hitung_jumlah_per_kecamatan(tahun_pilih).sort_values("jumlah", ascending=False)
        fig_kec = px.bar(
            agg, x="jumlah", y="kecamatan", orientation="h",
            color="jumlah", color_continuous_scale=SKALA_WARNA_PETA,
            text="jumlah",
        )
        fig_kec.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_kec.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Jumlah Kendaraan", yaxis_title="")
        st.plotly_chart(fig_kec, use_container_width=True)

    # ---- TAB 2: TREN PER KECAMATAN (diagram perbedaan tahun) ----
    with tab2:
        st.subheader("Perbandingan Jumlah Kendaraan per Tahun untuk 1 Kecamatan")
        kecamatan_pilih = st.selectbox("Pilih Kecamatan", daftar_kecamatan)

        total_semua = hitung_semua_tahun()
        data_kec = total_semua[total_semua["kecamatan"] == kecamatan_pilih].sort_values("tahun")

        fig_tren = go.Figure()
        fig_tren.add_trace(go.Bar(
            x=data_kec["tahun"].astype(str), y=data_kec["jumlah"],
            marker_color=WARNA_TEMA, text=data_kec["jumlah"], texttemplate="%{text:,}",
            textposition="outside", name="Jumlah Kendaraan",
        ))
        fig_tren.update_layout(
            title=f"Jumlah Kendaraan Terdaftar — {kecamatan_pilih}",
            xaxis_title="Tahun", yaxis_title="Jumlah Kendaraan",
        )
        st.plotly_chart(fig_tren, use_container_width=True)

        # tabel perubahan (selisih tahun ke tahun)
        data_kec = data_kec.reset_index(drop=True)
        data_kec["selisih"] = data_kec["jumlah"].diff()
        st.dataframe(
            data_kec[["tahun", "jumlah", "selisih"]].rename(
                columns={"tahun": "Tahun", "jumlah": "Jumlah Kendaraan", "selisih": "Selisih dari Tahun Sebelumnya"}
            ),
            use_container_width=True,
            hide_index=True,
        )


# ==================================================================
# HALAMAN: DATA TABEL
# ==================================================================
elif menu == "📋 Data Tabel":
    st.markdown(f"<h1 style='color:{WARNA_TEMA};'>Data Tabel</h1>", unsafe_allow_html=True)

    agg = hitung_jumlah_per_kecamatan(tahun_pilih)
    agg_tampil = agg[["kecamatan", "jumlah"]].sort_values("jumlah", ascending=False)
    agg_tampil.columns = ["Kecamatan", "Jumlah Kendaraan"]

    st.write(f"Menampilkan {agg_tampil.shape[0]} kecamatan untuk tahun **{tahun_pilih}**")
    st.dataframe(agg_tampil, use_container_width=True, hide_index=True)

    csv = agg_tampil.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download data ini sebagai CSV",
        data=csv,
        file_name=f"kendaraan_per_kecamatan_{tahun_pilih}.csv",
        mime="text/csv",
    )


# ==================================================================
# HALAMAN: UPLOAD DATA
# ==================================================================
elif menu == "📤 Upload Data":
    st.markdown(f"<h1 style='color:{WARNA_TEMA};'>Upload Data dari Luar</h1>", unsafe_allow_html=True)
    st.write(
        "Gunakan halaman ini untuk menambah atau memperbarui data dashboard tanpa mengubah kode "
        "sama sekali, yaitu data kendaraan (Excel/CSV) per tahun dan batas wilayah kecamatan (Shapefile)."
    )

    tab_excel, tab_shp = st.tabs(["📊 Data Kendaraan (Excel/CSV)", "🗺️ Batas Wilayah (Shapefile)"])

    # ---- TAB UPLOAD DATA KENDARAAN ----
    with tab_excel:
        st.subheader("Upload Data Kendaraan")
        st.caption(
            "File harus memiliki kolom nama kecamatan (boleh dengan nama kolom apa saja — "
            "pilih kolom yang sesuai di bawah setelah file terupload)."
        )

        file_excel = st.file_uploader(
            "Pilih file Excel (.xlsx) atau CSV (.csv)",
            type=["xlsx", "xls", "csv"],
            key="upload_excel",
        )

        if file_excel is not None:
            try:
                df_upload = baca_file_excel_csv(file_excel)
                st.success(
                    f"File **{file_excel.name}** berhasil dibaca — "
                    f"{df_upload.shape[0]} baris, {df_upload.shape[1]} kolom."
                )
                st.dataframe(df_upload.head(10), use_container_width=True)

                col_a, col_b = st.columns(2)
                with col_a:
                    tahun_target = st.number_input(
                        "Data ini untuk tahun berapa?",
                        min_value=2000, max_value=2100,
                        value=(max(daftar_tahun) + 1) if daftar_tahun else 2022,
                        step=1,
                    )
                with col_b:
                    daftar_kolom = list(df_upload.columns)
                    index_default = daftar_kolom.index("Kecamatan") if "Kecamatan" in daftar_kolom else 0
                    kolom_kecamatan_upload = st.selectbox(
                        "Kolom mana yang berisi nama Kecamatan?",
                        options=daftar_kolom,
                        index=index_default,
                    )

                if st.button("💾 Simpan Data Kendaraan Ini", type="primary"):
                    path_tersimpan = simpan_data_kendaraan(df_upload, int(tahun_target), kolom_kecamatan_upload)
                    load_data_kendaraan.clear()  # hapus cache supaya data baru ikut terbaca
                    st.success(f"Data tahun {int(tahun_target)} berhasil disimpan ke `{path_tersimpan}`.")
                    st.button("🔄 Muat Ulang Dashboard", key="reload_excel", on_click=st.rerun)

            except Exception as e:
                st.error(f"Gagal membaca file: {e}")

        st.markdown("---")
        st.caption(
            "Data tahun yang sudah tersedia saat ini: "
            + (", ".join(str(t) for t in daftar_tahun) if daftar_tahun else "(belum ada)")
        )

    # ---- TAB UPLOAD SHAPEFILE ----
    with tab_shp:
        st.subheader("Upload Batas Wilayah Kecamatan")
        st.caption(
            "Shapefile terdiri dari beberapa file sekaligus (.shp, .shx, .dbf, dan opsional .prj). "
            "Karena Streamlit hanya menerima 1 file per upload, kumpulkan semua file tersebut "
            "ke dalam 1 file **ZIP** terlebih dahulu, lalu upload ZIP-nya di sini."
        )

        file_zip = st.file_uploader(
            "Pilih file ZIP berisi shapefile",
            type=["zip"],
            key="upload_shp",
        )

        if file_zip is not None:
            if st.button("💾 Simpan Shapefile Ini", type="primary"):
                berhasil, pesan = simpan_shapefile_dari_zip(file_zip)
                if berhasil:
                    load_geojson.clear()  # hapus cache supaya shapefile baru ikut terbaca
                    st.success(pesan)
                    st.button("🔄 Muat Ulang Dashboard", key="reload_shp", on_click=st.rerun)
                else:
                    st.error(pesan)

        st.markdown("---")
        st.caption(f"Field nama kecamatan yang dipakai dashboard saat ini: `{FIELD_NAMA_KECAMATAN}`")
