import re
import cv2
import numpy as np
import fitz

# ==========================================================
# 1) DETECT SHAPES (OpenCV)
# ==========================================================
def detect_point_shapes_with_numbers(image_path, page, zoom=3, debug_output="detected_shapes.png"):
    import statistics

    img = cv2.imread(image_path)
    orig = img.copy()

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 120)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    shape_boxes_cv = []
    rejected_boxes_cv = []

    print("\n============================")
    print("   DEBUG SHAPE DETECTION")
    print("============================")

    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        x, y, w, h = cv2.boundingRect(cnt)
        ratio = w / h if h != 0 else 999
        rect_area = w * h
        extent = area / rect_area if rect_area > 0 else 0

        print(f"\n[Contour {i}]")
        print(f" area={area}, w={w}, h={h}, ratio={ratio:.2f}, extent={extent:.2f}")

        passed = True
        reasons = []

        if area < 70:
            passed = False
            reasons.append("area < 70")

        if not (6 < w < 320):
            passed = False
            reasons.append("width not in range(6-320)")

        if not (6 < h < 320):
            passed = False
            reasons.append("height not in range(6-320)")

        if not (0.2 < ratio < 4.0):
            passed = False
            reasons.append("ratio outside 0.2-4.0")

        if extent < 0.55:
            passed = False
            reasons.append(f"extent < 0.55 ({extent:.2f})")

        if passed:
            print("  ✔ PASS FILTER → SHAPE MAYORITAS")
            shape_boxes_cv.append((x, y, x+w, y+h))
        else:
            print("  ✖ FAIL:", reasons)
            if 4 < w < 350 and 4 < h < 350:
                rejected_boxes_cv.append((x, y, x+w, y+h))

    if len(shape_boxes_cv) > 0:
        widths  = [box[2] - box[0] for box in shape_boxes_cv]
        heights = [box[3] - box[1] for box in shape_boxes_cv]

        median_w = int(np.median(widths))
        median_h = int(np.median(heights))
    else:
        median_w = 50
        median_h = 50

    print("\n>> MAYORITAS SHAPE SIZE")
    print(" median_w =", median_w)
    print(" median_h =", median_h)

    for (x1, y1, x2, y2) in rejected_boxes_cv:
        w = x2 - x1
        h = y2 - y1

        if (0.6 * median_w < w < 1.4 * median_w) and \
           (0.6 * median_h < h < 1.4 * median_h):
            print(f"  ➕ MENERIMA MINORITAS (mirip mayoritas): w={w}, h={h}")
            shape_boxes_cv.append((x1, y1, x2, y2))
        else:
            print(f"  ➖ MENOLAK MINORITAS: w={w}, h={h}")

    shape_boxes_pdf = [
        (x1/zoom, y1/zoom, x2/zoom, y2/zoom)
        for (x1, y1, x2, y2) in shape_boxes_cv
    ]

    text_blocks = page.get_text("blocks")

    valid_shapes = []
    shape_number_map = {}   # 🔥 DITAMBAHKAN

    print("\n============================")
    print("   TEXT INSIDE SHAPE CHECK")
    print("============================")

    for i, box_pdf in enumerate(shape_boxes_pdf):
        sx0, sy0, sx1, sy1 = box_pdf
        shape_rect = fitz.Rect(sx0, sy0, sx1, sy1)

        numbers_inside = []

        print(f"\n[Shape {i}] x0={sx0:.2f}, y0={sy0:.2f}, x1={sx1:.2f}, y1={sy1:.2f}")

        for blk in text_blocks:
            x0, y0, x1, y1, text, *_ = blk
            t = text.strip()

            matches = re.findall(r"\b([0-9]+[A-Za-z]?)\b", t)
            if not matches:
                continue

            rect_t = fitz.Rect(x0, y0, x1, y1)

            for candidate in matches:
                fully_inside = (
                    rect_t.x0 >= shape_rect.x0 and
                    rect_t.y0 >= shape_rect.y0 and
                    rect_t.x1 <= shape_rect.x1 and
                    rect_t.y1 <= shape_rect.y1
                )

                if fully_inside:
                    print(f"   ✔ TEXT '{candidate}' is INSIDE")
                    numbers_inside.append(candidate)

        if len(numbers_inside) == 1:
            print("   --> VALID SHAPE ✔")
            valid_shapes.append(box_pdf)

            # 🔥 simpan mapping box → angka
            shape_number_map[box_pdf] = numbers_inside[0]

        else:
            print(f"   --> INVALID shape (labels={numbers_inside})")

    disp = orig.copy()
    for i, (sx0, sy0, sx1, sy1) in enumerate(valid_shapes):
        x1 = int(sx0 * zoom)
        y1 = int(sy0 * zoom)
        x2 = int(sx1 * zoom)
        y2 = int(sy1 * zoom)
        cv2.rectangle(disp, (x1, y1), (x2, y2), (0,255,0), 2)

    cv2.imwrite(debug_output, disp)
    print("\n============ DONE LOG ============\n")

    # 🔥 RETURN 4 VALUE SESUAI KEBUTUHAN replace_point_numbers
    return valid_shapes, shape_number_map, shape_boxes_cv, shape_boxes_pdf

