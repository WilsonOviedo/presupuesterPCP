# Configuración de OCR Remoto

## Configuración Básica

Para usar un servidor OCR remoto, agrega las siguientes variables a tu archivo `.env`:

```env
USE_REMOTE_OCR=true
OCR_SERVER_URL=http://pcp-server.local
```

O si el servidor está en un puerto específico:

```env
USE_REMOTE_OCR=true
OCR_SERVER_URL=http://pcp-server.local:8080
```

## Formato del Servidor Remoto

El servidor OCR remoto debe implementar un endpoint que acepte:

### Request

- **Método**: `POST`
- **URL**: `{OCR_SERVER_URL}/api/ocr/process` (se agrega automáticamente si no está en la URL)
- **Content-Type**: `multipart/form-data`

**Parámetros**:
- `imagen`: Archivo de imagen (PNG, JPG, etc.)
- `enable_preprocessing`: `'true'` o `'false'`
- `threshold`: `'0'` a `'255'` (string)
- `contrast`: `'-100'` a `'100'` (string)
- `brightness`: `'-100'` a `'100'` (string)
- `enable_smoothing`: `'true'` o `'false'`
- `enable_grayscale`: `'true'` o `'false'`
- `psm_mode`: Modo PSM de Tesseract (ej: `'6'`)
- `lang`: Idiomas (ej: `'spa+por+eng'`)
- `crop_region`: JSON string opcional con `{x, y, width, height}`

### Response

**Formato**: JSON

```json
{
  "text": "texto extraído completo...",
  "words": [
    [
      [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
      "palabra",
      0.95
    ],
    [
      [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
      "otra",
      0.87
    ]
  ],
  "word_count": 2
}
```

**Formato de palabras**:
- Cada palabra es un array con 3 elementos:
  1. Array de coordenadas: `[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]`
  2. Texto de la palabra: `"palabra"`
  3. Confianza: `0.95` (0.0 a 1.0) o `95` (0 a 100)

## Ejemplo de Configuración

### Archivo `.env`:

```env
# Usar OCR remoto
USE_REMOTE_OCR=true
OCR_SERVER_URL=http://192.168.1.100:5000

# O usar OCR local
# USE_REMOTE_OCR=false
```

### Ejemplo de Servidor OCR Remoto (Flask)

```python
from flask import Flask, request, jsonify
import pytesseract
import cv2
import numpy as np
from PIL import Image
import io

app = Flask(__name__)

@app.route('/api/ocr/process', methods=['POST'])
def process_ocr():
    if 'imagen' not in request.files:
        return jsonify({'error': 'No se proporcionó imagen'}), 400
    
    file = request.files['imagen']
    image_bytes = file.read()
    
    # Leer imagen
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Aplicar preprocesamiento según parámetros
    # ... (código de preprocesamiento)
    
    # Ejecutar OCR
    psm_mode = request.form.get('psm_mode', '6')
    lang = request.form.get('lang', 'spa+por+eng')
    
    custom_config = f'--psm {psm_mode} -l {lang}'
    ocr_data = pytesseract.image_to_data(img, config=custom_config, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(img, config=custom_config, lang=lang)
    
    # Formatear respuesta
    words = []
    n_boxes = len(ocr_data['text'])
    for i in range(n_boxes):
        word_text = ocr_data['text'][i].strip()
        conf = int(ocr_data['conf'][i])
        if word_text and conf > 30:
            x = ocr_data['left'][i]
            y = ocr_data['top'][i]
            w = ocr_data['width'][i]
            h = ocr_data['height'][i]
            words.append([
                [[x, y], [x+w, y], [x+w, y+h], [x, y+h]],
                word_text,
                conf / 100.0
            ])
    
    return jsonify({
        'text': text,
        'words': words,
        'word_count': len(words)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

## Verificación

Para verificar que la configuración funciona:

1. Asegúrate de que `USE_REMOTE_OCR=true` en tu `.env`
2. Verifica que `OCR_SERVER_URL` apunta al servidor correcto
3. Reinicia la aplicación Flask
4. Intenta procesar una imagen desde la interfaz web

Si hay errores, revisa los logs de la aplicación para ver mensajes de error específicos.

