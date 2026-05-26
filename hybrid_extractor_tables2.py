import pdfplumber
import pytesseract
import csv
from pdf2image import convert_from_path
from pytesseract import Output
import os
import re

# ==========================================
# CONFIGURACIÓN PARA WINDOWS
pytesseract.pytesseract.tesseract_cmd = r'C:\Programs\Tesseract-OCR\tesseract.exe'
ruta_poppler = r'C:\Programs\poppler\Library\bin'
# ==========================================

ruta_pdf = 'quijote90.pdf'
# ruta_pdf = 'quijote180.pdf'
archivo_salida = 'resultado_hibrido_estructurado.txt'
archivo_csv = 'resultado_hibrido_logs.csv'

MIN_CARACTERES = 30
IDIOMA_OCR = 'spa'


def clean_text(texto):
    if not texto:
        return ""
    # Normaliza espacios respetando saltos de linea.
    lineas_limpias = []
    for linea in texto.splitlines():
        linea_limpia = " ".join(linea.strip().split())
        if linea_limpia:
            lineas_limpias.append(linea_limpia)
    return "\n".join(lineas_limpias)


def fix_hyphenated_line_breaks(texto):
    """Corrige palabras cortadas por guión al final de línea de forma exhaustiva."""
    if not texto:
        return texto
    
    lineas = texto.split('\n')
    lineas_corregidas = []
    
    i = 0
    while i < len(lineas):
        linea = lineas[i].rstrip()
        
        # Mientras la línea termine con guión y haya siguiente línea, concatenar
        while linea.endswith('-') and i + 1 < len(lineas):
            siguiente = lineas[i + 1].lstrip()
            # Quita el guión del final y concatena con la siguiente línea
            # Sin espacio porque la palabra continúa
            linea = linea[:-1] + siguiente
            i += 1
        
        lineas_corregidas.append(linea)
        i += 1
    
    return '\n'.join(lineas_corregidas)


def extract_paragraph_for_check(texto, max_lines=4):
    """Extrae un párrafo corto desde el texto OCR para validaciones rápidas."""
    if not texto:
        return ""

    lineas = [linea.strip() for linea in texto.split('\n') if linea.strip()]
    if not lineas:
        return ""

    return " ".join(lineas[:max_lines])


def check_rotation_d(texto):
    """Función simulada: siempre devuelve True."""
    return True


def extract_ocr_with_orientation(ruta_pdf_local, numero_pagina, poppler_path):
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

    texto_ocr = clean_text(
        pytesseract.image_to_string(
            imagen_pagina,
            lang=IDIOMA_OCR,
            config='--oem 3 --psm 6'
        )
    )
    # Todo Implementar llamada
    parrafo_ocr = extract_paragraph_for_check(texto_ocr)
    if parrafo_ocr:
        orientacion['resultado_check_rotation_d'] = check_rotation_d(parrafo_ocr)
    if parrafo_ocr is False:
        # Rotar documento 90ªs adicionales y reintentar OCR
        for giro in [90, 180, 270]:
            imagen_pagina = imagen_pagina.rotate(90, expand=True)
            texto_ocr = clean_text(
                pytesseract.image_to_string(
                    imagen_pagina,
                    lang=IDIOMA_OCR,
                    config='--oem 3 --psm 6'
                )
            )
            parrafo_ocr = extract_paragraph_for_check(texto_ocr)
            if parrafo_ocr and check_rotation_d(parrafo_ocr):
                orientacion['angulo_detectado'] = (orientacion['angulo_detectado'] + giro) % 360
                orientacion['corregida'] = True
                break

    return texto_ocr, orientacion, imagen_pagina


