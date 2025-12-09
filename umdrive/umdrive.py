from flask import Flask, request, jsonify, send_from_directory, render_template, render_template_string
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from pathlib import Path
from flask import Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter
import os, json

app = Flask(__name__)

http_requests_total = Counter(
    "http_requests_total",
    "Total de requisições HTTP por endpoint e método",
    ["method", "endpoint"]
)

# Diretório de armazenamento (NFS montado)
STORAGE_DIR = Path('/app/storage')
METADATA_FILE = STORAGE_DIR / 'metadata.json'
STORAGE_DIR.mkdir(exist_ok=True)
if not METADATA_FILE.exists():
    METADATA_FILE.write_text(json.dumps({}, indent=2), encoding='utf-8')

@app.before_request
def before_request():
    http_requests_total.labels(
        method=request.method,
        endpoint=request.path
    ).inc()

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Limite de upload (1GB)
app.config['MAX_CONTENT_LENGTH'] = 1000 * 1024 * 1024

# --- Funções auxiliares ---
def load_metadata():
    try:
        return json.loads(METADATA_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save_metadata(md):
    METADATA_FILE.write_text(json.dumps(md, indent=2), encoding='utf-8')

def is_within_directory(child: Path, parent: Path) -> bool:
    return str(child.resolve()).startswith(str(parent.resolve()))

def file_info(path: Path):
    st = path.stat()
    return {
        'name': path.name,
        'size': st.st_size,
        'mtime': int(st.st_mtime),
        'download_url': f'/api/files/{path.name}/download',
        'metadata': load_metadata().get(path.name, {})
    }

# --- Rotas Flask ---
@app.route("/")
def index():
    return "<h1>Olá — o UM Drive está a funcionar!</h1><p>Servidor ativo.</p>"

@app.route("/api/files", methods=['GET'])
def list_files():
    files = [file_info(p) for p in STORAGE_DIR.iterdir() if p.is_file() and p.name != METADATA_FILE.name]
    return jsonify(sorted(files, key=lambda x: x['name'].lower()))

@app.route("/api/files", methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum ficheiro enviado'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'Nome de ficheiro vazio'}), 400
    filename = secure_filename(f.filename)
    f.save(str(STORAGE_DIR / filename))
    md = load_metadata(); md.setdefault(filename, {}); save_metadata(md)
    return jsonify({'message': 'uploaded', 'file': filename}), 201

@app.route("/api/files/<path:filename>/download", methods=['GET'])
def download_file(filename):
    safe_name = secure_filename(filename)
    path = STORAGE_DIR / safe_name
    if not path.exists(): return jsonify({'error': 'Não encontrado'}), 404
    if not is_within_directory(path, STORAGE_DIR): return jsonify({'error': 'Caminho inválido'}), 400
    return send_from_directory(str(STORAGE_DIR), safe_name, as_attachment=True)

@app.route("/api/files/<path:filename>", methods=['DELETE'])
def delete_file(filename):
    safe_name = secure_filename(filename)
    path = STORAGE_DIR / safe_name
    if not path.exists(): return jsonify({'error': 'Não encontrado'}), 404
    path.unlink(); md = load_metadata(); md.pop(safe_name, None); save_metadata(md)
    return jsonify({'message': 'deleted', 'file': safe_name})

@app.route("/api/files/<path:filename>/metadata", methods=['GET','POST'])
def metadata(filename):
    safe_name = secure_filename(filename)
    md = load_metadata()
    if request.method == 'GET': return jsonify(md.get(safe_name, {}))
    data = request.get_json()
    if not isinstance(data, dict): return jsonify({'error': 'Esperado JSON object'}), 400
    md[safe_name] = data; save_metadata(md)
    return jsonify({'message': 'metadata updated', 'file': safe_name})

@app.errorhandler(RequestEntityTooLarge)
def handle_large(e): return jsonify({'error': 'Ficheiro demasiado grande'}), 413

@app.route("/ui")
def ui(): return render_template("ui.html")

# =========================
# 🔹 SWAGGER / OPENAPI SETUP
# =========================

OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "umDrive API",
        "version": "1.0.0",
        "description": "API simples para listar, fazer upload/download e apagar ficheiros com metadata."
    },
    "servers": [{"url": "/"}],
    "paths": {
        "/api/files": {
            "get": {"summary": "Listar ficheiros", "responses": {"200": {"description": "Lista de ficheiros"}}},
            "post": {
                "summary": "Upload de ficheiro (multipart/form-data)",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {"file": {"type": "string", "format": "binary"}},
                                "required": ["file"]
                            }
                        }
                    }
                },
                "responses": {"201": {"description": "Ficheiro carregado"}, "400": {"description": "Erro no pedido"}}
            },
        },
        "/api/files/{filename}/download": {
            "get": {
                "summary": "Descarregar ficheiro",
                "parameters": [{"name": "filename", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Ficheiro binário"}, "404": {"description": "Não encontrado"}}
            }
        },
        "/api/files/{filename}": {
            "delete": {
                "summary": "Apagar ficheiro",
                "parameters": [{"name": "filename", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Apagado"}, "404": {"description": "Não encontrado"}}
            }
        },
        "/api/files/{filename}/metadata": {
            "get": {
                "summary": "Ler metadata",
                "parameters": [{"name": "filename", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "Metadata JSON"}}
            },
            "post": {
                "summary": "Atualizar metadata",
                "parameters": [{"name": "filename", "in": "path", "required": True, "schema": {"type": "string"}}],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}}
                },
                "responses": {"200": {"description": "Metadata atualizada"}}
            }
        }
    }
}

SWAGGER_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>umDrive Swagger UI</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@4/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@4/swagger-ui-bundle.js"></script>
    <script>
      const ui = SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout"
      });
    </script>
  </body>
</html>
"""

@app.route("/openapi.json")
def openapi_json():
    return jsonify(OPENAPI)

@app.route("/swagger")
def swagger_ui():
    return render_template_string(SWAGGER_HTML)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
