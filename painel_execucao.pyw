"""
Painel de Execução — Pipeline Dias+ (Base Natura → Diaslog → Dashboard)

Interface gráfica para rodar main.py sem usar o terminal (tela preta).
Dê DUPLO CLIQUE em "Abrir Painel Dias+.bat" (na raiz do projeto) para abrir esta tela.

Este arquivo NÃO deve ser renomeado/movido sem atualizar o .bat correspondente.
"""
import asyncio
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import credenciais_seguras as cred_seguras  # noqa: E402

# ---------------------------------------------------------------------------
# Paleta de cores (mesma identidade visual do dashboard Dias+)
# ---------------------------------------------------------------------------
BG = "#0B2E3A"          # fundo principal
BG_CARD = "#123244"     # fundo dos "cartões"
BG_LOG = "#04141A"      # fundo da área de log
TEAL = "#2DC5B4"        # destaque
TEAL_MID = "#1A8090"
TEAL_DARK = "#1A5A68"
WHITE = "#FFFFFF"
MUTED = "#9FB4BA"
AMBER = "#EAB308"
GREEN = "#2ECC71"
RED = "#E15C50"

FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SUB = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 10)
FONT_BTN = ("Segoe UI", 11, "bold")
FONT_LOG = ("Consolas", 9)
FONT_STATUS = ("Segoe UI", 10, "bold")


