import streamlit as st
import gspread
import pandas as pd
import json
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
 
# ── CONFIGURACIÓN ────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Propietario | Singular House",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)
 
SPREADSHEET_ID = "1vtN8POdaxUji7QyTdJyrx7TkZPvGIKVz-g1a7MzmBeM"
 
GRUPO_GIDS = {
    1: 641973106,
    2: 731876679,
    3: 598266783,
    4: 1086396529,
}
 
APARTMENTS = {
    "reina_cristina": {
        "nombre":       "Reina Cristina 1",
        "grupo":        4,
        "nombre_sheet": "REINA CRISTINA",
        "ciudad":       "Madrid",
    },
}
 
MONTHS_ES   = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
               "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MONTHS_SHORT = ["Ene","Feb","Mar","Abr","May","Jun",
                "Jul","Ago","Sep","Oct","Nov","Dic"]
MONTHS_NUM  = {m: i+1 for i, m in enumerate(MONTHS_ES)}
 
# Datos históricos 2024 y 2025 (hardcoded — el sheet solo contiene 2026)
HISTORICAL = {
    "reina_cristina": {
        2024: [
            {"mes":"Enero",      "reservas":2, "avg_pax":3.5, "dias":17, "ingreso":2837.38,  "comision":397.11,  "propietario":False, "precio_noche":165},
            {"mes":"Febrero",    "reservas":4, "avg_pax":4.0, "dias":23, "ingreso":5205.09,  "comision":723.76,  "propietario":False, "precio_noche":224},
            {"mes":"Marzo",      "reservas":4, "avg_pax":5.5, "dias":16, "ingreso":5188.32,  "comision":721.25,  "propietario":True,  "precio_noche":304},
            {"mes":"Abril",      "reservas":3, "avg_pax":4.0, "dias":14, "ingreso":4320.98,  "comision":605.40,  "propietario":False, "precio_noche":299},
            {"mes":"Mayo",       "reservas":5, "avg_pax":4.0, "dias":25, "ingreso":7498.94,  "comision":1053.59, "propietario":False, "precio_noche":301},
            {"mes":"Junio",      "reservas":2, "avg_pax":4.0, "dias":15, "ingreso":4594.59,  "comision":660.70,  "propietario":True,  "precio_noche":309},
            {"mes":"Julio",      "reservas":2, "avg_pax":5.0, "dias":22, "ingreso":4630.68,  "comision":666.10,  "propietario":True,  "precio_noche":219},
            {"mes":"Agosto",     "reservas":5, "avg_pax":3.6, "dias":24, "ingreso":6302.60,  "comision":874.14,  "propietario":False, "precio_noche":252},
            {"mes":"Septiembre", "reservas":4, "avg_pax":4.5, "dias":18, "ingreso":6639.89,  "comision":939.00,  "propietario":True,  "precio_noche":362},
            {"mes":"Octubre",    "reservas":5, "avg_pax":4.6, "dias":27, "ingreso":7618.83,  "comision":1214.45, "propietario":False, "precio_noche":279},
            {"mes":"Noviembre",  "reservas":3, "avg_pax":4.0, "dias":22, "ingreso":7150.81,  "comision":1167.20, "propietario":False, "precio_noche":314},
        ],
        2025: [
            {"mes":"Enero",      "reservas":3, "avg_pax":3.0, "dias":21, "ingreso":3925.23,  "comision":618.80,  "propietario":True,  "precio_noche":185},
            {"mes":"Febrero",    "reservas":3, "avg_pax":4.7, "dias":16, "ingreso":4076.45,  "comision":568.70,  "propietario":True,  "precio_noche":244},
            {"mes":"Marzo",      "reservas":4, "avg_pax":3.5, "dias":17, "ingreso":4702.86,  "comision":648.40,  "propietario":True,  "precio_noche":264},
            {"mes":"Abril",      "reservas":4, "avg_pax":4.0, "dias":21, "ingreso":6693.37,  "comision":947.00,  "propietario":False, "precio_noche":306},
            {"mes":"Mayo",       "reservas":6, "avg_pax":4.8, "dias":24, "ingreso":8673.31,  "comision":1215.30, "propietario":False, "precio_noche":346},
            {"mes":"Junio",      "reservas":3, "avg_pax":4.7, "dias":18, "ingreso":5930.85,  "comision":846.90,  "propietario":True,  "precio_noche":329},
            {"mes":"Julio",      "reservas":2, "avg_pax":2.5, "dias":15, "ingreso":3487.63,  "comision":494.60,  "propietario":True,  "precio_noche":217},
            {"mes":"Agosto",     "reservas":4, "avg_pax":4.3, "dias":21, "ingreso":4555.13,  "comision":626.30,  "propietario":False, "precio_noche":204},
            {"mes":"Septiembre", "reservas":6, "avg_pax":3.7, "dias":22, "ingreso":6827.81,  "comision":938.70,  "propietario":False, "precio_noche":295},
            {"mes":"Octubre",    "reservas":5, "avg_pax":4.0, "dias":19, "ingreso":7010.93,  "comision":980.40,  "propietario":False, "precio_noche":355},
            {"mes":"Noviembre",  "reservas":5, "avg_pax":4.6, "dias":21, "ingreso":8263.74,  "comision":1168.30, "propietario":False, "precio_noche":311},
            {"mes":"Diciembre",  "reservas":4, "avg_pax":4.3, "dias":24, "ingreso":7548.33,  "comision":1075.20, "propietario":False, "precio_noche":294},
        ],
    }
}
 
