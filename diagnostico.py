import gspread
from google.oauth2.service_account import Credentials
import os

SPREADSHEET_ID = "1_xlbloSTnckvq7dslFQJyhTuv0Krr-XlKAJmQu4D4RQ"
SHEET_GID      = 942391946
CREDS_FILE     = os.path.join(os.path.dirname(__file__), "credentials.json")

MESES_ORDER = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
    "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DIC": 12,
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "JUNE": 6, "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9,
    "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
    "JAN": 1, "DEC": 12,
}

scopes = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
creds  = Credentials.from_service_account_file(CREDS_FILE, scopes=scopes)
client = gspread.Client(auth=creds)

spreadsheet = client.open_by_key(SPREADSHEET_ID)
worksheet   = next((s for s in spreadsheet.worksheets() if s.id == SHEET_GID), None)
raw = worksheet.get_all_values()

year_row  = raw[4]
month_row = raw[5]
total_row = raw[58]   # fila 59
neto_row  = raw[89]   # fila 90

# Forward-fill años
years_filled = []
cur_year = None
for y in year_row:
    y = y.strip()
    if y.isdigit():
        cur_year = int(y)
    years_filled.append(cur_year)

# Columnas válidas
valid_cols = []
for i, (year, month) in enumerate(zip(years_filled, month_row)):
    if i < 2 or year is None:
        continue
    m = month.strip().upper()
    if not m:
        continue
    if "POST" in m or "GESTOR" in m:
        continue
    mes_num = next((v for k, v in MESES_ORDER.items() if k in m), None)
    if mes_num is None:
        continue
    valid_cols.append((i, year, month.strip(), mes_num))

print("=== VERIFICACIÓN FILA 59 (Total Pisos) y FILA 90 (Ingresos Netos) ===\n")
print(f"{'Año':<6} {'Mes':<10} {'Col idx':<8} {'Col Excel':<10} {'Total Pisos':<16} {'Ingreso Neto'}")
print("-" * 70)

def idx_to_col(n):
    """Convierte índice 0-based a nombre de columna Excel (A, B, ..., AA, AB...)"""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

for col_idx, year, month, mes_num in valid_cols:
    total_val = total_row[col_idx].strip() if col_idx < len(total_row) else ""
    neto_val  = neto_row[col_idx].strip()  if col_idx < len(neto_row)  else ""
    col_name  = idx_to_col(col_idx)
    print(f"{year:<6} {month:<10} {col_idx:<8} {col_name:<10} {total_val:<16} {neto_val}")
