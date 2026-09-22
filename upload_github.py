"""
Servidor local para upload dos CSVs finais ao GitHub.
Uso: python upload_github.py
Abre automaticamente no navegador.
"""
import json
import subprocess
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Timer

ROOT = Path(__file__).parent

_ARQUIVOS = [
    ROOT / "base_pronta.csv",
    ROOT / "base_falta_pronta.csv",
    ROOT / "relatorionotas.csv",
    ROOT / "BASE2" / "relatorionotas_falta.csv",
]

_HTML = b"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Upload GitHub \xe2\x80\x94 Dias+</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f0f2f5;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 24px;
  }
  .card {
    background: white;
    border-radius: 12px;
    padding: 32px;
    width: 100%;
    max-width: 520px;
    box-shadow: 0 4px 20px rgba(0,0,0,.1);
  }
  h1 { font-size: 20px; color: #1a1a2e; margin-bottom: 6px; }
  .sub { color: #666; font-size: 14px; margin-bottom: 24px; }
  .file-list { border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden; margin-bottom: 24px; }
  .file-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-bottom: 1px solid #f0f0f0;
    font-size: 14px;
  }
  .file-item:last-child { border-bottom: none; }
  .badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    white-space: nowrap;
    min-width: 60px;
    text-align: center;
  }
  .ok   { background: #e6f9f0; color: #1a7a4a; }
  .miss { background: #fde8e8; color: #c0392b; }
  .filename { color: #333; font-family: monospace; }
  button {
    width: 100%;
    background: #1a73e8;
    color: white;
    border: none;
    padding: 13px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background .2s;
  }
  button:hover:not(:disabled) { background: #1557b0; }
  button:disabled { background: #aab8c2; cursor: not-allowed; }
  #status {
    margin-top: 20px;
    border-radius: 8px;
    padding: 14px 16px;
    font-size: 13px;
    display: none;
  }
  #status.ok-box  { background: #e6f9f0; color: #1a7a4a; border: 1px solid #a8ddc1; }
  #status.err-box { background: #fde8e8; color: #c0392b; border: 1px solid #f5aaaa; }
  pre { white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff;
    border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; margin-right: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="card">
  <h1>\xf0\x9f\x93\xa4 Upload GitHub \xe2\x80\x94 Dias+</h1>
  <p class="sub">Envia os arquivos abaixo para o reposit\xc3\xb3rio remoto (main).</p>
  <div class="file-list" id="files">
    <div class="file-item"><span class="badge" style="background:#eee;color:#999">...</span><span class="filename">carregando</span></div>
  </div>
  <button id="btn" onclick="upload()">Upar para GitHub</button>
  <div id="status"></div>
</div>
<script>
async function checkFiles() {
  try {
    const r = await fetch('/status');
    const data = await r.json();
    document.getElementById('files').innerHTML = data.files.map(f =>
      `<div class="file-item">
        <span class="badge ${f.exists ? 'ok' : 'miss'}">${f.exists ? 'Pronto' : 'Ausente'}</span>
        <span class="filename">${f.name}</span>
      </div>`
    ).join('');
  } catch(e) {
    document.getElementById('files').innerHTML = '<div class="file-item">Erro ao verificar arquivos.</div>';
  }
}

async function upload() {
  const btn = document.getElementById('btn');
  const status = document.getElementById('status');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Enviando...';
  status.style.display = 'none';

  try {
    const r = await fetch('/upload', { method: 'POST' });
    const data = await r.json();
    status.className = data.ok ? 'ok-box' : 'err-box';
    status.style.display = 'block';
    status.innerHTML = `<pre>${data.message}</pre>`;
  } catch(e) {
    status.className = 'err-box';
    status.style.display = 'block';
    status.innerHTML = `<pre>Erro de conex\xc3\xa3o: ${e}</pre>`;
  }

  btn.disabled = false;
  btn.textContent = 'Upar para GitHub';
  checkFiles();
}

checkFiles();
</script>
</body>
</html>"""


def _git(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def _status_arquivos() -> list[dict]:
    return [{"name": a.name, "exists": a.exists()} for a in _ARQUIVOS]


def _executar_upload() -> tuple[bool, str]:
    hoje = date.today().strftime("%d/%m/%Y")
    existentes = [a for a in _ARQUIVOS if a.exists()]

    if not existentes:
        return False, "Nenhum arquivo encontrado. Rode o pipeline (main.py) primeiro."

    linhas: list[str] = []

    for arq in existentes:
        caminho = str(arq.relative_to(ROOT)).replace("\\", "/")
        ok, out = _git(["add", caminho])
        linhas.append(f"{'OK' if ok else 'ERRO'} git add {arq.name}")
        if out:
            linhas.append(f"   {out}")

    ok, out = _git(["commit", "-m", f"Atualiza bases finais — {hoje}"])
    _sem_mudanca = ("nothing to commit", "no changes added to commit")
    if not ok and any(m in out.lower() for m in _sem_mudanca):
        return True, "Nada a enviar — arquivos ja estao atualizados no GitHub."

    linhas.append(f"{'OK' if ok else 'ERRO'} git commit")
    if out:
        linhas.append(f"   {out}")

    if not ok:
        return False, "\n".join(linhas)

    ok, out = _git(["push"])
    linhas.append(f"{'OK' if ok else 'ERRO'} git push")
    if out:
        linhas.append(f"   {out}")

    msg = "\n".join(linhas)
    return ok, msg


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._json({"files": _status_arquivos()})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_HTML)))
        self.end_headers()
        self.wfile.write(_HTML)

    def do_POST(self):
        if self.path == "/upload":
            ok, msg = _executar_upload()
            self._json({"ok": ok, "message": msg})


if __name__ == "__main__":
    porta = 8765
    server = HTTPServer(("localhost", porta), _Handler)
    url = f"http://localhost:{porta}"
    print(f"Servidor iniciado → {url}")
    print("Pressione Ctrl+C para encerrar.")
    Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
