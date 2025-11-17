import streamlit as st
import pdfplumber
import pandas as pd
import numpy as np
import re
import traceback

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
# 📑 Ekstraksi tabel dari PDF
# ===================================================================================================
def extract_table_from_pdf(file):
    all_dataframes = []
    max_columns = 0
    with pdfplumber.open(file) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            page_tables = []
            # Log ALL RAW SCAN --------------------------------------------------------------//
            # st.write(f"📄 Halaman {page_num + 1}")
            # for table_idx, table in enumerate(tables):
            #     st.write(f"  ➤ Tabel {table_idx + 1} - Jumlah baris: {len(table)}")
            #     for i, row in enumerate(table):
            #         st.write(f"    Row {i}: {row}")
            # Log ALL RAW SCAN --------------------------------------------------------------//
            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                header_row_idx = None
                for idx, row in enumerate(table):
                    if row and any("Item" in str(cell) for cell in row):
                        header_row_idx = idx
                        break
                if header_row_idx is not None:
                    data = table[header_row_idx:]
                    expected_cols = 13
                    header = [deduplicate_words(str(h).strip()) if h is not None else "" for h in data[0]]
                    while len(header) < expected_cols:
                        header.append(f"Extra_{len(header)}")
                    normalized_data = []
                    for row in data[1:]:
                        padded_row = row + [""] * (len(header) - len(row))
                        target_idx = 2
                        if not padded_row[target_idx] or str(padded_row[target_idx]).strip() == "":
                            for val in padded_row[5:10]:  
                                val_clean = str(val).strip()
                                if val_clean.isdigit():
                                    padded_row[target_idx] = val_clean
                                    break
                        normalized_data.append(padded_row)

                    seen = {}
                    new_header = []
                    for col in header:
                        if col in seen:
                            seen[col] += 1
                            new_header.append(f"{col}_{seen[col]}")
                        else:
                            seen[col] = 0
                            new_header.append(col)
                    df = pd.DataFrame(normalized_data, columns=new_header)
                    page_tables.append(df)
                else:
                    df = pd.DataFrame(table)
                    page_tables.append(df)
                df["page_number"] = page_num + 1
            if page_tables:
                try:
                    merged_df = pd.concat(page_tables, axis=0, ignore_index=True)
                    all_dataframes.append(merged_df)
                except Exception as e:
                    st.warning(f"⚠️ Gagal merge tabel di halaman {page_num+1}: {e}")

    normalized_tables = []
    for df in all_dataframes:
        if df.shape[1] < max_columns:
            for i in range(df.shape[1], max_columns):
                df[f"Extra_{i}"] = ""
        normalized_tables.append(df)

    return pd.concat(normalized_tables, ignore_index=True) if normalized_tables else pd.DataFrame()

def merge_partial_rows(df, value_col="Standard", threshold=3):
    merged_rows = []
    buffer = None
    for _, row in df.iterrows():
        non_empty_cells = [str(v).strip() for v in row if str(v).strip().lower() not in ["", "none", "nan"]]
        if str(row.get("Item", "")).strip():
            if buffer is not None:
                merged_rows.append(buffer)
            buffer = row.copy()
        elif buffer is not None and len(non_empty_cells) <= threshold:
            existing_val = str(buffer.get(value_col, "")).strip()
            combined_val = ", ".join(filter(None, [existing_val] + non_empty_cells))
            buffer[value_col] = combined_val.strip(", ")
        else:
            if buffer is not None:
                merged_rows.append(buffer)
                buffer = None
            merged_rows.append(row)
    if buffer is not None:
        merged_rows.append(buffer)
    return pd.DataFrame(merged_rows)