# ============================================================================================================================================================//
# 2) CHECK SHAPE COLOR (White or Colored)
# ==========================================================
def is_colored_shape(img, box_cv, threshold=200):
    """
    Menentukan apakah shape berwarna atau putih.
    output=True → shape berwarna
    """
    x1, y1, x2, y2 = box_cv
    crop = img[y1:y2, x1:x2]

    if crop.size == 0:
        return False

    mean_color = crop.mean(axis=(0, 1))  # B,G,R

    # putih → sangat cerah
    is_white = all(c > threshold for c in mean_color)

    return not is_white  # True jika shape berwarna



# ==========================================================
# 3) REPLACE NUMBER INSIDE SHAPES
# ==========================================================
def replace_point_numbers(input_pdf, output_pdf, df_match, debug=True):
    """
    Mengganti nomor Q-Time → IS hanya pada shape OpenCV yang tervalidasi.
    """

    # ---------------------------
    # Render halaman jadi gambar
    # ---------------------------
    doc = fitz.open(input_pdf)
    page = doc[0]

    zoom = 3
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_path = "page_render.png"
    pix.save(img_path)

    img_cv = cv2.imread(img_path)

    # ---------------------------
    # Deteksi shape kandidat
    # ---------------------------
    valid_shapes, shape_number_map, shape_boxes_cv, shape_boxes_pdf = detect_point_shapes_with_numbers(img_path, page, zoom=zoom)
    # mapping OpenCV → PDF
    shape_boxes_pdf = [
        (x1/zoom, y1/zoom, x2/zoom, y2/zoom)
        for (x1, y1, x2, y2) in shape_boxes_cv
    ]

    # ---------------------------
    # Ambil blok teks dari PDF
    # ---------------------------
    blocks = page.get_text("blocks")

    # Kolom match
    q_col = next((c for c in df_match.columns if "Q-Time" in c and "No" in c), None)
    is_col = next((c for c in df_match.columns if "IS" in c and "No" in c), None)

    # ---------------------------
    # Shape → angka di dalamnya
    # ---------------------------
    shape_numbers = {box: [] for box in shape_boxes_pdf}

    for b in blocks:
        x0, y0, x1, y1, text, *_ = b
        t = text.strip()

        if not t.isdigit():
            continue

        rect_t = fitz.Rect(x0, y0, x1, y1)

        # cek apakah teks ini masuk shape
        for box_pdf in shape_boxes_pdf:
            sx0, sy0, sx1, sy1 = box_pdf
            shape_rect = fitz.Rect(sx0, sy0, sx1, sy1)

            if (rect_t.x0 >= shape_rect.x0 and
                rect_t.y0 >= shape_rect.y0 and
                rect_t.x1 <= shape_rect.x1 and
                rect_t.y1 <= shape_rect.y1):

                shape_numbers[box_pdf].append(t)

    # ---------------------------
    # Filter shape valid: 1 angka saja
    # ---------------------------
    valid_shapes = {
        box for box in shape_boxes_pdf
        if len(shape_numbers[box]) == 1
    }

    # ---------------------------
    # Replace tiap shape valid
    # ---------------------------
    for box_pdf, box_cv in zip(shape_boxes_pdf, shape_boxes_cv):
        if box_pdf not in valid_shapes:
            continue

        # skip shape berwarna
        if is_colored_shape(img_cv, box_cv):
            if debug:
                print(f"SKIP shape colored: {box_pdf}")
            continue

        old_no = shape_numbers[box_pdf][0]     # nomor yang terdeteksi di shape

        # cari match dari hasil RapidFuzz
        matched = df_match[df_match["Old No (Q-Time)"].astype(str) == old_no]

        if matched.empty:
            print(f"TIDAK ADA MATCH UNTUK: {old_no}")
            continue

        new_no = str(matched.iloc[0]["Matched No (IS)"])
        print(f"REPLACE {old_no} → {new_no}")

        # cari lokasi teksnya dalam PDF
        rect_text = None
        for b in blocks:
            x0, y0, x1, y1, text, *_ = b
            if text.strip() == old_no:
                r = fitz.Rect(x0, y0, x1, y1)
                if r.x0 >= box_pdf[0] and r.y0 >= box_pdf[1] and r.x1 <= box_pdf[2] and r.y1 <= box_pdf[3]:
                    rect_text = r
                    break

        if rect_text is None:
            continue

        # HAPUS teks lama
        page.draw_rect(rect_text, fill=(1, 1, 1), color=None)

        # TULIS teks baru
        page.insert_textbox(
            fitz.Rect(*box_pdf),
            new_no,
            fontsize=11,
            fontname="helv",
            align=1,
            color=(0, 0, 0),
            overlay=True
        )

    doc.save(output_pdf)
    doc.close()

    if debug:
        print("SUKSES replace point numbers.")


