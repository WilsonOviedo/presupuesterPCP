"""
Módulo para procesar presupuestos desde texto OCR (procesado con Tesseract.js en el navegador)
"""
import re
from datetime import datetime
import json

def procesar_texto_presupuesto(texto_completo, resultados_ocr=None):
    """
    Procesa texto OCR extraído de una imagen de presupuesto (procesado con Tesseract.js)
    
    Args:
        texto_completo: Texto extraído por OCR
        resultados_ocr: Lista opcional de resultados estructurados con coordenadas
    
    Retorna:
        dict con:
            - proveedor: str
            - fecha: datetime
            - items: list de dicts con {codigo, cantidad, unidad, descripcion, marca, precio_unitario, total}
            - total: float
    """
    if not texto_completo:
        raise ValueError("No se proporcionó texto OCR")
    
    # Extraer datos básicos del texto
    try:
        datos = extraer_datos_presupuesto(texto_completo, resultados_ocr or [])
    except Exception as e:
        import traceback
        raise Exception(f"Error al extraer datos: {e}\n{traceback.format_exc()}")
    
    # Si tenemos resultados estructurados, mejorar la extracción
    if resultados_ocr and isinstance(resultados_ocr, list) and len(resultados_ocr) > 0:
        try:
            datos = mejorar_extraccion_con_ocr_resultados(resultados_ocr, datos)
        except Exception as e:
            print(f"Error al mejorar extracción con coordenadas: {e}")
            # Continuar con datos básicos
    
    return datos

def extraer_datos_presupuesto(texto, resultados_ocr):
    """
    Extrae datos estructurados del texto OCR
    """
    datos = {
        'proveedor': None,
        'fecha': None,
        'numero_presupuesto': None,
        'items': [],
        'total': None
    }
    
    # Validar que texto sea una cadena
    if not isinstance(texto, str):
        if texto is None:
            texto = ""
        elif callable(texto):
            # Si es una función, no podemos procesarla
            print("Error: texto es una función, no una cadena")
            return datos
        else:
            texto = str(texto)
    
    if not texto:
        return datos
    
    try:
        texto_upper = texto.upper()
        lineas = texto.split('\n')
    except AttributeError as e:
        print(f"Error al procesar texto: {e}, tipo: {type(texto)}")
        return datos
    
    # Extraer proveedor (buscar nombre de empresa)
    proveedores_comunes = ['ENERLUZ', 'ENERGIA', 'ELECTRICA', 'ELECTRICIDAD']
    for prov in proveedores_comunes:
        if prov in texto_upper:
            # Buscar el nombre completo alrededor
            idx = texto_upper.find(prov)
            if idx >= 0:
                inicio = max(0, idx - 20)
                fin = min(len(texto) if isinstance(texto, str) else 0, idx + len(prov) + 20)
                datos['proveedor'] = texto[inicio:fin].strip()
                break
    
    if not datos['proveedor']:
        # Si no encontramos, usar la primera línea que parezca un nombre
        for linea in lineas[:5]:
            if len(linea) > 3 and len(linea) < 50 and not any(c.isdigit() for c in linea[:3]):
                datos['proveedor'] = linea.strip()
                break
    
    # Extraer fecha (buscar patrones de fecha)
    fecha_patterns = [
        r'(\d{1,2})/(\d{1,2})/(\d{4})',
        r'(\d{1,2})-(\d{1,2})-(\d{4})',
        r'(\d{4})-(\d{1,2})-(\d{1,2})',
    ]
    
    for pattern in fecha_patterns:
        match = re.search(pattern, texto)
        if match:
            try:
                if '/' in match.group(0):
                    dia, mes, año = match.groups()
                    datos['fecha'] = datetime(int(año), int(mes), int(dia))
                elif '-' in match.group(0) and len(match.group(1)) == 4:
                    año, mes, dia = match.groups()
                    datos['fecha'] = datetime(int(año), int(mes), int(dia))
                else:
                    dia, mes, año = match.groups()
                    datos['fecha'] = datetime(int(año), int(mes), int(dia))
                break
            except:
                continue
    
    if not datos['fecha']:
        datos['fecha'] = datetime.now()
    
    # Extraer número de presupuesto
    numero_match = re.search(r'(?:ORÇAMENTO|PRESUPUESTO|N°|Nº|NUMERO)[\s:]*(\d+[/-]\d+)', texto_upper)
    if numero_match:
        datos['numero_presupuesto'] = numero_match.group(1)
    
    # Limpiar y normalizar líneas
    lineas_limpias = []
    for linea in lineas:
        linea = linea.strip()
        # Eliminar líneas muy cortas o que parezcan ruido
        if len(linea) < 3:
            continue
        # Eliminar líneas que son solo símbolos o caracteres especiales
        if not re.search(r'[A-Za-z0-9]', linea):
            continue
        # Unir líneas que parecen estar divididas incorrectamente
        lineas_limpias.append(linea)
    
    # Extraer items de la tabla
    # Buscar la sección de la tabla (después de "Descrição do Produto" o similar)
    tabla_inicio = -1
    for i, linea in enumerate(lineas_limpias):
        linea_upper = linea.upper()
        if any(palabra in linea_upper for palabra in ['DESCRIÇÃO', 'DESCRIPCION', 'PRODUTO', 'PRODUCTO', 'CODIGO', 'CÓDIGO', 'ITEM', 'QTDE', 'CANTIDAD']):
            tabla_inicio = i
            break
    
    if tabla_inicio >= 0:
        # Procesar líneas de la tabla
        items_encontrados = []
        for i in range(tabla_inicio + 1, len(lineas_limpias)):
            linea = lineas_limpias[i]
            if not linea or len(linea) < 10:
                continue
            
            # Intentar extraer un item
            item = extraer_item_linea(linea, resultados_ocr)
            if item:
                items_encontrados.append(item)
    else:
        # Si no encontramos encabezado, procesar todas las líneas que parezcan items
        items_encontrados = []
        for linea in lineas_limpias:
            if len(linea) < 10:
                continue
            # Buscar líneas que contengan números (probablemente precios o cantidades)
            if re.search(r'\d+[.,]\d+', linea) or re.search(r'\d+\s+[A-Z]', linea):
                item = extraer_item_linea(linea, resultados_ocr)
                if item:
                    items_encontrados.append(item)
    
    datos['items'] = items_encontrados
    
    # Extraer total
    total_patterns = [
        r'TOTAL[\.\s:]*G?\$?\s*:?\s*([\d.,]+)',
        r'TOTAL[\.\s:]*([\d.,]+)',
    ]
    
    for pattern in total_patterns:
        match = re.search(pattern, texto_upper)
        if match:
            try:
                total_str = match.group(1).replace('.', '').replace(',', '.')
                datos['total'] = float(total_str)
                break
            except:
                continue
    
    return datos

