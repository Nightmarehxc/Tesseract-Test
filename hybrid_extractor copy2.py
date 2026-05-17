import pdfplumber
import pytesseract
import csv
from pdf2image import convert_from_path
from pytesseract import Output
import os

# ==========================================
# CONFIGURACIÓN PARA WINDOWS
pytesseract.pytesseract.tesseract_cmd = r'C:\Programs\Tesseract-OCR\tesseract.exe'
ruta_poppler = r'C:\Programs\poppler\Library\bin'
# ==========================================

ruta_pdf = '180.pdf'
archivo_salida = 'resultado_hibrido_estructurado.txt'
archivo_csv = 'resultado_hibrido_logs.csv'

MIN_CARACTERES = 30
IDIOMA_OCR = 'spa'


def limpiar_texto(texto):
    if not texto:
        return ""
    return texto.strip()


def extraer_ocr_con_orientacion(ruta_pdf_local, numero_pagina, poppler_path):
    """Extrae OCR de una página, detecta orientación OSD y corrige giro si aplica."""
    imagenes = convert_from_path(
        ruta_pdf_local,
        first_page=numero_pagina,
        last_page=numero_pagina,
        poppler_path=poppler_path
    )
    imagen_pagina = imagenes[0]

    orientacion = {
        'detectada': False,
        'angulo_detectado': 0,
        'corregida': False,
        'error': None
    }

    try:
        info_osd = pytesseract.image_to_osd(imagen_pagina, output_type=Output.DICT)
        angulo = int(info_osd.get('rotate', 0))
        orientacion['detectada'] = True
        orientacion['angulo_detectado'] = angulo

        if angulo != 0:
            imagen_pagina = imagen_pagina.rotate(-angulo, expand=True)
            orientacion['corregida'] = True
    except Exception as e:
        orientacion['error'] = str(e)

    texto_ocr = limpiar_texto(
        pytesseract.image_to_string(imagen_pagina, lang=IDIOMA_OCR)
    )
    return texto_ocr, orientacion


def construir_bloque_pagina(info_pagina):
    orient = info_pagina['orientacion']
    lineas = [
        f"--- PAGINA {info_pagina['numero']} ---",
        f"FUENTE_PRIORITARIA: {info_pagina['fuente_prioritaria']}",
        f"ORIENTACION_DETECTADA: {'SI' if orient['detectada'] else 'NO'}",
        f"ANGULO_DETECTADO: {orient['angulo_detectado']}",
        f"CORRECCION_APLICADA: {'SI' if orient['corregida'] else 'NO'}",
        f"LONGITUD_OCR: {info_pagina['longitud_ocr']}",
        f"LONGITUD_NATIVO: {info_pagina['longitud_nativo']}",
        "",
        "[TEXTO PRIORIZADO]",
        info_pagina['texto_priorizado'] or "(VACIO)",
        "",
        "[TEXTO NATIVO DE RESPALDO]",
        info_pagina['texto_nativo'] or "(VACIO)",
        ""
    ]

    if orient['error']:
        lineas.insert(6, f"NOTA_ORIENTACION: {orient['error']}")

    return "\n".join(lineas)


paginas_procesadas = []
texto_completo = []

print("Iniciando análisis híbrido del documento...")

# Abrimos el PDF para obtener texto nativo por página.
with pdfplumber.open(ruta_pdf) as pdf:
    total_paginas = len(pdf.pages)
    print(f"El documento tiene {total_paginas} páginas.\n")

    for i, pagina in enumerate(pdf.pages):
        numero_pagina = i + 1
        print(f"Procesando página {numero_pagina}...")

        # 1) OCR primero: prioridad a imagen/escaneo.
        texto_ocr, orientacion = extraer_ocr_con_orientacion(
            ruta_pdf,
            numero_pagina,
            ruta_poppler
        )

        if orientacion['corregida']:
            print(
                f"  -> OCR principal. Página enderezada "
                f"{orientacion['angulo_detectado']} grados."
            )
        else:
            print("  -> OCR principal completado.")

        # 2) Texto nativo como respaldo para comparación/complemento.
        texto_nativo = limpiar_texto(pagina.extract_text())

        # Priorizamos OCR. Si viene demasiado vacío, usamos texto nativo.
        if len(texto_ocr) >= MIN_CARACTERES:
            texto_priorizado = texto_ocr
            fuente_prioritaria = 'OCR'
        else:
            texto_priorizado = texto_nativo
            fuente_prioritaria = 'NATIVO_FALLBACK'
            print("  -> OCR corto/vacío. Se usa nativo como fallback.")

        info_pagina = {
            'numero': numero_pagina,
            'fuente_prioritaria': fuente_prioritaria,
            'orientacion': orientacion,
            'texto_priorizado': texto_priorizado,
            'texto_nativo': texto_nativo,
            'longitud_ocr': len(texto_ocr),
            'longitud_nativo': len(texto_nativo)
        }
        paginas_procesadas.append(info_pagina)
        texto_completo.append(construir_bloque_pagina(info_pagina))

resumen = [
    "=" * 50,
    "EXTRACCION HIBRIDA ESTRUCTURADA",
    "=" * 50,
    f"PDF: {ruta_pdf}",
    f"TOTAL_PAGINAS: {len(paginas_procesadas)}",
    f"PAGINAS_CON_OCR_PRIORITARIO: {sum(1 for p in paginas_procesadas if p['fuente_prioritaria'] == 'OCR')}",
    f"PAGINAS_CON_FALLBACK_NATIVO: {sum(1 for p in paginas_procesadas if p['fuente_prioritaria'] == 'NATIVO_FALLBACK')}",
    f"PAGINAS_CORREGIDAS_ROTACION: {sum(1 for p in paginas_procesadas if p['orientacion']['corregida'])}",
    "=" * 50,
    ""
]

salida_final = "\n".join(resumen + texto_completo)

print("\n" + "=" * 40)
print("EXTRACCIÓN COMPLETADA. MOSTRANDO RESULTADOS:")
print("=" * 40 + "\n")
print(salida_final)

# Guardar archivo de texto con extracción completa
with open(archivo_salida, 'w', encoding='utf-8') as f:
    f.write(salida_final)

print(f"\nResultado estructurado guardado en: {archivo_salida}")

# Generar CSV con logs de metadatos
nombre_pdf = os.path.basename(ruta_pdf)
with open(archivo_csv, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    
    # Encabezados
    writer.writerow([
        'Fichero',
        'Pagina',
        'Fuente_Prioritaria',
        'Orientacion_Detectada',
        'Angulo_Detectado',
        'Correccion_Aplicada',
        'Longitud_OCR',
        'Longitud_Nativo'
    ])
    
    # Datos de cada página
    for pagina_info in paginas_procesadas:
        writer.writerow([
            nombre_pdf,
            pagina_info['numero'],
            pagina_info['fuente_prioritaria'],
            'SI' if pagina_info['orientacion']['detectada'] else 'NO',
            pagina_info['orientacion']['angulo_detectado'],
            'SI' if pagina_info['orientacion']['corregida'] else 'NO',
            pagina_info['longitud_ocr'],
            pagina_info['longitud_nativo']
        ])

print(f"Logs en CSV guardados en: {archivo_csv}")