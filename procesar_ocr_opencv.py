"""
Módulo para procesar imágenes con OpenCV y Tesseract OCR
Soporta tanto OCR local como remoto
"""
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
import base64
import os
import platform
from dotenv import load_dotenv
import requests

# Cargar variables de entorno
load_dotenv()

# Configuración de OCR remoto
OCR_REMOTE_URL = os.getenv('OCR_SERVER_URL', '').strip()
USE_REMOTE_OCR = os.getenv('USE_REMOTE_OCR', 'false').lower() == 'true'

# Configurar ruta de Tesseract automáticamente
def configure_tesseract_path():
    """Configura la ruta de Tesseract según el sistema operativo"""
    system = platform.system()
    
    if system == "Windows":
        # Rutas comunes de Tesseract en Windows
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.getenv('USERNAME', '')),
            r"D:\Program Files\Tesseract-OCR\tesseract.exe",
            r"D:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        
        # También buscar en PATH usando shutil
        try:
            import shutil
            tesseract_cmd = shutil.which('tesseract')
            if tesseract_cmd and os.path.exists(tesseract_cmd):
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                print(f"Tesseract encontrado en PATH: {tesseract_cmd}")
                return
        except:
            pass
        
        # Buscar en rutas comunes
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                print(f"Tesseract encontrado en: {path}")
                return
        
        # Si no se encuentra, intentar usar la variable de entorno
        tesseract_env = os.getenv('TESSERACT_CMD')
        if tesseract_env and os.path.exists(tesseract_env):
            pytesseract.pytesseract.tesseract_cmd = tesseract_env
            return
        
        raise Exception(
            "Tesseract no encontrado. Por favor instálalo desde:\n"
            "https://github.com/UB-Mannheim/tesseract/wiki\n\n"
            "O configura la variable de entorno TESSERACT_CMD con la ruta completa a tesseract.exe"
        )
    elif system in ["Linux", "Darwin"]:  # Linux y macOS
        # En Linux/macOS, generalmente está en el PATH
        try:
            import shutil
            tesseract_cmd = shutil.which('tesseract')
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        except:
            pass
        # Si no está, pytesseract intentará usar 'tesseract' del PATH

# Configurar Tesseract al importar el módulo
try:
    configure_tesseract_path()
except Exception as e:
    print(f"Advertencia: {e}")

def preprocess_image_opencv(image_bytes, config):
    """
    Preprocesa una imagen usando OpenCV según la configuración
    
    Args:
        image_bytes: Bytes de la imagen
        config: dict con parámetros:
            - enable_preprocessing: bool
            - threshold: int (0-255)
            - contrast: int (-100 a 100)
            - brightness: int (-100 a 100)
            - enable_smoothing: bool
            - enable_grayscale: bool
            - crop_region: dict con x, y, width, height (opcional)
    
    Returns:
        numpy array de la imagen procesada
    """
    # Leer imagen desde bytes
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("No se pudo decodificar la imagen")
    
    # Recortar si hay región especificada
    if config.get('crop_region'):
        crop = config['crop_region']
        x = int(crop.get('x', 0))
        y = int(crop.get('y', 0))
        w = int(crop.get('width', img.shape[1]))
        h = int(crop.get('height', img.shape[0]))
        img = img[y:y+h, x:x+w]
    
    if not config.get('enable_preprocessing', True):
        return img
    
    # Convertir a escala de grises si está habilitado
    if config.get('enable_grayscale', True):
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Aplicar brillo
    brightness = config.get('brightness', 0)
    if brightness != 0:
        img = cv2.convertScaleAbs(img, alpha=1, beta=brightness)
    
    # Aplicar contraste
    contrast = config.get('contrast', 0)
    if contrast != 0:
        # Convertir contraste de -100 a 100 a factor alpha
        alpha = (contrast + 100) / 100.0
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=0)
    
    # Aplicar suavizado (blur)
    if config.get('enable_smoothing', True):
        img = cv2.GaussianBlur(img, (3, 3), 0)
    
    # Aplicar threshold (binarización)
    threshold = config.get('threshold', 128)
    if threshold > 0:
        _, img = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    
    return img

