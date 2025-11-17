import pdfplumber
import pandas as pd
import numpy as np
import re

# ===================================================================================================
# 🧩 Utility Function
# ===================================================================================================
def normalize_text(text):
    if not isinstance(text, str):
        return text
    return text.replace('\n', '').strip().lower()

def deduplicate_words(text):
    if not isinstance(text, str):
        return text
    words = text.strip().split()
    deduped = []
    for word in words:
        if not deduped or deduped[-1] != word:
            deduped.append(word)
    return " ".join(deduped)

# ===================================================================================================
# 📑 Ekstraksi tabel dari PDF Q-Time
# ===================================================================================================
def extract_qtime_from_pdf(file):
    """Ekstraksi tabel dari PDF Q-Time."""
    all_dataframes = []
    with pdfplumber.open(file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # cari header
                header_row_idx = None
                for idx, row in enumerate(table):
                    if row and any("Item" in str(cell) or "Standard" in str(cell) for cell in row):
                        header_row_idx = idx
                        break

                if header_row_idx is None:
                    continue

                data = table[header_row_idx:]
                expected_cols = 10
                header = [deduplicate_words(str(h).strip()) if h else "" for h in data[0]]
                while len(header) < expected_cols:
                    header.append(f"Extra_{len(header)}")

                normalized_data = []
                for row in data[1:]:
                    padded_row = row + [""] * (len(header) - len(row))
                    normalized_data.append(padded_row)

                # hilangkan duplikat nama kolom
                seen, new_header = {}, []
                for col in header:
                    if col in seen:
                        seen[col] += 1
                        new_header.append(f"{col}_{seen[col]}")
                    else:
                        seen[col] = 0
                        new_header.append(col)

                df = pd.DataFrame(normalized_data, columns=new_header)
                df["page_number"] = page_num + 1
                all_dataframes.append(df)

    return pd.concat(all_dataframes, ignore_index=True) if all_dataframes else pd.DataFrame()

# ===================================================================================================
# 🧹 Clean Q-Time
# ===================================================================================================
def clean_qtime(df):
    """Bersihkan hasil ekstraksi tabel Q-Time menjadi format terstruktur."""
    if df.empty:
        return df

    # gabungkan multi-baris header
    header_idx = None
    for i, row in df.iterrows():
        text = " ".join(str(x).lower() for x in row if pd.notnull(x))
        if "no" in text and "item" in text and "standard" in text:
            header_idx = i
            break

    if header_idx is not None:
        header = [deduplicate_words(str(x)) for x in df.iloc[header_idx]]
        df = df.iloc[header_idx + 1:].copy()
        df.columns = header[:len(df.columns)]

    df = df.replace(r"^\s*$", np.nan, regex=True).dropna(how="all")

    # ambil kolom penting
    col_no = next((c for c in df.columns if "no" in c.lower()), None)
    col_item = next((c for c in df.columns if "item" in c.lower()), None)
    col_std = next((c for c in df.columns if "standard" in c.lower()), None)
    col_method = next((c for c in df.columns if "method" in c.lower()), None)

    cols_map = {
        "No": col_no,
        "Item Check": col_item,
        "Standard": col_std,
        "Method": col_method,
    }

    df_clean = pd.DataFrame()
    for nice_name, raw_col in cols_map.items():
        df_clean[nice_name] = df[raw_col] if raw_col else np.nan

    # bersihkan None, isi no kosong
    df_clean = df_clean.replace("None", np.nan).reset_index(drop=True)
    df_clean["No"] = df_clean["No"].fillna(method="ffill")

    # ================================================================
    # 🔡 Gabungkan sub-point huruf (a., b., c.) ke No utama
    # ================================================================
    new_no, new_item = [], []
    for no, item in zip(df_clean["No"], df_clean["Item Check"]):
        no_str = str(no).strip() if pd.notna(no) else ""
        item_str = str(item).strip() if pd.notna(item) else ""
        m = re.match(r"^([a-zA-Z])[\.\)]\s*(.*)", item_str)
        if m:
            letter = m.group(1).lower()
            remainder = m.group(2).strip()
            new_no.append(f"{no_str}{letter}")
            new_item.append(remainder)
        else:
            new_no.append(no_str)
            new_item.append(item_str)
    df_clean["No"] = new_no
    df_clean["Item Check"] = new_item

    # ================================================================
    # 🧾 Tambah kolom Remark (ambil simbol huruf kapital di awal No)
    # ================================================================
    remarks = []
    clean_no = []
    for val in df_clean["No"]:
        val_str = str(val).strip()
        match = re.match(r"^([A-Z])\s*(.*)", val_str)
        if match:
            remarks.append(f"({match.group(1)})")   
            clean_no.append(match.group(2).strip()) 
        else:
            remarks.append("")
            clean_no.append(val_str)
    df_clean["Remark"] = remarks
    df_clean["No"] = clean_no

    # 🧹 Validasi: hapus baris kosong atau tidak bermakna--------------------------------------//
    def is_invalid_row(row):
        # kalau semua kolom NaN atau kosong → hapus
        if all(pd.isna(v) or str(v).strip() == "" for v in row):
            return True
        # ambil teks gabungan biar gampang
        row_text = " ".join(str(v).strip() for v in row if pd.notna(v)).strip()
        # kalau cuma angka (1 sampai 99999) → hapus
        if re.fullmatch(r"^\d{1,5}$", row_text):
            return True
        return False

    # apply filter
    df_clean = df_clean[~df_clean.apply(is_invalid_row, axis=1)].reset_index(drop=True)
    return df_clean

# ===================================================================================================
# 🚀 Pipeline Utama
def process_qtime(file):
    """Jalankan proses ekstraksi & cleaning Q-Time."""
    df_raw = extract_qtime_from_pdf(file)
    df_clean = clean_qtime(df_raw)
    return {"raw": df_raw, "clean": df_clean}
