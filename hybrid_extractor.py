import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from pytesseract import Output

# ==========================================
# CONFIGURACIÓN PARA WINDOWS
pytesseract.pytesseract.tesseract_cmd = r'C:\Programs\Tesseract-OCR\tesseract.exe'
ruta_poppler = r'C:\Programs\poppler\Library\bin'
# ==========================================

ruta_pdf = 'documento_mixto.pdf'
texto_completo = ""

print("Iniciando análisis híbrido del documento...")

# Abrimos el PDF con pdfplumber para intentar leer el texto nativo
with pdfplumber.open(ruta_pdf) as pdf:
    total_paginas = len(pdf.pages)
    print(f"El documento tiene {total_paginas} páginas.\n")

    for i, pagina in enumerate(pdf.pages):
        print(f"Procesando página {i + 1}...")

        # 1. Intentamos extraer el texto de forma nativa
        texto_nativo = pagina.extract_text()

        # Usamos un pequeño "truco": si hay menos de 50 letras, asumimos que es un escaneo.
        # (A veces los escaneos tienen números de página ocultos que confunden al sistema)
        if texto_nativo and len(texto_nativo.strip()) > 50:
            print("  -> Texto nativo detectado. Extracción ultra-rápida.")
            texto_completo += f"\n\n--- INICIO PÁGINA {i + 1} (NATIVO) ---\n\n"
            texto_completo += texto_nativo

        else:
            # 2. Si no hay texto, es una imagen o escaneo. Activamos Tesseract (OCR).
            print("  -> Imagen/Escaneo detectado. Activando OCR (Tesseract)...")

            # Convertimos SOLO esta página a imagen para no colapsar la memoria
            # Nota: convert_from_path empieza a contar en 1, no en 0
            imagenes = convert_from_path(
                ruta_pdf,
                first_page=i + 1,
                last_page=i + 1,
                poppler_path=ruta_poppler
            )
            imagen_pagina = imagenes[0]

            # --- Detección y corrección de rotación (OSD) ---
            try:
                info_osd = pytesseract.image_to_osd(imagen_pagina, output_type=Output.DICT)
                angulo = info_osd['rotate']

                if angulo != 0:
                    print(f"     ¡Página girada! Enderezando {angulo} grados...")
                    imagen_pagina = imagen_pagina.rotate(-angulo, expand=True)
            except Exception:
                pass  # Ignoramos si no puede detectar la orientación
            # ------------------------------------------------

            # Extraemos con Tesseract
            texto_ocr = pytesseract.image_to_string(imagen_pagina, lang='spa')

            texto_completo += f"\n\n--- INICIO PÁGINA {i + 1} (OCR) ---\n\n"
            texto_completo += texto_ocr

print("\n" + "=" * 40)
print("EXTRACCIÓN COMPLETADA. MOSTRANDO RESULTADOS:")
print("=" * 40 + "\n")
print(texto_completo)

# Opcional: Guardar en archivo
# with open('resultado_hibrido.txt', 'w', encoding='utf-8') as f:
#     f.write(texto_completo)