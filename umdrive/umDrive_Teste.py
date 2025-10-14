# UI simples: http://localhost:5000/ui
# Swagger UI: http://localhost:5000/swagger


from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string # type: ignore
from werkzeug.utils import secure_filename # type: ignore
from werkzeug.exceptions import RequestEntityTooLarge # type: ignore
from pathlib import Path
import os, json, time

app = Flask(__name__)

# Config
STORAGE_DIR = Path('storage')
METADATA_FILE = STORAGE_DIR / 'metadata.json'
STORAGE_DIR.mkdir(exist_ok=True)
if not METADATA_FILE.exists():
    METADATA_FILE.write_text(json.dumps({}, indent=2), encoding='utf-8')

# Limite de upload (ex.: 100 MB)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# Helpers
def load_metadata():
    try:
        return json.loads(METADATA_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save_metadata(md):
    METADATA_FILE.write_text(json.dumps(md, indent=2), encoding='utf-8')

def is_within_directory(child: Path, parent: Path) -> bool:
    parent_real = str(parent.resolve())
    child_real = str(child.resolve())
    return child_real == parent_real or child_real.startswith(parent_real + os.sep)

def file_info(path: Path):
    st = path.stat()
    return {
        'name': path.name,
        'size': st.st_size,
        'mtime': int(st.st_mtime),
        'download_url': f'/api/files/{path.name}/download',
        'metadata': load_metadata().get(path.name, {})
    }

# Basic index
@app.route("/")
def index():
    return "<h1>Olá — o UM Drive está a funcionar!</h1><p>Servidor ativo.</p>"

# API: listar ficheiros
@app.route("/api/files", methods=['GET'])
def list_files():
    files = [file_info(p) for p in STORAGE_DIR.iterdir() if p.is_file() and p.name != METADATA_FILE.name]
    files_sorted = sorted(files, key=lambda x: x['name'].lower())
    return jsonify(files_sorted)

# API: upload
@app.route("/api/files", methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum ficheiro enviado (campo "file" ausente)'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': 'Nome do ficheiro vazio'}), 400
    filename = secure_filename(f.filename)
    target = STORAGE_DIR / filename
    f.save(str(target))
    md = load_metadata()
    md.setdefault(filename, {})
    save_metadata(md)
    return jsonify({'message': 'uploaded', 'file': filename}), 201

# API: download
@app.route("/api/files/<path:filename>/download", methods=['GET'])
def download_file(filename):
    safe_name = secure_filename(filename)
    file_path = STORAGE_DIR / safe_name
    if not file_path.exists():
        return jsonify({'error': 'Ficheiro não encontrado'}), 404
    if not is_within_directory(file_path, STORAGE_DIR):
        return jsonify({'error': 'Caminho inválido'}), 400
    return send_from_directory(str(STORAGE_DIR), safe_name, as_attachment=True)

# API: apagar ficheiro
@app.route("/api/files/<path:filename>", methods=['DELETE'])
def delete_file(filename):
    safe_name = secure_filename(filename)
    file_path = STORAGE_DIR / safe_name
    if not file_path.exists():
        return jsonify({'error': 'Ficheiro não encontrado'}), 404
    if not is_within_directory(file_path, STORAGE_DIR):
        return jsonify({'error': 'Caminho inválido'}), 400
    file_path.unlink()
    md = load_metadata()
    md.pop(safe_name, None)
    save_metadata(md)
    return jsonify({'message': 'deleted', 'file': safe_name})

# API: ler / escrever metadados
@app.route("/api/files/<path:filename>/metadata", methods=['GET', 'POST'])
def metadata(filename):
    safe_name = secure_filename(filename)
    file_path = STORAGE_DIR / safe_name
    md = load_metadata()
    if request.method == 'GET':
        return jsonify(md.get(safe_name, {}))
    else:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({'error': 'Esperado body JSON object'}), 400
        md[safe_name] = data
        save_metadata(md)
        return jsonify({'message': 'metadata updated', 'file': safe_name})

# Tratamento de erro para ficheiros muito grandes
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({'error': 'Ficheiro demasiado grande'}), 413