def extraer_item_linea(linea, resultados_ocr=None):
    """
    Intenta extraer los datos de un item desde una línea de texto
    """
    # Limpiar línea
    if not isinstance(linea, str):
        linea = str(linea)
    linea = linea.strip()
    if len(linea) < 10:
        return None
    
    # Buscar números que podrían ser código, cantidad, precio
    numeros = re.findall(r'[\d.,]+', linea)
    
    if len(numeros) < 2:
        return None
    
    item = {
        'codigo': None,
        'cantidad': None,
        'unidad': None,
        'descripcion': None,
        'marca': None,
        'precio_unitario': None,
        'total': None
    }
    
    # Intentar identificar cantidad (generalmente un número entero pequeño al inicio)
    for num in numeros[:3]:
        try:
            num_clean = num.replace('.', '').replace(',', '')
            if num_clean.isdigit():
                cantidad = int(num_clean)
                if 1 <= cantidad <= 10000:
                    item['cantidad'] = cantidad
                    break
        except:
            continue
    
    # Buscar precios (números más grandes, generalmente con decimales)
    precios_encontrados = []
    for num in numeros:
        try:
            num_clean = num.replace('.', '').replace(',', '.')
            precio = float(num_clean)
            if precio > 0.1 and precio < 1000000:
                precios_encontrados.append(precio)
        except:
            continue
    
    if len(precios_encontrados) >= 2:
        # El último suele ser el total, el penúltimo el precio unitario
        item['total'] = precios_encontrados[-1]
        item['precio_unitario'] = precios_encontrados[-2]
    elif len(precios_encontrados) == 1:
        item['precio_unitario'] = precios_encontrados[0]
    
    # Extraer descripción (texto que no sean números)
    palabras = re.findall(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]+', linea)
    if palabras:
        # Filtrar palabras comunes de encabezados
        palabras_filtradas = [p for p in palabras if p.upper() not in ['ITE', 'CODIGO', 'QTDE', 'UND', 'DESCRIÇÃO', 'PRODUTO', 'MARCA', 'LOCAL', 'PRECO', 'UNIT', 'TOT', 'ITEM']]
        if palabras_filtradas:
            item['descripcion'] = ' '.join(palabras_filtradas[:10])  # Limitar a 10 palabras
    
    # Buscar marca (palabras en mayúsculas cortas)
    marcas_comunes = ['INDUSCABOS', 'DINWAY', 'TCM', 'ECOVILLE']
    for marca in marcas_comunes:
        if marca in linea.upper():
            item['marca'] = marca
            break
    
    # Buscar unidad (M, PC, UND, etc.)
    unidades = ['M', 'PC', 'UND', 'KG', 'M2', 'M3']
    for unidad in unidades:
        if re.search(r'\b' + unidad + r'\b', linea.upper()):
            item['unidad'] = unidad
            break
    
    # Solo retornar item si tiene al menos descripción o precio
    if item['descripcion'] or item['precio_unitario']:
        return item
    
    return None

