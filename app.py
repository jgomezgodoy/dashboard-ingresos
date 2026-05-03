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

# Colores fijos por año — más vivos y modernos
COLORES_AÑO = {
    2022: "#2dd4bf",   # teal
    2023: "#fb923c",   # naranja cálido
    2024: "#818cf8",   # índigo suave
    2025: "#f472b6",   # rosa
    2026: "#4ade80",   # verde lima
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
    /* Fondo general */
    .stApp { background-color: #f5f7fa; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e4ea; }

    /* KPI cards */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e0e4ea;
        border-radius: 16px;
        padding: 22px 24px;
        text-align: center;
        transition: transform .15s;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .kpi-card:hover { transform: translateY(-3px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }
    .kpi-label { color: #6b7280; font-size: 16px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 10px; }
    .kpi-value { color: #111827; font-size: 42px; font-weight: 700; line-height: 1; }
    .kpi-delta { font-size: 16px; margin-top: 8px; }
    .kpi-up   { color: #16a34a; }
    .kpi-down { color: #dc2626; }
    .kpi-neutral { color: #6b7280; }

    /* Section titles */
    .section-title {
        color: #111827;
        font-size: 18px;
        font-weight: 700;
        margin: 32px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #e0e4ea;
    }

    /* Sidebar filters */
    .sidebar-title {
        color: #2563eb;
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

# ── DATA LOADING ──────────────────────────────────────────────────────────────
def parse_amount(val: str) -> float:
    """Convierte string con formato español (1.234,56 €) a float."""
    if not val:
        return 0.0
    try:
        clean = val.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
        return float(clean)
    except Exception:
        return 0.0

def _parse_raw(raw):
    """Parsea los datos crudos del sheet y devuelve df, df_totals, df_margen."""

    year_row  = raw[4]   # fila 5
    month_row = raw[5]   # fila 6

    # Detectar dinámicamente filas de apartamentos (col B desde fila 8
    # hasta encontrar "Total Pisos Neto")
    apt_start = 7  # índice 0-based de fila 8
    total_idx = None
    for i in range(apt_start, len(raw)):
        col_b = raw[i][1].strip().lower() if len(raw[i]) > 1 else ""
        if "total pisos" in col_b:
            total_idx = i
            break

    if total_idx is None:
        total_idx = apt_start + 51  # fallback

    apt_rows  = raw[apt_start:total_idx]
    total_row = raw[total_idx] if total_idx < len(raw) else []

    # Detectar fila de Ingresos netos dinámicamente (buscar "ingresos netos" en col B)
    neto_row = []
    for i in range(total_idx, len(raw)):
        col_b = raw[i][1].strip().lower() if len(raw[i]) > 1 else ""
        if "ingresos netos" in col_b:
            neto_row = raw[i]
            break

    # Forward-fill años
    years_filled = []
    cur_year = None
    for y in year_row:
        y = y.strip()
        if y.isdigit():
            cur_year = int(y)
        years_filled.append(cur_year)

    # Extender years_filled si month_row es más largo (celdas fusionadas truncan year_row)
    if len(years_filled) < len(month_row):
        years_filled += [cur_year] * (len(month_row) - len(years_filled))

    # Columnas válidas (saltamos col A, col B y columnas POST GESTORES)
    valid_cols = []
    for i, (year, month) in enumerate(zip(years_filled, month_row)):
        if i < 2:
            continue
        if year is None:
            continue
        m = month.strip().upper()
        if not m:
            continue
        if "POST" in m or "GESTOR" in m:
            continue
        # Obtener número de mes para ordenar
        mes_num = next((v for k, v in MESES_ORDER.items() if k in m), None)
        if mes_num is None:
            continue
        valid_cols.append((i, year, month.strip(), mes_num))

    # Apartamentos
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

    # Totales por mes (fila 59) + columna POST GESTORES adyacente si existe
    totals = []
    for col_idx, year, month, mes_num in valid_cols:
        val_antes = total_row[col_idx].strip() if col_idx < len(total_row) else ""
        amount_antes = parse_amount(val_antes)

        # La columna POST GESTORES es la siguiente (col_idx + 1) si está vacía en month_row
        col_post = col_idx + 1
        post_label = month_row[col_post].strip().upper() if col_post < len(month_row) else ""
        if not post_label or "POST" in post_label or "GESTOR" in post_label:
            val_post   = total_row[col_post].strip() if col_post < len(total_row) else ""
            amount_post = parse_amount(val_post) if val_post else None
        else:
            amount_post = None

        totals.append({
            "año": year, "mes": month, "mes_num": mes_num,
            "total": amount_antes, "total_post": amount_post,
        })

    df_totals = pd.DataFrame(totals)

    # % gestores = (total - total_post) / total * 100 (solo cuando hay POST GESTORES)
    df_totals["coste_gestores"] = df_totals.apply(
        lambda r: r["total"] - r["total_post"] if r["total_post"] is not None and r["total"] > 0 else None, axis=1
    )
    df_totals["pct_gestores"] = df_totals.apply(
        lambda r: round(r["coste_gestores"] / r["total"] * 100, 1) if r["coste_gestores"] is not None and r["total"] > 0 else None, axis=1
    )

    # Beneficio neto por mes (fila 90)
    netos = []
    for col_idx, year, month, mes_num in valid_cols:
        val    = neto_row[col_idx].strip() if col_idx < len(neto_row) else ""
        amount = parse_amount(val)
        netos.append({"año": year, "mes": month, "mes_num": mes_num, "neto": amount})

    df_netos = pd.DataFrame(netos)

    # % beneficio neto = neto / total_pisos_neto * 100
    df_margen = df_totals.merge(df_netos, on=["año", "mes", "mes_num"])
    df_margen["margen_pct"] = df_margen.apply(
        lambda r: round(r["neto"] / r["total"] * 100, 1) if r["total"] > 0 else None, axis=1
    )

    return df, df_totals, df_margen

@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        # En Streamlit Cloud las credenciales vienen de st.secrets
        # En local se leen del archivo credentials.json
        try:
            has_secrets = "credentials_json" in st.secrets
        except Exception:
            has_secrets = False

        if has_secrets:
            import json
            creds = Credentials.from_service_account_info(
                json.loads(st.secrets["credentials_json"]), scopes=scopes
            )
        else:
            creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
        client = gspread.Client(auth=creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet   = next((s for s in spreadsheet.worksheets() if s.id == SHEET_GID), None)
        if worksheet is None:
            raise Exception("Hoja no encontrada")
        raw    = worksheet.get("A1:ZZ500")
        result = _parse_raw(raw)
        # Guardar caché local con timestamp
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"data": result, "ts": datetime.now()}, f)
        return result
    except Exception:
        # Sin internet: cargar desde caché local
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
            ts = cache["ts"].strftime("%d/%m/%Y %H:%M")
            st.warning(f"⚠️ Sin conexión — mostrando datos guardados el {ts}")
            return cache["data"]
        else:
            st.error("Sin conexión y sin datos guardados. Conéctate a internet al menos una vez.")
            st.stop()

# ── HEADER ────────────────────────────────────────────────────────────────────
col_titulo, col_btn = st.columns([5, 1])
with col_titulo:
    st.markdown("## 💰 Dashboard Ingresos")
with col_btn:
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with st.spinner("Cargando datos..."):
    df, df_totals, df_margen = load_data()

# Filtro de años
años_disponibles = sorted(df["año"].unique())
años_sel = st.multiselect("Filtrar por año", options=años_disponibles, default=años_disponibles, label_visibility="visible")

if not años_sel:
    st.warning("Selecciona al menos un año.")
    st.stop()

df_tot_f = df_totals[df_totals["año"].isin(años_sel)]
df_año   = df[df["año"].isin(años_sel)]

# ── KPI CARDS ─────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">Resumen general</div>', unsafe_allow_html=True)

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

# Fila 1: un card por año con ingresos + apartamentos activos
cols_años = st.columns(len(años_ord))
for i, año in enumerate(años_ord):
    df_año_i = df_año[df_año["año"] == año]
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
_hoy = datetime.now()
_mes_anterior = 12 if _hoy.month == 1 else _hoy.month - 1
_año_anterior = _hoy.year - 1 if _hoy.month == 1 else _hoy.year
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

    df_rank = (
        df[(df["año"] == _last_año) & (df["mes_num"] == _last_mes_num) & (df["comision"] > 0)]
        .groupby("apartamento")["comision"].sum()
        .reset_index()
        .sort_values("comision", ascending=True)   # ascending para que la barra más alta quede arriba en horizontal
    )

    _color = COLORES_AÑO.get(_last_año, "#4ade80")
    _total_mes = df_rank["comision"].sum()
    _n_apts_mes = contar_apts(df_rank["apartamento"])
    _media_mes = _total_mes / _n_apts_mes if _n_apts_mes > 0 else 0

    st.markdown(
        f'<div class="section-title">📊 Ingresos por apartamento — {_last_mes_lbl} {_last_año}</div>',
        unsafe_allow_html=True,
    )

    _c1, _c2, _c3 = st.columns(3)
    _c1.metric("Total mes", f"{_total_mes:,.0f} €".replace(",", "."))
    _c2.metric("Media por apartamento", f"{_media_mes:,.0f} €".replace(",", "."))
    _c3.metric("Apartamentos activos", f"{_n_apts_mes}")

    fig_rank = go.Figure()
    fig_rank.add_trace(go.Bar(
        x=df_rank["comision"],
        y=df_rank["apartamento"],
        orientation="h",
        marker=dict(
            color=[rgba(_color, 0.55) if v >= _media_mes else rgba(_color, 0.30) for v in df_rank["comision"]],
            line=dict(color=_color, width=1.5),
        ),
        text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in df_rank["comision"]],
        textposition="outside",
        textfont=dict(size=12, family="Inter, Arial", color="#111827"),
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} €<extra></extra>",
    ))
    fig_rank.add_vline(
        x=_media_mes,
        line_dash="dash", line_color="#374151", line_width=1.8,
        annotation_text=f"<b>Media: {_media_mes:,.0f} €</b>".replace(",", "."),
        annotation_position="top right",
        annotation_font=dict(size=13, color="#374151"),
    )
    fig_rank.update_layout(
        template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">🚀 Evolución mensual de ingresos</div>', unsafe_allow_html=True)

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
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=400,
    margin=dict(l=0, r=0, t=60, b=0),
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
st.markdown('<div class="section-title">🍾 Ingresos y Beneficio</div>', unsafe_allow_html=True)

df_anual = df_margen[df_margen["año"].isin(años_sel)].groupby("año").agg(
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
    marker=dict(size=16, color="#374151", line=dict(width=3, color="white"),
                symbol="diamond"),
    text=[f"<b>{v:.1f}%</b>" for v in df_anual["margen_pct"]],
    textposition="top center",
    textfont=dict(size=15, color="#374151"),
    hovertemplate="<b>%{x}</b><br>Beneficio: %{y:.1f}%<extra></extra>",
))

fig_anual.update_layout(
    template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">💀 Coste de Gestores externos</div>', unsafe_allow_html=True)

df_gest = df_totals[
    df_totals["pct_gestores"].notna() & df_totals["año"].isin(años_sel)
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
        line=dict(width=3.5, color="#374151", shape="spline", smoothing=0.7),
        marker=dict(size=10, color="white", line=dict(width=2.5, color="#374151")),
        text=[f"<b>{v:.1f}%</b>" for v in df_gest["pct_gestores"]],
        textposition="top center",
        textfont=dict(size=12, color="#374151", family="Inter, Arial"),
        hovertemplate="<b>%{x}</b><br>% gestores: %{y:.1f}%<extra></extra>",
        yaxis="y2",
    ))

    pct_media = df_gest["pct_gestores"].mean()
    coste_total = df_gest["coste_gestores"].sum()

    fig_gest.update_layout(
        template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">🏆 Top 10 meses récord</div>', unsafe_allow_html=True)

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
        color=[COLORES_AÑO.get(a, "#aaaaaa") for a in top10["año"]],
        line=dict(color=[rgba(COLORES_AÑO.get(a,"#aaa"),0.4) for a in top10["año"]], width=1),
    ),
    text=[f"<b>{v:,.0f} €</b>".replace(",", ".") for v in top10["total"]],
    textposition="outside",
    textfont=dict(size=14, color="#111827", family="Inter, Arial"),
    hovertemplate="<b>%{y}</b><br>%{x:,.0f} €<extra></extra>",
))
fig_top.update_layout(
    template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">🍩 Nuevos apartamentos incorporados por año</div>', unsafe_allow_html=True)

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
st.markdown('<div class="section-title">🔒 Retención de apartamentos por año</div>', unsafe_allow_html=True)

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
    marker=dict(size=16, color="#374151", line=dict(width=3, color="white"), symbol="circle"),
    text=[f"<b>{v}%</b>" for v in df_ret["pct"]],
    textposition="top center", textfont=dict(size=14, color="#374151", family="Inter, Arial"),
    hovertemplate="<b>%{x}</b><br>Retención: %{y}%<extra></extra>",
))

fig_ret.update_layout(
    template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">🌈 Pisos por debajo de la media anual</div>', unsafe_allow_html=True)

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
    line_dash="dash", line_color="#374151", line_width=2,
    annotation_text=f"<b>Media: {media_val:,.0f} €</b>".replace(",", "."),
    annotation_position="top right",
    annotation_font=dict(size=14, color="#374151"),
)
fig_media.update_layout(
    template=PLOTLY_TEMPLATE,
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
st.markdown('<div class="section-title">🔍 Evolución individual de apartamento</div>', unsafe_allow_html=True)

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
