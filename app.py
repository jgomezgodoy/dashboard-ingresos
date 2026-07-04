import json
import os
import pickle
from datetime import datetime
import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Ingresos",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


SPREADSHEET_ID = "1_xlbloSTnckvq7dslFQJyhTuv0Krr-XlKAJmQu4D4RQ"
SHEET_GID      = 942391946
CREDS_FILE     = os.path.join(os.path.dirname(__file__), "credentials.json")
CACHE_FILE     = os.path.join(os.path.dirname(__file__), "cache_datos.pkl")
FROZEN_FILE    = os.path.join(os.path.dirname(__file__), "datos_fijos.json")

MESES_ORDER = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    # English
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9,
    "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "DEC": 12,
}

PLOTLY_TEMPLATE = "plotly_white"

# Colores fijos por año — vivos, con el año de marca (rojo) para el más reciente
COLORES_AÑO = {
    2022: "#FFC145",   # amarillo dorado
    2023: "#FF7A3D",   # naranja vivo
    2024: "#2BC4A0",   # teal
    2025: "#4C6EF5",   # azul vivo
    2026: "#F59E0B",   # ámbar (año actual; grafito/negro queda como color corporativo)
}

APT_MULTIPLICADOR = {"ALAMO": 3, "ESPOZ Y MINA": 5}

def apt_peso(nombre):
    nombre_up = nombre.upper()
    for key, peso in APT_MULTIPLICADOR.items():
        if key in nombre_up:
            return peso
    return 1

def contar_apts(apt_iterable):
    return sum(apt_peso(a) for a in apt_iterable)

def rgba(hex_color, alpha=1.0):
    r, g, b = int(hex_color[1:3],16), int(hex_color[3:5],16), int(hex_color[5:7],16)
    return f"rgba({r},{g},{b},{alpha})"

LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, Arial, sans-serif", size=14, color="#111827"),
    hoverlabel=dict(font_size=15, font_family="Inter, Arial", namelength=-1,
                    bgcolor="white", bordercolor="#e0e4ea"),
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#e0e4ea", linewidth=1),
    yaxis=dict(gridcolor="#f0f2f5", gridwidth=1, zeroline=False, linecolor="#e0e4ea"),
    margin=dict(l=0, r=0, t=60, b=0),
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3/dist/tabler-icons.min.css');

    /* Fondo general */
    .stApp { background-color: #FAFAFA; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #f0f0f0; }

    /* KPI cards */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #f0f0f0;
        border-radius: 20px;
        padding: 22px 24px;
        text-align: center;
        transition: transform .15s, box-shadow .15s;
        box-shadow: 0 8px 22px rgba(0,0,0,0.06);
    }
    .kpi-card:hover { transform: translateY(-4px); box-shadow: 0 16px 32px rgba(0,0,0,0.10); }
    .kpi-label { color: #8a8a8a; font-size: 15px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 10px; }
    .kpi-value { color: #1A1A1A; font-size: 42px; font-weight: 700; line-height: 1; }
    .kpi-delta { display: inline-block; font-size: 14px; margin-top: 10px; padding: 3px 12px; border-radius: 20px; }
    .kpi-delta:empty { display: none; }
    .kpi-up   { color: #ffffff; background: #1A1A1A; }
    .kpi-down { color: #b00021; background: #FFE1E6; }
    .kpi-neutral { color: #7a7a7a; background: #F2F2F2; }

    /* Section titles con badge de icono clay */
    .section-title {
        display: flex;
        align-items: center;
        gap: 14px;
        color: #1A1A1A;
        font-size: 20px;
        font-weight: 700;
        margin: 36px 0 16px 0;
    }
    .section-title .sec-ico {
        width: 46px; height: 46px; flex: none;
        border-radius: 15px;
        display: inline-flex; align-items: center; justify-content: center;
        font-size: 24px; line-height: 1;
    }
    .sec-ico i {
        display: flex; align-items: center; justify-content: center;
        width: 100%; height: 100%; line-height: 1;
    }
    .sec-ico.red {
        color: #ffffff;
        background: linear-gradient(145deg, #FF3B57, #E4002B);
        box-shadow: 0 7px 14px rgba(228,0,43,0.34), inset 0 1px 1px rgba(255,255,255,0.4);
    }
    .sec-ico.tint {
        color: #E4002B;
        background: #FFE1E6;
        box-shadow: 0 6px 12px rgba(228,0,43,0.16);
    }

    /* Tarjeta suave alrededor de cada gráfica */
    [data-testid="stPlotlyChart"], .stPlotlyChart {
        background: #ffffff;
        border: 1px solid #f2f2f2;
        border-radius: 20px;
        padding: 12px 16px;
        box-shadow: 0 8px 22px rgba(0,0,0,0.06);
    }

    /* Métricas nativas */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #f2f2f2;
        border-radius: 16px;
        padding: 14px 18px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.05);
    }

    /* Botones redondeados */
    .stButton > button {
        border-radius: 14px;
        border: 1px solid #eeeeee;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        transition: all .15s;
    }
    .stButton > button:hover { border-color: #E4002B; color: #E4002B; transform: translateY(-1px); }

    /* Sidebar filters */
    .sidebar-title {
        color: #E4002B;
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .08em;
        margin-bottom: 4px;
    }

    /* Hide Streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# Helper: título de sección con badge de icono clay (alterna rojo sólido / rojo tinte)
_sec_counter = {"i": 0}

def section_title(icon, text):
    variant = "red" if _sec_counter["i"] % 2 == 0 else "tint"
    _sec_counter["i"] += 1
    st.markdown(
        f'<div class="section-title"><span class="sec-ico {variant}">'
        f'<i class="ti {icon}"></i></span><span>{text}</span></div>',
        unsafe_allow_html=True,
    )

# ── DATA LOADING ──────────────────────────────────────────────────────────────
def parse_amount(val: str) -> float:
    if not val:
        return 0.0
    try:
        clean = str(val).replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
        return float(clean)
    except Exception:
        return 0.0


def _get_cutoff():
    """Devuelve (año, mes) hasta el que se congelan datos (mes_actual - 2)."""
    hoy = datetime.now()
    mes = hoy.month - 2
    año = hoy.year
    if mes <= 0:
        mes += 12
        año -= 1
    return año, mes


def _parse_raw(raw):
    year_row  = raw[4]
    month_row = raw[5]

    apt_start = 7
    total_idx = None
    for i in range(apt_start, len(raw)):
        col_b = raw[i][1].strip().lower() if len(raw[i]) > 1 else ""
        if "total pisos" in col_b:
            total_idx = i
            break
    if total_idx is None:
        total_idx = apt_start + 51

    apt_rows  = raw[apt_start:total_idx]
    total_row = raw[total_idx] if total_idx < len(raw) else []

    neto_row = []
    for i in range(total_idx, len(raw)):
        col_b = raw[i][1].strip().lower() if len(raw[i]) > 1 else ""
        if "ingresos netos" in col_b:
            neto_row = raw[i]
            break

    years_filled = []
    cur_year = None
    for y in year_row:
        y = y.strip()
        if y.isdigit():
            cur_year = int(y)
        years_filled.append(cur_year)

    if len(years_filled) < len(month_row):
        years_filled += [cur_year] * (len(month_row) - len(years_filled))

    valid_cols = []
    for i, (year, month) in enumerate(zip(years_filled, month_row)):
        if i < 2 or year is None:
            continue
        m = month.strip().upper()
        if not m or "POST" in m or "GESTOR" in m:
            continue
        mes_num = next((v for k, v in MESES_ORDER.items() if k in m), None)
        if mes_num is None:
            continue
        valid_cols.append((i, year, month.strip(), mes_num))

    records = []
    for row in apt_rows:
        name = row[1].strip() if len(row) > 1 else ""
        if not name:
            continue
        for col_idx, year, month, mes_num in valid_cols:
            val    = row[col_idx].strip() if col_idx < len(row) else ""
            amount = parse_amount(val)
            records.append({
                "apartamento": name,
                "año":         year,
                "mes":         month,
                "mes_num":     mes_num,
                "comision":    amount,
            })

    df = pd.DataFrame(records)

    totals = []
    for col_idx, year, month, mes_num in valid_cols:
        val_antes    = total_row[col_idx].strip() if col_idx < len(total_row) else ""
        amount_antes = parse_amount(val_antes)
        col_post     = col_idx + 1
        post_label   = month_row[col_post].strip().upper() if col_post < len(month_row) else ""
        if not post_label or "POST" in post_label or "GESTOR" in post_label:
            val_post    = total_row[col_post].strip() if col_post < len(total_row) else ""
            amount_post = parse_amount(val_post) if val_post else None
        else:
            amount_post = None
        totals.append({
            "año": year, "mes": month, "mes_num": mes_num,
            "total": amount_antes, "total_post": amount_post,
        })

    df_totals = pd.DataFrame(totals)
    df_totals["coste_gestores"] = df_totals.apply(
        lambda r: r["total"] - r["total_post"] if r["total_post"] is not None and r["total"] > 0 else None, axis=1
    )
    df_totals["pct_gestores"] = df_totals.apply(
        lambda r: round(r["coste_gestores"] / r["total"] * 100, 1) if r["coste_gestores"] is not None and r["total"] > 0 else None, axis=1
    )

    netos = []
    for col_idx, year, month, mes_num in valid_cols:
        col_neto = col_idx + 1
        post_lbl = month_row[col_neto].strip().upper() if col_neto < len(month_row) else ""
        neto_col = col_neto if (not post_lbl or "POST" in post_lbl or "GESTOR" in post_lbl) else col_idx
        val      = neto_row[neto_col].strip() if neto_col < len(neto_row) else ""
        amount   = parse_amount(val) if val and val != "#REF!" else 0.0
        netos.append({"año": year, "mes": month, "mes_num": mes_num, "neto": amount})

    df_netos  = pd.DataFrame(netos)
    df_margen = df_totals.merge(df_netos, on=["año", "mes", "mes_num"])
    df_margen["margen_pct"] = df_margen.apply(
        lambda r: round(r["neto"] / r["total"] * 100, 1) if r["total"] > 0 else None, axis=1
    )

    return df, df_totals, df_margen


def _load_frozen():
    if not os.path.exists(FROZEN_FILE):
        return None
    with open(FROZEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_frozen(df_all, dt_all, dm_all, cutoff_year, cutoff_month):
    def is_frozen(row):
        return (row["año"] < cutoff_year) or (row["año"] == cutoff_year and row["mes_num"] <= cutoff_month)

    def to_records(df):
        return df[df.apply(is_frozen, axis=1)].where(pd.notnull(df), None).to_dict("records")

    data = {
        "frozen_until": {"year": cutoff_year, "month": cutoff_month},
        "last_updated": datetime.now().isoformat(),
        "records": to_records(df_all),
        "totals":  to_records(dt_all),
        "margen":  to_records(dm_all),
    }
    with open(FROZEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _frozen_to_dfs(frozen):
    df  = pd.DataFrame(frozen["records"])
    dt  = pd.DataFrame(frozen["totals"])
    dm  = pd.DataFrame(frozen["margen"])
    return df, dt, dm


def _fetch_from_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    try:
        has_secrets = "credentials_json" in st.secrets
    except Exception:
        has_secrets = False

    if has_secrets:
        creds = Credentials.from_service_account_info(
            json.loads(st.secrets["credentials_json"]), scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)

    client      = gspread.Client(auth=creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet   = next((s for s in spreadsheet.worksheets() if s.id == SHEET_GID), None)
    if worksheet is None:
        raise Exception("Hoja no encontrada")
    return worksheet.get("A1:ZZ500")


@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    cutoff_year, cutoff_month = _get_cutoff()
    frozen = _load_frozen()
    frozen_until = (0, 0)
    if frozen:
        fu = frozen.get("frozen_until", {})
        frozen_until = (fu.get("year", 0), fu.get("month", 0))

    needs_update = frozen_until < (cutoff_year, cutoff_month)

    try:
        raw = _fetch_from_sheet()
        df_all, dt_all, dm_all = _parse_raw(raw)

        # Si el cutoff avanzó, actualizar el JSON automáticamente
        if needs_update:
            _save_frozen(df_all, dt_all, dm_all, cutoff_year, cutoff_month)
            frozen = _load_frozen()

        # Datos congelados desde JSON (más seguros), datos recientes desde el sheet
        if frozen:
            df_frz, dt_frz, dm_frz = _frozen_to_dfs(frozen)

            def is_live(sub):
                return ~(
                    (sub["año"] < cutoff_year) |
                    ((sub["año"] == cutoff_year) & (sub["mes_num"] <= cutoff_month))
                )

            df = pd.concat([df_frz, df_all[is_live(df_all)]], ignore_index=True)
            dt = pd.concat([dt_frz, dt_all[is_live(dt_all)]], ignore_index=True)
            dm = pd.concat([dm_frz, dm_all[is_live(dm_all)]], ignore_index=True)
        else:
            df, dt, dm = df_all, dt_all, dm_all

        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"data": (df, dt, dm), "ts": datetime.now()}, f)
        return df, dt, dm

    except Exception:
        # Sin conexión: usar JSON congelado + pickle para meses recientes
        if frozen:
            df_frz, dt_frz, dm_frz = _frozen_to_dfs(frozen)
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "rb") as f:
                    cache = pickle.load(f)
                cached_df, cached_dt, cached_dm = cache["data"]
                ts = cache["ts"].strftime("%d/%m/%Y %H:%M")
                st.warning(f"Sin conexion - datos congelados + cache del {ts}")

                def is_live(sub):
                    return ~(
                        (sub["año"] < cutoff_year) |
                        ((sub["año"] == cutoff_year) & (sub["mes_num"] <= cutoff_month))
                    )

                df = pd.concat([df_frz, cached_df[is_live(cached_df)]], ignore_index=True)
                dt = pd.concat([dt_frz, cached_dt[is_live(cached_dt)]], ignore_index=True)
                dm = pd.concat([dm_frz, cached_dm[is_live(cached_dm)]], ignore_index=True)
                return df, dt, dm
            else:
                st.warning("Sin conexion - mostrando solo datos congelados (sin meses recientes)")
                return df_frz, dt_frz, dm_frz
        elif os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
            ts = cache["ts"].strftime("%d/%m/%Y %H:%M")
            st.warning(f"Sin conexion - datos guardados el {ts}")
            return cache["data"]
        else:
            st.error("Sin conexion y sin datos guardados. Conectate a internet al menos una vez.")
            st.stop()

# ── HEADER ────────────────────────────────────────────────────────────────────
col_titulo, col_btn = st.columns([5, 1])
with col_titulo:
    st.markdown(
        '<div style="display:flex; align-items:center; gap:14px; margin:4px 0 2px;">'
        '<span class="sec-ico red" style="width:54px; height:54px; border-radius:18px; font-size:30px;">'
        '<i class="ti ti-building-skyscraper"></i></span>'
        '<span style="font-size:30px; font-weight:800; color:#1A1A1A;">Dashboard Ingresos</span></div>',
        unsafe_allow_html=True,
    )
with col_btn:
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Cargando datos..."):
    df, df_totals, df_margen = load_data()

# Filtro de años — pastillas: los 3 años más recientes activos, el resto en gris (clicables)
años_disponibles = sorted(df["año"].unique())
años_default = años_disponibles[-3:]  # los 3 años más recientes disponibles
años_sel = st.pills(
    "Filtrar por año",
    options=años_disponibles,
    default=años_default,
    selection_mode="multi",
    label_visibility="visible",
)

if not años_sel:
    st.warning("Selecciona al menos un año.")
    st.stop()

df_tot_f = df_totals[df_totals["año"].isin(años_sel)]
df_año   = df[df["año"].isin(años_sel)]

# ── KPI CARDS ─────────────────────────────────────────────────────────────────
section_title("ti-gauge", "Resumen general")

# Calcular KPIs
n_apts_activos = contar_apts(df_año[df_año["comision"] > 0]["apartamento"].unique())
años_ord = sorted(años_sel)

# Mejor mes (por total)
mejor_mes_row = df_tot_f.loc[df_tot_f["total"].idxmax()] if not df_tot_f.empty else None
mejor_mes_str = f"{mejor_mes_row['mes']} {mejor_mes_row['año']}" if mejor_mes_row is not None else "—"
mejor_mes_val = mejor_mes_row["total"] if mejor_mes_row is not None else 0

def kpi(col, label, value, delta="", delta_cls="kpi-neutral"):
    col.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-delta {delta_cls}">{delta}</div>
    </div>""", unsafe_allow_html=True)

# Fecha de referencia: el mes anterior al actual es el último mes completo
_hoy = datetime.now()
_mes_anterior = 12 if _hoy.month == 1 else _hoy.month - 1
_año_anterior = _hoy.year - 1 if _hoy.month == 1 else _hoy.year

# Fila 1: un card por año con ingresos + apartamentos activos
cols_años = st.columns(len(años_ord))
for i, año in enumerate(años_ord):
    df_año_i = df_año[df_año["año"] == año]
    # Para el año actual, solo contar meses ya cerrados
    if año == _año_anterior:
        df_año_i = df_año_i[df_año_i["mes_num"] <= _mes_anterior]
    ing      = df_año_i["comision"].sum()
    n_apts   = contar_apts(df_año_i[df_año_i["comision"] > 0]["apartamento"].unique())
    if i > 0:
        ing_ant = df_año[df_año["año"] == años_ord[i-1]]["comision"].sum()
        pct = ((ing - ing_ant) / ing_ant * 100) if ing_ant > 0 else 0
        d_str = f"{'▲' if pct >= 0 else '▼'} {abs(pct):.1f}% vs {años_ord[i-1]}"
        d_cls = "kpi-up" if pct >= 0 else "kpi-down"
    else:
        d_str = "primer año"
        d_cls = "kpi-neutral"
    meses_con_datos = df_año_i[df_año_i["comision"] > 0]["mes_num"].nunique()
    divisor_mes = meses_con_datos if meses_con_datos < 12 else 12
    media_apt_año = ing / n_apts if n_apts > 0 else 0
    media_apt_mes = (ing / n_apts / divisor_mes) if n_apts > 0 and divisor_mes > 0 else 0
    nota_mes = f"(sobre {divisor_mes} meses)" if divisor_mes < 12 else ""
    cols_años[i].markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{año}</div>
        <div class="kpi-value"><b>{ing:,.0f} €</b></div>
        <div style="color:#6b7280; font-size:16px; margin-top:8px;">🏠 {n_apts} apartamentos activos</div>
        <div class="kpi-delta {d_cls}">{d_str}</div>
        <div style="border-top:1px solid #e0e4ea; margin-top:14px; padding-top:12px;">
            <div style="color:#6b7280; font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:.05em;">Media por apartamento</div>
            <div style="color:#111827; font-size:20px; font-weight:700; margin-top:6px;"><b>{media_apt_año:,.0f} € / año</b></div>
            <div style="color:#111827; font-size:20px; font-weight:700;"><b>{media_apt_mes:,.0f} € / mes</b> <span style="color:#6b7280; font-size:13px;">{nota_mes}</span></div>
        </div>
    </div>""".replace(",", "."), unsafe_allow_html=True)

# Fila 2: KPIs generales
st.markdown("")
col_b, col_c = st.columns(2)
kpi(col_b, "Mejor mes", mejor_mes_str, f"{mejor_mes_val:,.0f} €".replace(",", "."), "kpi-up")
total_global = df_año["comision"].sum()
kpi(col_c, "Total acumulado", f"{total_global:,.0f} €".replace(",", "."), f"{len(años_ord)} años seleccionados", "kpi-neutral")

# ── RANKING ÚLTIMO MES ────────────────────────────────────────────────────────
# Solo datos hasta el mes anterior (nunca meses futuros ni el mes actual)
_df_hasta_ant = df[
    (df["comision"] > 0) & (
        (df["año"] < _año_anterior) |
        ((df["año"] == _año_anterior) & (df["mes_num"] <= _mes_anterior))
    )
]
_df_mes_ant = _df_hasta_ant[(df["año"] == _año_anterior) & (df["mes_num"] == _mes_anterior)]
if not _df_mes_ant.empty:
    _last_año, _last_mes_num = _año_anterior, _mes_anterior
    _last_mes_lbl = _df_mes_ant["mes"].iloc[0]
elif not _df_hasta_ant.empty:
    _last_año     = int(_df_hasta_ant["año"].max())
    _last_mes_num = int(_df_hasta_ant[_df_hasta_ant["año"] == _last_año]["mes_num"].max())
    _last_mes_lbl = _df_hasta_ant[
        (_df_hasta_ant["año"] == _last_año) & (_df_hasta_ant["mes_num"] == _last_mes_num)
    ]["mes"].iloc[0]
else:
    _last_año = None

if _last_año is not None:
    df_rank = (
        df[(df["año"] == _last_año) & (df["mes_num"] == _last_mes_num) & (df["comision"] > 0)]
        .groupby("apartamento")["comision"].sum()
        .reset_index()
    )
    # Ingreso por unidad: divide por el número de apartamentos que representa cada entrada
    df_rank["comision_unit"] = df_rank.apply(
        lambda r: r["comision"] / apt_peso(r["apartamento"]), axis=1
    )
    df_rank = df_rank.sort_values("comision_unit", ascending=True)

    _color = COLORES_AÑO.get(_last_año, "#4ade80")
    _total_mes = df_rank["comision"].sum()
    _n_apts_mes = contar_apts(df_rank["apartamento"])
    _media_mes = _total_mes / _n_apts_mes if _n_apts_mes > 0 else 0

    section_title("ti-report-money", f"Ingresos por apartamento — {_last_mes_lbl} {_last_año}")

    _c1, _c2, _c3 = st.columns(3)
    _c1.metric("Total mes", f"{_total_mes:,.0f} €".replace(",", "."))
    _c2.metric("Media por apartamento", f"{_media_mes:,.0f} €".replace(",", "."))
    _c3.metric("Apartamentos activos", f"{_n_apts_mes}")

    fig_rank = go.Figure()
    fig_rank.add_trace(go.Bar(
        x=df_rank["comision_unit"],
        y=df_rank["apartamento"],
        orientation="h",
        marker=dict(
            color=[rgba(_color, 0.55) if v >= _media_mes else rgba(_color, 0.30) for v in df_rank["comision_unit"]],
            line=dict(color=_color, width=1.5),
        ),
        text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in df_rank["comision_unit"]],
        textposition="outside",
        textfont=dict(size=12, family="Inter, Arial", color="#111827"),
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} € / apt<extra></extra>",
    ))
    fig_rank.add_vline(
        x=_media_mes,
        line_dash="dash", line_color="#1A1A1A", line_width=1.8,
        annotation_text=f"<b>Media: {_media_mes:,.0f} €</b>".replace(",", "."),
        annotation_position="top right",
        annotation_font=dict(size=13, color="#1A1A1A"),
    )
    fig_rank.update_layout(
        template=PLOTLY_TEMPLATE,
    barcornerradius=10,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(480, len(df_rank) * 30),
        margin=dict(l=0, r=110, t=20, b=0),
        bargap=0.3,
        font=dict(size=13, family="Inter, Arial"),
        yaxis=dict(tickfont=dict(size=13), showgrid=False, zeroline=False),
        xaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False),
        showlegend=False,
        hoverlabel=dict(font_size=15, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
    )
    st.plotly_chart(fig_rank, use_container_width=True)

# ── EVOLUCIÓN MENSUAL ─────────────────────────────────────────────────────────
section_title("ti-trending-up", "Evolución mensual de ingresos")

df_tot_sorted = df_tot_f.sort_values(["año", "mes_num"])
df_tot_sorted["periodo"] = df_tot_sorted["mes"] + " " + df_tot_sorted["año"].astype(str)

fig_line = go.Figure()

for año in sorted(df_tot_f["año"].unique()):
    sub   = df_tot_sorted[df_tot_sorted["año"] == año]
    color = COLORES_AÑO.get(año, "#aaaaaa")
    fig_line.add_trace(go.Scatter(
        x=sub["mes_num"], y=sub["total"],
        name=str(año),
        mode="lines+markers",
        line=dict(width=3.5, color=color, shape="spline", smoothing=0.8),
        marker=dict(size=9, color="white", line=dict(width=2.5, color=color)),
        fill="tozeroy",
        fillcolor=rgba(color, 0.12),
        hovertemplate=f"<b>%{{x}}</b> {año}<br>%{{y:,.0f}} €<extra></extra>",
    ))

fig_line.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=430,
    margin=dict(l=0, r=0, t=60, b=50),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        xanchor="center", x=0.5, font=dict(size=20),
    ),
    xaxis=dict(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"],
        showgrid=False, zeroline=False, linecolor="#e0e4ea",
    ),
    yaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False),
    hovermode="x unified",
    hoverlabel=dict(font_size=22, font_family="Inter, Arial", namelength=-1,
                    bgcolor="white", bordercolor="#e0e4ea"),
)
st.plotly_chart(fig_line, use_container_width=True)

# ── BENEFICIO ANUAL ───────────────────────────────────────────────────────────
section_title("ti-currency-euro", "Ingresos y beneficio")

_dm = df_margen[
    df_margen["año"].isin(años_sel) &
    ((df_margen["año"] < _año_anterior) | (df_margen["mes_num"] <= _mes_anterior))
]
df_anual = _dm.groupby("año").agg(
    total=("total", "sum"),
    neto=("neto", "sum"),
).reset_index()
df_anual["margen_pct"] = (df_anual["neto"] / df_anual["total"] * 100).round(1)
df_anual = df_anual.sort_values("año")

años_str = df_anual["año"].astype(str).tolist()

fig_anual = go.Figure()

# Barras: Total comisiones
fig_anual.add_trace(go.Bar(
    x=años_str, y=df_anual["total"],
    name="Total comisiones",
    marker=dict(
        color=[rgba(COLORES_AÑO.get(a, "#aaaaaa"), 0.45) for a in df_anual["año"]],
        line=dict(color=[COLORES_AÑO.get(a, "#aaaaaa") for a in df_anual["año"]], width=2),
    ),
    text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in df_anual["total"]],
    textposition="outside",
    textfont=dict(size=14, color="black", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Total comisiones: %{y:,.0f} €<extra></extra>",
))

# Barras: Beneficio post gastos
fig_anual.add_trace(go.Bar(
    x=años_str, y=df_anual["neto"],
    name="Beneficio post gastos",
    marker=dict(
        color=[COLORES_AÑO.get(a, "#aaaaaa") for a in df_anual["año"]],
        line=dict(color=[rgba(COLORES_AÑO.get(a, "#aaaaaa"), 0.5) for a in df_anual["año"]], width=1),
    ),
    text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in df_anual["neto"]],
    textposition="outside",
    textfont=dict(size=14, color="#111827"),
    hovertemplate="<b>%{x}</b><br>Beneficio post gastos: %{y:,.0f} €<extra></extra>",
))

# Puntos: % margen (eje derecho)
fig_anual.add_trace(go.Scatter(
    x=años_str, y=df_anual["margen_pct"],
    name="% Beneficio",
    mode="markers+text",
    yaxis="y2",
    marker=dict(size=16, color="#1A1A1A", line=dict(width=3, color="white"),
                symbol="diamond"),
    text=[f"<b>{v:.1f}%</b>" for v in df_anual["margen_pct"]],
    textposition="top center",
    textfont=dict(size=15, color="#1A1A1A"),
    hovertemplate="<b>%{x}</b><br>Beneficio: %{y:.1f}%<extra></extra>",
))

fig_anual.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=480,
    margin=dict(l=0, r=60, t=60, b=0),
    font=dict(size=15, family="Inter, Arial"),
    bargap=0.25, bargroupgap=0.08,
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02,
        xanchor="center", x=0.5, font=dict(size=16),
    ),
    xaxis=dict(
        tickfont=dict(size=16, family="Inter, Arial"),
        ticktext=[f"<b>{a}</b>" for a in años_str],
        tickvals=años_str,
        showgrid=False, zeroline=False, linecolor="#e0e4ea",
    ),
    yaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False, title="Importe (€)"),
    yaxis2=dict(
        overlaying="y", side="right",
        ticksuffix="%", title="% Beneficio",
        showgrid=False,
    ),
    hoverlabel=dict(font_size=16, font_family="Inter, Arial", namelength=-1,
                    bgcolor="white", bordercolor="#e0e4ea"),
    hovermode="x unified",
)
st.plotly_chart(fig_anual, use_container_width=True)

# ── % GESTORES ────────────────────────────────────────────────────────────────
section_title("ti-users", "Coste de gestores externos")

df_gest = df_totals[
    df_totals["pct_gestores"].notna() & df_totals["año"].isin(años_sel) &
    ((df_totals["año"] < _año_anterior) | (df_totals["mes_num"] <= _mes_anterior))
].copy().sort_values(["año", "mes_num"])

if df_gest.empty:
    st.info("No hay datos de gestores externos en el período seleccionado.")
else:
    # Etiqueta período
    MESES_ABREV = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
                   7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
    df_gest["periodo"] = df_gest.apply(
        lambda r: f"{MESES_ABREV.get(r['mes_num'], r['mes'])} {r['año']}", axis=1
    )

    colores_barras = [COLORES_AÑO.get(a, "#aaaaaa") for a in df_gest["año"]]

    fig_gest = go.Figure()

    # Barras: coste en euros
    fig_gest.add_trace(go.Bar(
        x=df_gest["periodo"],
        y=df_gest["coste_gestores"],
        name="Coste gestores (€)",
        marker=dict(
            color=[rgba(c, 0.7) for c in colores_barras],
            line=dict(color=colores_barras, width=1.5),
        ),
        hovertemplate="<b>%{x}</b><br>Coste gestores: %{y:,.0f} €<extra></extra>",
        yaxis="y",
    ))

    # Línea suavizada: % sobre ingresos
    fig_gest.add_trace(go.Scatter(
        x=df_gest["periodo"],
        y=df_gest["pct_gestores"],
        name="% sobre ingresos",
        mode="lines+markers+text",
        line=dict(width=3.5, color="#1A1A1A", shape="spline", smoothing=0.7),
        marker=dict(size=10, color="white", line=dict(width=2.5, color="#1A1A1A")),
        text=[f"<b>{v:.1f}%</b>" for v in df_gest["pct_gestores"]],
        textposition="top center",
        textfont=dict(size=12, color="#1A1A1A", family="Inter, Arial"),
        hovertemplate="<b>%{x}</b><br>% gestores: %{y:.1f}%<extra></extra>",
        yaxis="y2",
    ))

    pct_media = df_gest["pct_gestores"].mean()
    coste_total = df_gest["coste_gestores"].sum()

    fig_gest.update_layout(
        template=PLOTLY_TEMPLATE,
    barcornerradius=10,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=440,
        margin=dict(l=0, r=60, t=60, b=60),
        bargap=0.3,
        font=dict(size=14, family="Inter, Arial"),
        xaxis=dict(
            tickfont=dict(size=12),
            tickangle=-40,
            showgrid=False, zeroline=False, linecolor="#e0e4ea",
        ),
        yaxis=dict(
            ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False,
            title="Coste gestores (€)",
        ),
        yaxis2=dict(
            overlaying="y", side="right",
            ticksuffix="%", title="% sobre ingresos",
            showgrid=False,
            range=[0, max(df_gest["pct_gestores"].max() * 1.4, 30)],
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5, font=dict(size=14),
        ),
        hoverlabel=dict(font_size=15, font_family="Inter, Arial", namelength=-1,
                        bgcolor="white", bordercolor="#e0e4ea"),
        hovermode="x unified",
    )

    # KPIs gestores
    col_g1, col_g2, col_g3 = st.columns(3)
    col_g1.metric("% medio de gestores", f"{pct_media:.1f}%")
    col_g2.metric("Coste total gestores", f"{coste_total:,.0f} €".replace(",", "."))
    col_g3.metric("Meses con gestores", f"{len(df_gest)}")

    st.plotly_chart(fig_gest, use_container_width=True)

    # Tabla resumen anual de gestores
    with st.expander("Ver resumen anual de gestores"):
        df_gest_anual = df_gest.groupby("año").agg(
            coste_total=("coste_gestores", "sum"),
            ingresos_total=("total", "sum"),
            pct_medio=("pct_gestores", "mean"),
            meses=("pct_gestores", "count"),
        ).reset_index()
        df_gest_anual["pct_sobre_ingresos"] = (df_gest_anual["coste_total"] / df_gest_anual["ingresos_total"] * 100).round(1)
        df_gest_anual = df_gest_anual.rename(columns={
            "año": "Año", "coste_total": "Coste gestores (€)",
            "ingresos_total": "Ingresos brutos (€)",
            "pct_sobre_ingresos": "% coste / ingresos",
            "pct_medio": "% medio mensual", "meses": "Meses"
        })
        st.dataframe(
            df_gest_anual.style.format({
                "Coste gestores (€)": "{:,.0f}",
                "Ingresos brutos (€)": "{:,.0f}",
                "% coste / ingresos": "{:.1f}%",
                "% medio mensual": "{:.1f}%",
            }),
            use_container_width=True, hide_index=True,
        )

# ── MESES RÉCORD ──────────────────────────────────────────────────────────────
section_title("ti-trophy", "Top 10 meses récord")

df_tot_all = df_totals[df_totals["año"].isin(años_sel)].copy()
df_tot_all["periodo"] = df_tot_all["mes"] + " " + df_tot_all["año"].astype(str)
top10 = df_tot_all[df_tot_all["total"] > 0].sort_values("total", ascending=False).head(10).reset_index(drop=True)
top10.index += 1

fig_top = go.Figure()
fig_top.add_trace(go.Bar(
    x=top10["total"],
    y=top10["periodo"],
    orientation="h",
    marker=dict(
        color=[rgba(COLORES_AÑO.get(a, "#aaaaaa"), 0.7) for a in top10["año"]],
        line=dict(color=[COLORES_AÑO.get(a, "#aaaaaa") for a in top10["año"]], width=1.5),
    ),
    text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in top10["total"]],
    textposition="outside",
    textfont=dict(size=14, color="#111827", family="Inter, Arial"),
    hovertemplate="<b>%{y}</b><br>%{x:,.0f} €<extra></extra>",
))
fig_top.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=420,
    margin=dict(l=0, r=90, t=10, b=0),
    bargap=0.3,
    yaxis=dict(categoryorder="total ascending", tickfont=dict(size=14), showgrid=False),
    xaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False),
    hoverlabel=dict(font_size=16, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
    showlegend=False,
)
st.plotly_chart(fig_top, use_container_width=True)

# ── NUEVOS PISOS POR AÑO ──────────────────────────────────────────────────────
section_title("ti-circle-plus", "Nuevos apartamentos incorporados por año")

# Primer año con comisión > 0 para cada apartamento
df_primero = df[df["comision"] > 0].groupby("apartamento")["año"].min().reset_index()
df_primero.columns = ["apartamento", "año_entrada"]
df_primero["peso"] = df_primero["apartamento"].map(apt_peso)
nuevos_año = df_primero[df_primero["año_entrada"].isin(años_sel)].groupby("año_entrada")["peso"].sum().reset_index()
nuevos_año.columns = ["año", "nuevos"]

fig_nuevos = go.Figure()
fig_nuevos.add_trace(go.Bar(
    x=nuevos_año["año"].astype(str),
    y=nuevos_año["nuevos"],
    marker=dict(
        color=[COLORES_AÑO.get(a, "#aaaaaa") for a in nuevos_año["año"]],
        line=dict(color=[rgba(COLORES_AÑO.get(a,"#aaa"),0.4) for a in nuevos_año["año"]], width=2),
    ),
    text=[f"<b>{v}</b>" for v in nuevos_año["nuevos"]],
    textposition="outside",
    textfont=dict(size=18, color="#111827", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>%{y} nuevos apartamentos<extra></extra>",
))
fig_nuevos.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=350,
    margin=dict(l=0, r=0, t=40, b=0),
    bargap=0.4,
    yaxis=dict(title="Nº apartamentos", gridcolor="#f0f2f5", tickfont=dict(size=14), zeroline=False),
    xaxis=dict(tickfont=dict(size=16, family="Inter, Arial"), showgrid=False, zeroline=False),
    showlegend=False,
    hoverlabel=dict(font_size=16, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
)
st.plotly_chart(fig_nuevos, use_container_width=True)

# Lista de nuevos por año (expandible)
with st.expander("Ver qué apartamentos se incorporaron cada año"):
    for año in sorted(nuevos_año["año"]):
        apts_nuevos = df_primero[df_primero["año_entrada"] == año]["apartamento"].tolist()
        st.markdown(f"**{año}** ({len(apts_nuevos)}): {', '.join(sorted(apts_nuevos))}")

# ── RETENCIÓN ─────────────────────────────────────────────────────────────────
section_title("ti-shield-check", "Retención de apartamentos por año")

años_ord_ret = sorted(años_sel)
transiciones = []
detalle_ret  = {}

for i in range(len(años_ord_ret) - 1):
    a1 = años_ord_ret[i]
    a2 = años_ord_ret[i + 1]
    set1 = set(df[(df["año"] == a1) & (df["comision"] > 0)]["apartamento"].unique())
    set2 = set(df[(df["año"] == a2) & (df["comision"] > 0)]["apartamento"].unique())
    retenidos  = set1 & set2
    perdidos   = set1 - set2
    nuevos     = set2 - set1
    pct        = round(contar_apts(retenidos) / contar_apts(set1) * 100, 1) if set1 else 0
    label      = f"{a1}→{a2}"
    transiciones.append({"transicion": label, "Retenidos": contar_apts(retenidos), "Bajas": contar_apts(perdidos), "Nuevos": contar_apts(nuevos), "pct": pct})
    detalle_ret[label] = {"retenidos": retenidos, "perdidos": perdidos, "nuevos": nuevos}

df_ret = pd.DataFrame(transiciones)

# Gráfica de barras agrupadas
fig_ret = go.Figure()
fig_ret.add_trace(go.Bar(
    x=df_ret["transicion"], y=df_ret["Retenidos"],
    name="Retenidos",
    marker=dict(color="#10b981", line=dict(color="#059669", width=1.5)),
    text=[f"<b>{v}</b>" for v in df_ret["Retenidos"]],
    textposition="outside", textfont=dict(size=14, color="#059669", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Retenidos: %{y}<extra></extra>",
))
fig_ret.add_trace(go.Bar(
    x=df_ret["transicion"], y=df_ret["Nuevos"],
    name="Nuevos",
    marker=dict(color="#60a5fa", line=dict(color="#2563eb", width=1.5)),
    text=[f"<b>{v}</b>" for v in df_ret["Nuevos"]],
    textposition="outside", textfont=dict(size=14, color="#2563eb", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Nuevos: %{y}<extra></extra>",
))
fig_ret.add_trace(go.Bar(
    x=df_ret["transicion"], y=df_ret["Bajas"],
    name="Bajas",
    marker=dict(color="#fca5a5", line=dict(color="#dc2626", width=1.5)),
    text=[f"<b>{v}</b>" for v in df_ret["Bajas"]],
    textposition="outside", textfont=dict(size=14, color="#dc2626", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Bajas: %{y}<extra></extra>",
))
# Puntos % retención
fig_ret.add_trace(go.Scatter(
    x=df_ret["transicion"], y=df_ret["pct"],
    name="% Retención", yaxis="y2",
    mode="markers+text",
    marker=dict(size=16, color="#1A1A1A", line=dict(width=3, color="white"), symbol="circle"),
    text=[f"<b>{v}%</b>" for v in df_ret["pct"]],
    textposition="top center", textfont=dict(size=14, color="#1A1A1A", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Retención: %{y}%<extra></extra>",
))

fig_ret.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=420,
    margin=dict(l=0, r=60, t=40, b=0),
    bargap=0.3, bargroupgap=0.06,
    font=dict(size=14, family="Inter, Arial"),
    xaxis=dict(tickfont=dict(size=15, family="Inter, Arial"), showgrid=False, zeroline=False),
    yaxis=dict(title="Nº apartamentos", gridcolor="#f0f2f5", zeroline=False),
    yaxis2=dict(overlaying="y", side="right", ticksuffix="%", title="% Retención", showgrid=False, range=[0, 130]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14)),
    hoverlabel=dict(font_size=15, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
)
st.plotly_chart(fig_ret, use_container_width=True)

# Detalle desplegable por transición
for label, datos in detalle_ret.items():
    with st.expander(f"Ver detalle {label}"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**✅ Retenidos ({len(datos['retenidos'])})**")
            st.write(", ".join(sorted(datos["retenidos"])) or "—")
        with c2:
            st.markdown(f"**🆕 Nuevos ({len(datos['nuevos'])})**")
            st.write(", ".join(sorted(datos["nuevos"])) or "—")
        with c3:
            st.markdown(f"**❌ Bajas ({len(datos['perdidos'])})**")
            st.write(", ".join(sorted(datos["perdidos"])) or "—")

apts_con_comision = sorted(df_año[df_año["comision"] > 0]["apartamento"].unique())
apts_sel = apts_con_comision
df_f = df_año[df_año["apartamento"].isin(apts_sel)]

# ── PISOS POR DEBAJO DE LA MEDIA ──────────────────────────────────────────────
section_title("ti-chart-bar", "Pisos por debajo de la media anual")

año_media = st.selectbox("Año a analizar", sorted(años_sel, reverse=True), key="sel_media")

df_media_año = df_f[df_f["año"] == año_media].groupby("apartamento")["comision"].sum().reset_index()
df_media_año = df_media_año[df_media_año["comision"] > 0].sort_values("comision", ascending=True)
media_val = df_media_año["comision"].sum() / contar_apts(df_media_año["apartamento"]) if not df_media_año.empty else 0

df_media_año["color"] = df_media_año.apply(
    lambda r: "#f87171" if r["comision"] / apt_peso(r["apartamento"]) < media_val else "#34d399", axis=1
)
df_media_año["border"] = df_media_año.apply(
    lambda r: "#dc2626" if r["comision"] / apt_peso(r["apartamento"]) < media_val else "#10b981", axis=1
)

fig_media = go.Figure()
fig_media.add_trace(go.Bar(
    x=df_media_año["comision"],
    y=df_media_año["apartamento"],
    orientation="h",
    marker=dict(
        color=df_media_año["color"],
        line=dict(color=df_media_año["border"], width=1.5),
    ),
    text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in df_media_año["comision"]],
    textposition="outside",
    textfont=dict(size=12, family="Inter, Arial"),
    hovertemplate="<b>%{y}</b><br>%{x:,.0f} €<extra></extra>",
))
fig_media.add_vline(
    x=media_val,
    line_dash="dash", line_color="#1A1A1A", line_width=2,
    annotation_text=f"<b>Media: {media_val:,.0f} €</b>".replace(",", "."),
    annotation_position="top right",
    annotation_font=dict(size=14, color="#1A1A1A"),
)
fig_media.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=max(500, len(df_media_año) * 28),
    margin=dict(l=0, r=100, t=20, b=0),
    bargap=0.35,
    font=dict(size=13, family="Inter, Arial"),
    yaxis=dict(tickfont=dict(size=13), showgrid=False, zeroline=False),
    xaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False),
    showlegend=False,
    hoverlabel=dict(font_size=15, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
)

n_bajo = int(df_media_año.apply(lambda r: apt_peso(r["apartamento"]) if r["comision"] / apt_peso(r["apartamento"]) < media_val else 0, axis=1).sum())
n_sobre = int(df_media_año.apply(lambda r: apt_peso(r["apartamento"]) if r["comision"] / apt_peso(r["apartamento"]) >= media_val else 0, axis=1).sum())
st.caption(f"🔴 {n_bajo} pisos por debajo de la media · 🟢 {n_sobre} pisos por encima")
st.plotly_chart(fig_media, use_container_width=True)

# ── EVOLUCIÓN INDIVIDUAL DE PISO ──────────────────────────────────────────────
section_title("ti-search", "Evolución individual de apartamento")

apt_sel = st.selectbox("Selecciona un apartamento", sorted(df_f["apartamento"].unique()), key="sel_apt")

df_apt = df_f[df_f["apartamento"] == apt_sel].sort_values(["año", "mes_num"])
df_apt = df_apt[df_apt["comision"] > 0]

fig_apt = go.Figure()
for año in sorted(df_apt["año"].unique()):
    sub   = df_apt[df_apt["año"] == año]
    color = COLORES_AÑO.get(año, "#aaaaaa")
    fig_apt.add_trace(go.Scatter(
        x=sub["mes_num"], y=sub["comision"],
        name=str(año),
        mode="lines+markers",
        line=dict(width=3.5, color=color, shape="spline", smoothing=0.8),
        marker=dict(size=10, color="white", line=dict(width=2.5, color=color)),
        fill="tozeroy",
        fillcolor=rgba(color, 0.10),
        hovertemplate=f"<b>%{{x}}</b> {año}<br>%{{y:,.0f}} €<extra></extra>",
    ))

media_apt = df_apt["comision"].mean()
fig_apt.add_hline(
    y=media_apt, line_dash="dot", line_color="#9ca3af", line_width=1.5,
    annotation_text=f"Media: {media_apt:,.0f} €".replace(",", "."),
    annotation_position="top left",
    annotation_font=dict(size=12, color="#6b7280"),
)

fig_apt.update_layout(
    template=PLOTLY_TEMPLATE,
    barcornerradius=10,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=400,
    margin=dict(l=0, r=0, t=60, b=0),
    font=dict(family="Inter, Arial"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=16)),
    xaxis=dict(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"],
        showgrid=False, zeroline=False, linecolor="#e0e4ea",
    ),
    yaxis=dict(ticksuffix=" €", gridcolor="#f0f2f5", zeroline=False),
    hovermode="x unified",
    hoverlabel=dict(font_size=16, font_family="Inter, Arial", bgcolor="white", bordercolor="#e0e4ea"),
)
total_apt = df_apt["comision"].sum()
st.caption(f"Total acumulado: **{total_apt:,.0f} €** · Media mensual: **{media_apt:,.0f} €**".replace(",", "."))
st.plotly_chart(fig_apt, use_container_width=True)