def group_rows_by_item(df):
    if "Item" not in df.columns or "Standard" not in df.columns:
        return df
    grouped_rows = []
    buffer_row = None
    for idx, row in df.iterrows():
        item = str(row.get("Item", "")).strip()
        std = str(row.get("Standard", "")).strip()
        detail = str(row.get("Detail Standard", "")).strip() if "Detail Standard" in df.columns else ""
        if item != "":
            if buffer_row is not None:
                grouped_rows.append(buffer_row)
            buffer_row = row.copy()
        else:
            if buffer_row is not None:
                buffer_row["Standard"] = f"{buffer_row['Standard']}, {std}".strip(', ')
                if "Detail Standard" in buffer_row and detail:
                    buffer_row["Detail Standard"] = f"{buffer_row['Detail Standard']}, {detail}".strip(', ')
    if buffer_row is not None:
        grouped_rows.append(buffer_row)

    return pd.DataFrame(grouped_rows)

# ===================================================================================================
# 🧹 Cleaned Inspection Standard & Clean Footer
# ===================================================================================================
def clean_inspection_standard(df):
    if df.empty:
        return df

    header_indices = []
    for i in range(len(df)):
        row_text = " ".join(str(x).lower() for x in df.iloc[i].values if pd.notnull(x))
        if "no" in row_text and "item" in row_text and "standard" in row_text:
            header_indices.append(i)

    if not header_indices:
        return df

    result_tables = []

    for idx, start_idx in enumerate(header_indices):
        end_idx = header_indices[idx + 1] if idx + 1 < len(header_indices) else len(df)
        sub_df = df.iloc[start_idx:end_idx].copy()

        # cari batas header atas & bawah
        header_rows_idx = []
        for j in range(len(sub_df)):
            row_text = " ".join(str(x).lower() for x in sub_df.iloc[j].values if pd.notnull(x))
            if "no" in row_text and "item" in row_text and not header_rows_idx:
                header_rows_idx.append(j)
            elif "method" in row_text and header_rows_idx:
                header_rows_idx.append(j)
                break

        if not header_rows_idx:
            continue

        start_h = header_rows_idx[0]
        end_h = header_rows_idx[-1]
        header_rows = sub_df.iloc[start_h:end_h + 1].values.tolist()

        # samakan panjang semua baris header
        max_len = max(len(r) for r in header_rows)
        header_rows = [list(r) + [""] * (max_len - len(r)) for r in header_rows]

        # gabungkan baris header
        header_final = []
        for col_i in range(max_len):
            parts = [str(r[col_i]).strip() for r in header_rows if str(r[col_i]).strip()]
            joined = " ".join(parts)
            header_final.append(re.sub(r"\s+", " ", joined))

        data_df = sub_df.iloc[end_h + 1:].copy()
        data_df.columns = header_final[:len(data_df.columns)]

        # fungsi bantu cari kolom
        def get_col(df, patterns):
            for c in df.columns:
                low = c.lower().replace(".", " ")
                if all(p in low for p in patterns):
                    return c
            return None

        # cari kolom inti lain
        col_no   = get_col(data_df, ["no"])
        col_item = get_col(data_df, ["item"])
        col_std  = get_col(data_df, ["standard"])
        col_vjs  = get_col(data_df, ["verifikasi", "job", "method"])
        col_qt   = get_col(data_df, ["q", "time", "method"])
        col_op   = get_col(data_df, ["100", "method"]) or get_col(data_df, ["operator", "method"])

        # deteksi kolom insp normal method dan frek
        insp_cols = [c for c in data_df.columns if "insp" in c.lower() and "normal" in c.lower()]

        col_insp_method = None
        col_insp_frek = None

        if insp_cols:
            for c in insp_cols:
                cl = c.lower()
                if "method" in cl and "frek" not in cl:
                    col_insp_method = c
                elif "frek" in cl and "method" not in cl:
                    col_insp_frek = c

            # fallback: kalau cuma ada 1 kolom tapi headernya gabung “Method Frek.”
            if col_insp_method and not col_insp_frek:
                right_index = list(data_df.columns).index(col_insp_method) + 1
                if right_index < len(data_df.columns):
                    right_name = data_df.columns[right_index].lower()
                    if "frek" in right_name:
                        col_insp_frek = data_df.columns[right_index]
            elif not col_insp_method and insp_cols:
                if re.search(r"method.*frek|frek.*method", insp_cols[0].lower()):
                    col_insp_method = insp_cols[0]
                    col_insp_frek = insp_cols[0]

        # mapping hasil akhir
        cols_map = {
            "No": col_no,
            "Item": col_item,
            "Standard": col_std,
            "Verifikasi Job Set Up (Method)": col_vjs,
            "Insp. Normal (Method)": col_insp_method,
            "Insp. Normal (Frek.)": col_insp_frek,
            "Q Time (Method)": col_qt,
            "100% (Method)": col_op,
        }

        clean_df = pd.DataFrame()
        for nice_name, raw_col in cols_map.items():
            if raw_col:
                matched = [c for c in data_df.columns if c == raw_col or c.startswith(raw_col + "_")]
                if matched:
                    col_data = data_df[matched[0]]
                    if isinstance(col_data, pd.DataFrame):
                        col_data = col_data.iloc[:, 0]
                    clean_df[nice_name] = col_data
                else:
                    clean_df[nice_name] = np.nan
            else:
                clean_df[nice_name] = np.nan

        # bersihkan baris kosong
        clean_df = clean_df.dropna(how="all").reset_index(drop=True)
        # isi kolom penting
        for c in ["No", "Item", "Standard"]:
            clean_df[c] = clean_df[c].fillna(method="ffill")

        # ffill kolom frek kalau kosong tapi method aktif
        if "Insp. Normal (Frek.)" in clean_df.columns and "Insp. Normal (Method)" in clean_df.columns:
            for i in range(1, len(clean_df)):
                method_now = str(clean_df.loc[i, "Insp. Normal (Method)"]).strip()
                frek_now   = str(clean_df.loc[i, "Insp. Normal (Frek.)"]).strip()
                frek_prev  = str(clean_df.loc[i - 1, "Insp. Normal (Frek.)"]).strip()
                if frek_now == "" and method_now != "" and frek_prev != "":
                    clean_df.loc[i, "Insp. Normal (Frek.)"] = frek_prev

        result_tables.append(clean_df)

    return pd.concat(result_tables, ignore_index=True) if result_tables else df