class PainelExecucao(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Painel Dias+ — Execução do Pipeline")
        self.geometry("920x680")
        self.minsize(760, 560)
        self.configure(bg=BG)

        self.proc = None
        self.fila = queue.Queue()

        self._montar_header()
        self._montar_credenciais()
        self._montar_opcoes()
        self._montar_botoes()
        self._montar_status()
        self._montar_log()

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ------------------------------------------------------------------
    def _montar_header(self):
        topo = tk.Frame(self, bg=BG)
        topo.pack(fill="x", padx=24, pady=(20, 10))

        tk.Label(topo, text="DIAS+", font=FONT_TITLE, fg=TEAL, bg=BG).pack(anchor="w")
        tk.Label(
            topo,
            text="Pipeline: Base Natura → Diaslog → Dashboard",
            font=FONT_SUB, fg=MUTED, bg=BG,
        ).pack(anchor="w")

    # ------------------------------------------------------------------
    def _montar_credenciais(self):
        card = tk.Frame(self, bg=BG_CARD, highlightbackground=TEAL_DARK, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=(8, 0))

        tk.Label(
            card, text="🔐 Credenciais do Diaslog (TMS)",
            font=("Segoe UI", 11, "bold"), fg=WHITE, bg=BG_CARD,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(10, 2))

        tk.Label(card, text="Usuário:", font=FONT_LABEL, fg=MUTED, bg=BG_CARD)\
            .grid(row=1, column=0, sticky="w", padx=(16, 4), pady=6)
        self.entry_usuario = tk.Entry(card, font=FONT_LABEL, width=20, bg="white")
        self.entry_usuario.grid(row=1, column=1, sticky="w", pady=6)

        tk.Label(card, text="Senha:", font=FONT_LABEL, fg=MUTED, bg=BG_CARD)\
            .grid(row=1, column=2, sticky="w", padx=(16, 4), pady=6)
        self.entry_senha = tk.Entry(card, font=FONT_LABEL, width=20, bg="white", show="•")
        self.entry_senha.grid(row=1, column=3, sticky="w", pady=6)

        self.mostrar_senha_var = tk.BooleanVar(value=False)
        chk_mostrar = tk.Checkbutton(
            card, text="mostrar", variable=self.mostrar_senha_var,
            font=("Segoe UI", 8), fg=MUTED, bg=BG_CARD,
            activebackground=BG_CARD, activeforeground=WHITE, selectcolor=BG_CARD,
            command=self._alternar_mostrar_senha,
        )
        chk_mostrar.grid(row=1, column=4, sticky="w", padx=(4, 16))

        botoes = tk.Frame(card, bg=BG_CARD)
        botoes.grid(row=2, column=0, columnspan=5, sticky="w", padx=12, pady=(2, 4))

        tk.Button(
            botoes, text="💾 Salvar", font=("Segoe UI", 9, "bold"),
            bg=TEAL_MID, fg=WHITE, activebackground=TEAL, relief="flat",
            padx=10, pady=4, cursor="hand2", command=self._salvar_credenciais,
        ).pack(side="left", padx=4)

        self.btn_testar_login = tk.Button(
            botoes, text="🧪 Testar login", font=("Segoe UI", 9, "bold"),
            bg=BG, fg=WHITE, activebackground=TEAL_DARK, relief="flat",
            padx=10, pady=4, cursor="hand2", command=self._testar_login,
        )
        self.btn_testar_login.pack(side="left", padx=4)

        tk.Button(
            botoes, text="🗑 Remover", font=("Segoe UI", 9),
            bg=BG, fg=MUTED, activebackground="#3a1f1c", activeforeground=WHITE, relief="flat",
            padx=10, pady=4, cursor="hand2", command=self._remover_credenciais,
        ).pack(side="left", padx=4)

        self.cred_status_label = tk.Label(
            card, text="", font=("Segoe UI", 8, "italic"), fg=MUTED, bg=BG_CARD,
        )
        self.cred_status_label.grid(row=3, column=0, columnspan=5, sticky="w", padx=16, pady=(0, 10))

        # Pré-carrega credencial salva (se houver) — criptografada, local a este Windows/usuário.
        salva = cred_seguras.carregar_credenciais()
        if salva:
            usuario, senha = salva
            self.entry_usuario.insert(0, usuario)
            self.entry_senha.insert(0, senha)
            self._set_cred_status("Credencial salva carregada (criptografada nesta máquina).", MUTED)
        else:
            self._set_cred_status("Nenhuma credencial salva — o pipeline usará o arquivo .env.", MUTED)

    def _alternar_mostrar_senha(self):
        self.entry_senha.config(show="" if self.mostrar_senha_var.get() else "•")

    def _set_cred_status(self, texto, cor):
        self.cred_status_label.config(text=texto, fg=cor)

    def _salvar_credenciais(self):
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get().strip()
        if not usuario or not senha:
            self._set_cred_status("Preencha usuário e senha antes de salvar.", AMBER)
            return
        try:
            cred_seguras.salvar_credenciais(usuario, senha)
            self._set_cred_status("💾 Credenciais salvas com segurança (criptografadas nesta máquina).", GREEN)
        except Exception as e:
            self._set_cred_status(f"Erro ao salvar: {e}", RED)

    def _remover_credenciais(self):
        if not cred_seguras.existe_credencial_salva():
            self._set_cred_status("Não há credencial salva para remover.", MUTED)
            return
        if not messagebox.askyesno(
            "Remover credenciais",
            "Remover a credencial salva do Diaslog nesta máquina?\n"
            "O pipeline voltará a usar o arquivo .env.",
        ):
            return
        cred_seguras.remover_credenciais()
        self.entry_usuario.delete(0, "end")
        self.entry_senha.delete(0, "end")
        self._set_cred_status("Credenciais removidas — o pipeline usará o arquivo .env.", MUTED)

    def _testar_login(self):
        usuario = self.entry_usuario.get().strip()
        senha = self.entry_senha.get().strip()
        if not usuario or not senha:
            self._set_cred_status("Preencha usuário e senha antes de testar.", AMBER)
            return
        self.btn_testar_login.config(state="disabled")
        self._set_cred_status("🧪 Testando login no Diaslog...", AMBER)
        threading.Thread(target=self._testar_login_thread, args=(usuario, senha), daemon=True).start()

    def _testar_login_thread(self, usuario, senha):
        try:
            from automacao_diaslog import testar_login
            ok, msg = asyncio.run(testar_login(usuario, senha, headless=True))
        except Exception as e:
            ok, msg = False, f"Erro inesperado: {e}"
        self.after(0, self._testar_login_concluido, ok, msg)

    def _testar_login_concluido(self, ok, msg):
        self._set_cred_status(("✅ " if ok else "❌ ") + msg, GREEN if ok else RED)
        self.btn_testar_login.config(state="normal")

    # ------------------------------------------------------------------
    def _montar_opcoes(self):
        card = tk.Frame(self, bg=BG_CARD, highlightbackground=TEAL_DARK, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=8)

        pad = {"padx": 16, "pady": 8}

        # Modo do navegador
        self.headless_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(
            card,
            text="Rodar navegador em segundo plano (mais rápido — desmarque para acompanhar o login no Diaslog)",
            variable=self.headless_var,
            font=FONT_LABEL, fg=WHITE, bg=BG_CARD,
            activebackground=BG_CARD, activeforeground=WHITE,
            selectcolor=BG_CARD, anchor="w",
        )
        chk.grid(row=0, column=0, columnspan=2, sticky="w", **pad)

        # Período (filtro dos Top ofensores)
        tk.Label(
            card, text="Filtro de período — Top ofensores (opcional):",
            font=FONT_LABEL, fg=WHITE, bg=BG_CARD,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))

        tk.Label(card, text="Data inicial (dd/mm/aaaa):", font=FONT_LABEL, fg=MUTED, bg=BG_CARD)\
            .grid(row=2, column=0, sticky="w", padx=16, pady=4)
        self.entry_inicio = tk.Entry(card, font=FONT_LABEL, width=16, bg="white")
        self.entry_inicio.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=4)

        tk.Label(card, text="Data final (dd/mm/aaaa):", font=FONT_LABEL, fg=MUTED, bg=BG_CARD)\
            .grid(row=3, column=0, sticky="w", padx=16, pady=(4, 12))
        self.entry_fim = tk.Entry(card, font=FONT_LABEL, width=16, bg="white")
        self.entry_fim.grid(row=3, column=1, sticky="w", padx=(0, 16), pady=(4, 12))

        tk.Label(
            card,
            text="Deixe as duas datas em branco para considerar o histórico completo.",
            font=("Segoe UI", 8, "italic"), fg=MUTED, bg=BG_CARD,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))

    # ------------------------------------------------------------------
    def _montar_botoes(self):
        linha = tk.Frame(self, bg=BG)
        linha.pack(fill="x", padx=24, pady=8)

        self.btn_executar = tk.Button(
            linha, text="▶  Executar Pipeline", font=FONT_BTN,
            bg=TEAL, fg=BG, activebackground=TEAL_MID, activeforeground=WHITE,
            relief="flat", padx=18, pady=10, cursor="hand2",
            command=self._iniciar_execucao,
        )
        self.btn_executar.pack(side="left")

        self.btn_parar = tk.Button(
            linha, text="⏹  Parar", font=FONT_BTN,
            bg=RED, fg=WHITE, activebackground="#c94b40", activeforeground=WHITE,
            relief="flat", padx=14, pady=10, cursor="hand2", state="disabled",
            command=self._parar_execucao,
        )
        self.btn_parar.pack(side="left", padx=(10, 0))

        self.btn_pasta = tk.Button(
            linha, text="📂  Abrir pasta de saída", font=("Segoe UI", 10),
            bg=BG_CARD, fg=WHITE, activebackground=TEAL_DARK, activeforeground=WHITE,
            relief="flat", padx=14, pady=10, cursor="hand2",
            command=self._abrir_pasta_saida,
        )
        self.btn_pasta.pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    def _montar_status(self):
        barra = tk.Frame(self, bg=BG)
        barra.pack(fill="x", padx=24, pady=(4, 4))

        self.status_dot = tk.Label(barra, text="●", font=("Segoe UI", 12), fg=MUTED, bg=BG)
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(
            barra, text="Pronto para iniciar.", font=FONT_STATUS, fg=MUTED, bg=BG,
        )
        self.status_label.pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------------
    def _montar_log(self):
        moldura = tk.Frame(self, bg=BG)
        moldura.pack(fill="both", expand=True, padx=24, pady=(4, 20))

        self.log = scrolledtext.ScrolledText(
            moldura, bg=BG_LOG, fg="#D6EEF0", insertbackground=WHITE,
            font=FONT_LOG, wrap="word", state="disabled", relief="flat",
            padx=10, pady=8,
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("erro", foreground=RED)
        self.log.tag_config("ok", foreground=GREEN)

    # ------------------------------------------------------------------
    # Execução do pipeline
    # ------------------------------------------------------------------
    def _iniciar_execucao(self):
        if self.proc is not None:
            return  # já está rodando

        inicio = self.entry_inicio.get().strip()
        fim = self.entry_fim.get().strip()

        cmd = [self._python_console(), str(ROOT / "main.py"), "--auto"]
        if self.headless_var.get():
            cmd.append("--headless")
        if inicio:
            cmd += ["--data-inicio", inicio]
        if fim:
            cmd += ["--data-fim", fim]

        self._limpar_log()
        self._log_linha(f"Iniciando pipeline...  ({' '.join(cmd[1:])})\n")
        self._set_status("Executando...", AMBER)
        self.btn_executar.config(state="disabled")
        self.btn_parar.config(state="normal")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        # Se usuário/senha estiverem preenchidos no painel, usam-se estes (têm prioridade
        # sobre o .env — nunca gravados em disco em texto puro, só passados em memória
        # para o processo filho). Se os campos estiverem vazios, o automacao_diaslog.py
        # cai no comportamento de sempre (lê do .env compartilhado).
        usuario_cred = self.entry_usuario.get().strip()
        senha_cred = self.entry_senha.get().strip()
        if usuario_cred and senha_cred:
            env["DIASLOG_USUARIO"] = usuario_cred
            env["DIASLOG_SENHA"] = senha_cred

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(ROOT),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, creationflags=creationflags,
            )
        except Exception as e:
            self._log_linha(f"\nErro ao iniciar o processo: {e}\n", "erro")
            self._finalizar(sucesso=False)
            return

        threading.Thread(target=self._ler_saida, args=(self.proc,), daemon=True).start()
        self.after(80, self._drenar_fila)

    def _python_console(self) -> str:
        """Garante o uso do python.exe de console (não pythonw), para capturar a saída."""
        py = sys.executable
        if py.lower().endswith("pythonw.exe"):
            candidato = py[: -len("pythonw.exe")] + "python.exe"
            if os.path.exists(candidato):
                return candidato
        return py

    def _ler_saida(self, proc):
        try:
            for linha in proc.stdout:
                self.fila.put(("linha", linha))
        except Exception as e:
            self.fila.put(("linha", f"\n[Painel] Erro lendo saída: {e}\n"))
        finally:
            codigo = proc.wait()
            self.fila.put(("fim", codigo))

    def _drenar_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "linha":
                    tag = "erro" if ("❌" in valor or "Erro" in valor or "ERRO" in valor) else None
                    self._log_linha(valor, tag)
                elif tipo == "fim":
                    self._finalizar(sucesso=(valor == 0))
                    return
        except queue.Empty:
            pass
        if self.proc is not None:
            self.after(80, self._drenar_fila)

    def _parar_execucao(self):
        if self.proc is not None and self.proc.poll() is None:
            self._log_linha("\n[Painel] Interrompendo o processo...\n", "erro")
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _finalizar(self, sucesso: bool):
        if sucesso:
            self._set_status("Concluído com sucesso!", GREEN)
            self._log_linha("\n✅ Pipeline finalizado com sucesso.\n", "ok")
        else:
            self._set_status("Finalizado com erro — veja o log acima.", RED)
            self._log_linha("\n❌ Pipeline finalizado com erro.\n", "erro")
        self.proc = None
        self.btn_executar.config(state="normal")
        self.btn_parar.config(state="disabled")

    # ------------------------------------------------------------------
    # Utilidades de UI
    # ------------------------------------------------------------------
    def _set_status(self, texto, cor):
        self.status_dot.config(fg=cor)
        self.status_label.config(text=texto, fg=cor)

    def _limpar_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _log_linha(self, texto, tag=None):
        self.log.config(state="normal")
        self.log.insert("end", texto, tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _abrir_pasta_saida(self):
        pasta = ROOT / "outputs"
        pasta.mkdir(exist_ok=True)
        try:
            os.startfile(str(pasta))
        except Exception as e:
            self._log_linha(f"\nNão foi possível abrir a pasta: {e}\n", "erro")

    def _ao_fechar(self):
        if self.proc is not None and self.proc.poll() is None:
            self._parar_execucao()
        self.destroy()


if __name__ == "__main__":
    app = PainelExecucao()
    app.mainloop()