# UI simples (upload, listar, download, apagar)
UI_HTML = """
<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>umDrive — UI</title>

  <!-- Bootstrap CSS (CDN) -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">

  <style>
    body { padding: 1.5rem; background: #f8f9fa; }
    .dropzone {
      border: 2px dashed #ced4da;
      border-radius: .5rem;
      padding: 1.25rem;
      text-align: center;
      background: #fff;
      transition: border-color .15s, background .15s;
    }
    .dropzone.dragover { border-color: #0d6efd; background: #eef6ff; }
    .file-row:hover { background: #fffbe6; }
    .small-muted { font-size: .85rem; color: #6c757d; }
    #progressBar { height: 1rem; }
    .truncate { max-width: 42ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: middle; }
  </style>
</head>
<body>
  <div class="container">
    <div class="d-flex align-items-center mb-3">
      <h2 class="me-auto"><i class="bi bi-hdd-stack-fill me-2"></i>umDrive</h2>
      <a class="btn btn-outline-secondary btn-sm" href="/swagger" target="_blank"><i class="bi bi-card-text"></i> API</a>
    </div>

    <div class="row g-3">
      <div class="col-lg-5">
        <div id="dropzone" class="dropzone mb-3">
          <p class="mb-1"><strong>Arrasta ficheiros aqui</strong> ou clica para escolher</p>
          <p class="small-muted mb-0">Tamanho máximo: 100 MB</p>
          <input id="fileInput" type="file" class="form-control d-none" />
          <div class="mt-3">
            <button id="chooseBtn" class="btn btn-primary btn-sm"><i class="bi bi-upload"></i> Escolher ficheiro</button>
          </div>

          <div class="mt-3">
            <div class="progress" style="height:1.1rem; display:none;" id="progressWrapper">
              <div id="progressBar" class="progress-bar" role="progressbar" style="width:0%">0%</div>
            </div>
            <div id="uploadMsg" class="mt-2 small-muted"></div>
          </div>
        </div>

        <div class="card shadow-sm">
          <div class="card-body p-3">
            <h6 class="card-title">Sobre</h6>
            <p class="card-text small-muted mb-1">Interface moderna para gerir ficheiros no umDrive. Usa o Swagger para testes mais avançados.</p>
            <div class="d-flex gap-2">
              <button id="refreshBtn" class="btn btn-outline-primary btn-sm"><i class="bi bi-arrow-clockwise"></i> Atualizar</button>
              <button id="clearStorageBtn" class="btn btn-outline-danger btn-sm" title="Apagar todos os ficheiros (não implementado no backend)">Apagar tudo</button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-lg-7">
        <div class="mb-2 d-flex">
          <input id="searchInput" type="search" class="form-control me-2" placeholder="Procurar por nome...">
          <select id="sortSelect" class="form-select" style="max-width: 200px;">
            <option value="name_asc">Nome ↑</option>
            <option value="name_desc">Nome ↓</option>
            <option value="size_desc">Tamanho ↓</option>
            <option value="mtime_desc">Modificação ↓</option>
          </select>
        </div>

        <div id="filesList" class="list-group shadow-sm">
          <!-- preenchido por JS -->
        </div>

        <div class="mt-3 small-muted">Se não aparecerem ficheiros, clica em <strong>Atualizar</strong>. Para testes avançados abre <a href="/swagger" target="_blank">Swagger UI</a>.</div>
      </div>
    </div>
  </div>

  <!-- Metadata Modal -->
  <div class="modal fade" id="metaModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-lg modal-dialog-centered">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Metadata — <span id="metaFilename" class="fw-semibold"></span></h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button>
        </div>
        <div class="modal-body">
          <textarea id="metaEditor" class="form-control" rows="8"></textarea>
          <div class="form-text mt-2 small-muted">JSON object. Se estiver vazio será criado.</div>
        </div>
        <div class="modal-footer">
          <button id="saveMetaBtn" type="button" class="btn btn-primary">Guardar</button>
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Bootstrap JS (CDN) -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>

  <script>
    const fileInput = document.getElementById('fileInput');
    const chooseBtn = document.getElementById('chooseBtn');
    const dropzone = document.getElementById('dropzone');
    const progressWrapper = document.getElementById('progressWrapper');
    const progressBar = document.getElementById('progressBar');
    const uploadMsg = document.getElementById('uploadMsg');
    const filesList = document.getElementById('filesList');
    const refreshBtn = document.getElementById('refreshBtn');
    const searchInput = document.getElementById('searchInput');
    const sortSelect = document.getElementById('sortSelect');

    const metaModalEl = document.getElementById('metaModal');
    const metaModal = new bootstrap.Modal(metaModalEl);
    const metaEditor = document.getElementById('metaEditor');
    const metaFilename = document.getElementById('metaFilename');
    const saveMetaBtn = document.getElementById('saveMetaBtn');

    chooseBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => handleFiles(fileInput.files));

    // Drag & drop
    ['dragenter','dragover'].forEach(e => dropzone.addEventListener(e, (ev) => { ev.preventDefault(); ev.stopPropagation(); dropzone.classList.add('dragover'); }));
    ['dragleave','drop','dragend'].forEach(e => dropzone.addEventListener(e, (ev) => { ev.preventDefault(); ev.stopPropagation(); dropzone.classList.remove('dragover'); }));
    dropzone.addEventListener('drop', (ev) => {
      const dt = ev.dataTransfer;
      if (dt && dt.files && dt.files.length) handleFiles(dt.files);
    });

    async function handleFiles(files) {
      if (!files.length) return;
      const file = files[0];
      await uploadSingleFile(file);
      fileInput.value = '';
      await loadFiles();
    }

    async function uploadSingleFile(file) {
      uploadMsg.textContent = '';
      progressWrapper.style.display = 'block';
      progressBar.style.width = '0%';
      progressBar.textContent = '0%';
      const fd = new FormData();
      fd.append('file', file);

      // Usa XMLHttpRequest para ter progresso
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/files');
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 100);
            progressBar.style.width = pct + '%';
            progressBar.textContent = pct + '%';
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            uploadMsg.textContent = 'Upload concluído ✅';
            setTimeout(()=>{ progressWrapper.style.display='none'; progressBar.style.width='0%'; }, 800);
            resolve();
          } else {
            uploadMsg.textContent = 'Erro no upload: ' + xhr.statusText;
            progressWrapper.style.display = 'none';
            reject();
          }
        };
        xhr.onerror = () => { uploadMsg.textContent = 'Erro no upload (network)'; progressWrapper.style.display = 'none'; reject(); };
        xhr.send(fd);
      });
    }

    async function loadFiles() {
      try {
        const res = await fetch('/api/files');
        const files = await res.json();
        renderFiles(files);
      } catch (err) {
        filesList.innerHTML = '<div class="list-group-item">Erro ao carregar ficheiros</div>';
      }
    }

    function renderFiles(files) {
      const q = searchInput.value.trim().toLowerCase();
      let arr = files.filter(f => f.name.toLowerCase().includes(q));
      const sort = sortSelect.value;
      if (sort === 'name_asc') arr.sort((a,b)=>a.name.localeCompare(b.name));
      if (sort === 'name_desc') arr.sort((a,b)=>b.name.localeCompare(a.name));
      if (sort === 'size_desc') arr.sort((a,b)=>b.size - a.size);
      if (sort === 'mtime_desc') arr.sort((a,b)=>b.mtime - a.mtime);

      if (!arr.length) { filesList.innerHTML = '<div class="list-group-item small-muted">Sem ficheiros</div>'; return; }

      filesList.innerHTML = '';
      arr.forEach(f => {
        const item = document.createElement('div');
        item.className = 'list-group-item d-flex gap-3 align-items-center file-row';
        item.innerHTML = `
          <div class="flex-shrink-0 text-center" style="width:48px;">
            <i class="bi bi-file-earmark-fill fs-3"></i>
          </div>
          <div class="flex-grow-1">
            <div><span class="fw-semibold truncate" title="${f.name}">${f.name}</span></div>
            <div class="small-muted mt-1">${f.size} bytes • mod: ${new Date(f.mtime*1000).toLocaleString()}</div>
          </div>
          <div class="d-flex gap-2 align-items-center">
            <a class="btn btn-outline-success btn-sm" href="${f.download_url}" download><i class="bi bi-download"></i></a>
            <button class="btn btn-outline-secondary btn-sm" data-meta="${encodeURIComponent(f.name)}"><i class="bi bi-pencil"></i></button>
            <button class="btn btn-outline-danger btn-sm" data-del="${encodeURIComponent(f.name)}"><i class="bi bi-trash"></i></button>
          </div>
        `;
        filesList.appendChild(item);
      });

      // attach handlers
      filesList.querySelectorAll('button[data-del]').forEach(btn => {
        btn.onclick = async () => {
          const name = decodeURIComponent(btn.getAttribute('data-del'));
          if (!confirm('Apagar ' + name + '?')) return;
          const r = await fetch('/api/files/' + encodeURIComponent(name), { method: 'DELETE' });
          if (r.ok) loadFiles(); else alert('Erro ao apagar');
        };
      });

      filesList.querySelectorAll('button[data-meta]').forEach(btn => {
        btn.onclick = async () => {
          const name = decodeURIComponent(btn.getAttribute('data-meta'));
          metaFilename.textContent = name;
          // carrega metadata
          const r = await fetch('/api/files/' + encodeURIComponent(name) + '/metadata');
          let md = {};
          if (r.ok) md = await r.json(); else md = {};
          metaEditor.value = JSON.stringify(md, null, 2);
          metaModal.show();
        };
      });
    }

    saveMetaBtn.addEventListener('click', async () => {
      const name = metaFilename.textContent;
      let parsed;
      try { parsed = JSON.parse(metaEditor.value || '{}'); }
      catch (e) { return alert('JSON inválido'); }
      const r = await fetch('/api/files/' + encodeURIComponent(name) + '/metadata', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(parsed)
      });
      if (r.ok) { metaModal.hide(); loadFiles(); } else alert('Erro a guardar metadata');
    });

    refreshBtn.addEventListener('click', loadFiles);
    searchInput.addEventListener('input', loadFiles);
    sortSelect.addEventListener('change', loadFiles);

    // inicial
    loadFiles();
  </script>
</body>
</html>
"""


@app.route("/ui")
def ui():
    return render_template_string(UI_HTML)


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