# Section Nomor -----------------//
def tambah_section_nomor(df):
    if df.empty:
        return df
    SECTION_REGEX = r'^\s*(I{1,3}|IV|V|VI{0,3}|VII{0,3}|VIII|IX|X)\s*[\.\-–]\s*(.+)$'
    def roman_to_int(roman):
        roman = roman.upper()
        roman_dict = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
        result, prev = 0, 0
        for char in reversed(roman):
            val = roman_dict.get(char, 0)
            result += val if val >= prev else -val
            prev = val
        return result
    cleaned_rows = []
    section_col = []
    current_section = None
    for _, row in df.iterrows():
        first_col = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        match = re.match(SECTION_REGEX, first_col, re.IGNORECASE)
        if match:
            roman = match.group(1)
            title = match.group(2).strip()  
            number = roman_to_int(roman)
            current_section = f"{number}. {title}"  
            continue  
        cleaned_rows.append(row)
        section_col.append(current_section)

    # gabung hasil
    clean_df = pd.DataFrame(cleaned_rows, columns=df.columns)
    clean_df.insert(0, "Section", section_col)
    clean_df["Section"] = clean_df["Section"].ffill()

    return clean_df

# gabungin point nomor menjadi 1a, 1b, 1c --------------------//
def merge_point_item(df):
    if df.empty:
        return df

    col_no = None
    col_item = None
    for c in df.columns:
        lc = c.lower()
        if "no" == lc.strip():
            col_no = c
        elif "item" in lc:
            col_item = c

    if not col_no or not col_item:
        return df  

    new_no = []
    new_item = []
    for no, item in zip(df[col_no], df[col_item]):
        no_str = str(no).strip() if pd.notna(no) else ""
        item_str = str(item).strip() if pd.notna(item) else ""

        # Deteksi awalan huruf + titik (contoh: a., b., c.)
        match = re.match(r"^([a-zA-Z])[\.\)]\s*(.*)", item_str)
        if match:
            letter = match.group(1).lower()
            remaining_item = match.group(2).strip()
            combined_no = f"{no_str}{letter}"
            new_no.append(combined_no)
            new_item.append(remaining_item)
        else:
            new_no.append(no_str)
            new_item.append(item_str)

    df[col_no] = new_no
    df[col_item] = new_item
    return df