# ── HELPERS ──────────────────────────────────────────────────
def parse_eur(s):
    """'€4.101,45' o '1.264,73 €'  →  float"""
    if not s:
        return 0.0
    s = str(s).replace("€","").replace(" ","").replace(".","").replace(",",".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0
 
def parse_num(s):
    """'8,00' → float"""
    if not s:
        return 0.0
    s = str(s).replace(",",".").strip()
    try:
        return float(s)
    except Exception:
        return 0.0
 
def fmt_eur(v):
    return f"€{v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
 
def fmt_int(v):
    return f"{int(v):,}".replace(",",".")
 
# ── GOOGLE SHEETS ─────────────────────────────────────────────
@st.cache_resource(ttl=1800)
def get_client():
    creds_info = json.loads(st.secrets["credentials_json"])
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)
 
@st.cache_data(ttl=1800)
def load_sheet(gid: int):
    client = get_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = spreadsheet.get_worksheet_by_id(gid)
    return ws.get_all_values()
 
# ── PARSING ───────────────────────────────────────────────────
def parse_apartment(rows, apt_name):
    """
    Extrae reservas y resúmenes mensuales de un apartamento del sheet.
    Estructura esperada (columnas 0-indexed):
      [0]J [1]gestor [2]%comision [3]mes [4]vivienda [5]huesped [6]pais
      [7]pax [8]checkin [9]checkout [10]€/noche [11]total [12]dias
      [13]limpieza [14]neto [15]comision_sh  [16]etiqueta [17]valor
    """
    reservas   = []
    resumen    = {}   # {mes: {facturacion, precio_medio, limpieza, neto, comision, num_reservas, propietario}}
 
    for row in rows:
        if len(row) < 5:
            continue
        if row[4].strip().upper() != apt_name.upper():
            continue
        mes = row[3].strip()
        if mes not in MONTHS_NUM:
            continue
 
        if mes not in resumen:
            resumen[mes] = {"propietario": False, "facturacion": 0, "precio_medio": 0,
                            "limpieza": 0, "neto": 0, "comision": 0, "num_reservas": 0}
 
        guest = row[5].strip() if len(row) > 5 else ""
 
        # Fila de reserva real
        if guest and guest.lower() not in ("", "propietario"):
            try:
                reservas.append({
                    "mes":        mes,
                    "mes_num":    MONTHS_NUM[mes],
                    "huesped":    guest,
                    "pais":       row[6].strip()         if len(row) > 6  else "",
                    "pax":        int(parse_num(row[7])) if len(row) > 7  else 0,
                    "checkin":    row[8].strip()         if len(row) > 8  else "",
                    "checkout":   row[9].strip()         if len(row) > 9  else "",
                    "precio_noche": parse_eur(row[10])   if len(row) > 10 else 0,
                    "total":      parse_eur(row[11])     if len(row) > 11 else 0,
                    "dias":       int(parse_num(row[12]))if len(row) > 12 else 0,
                    "limpieza":   parse_eur(row[13])     if len(row) > 13 else 0,
                    "neto":       parse_eur(row[14])     if len(row) > 14 else 0,
                    "comision_sh":parse_eur(row[15])     if len(row) > 15 else 0,
                })
            except Exception:
                pass
 
        # Fila de uso propietario
        if guest.lower() == "propietario":
            resumen[mes]["propietario"] = True
 
        # Etiquetas del resumen mensual
        label = row[16].strip() if len(row) > 16 else ""
        valor = row[17].strip() if len(row) > 17 else ""
        if label and valor:
            if "Facturación mensual" in label:
                resumen[mes]["facturacion"]   = parse_eur(valor)
            elif "Precio medio" in label:
                resumen[mes]["precio_medio"]  = parse_eur(valor)
            elif "Coste limpieza total" in label:
                resumen[mes]["limpieza"]      = parse_eur(valor)
            elif "Neto" in label and "Neto" == label:
                resumen[mes]["neto"]          = parse_eur(valor)
            elif "Número de reservas" in label:
                try:
                    resumen[mes]["num_reservas"] = int(parse_num(valor))
                except Exception:
                    pass
            elif mes in label and apt_name.split()[0] in label.upper():
                # Línea tipo "Enero REINA CRISTINA" → comisión SH del mes
                resumen[mes]["comision"] = parse_eur(valor)
 
    return reservas, resumen
 
