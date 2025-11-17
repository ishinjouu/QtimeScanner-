import re
import pandas as pd
from rapidfuzz import fuzz

# ===================================================================================================
# 🔍 Matching Q-Time dengan Inspection Standard
# ===================================================================================================
def text_similarity(a, b):
    if not a or not b:
        return 0.0
    return max(
        fuzz.token_sort_ratio(a, b),
        fuzz.partial_ratio(a, b)
    ) / 100.0

def match_qtime_to_is(df_is, df_qtime):
    matches = []
    for _, q_row in df_qtime.iterrows():
        method = str(q_row.get("Method", "")).strip()
        if not method:
            continue

        q_std = str(q_row.get("Standard", "")).strip()
        q_item = str(q_row.get("Item Check", "")).strip()

        # Filter IS aktif (yang punya Method & Standard)
        if "Q Time (Method)" in df_is.columns:
            df_is_active = df_is[
                df_is["Q Time (Method)"].notna() &
                (df_is["Q Time (Method)"].astype(str).str.strip() != "") &
                df_is["Standard"].notna() &
                (df_is["Standard"].astype(str).str.strip() != "")
            ]
        else:
            df_is_active = df_is[
                df_is["Standard"].notna() &
                (df_is["Standard"].astype(str).str.strip() != "")
            ]

        # Cari exact match di kolom Standard
        exact_matches = df_is_active[
            df_is_active["Standard"].astype(str).str.strip().str.lower() == q_std.lower()
        ]
        if not exact_matches.empty:
            best_matches = exact_matches["No"].tolist()
            best_score = 1.0
        else:
            # fallback fuzzy (hanya standard)
            scores = []
            for _, is_row in df_is_active.iterrows():
                is_std = str(is_row.get("Standard", "")).strip()
                sim_std = text_similarity(q_std, is_std)
                scores.append({
                    "No": is_row.get("No", ""),
                    "Score": sim_std
                })

            if scores:
                df_scores = pd.DataFrame(scores)
                max_score = df_scores["Score"].max()

                if max_score < 0.3:  # kalau di bawah 30%, anggap gak ketemu
                    best_matches = []
                    best_score = max_score
                else:
                    best_rows = df_scores[df_scores["Score"] >= max_score - 0.01]
                    best_matches = best_rows["No"].tolist()
                    best_score = max_score
            else:
                best_matches = []
                best_score = 0.0

        matches.append({
            "Old No (Q-Time)": q_row.get("No", ""),
            "Remark (Q-Time)": q_row.get("Remark", ""),
            "Item Check (Q-Time)": q_item,
            "Standard (Q-Time)": q_std,
            "Method (Q-Time)": method,
            "Matched No (IS)": ", ".join(best_matches) if best_matches else "-",
            "Best Score": round(best_score, 3)
        })
    # Tangani duplikat dan nomor yang tidak punya match
    df_matches = pd.DataFrame(matches)

    expanded_rows = []
    for _, row in df_matches.iterrows():
        matched_list = [x.strip() for x in str(row["Matched No (IS)"]).split(",") if x.strip()]
        if not matched_list:
            expanded_rows.append(row)
        else:
            for no in matched_list:
                new_row = row.copy()
                new_row["Matched No (IS)"] = no
                expanded_rows.append(new_row)

    df_expanded = pd.DataFrame(expanded_rows)
    # df_expanded = df_expanded.sort_values(by="Best Score", ascending=False).reset_index(drop=True)
    # Cari nomor terakhir dari IS (misal "58")
    existing_nos = []
    for val in df_is["No"]:
        if isinstance(val, (int, float)) and not pd.isna(val):
            existing_nos.append(int(val))
        else:
            match = re.match(r"(\d+)", str(val))
            if match:
                existing_nos.append(int(match.group(1)))
    next_no = max(existing_nos) + 1 if existing_nos else 1

    # Cegah duplikat nomor: simpan yang best score, duplikat diberi nomor baru
    seen_nos = set()
    new_numbers = []

    for _, row in df_expanded.iterrows():
        current_no = str(row["Matched No (IS)"]).strip()
        if current_no == "-" or current_no in seen_nos or current_no == "":
            # kasih nomor baru
            new_numbers.append(str(next_no))
            next_no += 1
        else:
            seen_nos.add(current_no)
            new_numbers.append(current_no)

    df_expanded["Matched No (IS)"] = new_numbers
    df_expanded["Matched No (IS)"] = df_expanded["Matched No (IS)"].astype(str)

    def _natural_key(val: str):
        m = re.match(r"^\s*(\d+)([a-zA-Z]?)\s*$", str(val))
        if m:
            num = int(m.group(1))
            suf = m.group(2).lower()
            return (num, suf)
        return (float("inf"), str(val))  

    df_final = df_expanded.sort_values(
        by="Matched No (IS)",
        key=lambda s: s.map(_natural_key),
        ascending=True
    ).reset_index(drop=True)

    return df_final