# Footer -----------------//
def hapus_footer(df):
    if df.empty:
        return df
    # indikator footer
    footer_signals = [
        "dibuat", "bambang", "instruksi kerja", 
        "inspection standard", "berlaku mulai"
    ]
    drop_indexes = []
    for idx in df.index:
        row_text = " ".join(str(x).lower() for x in df.loc[idx].values if pd.notnull(x))
        if any(sig in row_text for sig in footer_signals):
            drop_indexes.append(idx)
    if drop_indexes:
        st.info(f"🧹 Menghapus {len(drop_indexes)} baris footer yang terdeteksi: {drop_indexes}")
        df = df.drop(index=drop_indexes)
    df = df.replace(r"^\s*$", np.nan, regex=True).dropna(how="all")
    df = df.reset_index(drop=True)
    return df

# ===================================================================================================
# Streamlit UI
# ===================================================================================================
# st.set_page_config(page_title="Scanner IS", layout="wide")
# st.title("Scanner IS (Versi Standalone)")

# uploaded_file = st.file_uploader("Upload file IS (PDF)", type="pdf")

# if uploaded_file:
#     try:
#         # 1️Ekstrak tabel dari PDF
#         df_raw = extract_table_from_pdf(uploaded_file)
#         if df_raw.empty:
#             st.warning("Tidak ada tabel terdeteksi di file ini.")
#         else:
#             st.success(f"Berhasil ekstrak {len(df_raw)} baris dari file IS.")
#             st.subheader("Data Mentah")
#             st.dataframe(df_raw, use_container_width=True, hide_index=True)

#         # Bersihkan tabel (gabung 3 baris header)
#         df_cleaned = clean_inspection_standard(df_raw)
#         # Hapus footer (setelah tabel bersih)
#         df_final = hapus_footer(df_cleaned)
#         # Tambah kolom section
#         df_final = tambah_section_nomor(df_final)
#         df_final = merge_point_item(df_final)

#         # Tampilkan hasil akhir
#         if not df_final.empty:
#             st.subheader("Inspection Standard (Cleaned & Footer Removed)")
#             st.dataframe(df_final, use_container_width=True, hide_index=True)

#             csv_clean = df_final.to_csv(index=False).encode("utf-8")
#             st.download_button(
#                 "Download hasil bersih (CSV)",
#                 csv_clean,
#                 "inspection_standard_clean.csv",
#                 "text/csv",
#             )
#         else:
#             st.warning("Tidak ada data bersih yang bisa ditampilkan.")
#             csv = df_raw.to_csv(index=False).encode("utf-8")
#             st.download_button("Download hasil CSV", csv, "hasil_scan_is.csv", "text/csv")

#     except Exception as e:
#         st.error(f"Terjadi error saat memproses file: {e}")
#         st.text(traceback.format_exc())

# ===================================================================================================
# 🚀 Pipeline Utama
def process_inspection_standard(file):
    df_raw = extract_table_from_pdf(file)
    df_cleaned = clean_inspection_standard(df_raw)
    df_no_footer = hapus_footer(df_cleaned)
    df_with_section = tambah_section_nomor(df_no_footer)
    df_final = merge_point_item(df_with_section)
    return df_final