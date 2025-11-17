import os
import tempfile
import streamlit as st
import traceback
from inspectionStd import process_inspection_standard 
from qtimeMaker import process_qtime
from matcher import match_qtime_to_is
from imageExtractor import replace_point_numbers

# --------------------------------------------------------------------------------
# Streamlit UI Setup
# --------------------------------------------------------------------------------
st.set_page_config(page_title="Scanner IS & Q-Time", layout="wide")
st.title("📄 Scanner IS & Q-Time (Versi Standalone)")

# Uploaders — Inspection Standard & Q-Time
col1, col2 = st.columns(2)
with col1:
    uploaded_is = st.file_uploader("📤 Upload file IS (Inspection Standard - PDF)", type="pdf", key="is_upload")
with col2:
    uploaded_qtime = st.file_uploader("📤 Upload file Q-Time (PDF)", type="pdf", key="qtime_upload")

# --------------------------------------------------------------------------------
# 🧩 PROCESS: Inspection Standard
# --------------------------------------------------------------------------------
if uploaded_is:
    try:
        df_is_final = process_inspection_standard(uploaded_is)

        if df_is_final.empty:
            st.warning("⚠️ Tidak ada tabel terdeteksi di file IS.")
        else:
            st.success(f"✅ Berhasil memproses {len(df_is_final)} baris dari file IS.")
            st.subheader("🧹 Inspection Standard (Cleaned & Footer Removed)")
            st.dataframe(df_is_final, use_container_width=True, hide_index=True)

            # # Download cleaned IS
            # csv_is = df_is_final.to_csv(index=False).encode("utf-8")
            # st.download_button(
            #     "💾 Download hasil IS (CSV)",
            #     csv_is,
            #     "inspection_standard_clean.csv",
            #     "text/csv",
            # )
    except Exception as e:
        st.error(f"🔥 Error saat memproses Inspection Standard: {e}")
        st.text(traceback.format_exc())

# --------------------------------------------------------------------------------
# 🧩 PROCESS: Q-Time
# --------------------------------------------------------------------------------
if uploaded_qtime:
    try:
        qtime_result = process_qtime(uploaded_qtime)
        df_qtime_clean = qtime_result["clean"]

        if df_qtime_clean.empty:
            st.warning("⚠️ Tidak ada tabel terdeteksi di file Q-Time.")
        else:
            st.success(f"✅ Berhasil memproses {len(df_qtime_clean)} baris dari file Q-Time.")
            st.subheader("🧹 Q-Time (Cleaned)")
            st.dataframe(df_qtime_clean, use_container_width=True, hide_index=True)

            # # Download cleaned Q-Time
            # csv_qtime = df_qtime_clean.to_csv(index=False).encode("utf-8")
            # st.download_button(
            #     "💾 Download hasil Q-Time (CSV)",
            #     csv_qtime,
            #     "qtime_clean.csv",
            #     "text/csv",
            # )

    except Exception as e:
        st.error(f"🔥 Error saat memproses Q-Time: {e}")
        st.text(traceback.format_exc())

# --------------------------------------------------------------------------------
# Matching Process (Tnetukan berdasarkan kemiripan is : Qtime)
# --------------------------------------------------------------------------------
if uploaded_is and uploaded_qtime:
    st.info("✨ Kedua file sudah berhasil diupload. Siap untuk langkah berikutnya: perbandingan & sinkronisasi IS ↔ Q-Time.")
    try:
        df_is_final = process_inspection_standard(uploaded_is)
        qtime_result = process_qtime(uploaded_qtime)
        df_qtime_clean = qtime_result["clean"]

        # Jalankan perbandingan otomatis
        df_match = match_qtime_to_is(df_is_final, df_qtime_clean)

        st.subheader("🧩 Hasil Perbandingan Q-Time vs Inspection Standard")
        st.dataframe(df_match, use_container_width=True, hide_index=True)

        # # Tombol download hasil match
        # csv_match = df_match.to_csv(index=False).encode("utf-8")
        # st.download_button(
        #     "💾 Download hasil perbandingan (CSV)",
        #     csv_match,
        #     "match_qtime_vs_is.csv",
        #     "text/csv",
        # )

    except Exception as e:
        st.error(f"🔥 Error saat melakukan perbandingan IS vs Q-Time: {e}")
        st.text(traceback.format_exc())

# --------------------------------------------------------------------------------
# Tambahin uploader untuk gambar part Q-Time
# --------------------------------------------------------------------------------
uploaded_part = st.file_uploader("📤 Upload gambar part (PDF)", type="pdf", key="part_upload")

# --------------------------------------------------------------------------------
# Replace nomor di gambar (preview)
# --------------------------------------------------------------------------------
if uploaded_qtime and uploaded_is and uploaded_part:
    try:
        temp_part_pdf = "temp_part_input.pdf"
        with open(temp_part_pdf, "wb") as f:
            f.write(uploaded_part.getbuffer())

        # proses IS & Qtime
        df_is_final = process_inspection_standard(uploaded_is)
        qtime_result = process_qtime(uploaded_qtime)
        df_qtime_clean = qtime_result["clean"]
        df_match = match_qtime_to_is(df_is_final, df_qtime_clean)

        output_pdf = "part_fixed.pdf"
        from imageExtractor import replace_point_numbers
        replace_point_numbers(temp_part_pdf, output_pdf, df_match)

        st.success("✅ Nomor di gambar berhasil diganti!")

        # === NEW: tampilkan hasil PNG preview (diperkecil) ===
        preview_png = "detected_shapes.png"

        if os.path.exists(preview_png):
            st.subheader("👀 Preview hasil sebelum download")
            st.image(preview_png, caption="Preview hasil replace nomor", width=500)
        else:
            st.warning("⚠️ Tidak ditemukan file preview PNG.")

        # download PDF final
        with open(output_pdf, "rb") as f:
            st.download_button("💾 Download hasil gambar (PDF)", f, file_name="part_fixed.pdf")

    except Exception as e:
        st.error(f"🔥 Error saat mengganti nomor pada gambar: {e}")
        st.text(traceback.format_exc())