def process_ocr_remote(image_bytes, config):
    """
    Procesa OCR usando un servidor remoto
    
    Args:
        image_bytes: Bytes de la imagen
        config: dict con parámetros de configuración
    
    Returns:
        dict con text y words
    """
    if not OCR_REMOTE_URL:
        raise ValueError("OCR_SERVER_URL no está configurado en las variables de entorno")
    
    # Preparar datos para enviar
    files = {
        'imagen': ('image.png', image_bytes, 'image/png')
    }
    
    data = {
        'enable_preprocessing': str(config.get('enable_preprocessing', True)),
        'threshold': str(config.get('threshold', 128)),
        'contrast': str(config.get('contrast', 0)),
        'brightness': str(config.get('brightness', 0)),
        'enable_smoothing': str(config.get('enable_smoothing', True)),
        'enable_grayscale': str(config.get('enable_grayscale', True)),
        'psm_mode': str(config.get('psm_mode', '6')),
        'lang': config.get('lang', 'spa+por+eng')
    }
    
    # Agregar región de recorte si existe
    if config.get('crop_region'):
        import json
        data['crop_region'] = json.dumps(config['crop_region'])
    
    # Determinar URL del endpoint
    if OCR_REMOTE_URL.endswith('/'):
        ocr_url = OCR_REMOTE_URL.rstrip('/')
    else:
        ocr_url = OCR_REMOTE_URL
    
    # Si no termina con /api/ocr/process, agregarlo
    if '/api/ocr/process' not in ocr_url:
        if not ocr_url.endswith('/'):
            ocr_url += '/'
        ocr_url += 'api/ocr/process'
    
    try:
        # Enviar petición al servidor remoto
        response = requests.post(
            ocr_url,
            files=files,
            data=data,
            timeout=120  # 2 minutos de timeout
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Convertir formato de palabras si es necesario
        words = []
        if 'words' in result:
            for word in result['words']:
                if isinstance(word, list) and len(word) >= 3:
                    # Formato: [[coords], text, confidence]
                    bbox_coords = word[0]
                    text = word[1]
                    conf = word[2]
                    
                    # Convertir coordenadas a formato esperado
                    if len(bbox_coords) >= 4:
                        words.append({
                            'text': text,
                            'confidence': conf * 100 if conf < 1 else conf,
                            'bbox': {
                                'x0': bbox_coords[0][0],
                                'y0': bbox_coords[0][1],
                                'x1': bbox_coords[2][0],
                                'y1': bbox_coords[2][1]
                            }
                        })
                elif isinstance(word, dict):
                    # Ya está en formato correcto
                    words.append(word)
        
        return {
            'text': result.get('text', ''),
            'words': words
        }
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error al conectar con servidor OCR remoto ({ocr_url}): {str(e)}")
    except Exception as e:
        raise Exception(f"Error al procesar respuesta del servidor OCR remoto: {str(e)}")

def process_ocr_opencv(image_bytes, config):
    """
    Procesa una imagen con OpenCV y Tesseract OCR (local)
    
    Args:
        image_bytes: Bytes de la imagen
        config: dict con parámetros de preprocesamiento y OCR:
            - enable_preprocessing: bool
            - threshold: int (0-255)
            - contrast: int (-100 a 100)
            - brightness: int (-100 a 100)
            - enable_smoothing: bool
            - enable_grayscale: bool
            - crop_region: dict (opcional)
            - psm_mode: str (modo PSM de Tesseract, default '6')
            - lang: str (idiomas, default 'spa+por+eng')
    
    Returns:
        dict con:
            - text: str (texto extraído)
            - words: list de dicts con {text, confidence, bbox}
    """
    # Preprocesar imagen
    processed_img = preprocess_image_opencv(image_bytes, config)
    
    # Configurar Tesseract
    psm_mode = config.get('psm_mode', '6')
    lang = config.get('lang', 'spa+por+eng')
    
    # Configuración de Tesseract
    custom_config = f'--psm {psm_mode} -l {lang}'
    
    # Ejecutar OCR
    ocr_data = pytesseract.image_to_data(
        processed_img,
        config=custom_config,
        output_type=pytesseract.Output.DICT
    )
    
    # Extraer texto completo
    text = pytesseract.image_to_string(processed_img, config=custom_config, lang=lang)
    
    # Procesar palabras con coordenadas y confianza
    words = []
    n_boxes = len(ocr_data['text'])
    
    for i in range(n_boxes):
        word_text = ocr_data['text'][i].strip()
        conf = int(ocr_data['conf'][i])
        
        # Filtrar palabras vacías o con confianza muy baja
        if word_text and conf > 30:
            x = ocr_data['left'][i]
            y = ocr_data['top'][i]
            w = ocr_data['width'][i]
            h = ocr_data['height'][i]
            
            words.append({
                'text': word_text,
                'confidence': conf,
                'bbox': {
                    'x0': x,
                    'y0': y,
                    'x1': x + w,
                    'y1': y + h
                }
            })
    
    return {
        'text': text,
        'words': words
    }

def process_ocr(image_bytes, config):
    """
    Procesa OCR usando servidor remoto o local según configuración
    
    Args:
        image_bytes: Bytes de la imagen
        config: dict con parámetros de configuración
    
    Returns:
        dict con text y words
    """
    if USE_REMOTE_OCR and OCR_REMOTE_URL:
        return process_ocr_remote(image_bytes, config)
    else:
        return process_ocr_opencv(image_bytes, config)

def image_to_base64(img_array):
    """
    Convierte un array de numpy (imagen OpenCV) a base64
    """
    if len(img_array.shape) == 2:
        # Escala de grises
        pil_img = Image.fromarray(img_array)
    else:
        # Color
        img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
    
    buffered = io.BytesIO()
    pil_img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"
