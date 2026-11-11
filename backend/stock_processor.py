from __future__ import annotations

import re
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GIX_REPORT = ROOT / "files" / "gix" / "Relatorio estoque basf.csv"
MAPPING_FILE = ROOT / "data" / "relacao_sku_basf_codigo_gix.csv"
OUTPUT_DIR = ROOT / "files" / "output"
OUTPUT_CSV = OUTPUT_DIR / "estoque_vtex_basf.csv"
OUTPUT_XLS = OUTPUT_DIR / "estoque_vtex_basf.xls"

COLUMNS = [
    "SkuId",
    "TotalQuantity",
    "ReservedQuantity",
    "AvailableQuantity",
    "WarehouseId",
    "WarehouseName",
    "RefId",
    "IsActive",
    "UnlimitedQuantity",
    "LockIds",
    "DispatchedReservations",
]


def normalize_text(value: object) -> str:
    mapping = str.maketrans(
        {
            "á": "a",
            "à": "a",
            "â": "a",
            "ã": "a",
            "ä": "a",
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "í": "i",
            "ì": "i",
            "î": "i",
            "ï": "i",
            "ó": "o",
            "ò": "o",
            "ô": "o",
            "õ": "o",
            "ö": "o",
            "ú": "u",
            "ù": "u",
            "û": "u",
            "ü": "u",
            "ç": "c",
            "ñ": "n",
            "ý": "y",
            "æ": "ae",
            "œ": "oe",
        }
    )
    cleaned = str(value).replace("�", "").replace("\ufffd", "")
    return re.sub(r"[^a-z0-9]+", "", cleaned.lower().translate(mapping))


def read_with_fallback(path: Path, sep: str = ";") -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, sep=sep, encoding=encoding, engine="python")
        except (UnicodeDecodeError, ValueError) as exc:  # pragma: no cover - depends on file encoding
            last_error = exc
    raise last_error


def find_column(df: pd.DataFrame, *keywords: str) -> str:
    normalized_columns = [(str(column), normalize_text(column)) for column in df.columns]

    for keyword in keywords:
        keyword_norm = normalize_text(keyword)
        for column, normalized in normalized_columns:
            if keyword_norm in normalized:
                return column
            if get_close_matches(keyword_norm, [normalized], n=1, cutoff=0.7):
                return column

    raise KeyError(f"Nenhuma coluna encontrada para {keywords!r} em {list(df.columns)}")


def parse_quantity(value: object) -> int:
    if pd.isna(value):
        return 0
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return 0
    text = text.replace(".", "").replace(",", ".")
    try:
        return int(float(text))
    except ValueError:
        return 0


def build_vtex_stock_file(
    gix_path: Path = GIX_REPORT,
    mapping_path: Path = MAPPING_FILE,
) -> pd.DataFrame:
    gix_df = read_with_fallback(gix_path)
    mapping_df = read_with_fallback(mapping_path)

    gix_code_col = find_column(gix_df, "codigo")
    stock_col = find_column(gix_df, "estoque", "atual")

    mapping_code_col = find_column(mapping_df, "gix")
    sku_col = find_column(mapping_df, "sku", "vtex")

    gix_df = gix_df[[gix_code_col, stock_col]].copy()
    gix_df.columns = ["GIX", "ESTOQUEATUAL"]
    gix_df["GIX"] = gix_df["GIX"].astype(str).str.strip()

    mapping_df = mapping_df[[mapping_code_col, sku_col]].copy()
    mapping_df.columns = ["GIX", "SKU_VTEX"]
    mapping_df["GIX"] = mapping_df["GIX"].astype(str).str.strip()
    mapping_df["SKU_VTEX"] = mapping_df["SKU_VTEX"].astype(str).str.strip()

    merged = gix_df.merge(mapping_df, on="GIX", how="inner")
    merged["TotalQuantity"] = merged["ESTOQUEATUAL"].apply(parse_quantity)
    merged = merged.dropna(subset=["SKU_VTEX"]).copy()
    merged["SKU_VTEX"] = merged["SKU_VTEX"].astype(str).str.strip()
    merged = merged[~merged["SKU_VTEX"].str.upper().isin(["", "NULL", "NAN"])].copy()

    result = pd.DataFrame(
        {
            "SkuId": merged["SKU_VTEX"].astype(str).str.strip(),
            "TotalQuantity": merged["TotalQuantity"].astype(int),
            "ReservedQuantity": 0,
            "AvailableQuantity": merged["TotalQuantity"].astype(int),
            "WarehouseId": "1_1",
            "WarehouseName": "Estoque principal",
            "RefId": 0,
            "IsActive": True,
            "UnlimitedQuantity": False,
            "LockIds": "",
            "DispatchedReservations": 0,
        }
    )

    result = result[COLUMNS]
    result["SkuId"] = result["SkuId"].astype(str).str.strip()

    result["_sort"] = pd.to_numeric(result["SkuId"], errors="coerce")
    result = result.sort_values("_sort", kind="mergesort")
    result = result.drop(columns="_sort").reset_index(drop=True)
    return result


def save_outputs(
    frame: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[Path, Path]:
    import xlwt

    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv = output_dir / OUTPUT_CSV.name
    output_xls = output_dir / OUTPUT_XLS.name

    frame.to_csv(
        output_csv,
        index=False,
        sep=",",
        encoding="utf-8-sig",
    )

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Estoque VTEX")
    header_style = xlwt.easyxf("font: bold on")

    for col_idx, column in enumerate(frame.columns):
        sheet.write(0, col_idx, column, header_style)

    for row_idx, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        for col_idx, value in enumerate(row):
            if pd.isna(value):
                value = ""

            if frame.columns[col_idx] == "SkuId":
                sheet.write(row_idx, col_idx, str(value))
            else:
                sheet.write(row_idx, col_idx, value)

    workbook.save(str(output_xls))
    return output_csv, output_xls