def build_monthly_stats(reservas, resumen):
    """Combina reservas y resumen en una lista ordenada por mes."""
    stats = []
    for mes in MONTHS_ES:
        rs = [r for r in reservas if r["mes"] == mes]
        sm = resumen.get(mes, {})
        if not rs and not sm.get("facturacion"):
            continue
        ingreso   = sm.get("facturacion") or sum(r["total"] for r in rs)
        comision  = sm.get("comision")    or sum(r["comision_sh"] for r in rs)
        dias      = sum(r["dias"] for r in rs)
        n_res     = sm.get("num_reservas") or len(rs)
        avg_pax   = (sum(r["pax"] for r in rs) / len(rs)) if rs else 0
        pm        = sm.get("precio_medio") or (ingreso / dias if dias else 0)
        prop      = sm.get("propietario", False)
        stats.append({
            "mes": mes, "mes_num": MONTHS_NUM[mes],
            "ingreso": ingreso, "comision": comision,
            "dias": dias, "reservas": n_res,
            "avg_pax": round(avg_pax, 1),
            "precio_medio": round(pm, 2),
            "propietario": prop,
        })
    return stats
 
# ── CSS ───────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    /* Header */
    .sh-header {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e3a8a 100%);
        border-radius: 14px;
        padding: 24px 32px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .sh-header h1 { color: white; font-size: 22px; margin: 0; font-weight: 700; }
    .sh-header p  { color: rgba(255,255,255,0.7); margin: 4px 0 0 0; font-size: 13px; }
    .sh-badge {
        background: rgba(255,255,255,0.15);
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 8px;
        padding: 6px 14px;
        color: white;
        font-size: 12px;
        font-weight: 600;
    }
    /* KPI cards */
    .kpi-card {
        background: white;
        border-radius: 14px;
        padding: 20px;
        border: 1px solid #e2e8f0;
        border-top: 4px solid var(--accent, #1d4ed8);
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        text-align: left;
    }
    .kpi-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 0.8px; color: #94a3b8; margin-bottom: 8px; }
    .kpi-value { font-size: 26px; font-weight: 800; color: #0f172a; line-height: 1; }
    .kpi-sub   { font-size: 12px; color: #94a3b8; margin-top: 4px; }
    /* Info banner */
    .partial-note {
        background: #fef9c3;
        border: 1px solid #fde047;
        border-radius: 10px;
        padding: 10px 16px;
        font-size: 13px;
        color: #713f12;
        margin-bottom: 20px;
    }
    /* Section title */
    .section-title {
        font-size: 16px;
        font-weight: 700;
        color: #1e293b;
        margin: 24px 0 12px 0;
        border-left: 4px solid #1d4ed8;
        padding-left: 12px;
    }
    /* Hide Streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)
 
# ── COMPONENTES UI ────────────────────────────────────────────
def render_header(apt_cfg):
    from datetime import datetime
    fecha = datetime.today().strftime("%d/%m/%Y")
    st.markdown(f"""
    <div class="sh-header">
      <div>
        <h1>🏠 {apt_cfg['nombre']}</h1>
        <p>Dashboard Propietario · {apt_cfg['ciudad']} · Actualizado {fecha}</p>
      </div>
      <div class="sh-badge">Singular House</div>
    </div>
    """, unsafe_allow_html=True)
 
def render_kpis(stats_2026, apt_key):
    ingreso_total = sum(m["ingreso"]  for m in stats_2026)
    comision_total= sum(m["comision"] for m in stats_2026)
    dias_total    = sum(m["dias"]     for m in stats_2026)
    res_total     = sum(m["reservas"] for m in stats_2026)
    avg_precio    = ingreso_total / dias_total if dias_total else 0
    neto_total    = ingreso_total - comision_total
 
    cols = st.columns(5)
    kpis = [
        ("Ingresos Brutos 2026",   fmt_eur(ingreso_total),  "acumulado año en curso", "#1d4ed8"),
        ("Neto Propietario 2026",  fmt_eur(neto_total),     "después de comisión SH", "#059669"),
        ("Días Ocupados",          str(dias_total),          "noches alquiladas",      "#7c3aed"),
        ("Reservas",               str(res_total),           "en 2026",                "#d97706"),
        ("Precio Medio / Noche",   fmt_eur(avg_precio),     "tarifa media 2026",      "#0891b2"),
    ]
    for col, (label, value, sub, accent) in zip(cols, kpis):
        with col:
            st.markdown(f"""
            <div class="kpi-card" style="--accent:{accent}">
              <div class="kpi-label">{label}</div>
              <div class="kpi-value">{value}</div>
              <div class="kpi-sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)
 
def render_chart_ingresos(stats_2026, hist_2024, hist_2025):
    meses_labels = MONTHS_SHORT
    def to_series(data):
        d = {m["mes"]: m["ingreso"] for m in data}
        return [d.get(mes, None) for mes in MONTHS_ES]
 
    s24 = to_series(hist_2024)
    s25 = to_series(hist_2025)
    s26 = to_series(stats_2026)
 
    fig = go.Figure()
    fig.add_trace(go.Bar(name="2024", x=meses_labels, y=s24,
                         marker_color="#cbd5e1", opacity=0.7))
    fig.add_trace(go.Bar(name="2025", x=meses_labels, y=s25,
                         marker_color="#93c5fd", opacity=0.85))
    fig.add_trace(go.Bar(name="2026", x=meses_labels, y=s26,
                         marker_color="#1d4ed8"))
    fig.update_layout(
        barmode="group",
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=320,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(gridcolor="#f1f5f9", tickprefix="€"),
        xaxis=dict(gridcolor="#f1f5f9"),
        title=dict(text="Ingresos mensuales — comparativa 3 años", font=dict(size=14)),
    )
    st.plotly_chart(fig, use_container_width=True)
 
def render_chart_ocupacion(stats_2026):
    meses   = [m["mes"][:3] for m in stats_2026]
    dias    = [m["dias"]    for m in stats_2026]
    colors  = ["#f59e0b" if m["propietario"] else "#1d4ed8" for m in stats_2026]
 
    fig = go.Figure()
    fig.add_trace(go.Bar(x=meses, y=dias, marker_color=colors,
                         text=dias, textposition="outside"))
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        height=280, margin=dict(l=0, r=0, t=30, b=0),
        yaxis=dict(gridcolor="#f1f5f9"),
        title=dict(text="Días ocupados 2026  (🟡 = mes con uso propietario)", font=dict(size=14)),
    )
    st.plotly_chart(fig, use_container_width=True)
 
def render_tabla_mensual(stats_2026):
    st.markdown('<div class="section-title">Detalle mensual 2026</div>', unsafe_allow_html=True)
    rows = []
    for m in stats_2026:
        prop_badge = " 🏠" if m["propietario"] else ""
        rows.append({
            "Mes":              m["mes"] + prop_badge,
            "Reservas":         m["reservas"],
            "Días":             m["dias"],
            "Media Huéspedes":  m["avg_pax"],
            "Precio/Noche":     fmt_eur(m["precio_medio"]),
            "Ingresos Brutos":  fmt_eur(m["ingreso"]),
            "Comisión SH":      fmt_eur(m["comision"]),
            "Neto Propietario": fmt_eur(m["ingreso"] - m["comision"]),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"Mes": st.column_config.TextColumn(width="medium")})
 
def render_reservas(reservas):
    st.markdown('<div class="section-title">Reservas 2026</div>', unsafe_allow_html=True)
    if not reservas:
        st.info("No hay reservas registradas en el sheet para 2026.")
        return
    rows = []
    for r in sorted(reservas, key=lambda x: (x["mes_num"], x["checkin"])):
        rows.append({
            "Mes":        r["mes"],
            "Huésped":    r["huesped"],
            "País":       r["pais"],
            "Pax":        r["pax"],
            "Entrada":    r["checkin"],
            "Salida":     r["checkout"],
            "Días":       r["dias"],
            "€/Noche":    fmt_eur(r["precio_noche"]),
            "Total":      fmt_eur(r["total"]),
            "Limpieza":   fmt_eur(r["limpieza"]),
            "Neto":       fmt_eur(r["neto"]),
            "Comisión SH":fmt_eur(r["comision_sh"]),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
 
def render_comparativa(stats_2026, hist_2024, hist_2025):
    st.markdown('<div class="section-title">Comparativa 3 años</div>', unsafe_allow_html=True)
 
    def total(data):
        return {
            "ingreso":  sum(m["ingreso"]  for m in data),
            "comision": sum(m["comision"] for m in data),
            "dias":     sum(m["dias"]     for m in data),
            "reservas": sum(m["reservas"] for m in data),
        }
 
    t24 = total(hist_2024)
    t25 = total(hist_2025)
    t26 = total(stats_2026)
 
    def delta(old, new):
        if old == 0:
            return ""
        pct = (new - old) / old * 100
        arrow = "▲" if pct >= 0 else "▼"
        color = "green" if pct >= 0 else "red"
        return f'<span style="color:{color};font-size:12px">{arrow} {abs(pct):.1f}%</span>'
 
    cols = st.columns(4)
    metricas = [
        ("Ingresos Totales",  fmt_eur(t24["ingreso"]),  fmt_eur(t25["ingreso"]),  fmt_eur(t26["ingreso"]),
         delta(t24["ingreso"], t25["ingreso"]), delta(t25["ingreso"], t26["ingreso"])),
        ("Días Ocupados",     str(t24["dias"]),          str(t25["dias"]),          str(t26["dias"]),
         delta(t24["dias"], t25["dias"]), delta(t25["dias"], t26["dias"])),
        ("Reservas",          str(t24["reservas"]),      str(t25["reservas"]),      str(t26["reservas"]),
         delta(t24["reservas"], t25["reservas"]), delta(t25["reservas"], t26["reservas"])),
        ("Comisión SH",       fmt_eur(t24["comision"]), fmt_eur(t25["comision"]), fmt_eur(t26["comision"]),
         delta(t24["comision"], t25["comision"]), delta(t25["comision"], t26["comision"])),
    ]
    for col, (label, v24, v25, v26, d2425, d2526) in zip(cols, metricas):
        with col:
            st.markdown(f"""
            <div class="kpi-card" style="--accent:#1d4ed8; padding:16px;">
              <div class="kpi-label">{label}</div>
              <div style="margin:6px 0;font-size:13px">
                <span style="background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;color:#64748b">2024</span>
                <strong style="margin-left:6px">{v24}</strong>
              </div>
              <div style="margin:6px 0;font-size:13px">
                <span style="background:#dbeafe;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;color:#1d4ed8">2025</span>
                <strong style="margin-left:6px">{v25}</strong>
                <span style="margin-left:6px">{d2425}</span>
              </div>
              <div style="margin:6px 0;font-size:13px">
                <span style="background:#1d4ed8;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:700;color:white">2026</span>
                <strong style="margin-left:6px">{v26}</strong>
                <span style="margin-left:6px">{d2526}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)
 
    st.markdown("<br>", unsafe_allow_html=True)
    render_chart_ingresos(stats_2026, hist_2024, hist_2025)
 
# ── MAIN ──────────────────────────────────────────────────────
def main():
    inject_css()
 
    # Leer parámetro de URL: ?apt=reina_cristina
    apt_key = st.query_params.get("apt", "reina_cristina")
 
    if apt_key not in APARTMENTS:
        st.error(f"Apartamento '{apt_key}' no encontrado.")
        st.stop()
 
    apt_cfg  = APARTMENTS[apt_key]
    hist_24  = HISTORICAL.get(apt_key, {}).get(2024, [])
    hist_25  = HISTORICAL.get(apt_key, {}).get(2025, [])
 
    render_header(apt_cfg)
 
    # Cargar datos del sheet
    with st.spinner("Cargando datos del sheet..."):
        try:
            rows     = load_sheet(GRUPO_GIDS[apt_cfg["grupo"]])
            reservas, resumen = parse_apartment(rows, apt_cfg["nombre_sheet"])
            stats_26 = build_monthly_stats(reservas, resumen)
            sheet_ok = True
        except Exception as e:
            st.warning(f"⚠️ No se pudo conectar al sheet: {e}")
            stats_26 = []
            reservas = []
            sheet_ok = False
 
    if not stats_26:
        st.info("No hay datos de 2026 disponibles todavía en el sheet.")
 
    st.markdown('<div class="partial-note">⏳ <strong>2026 en curso</strong> — Los datos se actualizan automáticamente desde Google Sheets cada 30 minutos.</div>', unsafe_allow_html=True)
 
    # KPIs
    if stats_26:
        render_kpis(stats_26, apt_key)
 
    st.markdown("<br>", unsafe_allow_html=True)
 
    # Pestañas
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ingresos & Ocupación", "📋 Mensual 2026", "🧳 Reservas", "⚡ Comparativa 3 años"])
 
    with tab1:
        if stats_26:
            col1, col2 = st.columns([3, 2])
            with col1:
                render_chart_ingresos(stats_26, hist_24, hist_25)
            with col2:
                render_chart_ocupacion(stats_26)
        else:
            st.info("Sin datos de 2026 aún.")
 
    with tab2:
        if stats_26:
            render_tabla_mensual(stats_26)
        else:
            st.info("Sin datos de 2026 aún.")
 
    with tab3:
        render_reservas(reservas)
 
    with tab4:
        render_comparativa(stats_26 if stats_26 else [], hist_24, hist_25)
 
 
if __name__ == "__main__":
    main()
