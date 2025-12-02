# Configuración de OCR (Local o Remoto)

## Usar Servidor OCR Remoto

Si tienes un servidor OCR remoto (por ejemplo, en `pcp-server.local`), puedes configurarlo en el archivo `.env`:

```env
USE_REMOTE_OCR=true
OCR_SERVER_URL=http://pcp-server.local
```

O si el endpoint es diferente:

```env
USE_REMOTE_OCR=true
OCR_SERVER_URL=http://pcp-server.local/ocr
```

El servidor remoto debe aceptar:
- **Método**: POST
- **Endpoint**: `/api/ocr/process` (o el que especifiques en `OCR_SERVER_URL`)
- **Formato**: multipart/form-data
- **Parámetros**:
  - `imagen`: archivo de imagen (PNG)
  - `enable_preprocessing`: 'true' o 'false'
  - `threshold`: '0' a '255'
  - `contrast`: '-100' a '100'
  - `brightness`: '-100' a '100'
  - `enable_smoothing`: 'true' o 'false'
  - `enable_grayscale`: 'true' o 'false'
  - `psm_mode`: modo PSM de Tesseract (ej: '6')
  - `lang`: idiomas (ej: 'spa+por+eng')
  - `crop_region`: JSON string con {x, y, width, height} (opcional)
- **Respuesta JSON**:
  ```json
  {
    "text": "texto extraído...",
    "words": [
      [
        [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "palabra",
        0.95
      ]
    ],
    "word_count": 10
  }
  ```

Si `USE_REMOTE_OCR=false` o no está configurado, se usará Tesseract local.

---

# Instalación de Tesseract OCR (Solo para uso local)

## Windows

### Opción 1: Instalador oficial (Recomendado)

1. Descarga el instalador desde: https://github.com/UB-Mannheim/tesseract/wiki
2. Ejecuta el instalador y sigue las instrucciones
3. **IMPORTANTE**: Durante la instalación, marca la opción "Add to PATH" o agrega manualmente la ruta de instalación al PATH del sistema
4. La ruta típica es: `C:\Program Files\Tesseract-OCR\tesseract.exe`

### Opción 2: Chocolatey

```powershell
choco install tesseract
```

### Verificar instalación

Abre PowerShell o CMD y ejecuta:
```cmd
tesseract --version
```

Si no funciona, agrega manualmente al PATH:
1. Busca "Variables de entorno" en Windows
2. Edita la variable "Path" del sistema
3. Agrega: `C:\Program Files\Tesseract-OCR`
4. Reinicia la terminal

### Configurar variable de entorno (Opcional)

Si Tesseract está instalado en una ubicación no estándar, puedes crear un archivo `.env` en la raíz del proyecto:

```
TESSERACT_CMD=C:\Ruta\Completa\A\tesseract.exe
```

## Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-spa tesseract-ocr-por tesseract-ocr-eng
```

## macOS

```bash
brew install tesseract tesseract-lang
```

## Verificar que funciona

Después de instalar, ejecuta en Python:

```python
import pytesseract
print(pytesseract.get_tesseract_version())
```

Si obtienes un error, el código intentará detectar automáticamente la ruta de Tesseract en Windows.

