import pytesseract
from pdf2image import convert_from_path
from pytesseract import Output  # IMPORTANTE: Añadimos esto para manejar los datos de orientación

# ==========================================
# CONFIGURACIÓN PARA WINDOWS
# 1. Ruta al ejecutable de Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Programs\Tesseract-OCR\tesseract.exe'
# 2. Ruta a la carpeta "bin" de Poppler
ruta_poppler = r'C:\Programs\poppler\Library\bin'
# ==========================================

ruta_pdf = 'Baby Bestiary.pdf'

print("Convirtiendo PDF a imágenes... (esto puede tardar dependiendo del tamaño)")

paginas = convert_from_path(ruta_pdf, poppler_path=ruta_poppler)

texto_completo = ""

# Recorremos cada página (que ahora es una imagen)
for i, pagina_imagen in enumerate(paginas):
    print(f"Procesando página {i + 1}...")

    # ---------------------------------------------------------
    # NUEVO: Detección y corrección de orientación (OSD)
    # ---------------------------------------------------------
    try:
        # Analizamos la página para detectar la orientación
        info_osd = pytesseract.image_to_osd(pagina_imagen, output_type=Output.DICT)
        angulo_de_rotacion = info_osd['rotate']

        # Si Tesseract nos dice que hay que rotarla...
        if angulo_de_rotacion != 0:
            print(f"  -> ¡Página girada detectada! Corrigiendo rotación de {angulo_de_rotacion} grados...")
            # Rotamos la imagen. Usamos el ángulo en negativo porque Pillow rota en sentido antihorario.
            # El parámetro expand=True evita que las esquinas se recorten al rotar imágenes rectangulares.
            pagina_imagen = pagina_imagen.rotate(-angulo_de_rotacion, expand=True)

    except Exception as e:
        # Si la página tiene muy poco texto o solo una imagen gigante, OSD puede fallar.
        # En ese caso, la dejamos como está y pasamos al siguiente paso.
        print("  -> Aviso: No se pudo determinar la orientación automáticamente.")
    # ---------------------------------------------------------

    # Extraemos el texto de la imagen (que ahora ya está enderezada si hacía falta)
    texto_pagina = pytesseract.image_to_string(pagina_imagen, lang='spa')

    # Lo añadimos a nuestra variable final
    texto_completo += f"\n\n--- INICIO PÁGINA {i + 1} ---\n\n"
    texto_completo += texto_pagina

print("\nExtracción completada. Aquí está el texto:")
print("=" * 40)
print(texto_completo)

# Opcional: Guardar el resultado en un archivo de texto
with open('texto_extraido.txt', 'w', encoding='utf-8') as f:
     f.write(texto_completo)