def extract_ocr_table_from_crop(imagen_recorte):
    """Reconstruye una tabla desde un recorte usando OCR por palabras y geometria."""
    datos = pytesseract.image_to_data(
        imagen_recorte,
        lang=IDIOMA_OCR,
        config='--oem 3 --psm 6',
        output_type=Output.DICT
    )

    palabras = []
    total_items = len(datos.get('text', []))
    for i in range(total_items):
        texto = (datos['text'][i] or '').strip()
        conf_raw = str(datos['conf'][i]).strip()
        try:
            conf = float(conf_raw)
        except ValueError:
            conf = -1.0

        if not texto or conf < 35:
            continue

        left = int(datos['left'][i])
        top = int(datos['top'][i])
        width = int(datos['width'][i])
        height = int(datos['height'][i])
        palabras.append(
            {
                'text': texto,
                'left': left,
                'top': top,
                'right': left + width,
                'h': height,
            }
        )

    if not palabras:
        return []

    palabras.sort(key=lambda p: (p['top'], p['left']))
    alto_promedio = sum(p['h'] for p in palabras) / len(palabras)
    umbral_fila = max(8, int(alto_promedio * 0.7))

    filas = []
    for palabra in palabras:
        centro_y = palabra['top'] + (palabra['h'] // 2)
        fila_objetivo = None

        for fila in filas:
            if abs(centro_y - fila['y']) <= umbral_fila:
                fila_objetivo = fila
                break

        if fila_objetivo is None:
            filas.append({'y': centro_y, 'words': [palabra]})
        else:
            fila_objetivo['words'].append(palabra)

    filas.sort(key=lambda f: f['y'])

    tabla = []
    max_columnas = 0
    for fila in filas:
        words = sorted(fila['words'], key=lambda p: p['left'])
        ancho_promedio = max(8, int(sum(w['right'] - w['left'] for w in words) / len(words)))
        salto_columna = max(20, ancho_promedio * 2)

        celdas = []
        actual = words[0]['text']
        ultimo_derecha = words[0]['right']

        for word in words[1:]:
            if word['left'] - ultimo_derecha > salto_columna:
                celdas.append(actual.strip())
                actual = word['text']
            else:
                actual = f"{actual} {word['text']}"
            ultimo_derecha = max(ultimo_derecha, word['right'])

        celdas.append(actual.strip())
        if any(celda for celda in celdas):
            tabla.append(celdas)
            max_columnas = max(max_columnas, len(celdas))

    if not tabla:
        return []

    return [fila + [''] * (max_columnas - len(fila)) for fila in tabla]


def extract_advanced_ocr_tables(pagina_pdf, imagen_pagina):
    """Extrae tablas con OCR: primero por regiones de tabla, luego fallback de pagina completa."""
    tablas_ocr = []

    table_settings = {
        'vertical_strategy': 'lines',
        'horizontal_strategy': 'lines',
        'intersection_tolerance': 8,
    }
    tablas_detectadas = pagina_pdf.find_tables(table_settings=table_settings)

    escala_x = imagen_pagina.width / float(pagina_pdf.width)
    escala_y = imagen_pagina.height / float(pagina_pdf.height)

    for tabla in tablas_detectadas:
        x0, top, x1, bottom = tabla.bbox
        recorte = (
            int(max(0, x0 * escala_x)),
            int(max(0, top * escala_y)),
            int(min(imagen_pagina.width, x1 * escala_x)),
            int(min(imagen_pagina.height, bottom * escala_y)),
        )

        if recorte[2] - recorte[0] < 20 or recorte[3] - recorte[1] < 20:
            continue

        imagen_recorte = imagen_pagina.crop(recorte)
        tabla_ocr = extract_ocr_table_from_crop(imagen_recorte)
        if tabla_ocr:
            tablas_ocr.append(tabla_ocr)

    if tablas_ocr:
        return tablas_ocr

    # Fallback: OCR de pagina completa preservando espacios para separar columnas.
    texto_tabular = pytesseract.image_to_string(
        imagen_pagina,
        lang=IDIOMA_OCR,
        config='--oem 3 --psm 4 -c preserve_interword_spaces=1'
    )

    filas = []
    for linea in texto_tabular.splitlines():
        linea = linea.rstrip()
        if not linea:
            continue
        celdas = [c.strip() for c in re.split(r'\s{2,}', linea) if c.strip()]
        if len(celdas) >= 2:
            filas.append(celdas)

    if not filas:
        return []

    max_columnas = max(len(fila) for fila in filas)
    tabla_fallback = [fila + [''] * (max_columnas - len(fila)) for fila in filas]
    return [tabla_fallback]


def table_to_text(tabla):
    """Convierte una tabla (lista de listas) a formato de texto legible."""
    if not tabla:
        return ""
    
    # Calcular ancho máximo por columna
    num_cols = len(tabla[0]) if tabla else 0
    anchos = [0] * num_cols
    
    for fila in tabla:
        for i, celda in enumerate(fila):
            texto_celda = str(celda) if celda is not None else ""
            anchos[i] = max(anchos[i], len(texto_celda))
    
    # Construir tabla formateada
    lineas = []
    for fila in tabla:
        celdas_formateadas = []
        for i, celda in enumerate(fila):
            texto_celda = str(celda) if celda is not None else ""
            celdas_formateadas.append(texto_celda.ljust(anchos[i]))
        lineas.append(" | ".join(celdas_formateadas))
    
    return "\n".join(lineas)


def build_page_block(info_pagina):
    lineas = [
        f"--- PAGINA {info_pagina['numero']} ---",
        "",
        "[TEXTO]",
        info_pagina['texto_priorizado'] or "(VACIO)",
        ""
    ]

    # Agregar tablas si existen
    if info_pagina['tablas']:
        lineas.append("[TABLAS]")
        for idx, tabla in enumerate(info_pagina['tablas'], 1):
            lineas.append(f"\nTabla {idx}:")
            lineas.append(table_to_text(tabla))
        lineas.append("")

    return "\n".join(lineas)


def generate_csv_log(ruta_pdf, archivo_csv, paginas_procesadas):
    """Genera el CSV con metadatos por página del proceso de extracción."""
    nombre_pdf = os.path.basename(ruta_pdf)
    with open(archivo_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)

        writer.writerow([
            'Fichero',
            'Pagina',
            'Fuente_Prioritaria',
            'Orientacion_Detectada',
            'Angulo_Detectado',
            'Correccion_Aplicada',
            'Longitud_OCR',
            'Longitud_Nativo',
            'Num_Tablas',
            'Origen_Tablas'
        ])

        for pagina_info in paginas_procesadas:
            writer.writerow([
                nombre_pdf,
                pagina_info['numero'],
                pagina_info['fuente_prioritaria'],
                'SI' if pagina_info['orientacion']['detectada'] else 'NO',
                pagina_info['orientacion']['angulo_detectado'],
                'SI' if pagina_info['orientacion']['corregida'] else 'NO',
                pagina_info['longitud_ocr'],
                pagina_info['longitud_nativo'],
                pagina_info['num_tablas'],
                pagina_info['origen_tablas']
            ])


def run_hybrid_extraction_pipeline():
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
            texto_ocr, orientacion, imagen_pagina = extract_ocr_with_orientation(
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
            texto_nativo = clean_text(pagina.extract_text())

            # 3) Extracción de tablas con OCR avanzado.
            tablas_ocr = extract_advanced_ocr_tables(pagina, imagen_pagina)
            tablas_pdf = pagina.extract_tables() or []

            if tablas_ocr:
                tablas = tablas_ocr
                origen_tablas = 'OCR_AVANZADO'
            elif tablas_pdf:
                tablas = tablas_pdf
                origen_tablas = 'PDFPLUMBER'
            else:
                tablas = []
                origen_tablas = 'SIN_TABLAS'

            if tablas:
                print(f"  -> {len(tablas)} tabla(s) detectada(s) [{origen_tablas}].")

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
                'longitud_nativo': len(texto_nativo),
                'tablas': tablas or [],
                'num_tablas': len(tablas) if tablas else 0,
                'origen_tablas': origen_tablas,
            }
            paginas_procesadas.append(info_pagina)
            texto_completo.append(build_page_block(info_pagina))

    resumen = [
        "=" * 50,
        "EXTRACCION HIBRIDA ESTRUCTURADA",
        "=" * 50,
        f"PDF: {ruta_pdf}",
        f"TOTAL_PAGINAS: {len(paginas_procesadas)}",
        f"PAGINAS_CON_OCR_PRIORITARIO: {sum(1 for p in paginas_procesadas if p['fuente_prioritaria'] == 'OCR')}",
        f"PAGINAS_CON_FALLBACK_NATIVO: {sum(1 for p in paginas_procesadas if p['fuente_prioritaria'] == 'NATIVO_FALLBACK')}",
        f"PAGINAS_CORREGIDAS_ROTACION: {sum(1 for p in paginas_procesadas if p['orientacion']['corregida'])}",
        f"TABLAS_TOTALES_DETECTADAS: {sum(p['num_tablas'] for p in paginas_procesadas)}",
        f"PAGINAS_CON_TABLAS: {sum(1 for p in paginas_procesadas if p['num_tablas'] > 0)}",
        "=" * 50,
        ""
    ]

    salida_consola = "\n".join(resumen + texto_completo)
    salida_archivo = "\n".join(texto_completo)

    print("\n" + "=" * 40)
    print("EXTRACCIÓN COMPLETADA. MOSTRANDO RESULTADOS:")
    print("=" * 40 + "\n")
    print(salida_consola)

    # Guardar archivo de texto con extracción completa (sin resumen)
    with open(archivo_salida, 'w', encoding='utf-8') as f:
        f.write(salida_archivo)

    print(f"\nResultado estructurado guardado en: {archivo_salida}")
    return paginas_procesadas


paginas_procesadas = run_hybrid_extraction_pipeline()

# Generar CSV con logs de metadatos
generate_csv_log(ruta_pdf, archivo_csv, paginas_procesadas)

print(f"Logs en CSV guardados en: {archivo_csv}")