def mejorar_extraccion_con_ocr_resultados(resultados_ocr, datos_iniciales):
    """
    Usa las coordenadas del OCR para mejorar la extracción de datos
    """
    # Verificar que resultados_ocr sea una lista
    if not isinstance(resultados_ocr, list):
        print(f"Error: resultados_ocr no es una lista, es {type(resultados_ocr)}")
        return datos_iniciales
    
    # Agrupar resultados por posición Y (líneas)
    lineas_y = {}
    for idx, resultado in enumerate(resultados_ocr):
        try:
            # Validar estructura del resultado
            if not isinstance(resultado, (list, tuple)):
                print(f"Resultado {idx} no es lista/tupla: {type(resultado)}")
                continue
            
            if len(resultado) < 3:
                print(f"Resultado {idx} tiene menos de 3 elementos: {len(resultado)}")
                continue
            
            # Extraer componentes con validación
            bbox = resultado[0]
            texto = resultado[1]
            confianza = resultado[2]
            
            # Verificar que bbox sea una lista/tupla y no una función
            if callable(bbox):
                print(f"Error: bbox en resultado {idx} es una función: {bbox}")
                continue
                
            if not isinstance(bbox, (list, tuple)):
                print(f"Error: bbox en resultado {idx} no es lista/tupla: {type(bbox)}")
                continue
                
            if len(bbox) == 0:
                print(f"Advertencia: bbox en resultado {idx} está vacío")
                continue
            
            # Validar que bbox contenga coordenadas válidas
            if not all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in bbox):
                print(f"Error: bbox en resultado {idx} no tiene coordenadas válidas")
                continue
            
            # Calcular Y promedio del bbox
            try:
                y_promedio = sum([p[1] for p in bbox]) / len(bbox)
            except (TypeError, IndexError) as e:
                print(f"Error al calcular y_promedio para resultado {idx}: {e}")
                continue
            
            # Calcular X promedio del bbox
            try:
                x_promedio = sum([p[0] for p in bbox]) / len(bbox)
            except (TypeError, IndexError) as e:
                print(f"Error al calcular x_promedio para resultado {idx}: {e}")
                continue
            
            # Agrupar por línea (tolerancia de 10 píxeles)
            linea_key = int(y_promedio / 10) * 10
            
            if linea_key not in lineas_y:
                lineas_y[linea_key] = []
            
            lineas_y[linea_key].append({
                'texto': str(texto) if texto else "",
                'x': x_promedio,
                'confianza': confianza
            })
        except Exception as e:
            print(f"Error inesperado al procesar resultado {idx}: {e}")
            import traceback
            print(traceback.format_exc())
            continue
    
    # Ordenar líneas por Y
    lineas_ordenadas = sorted(lineas_y.items())
    
    # Procesar cada línea para extraer items
    items_mejorados = []
    for y, elementos in lineas_ordenadas:
        if not elementos:
            continue
            
        # Ordenar elementos por X (columnas)
        elementos_ordenados = sorted(elementos, key=lambda e: e.get('x', 0))
        
        # Reconstruir línea
        linea_texto = ' '.join([str(e.get('texto', '')) for e in elementos_ordenados])
        
        # Extraer item (pasar None en lugar de resultados_ocr ya que no lo usamos en esta función)
        item = extraer_item_linea(linea_texto, None)
        if item:
            items_mejorados.append(item)
    
    if items_mejorados:
        datos_iniciales['items'] = items_mejorados
    
    return datos_iniciales

