"""
Armazenamento seguro de credenciais do Diaslog (TMS), usado pelo Painel de Execução.

Usa DPAPI do Windows (win32crypt.CryptProtectData/CryptUnprotectData) — a mesma
tecnologia usada pelo Chrome/Credential Manager para guardar senhas locais. O
arquivo criptografado só pode ser decifrado pelo MESMO usuário do Windows, NESTA
máquina. Copiado para outro PC ou outra conta, o conteúdo é inutilizável.

NÃO é um substituto do .env compartilhado entre as 3 máquinas do pipeline — é uma
conveniência local e opcional, só para quem usa o Painel de Execução gráfico.
Rodando `python main.py` direto no terminal, o comportamento antigo (ler o .env)
continua exatamente igual.
"""
from pathlib import Path

import win32crypt

ROOT = Path(__file__).resolve().parent
_ARQ_CRED = ROOT / "BASE2" / ".diaslog_cred.enc"
_DESCRICAO = "Diaslog TMS - Dias+ (Painel de Execucao)"


def salvar_credenciais(usuario: str, senha: str) -> None:
    """Criptografa e salva usuário/senha localmente (vinculado ao usuário do Windows)."""
    dados = f"{usuario}\n{senha}".encode("utf-8")
    criptografado = win32crypt.CryptProtectData(dados, _DESCRICAO, None, None, None, 0)
    _ARQ_CRED.parent.mkdir(parents=True, exist_ok=True)
    _ARQ_CRED.write_bytes(criptografado)


def carregar_credenciais() -> tuple[str, str] | None:
    """Retorna (usuario, senha) se houver credencial salva e decifrável; senão None."""
    if not _ARQ_CRED.exists():
        return None
    try:
        criptografado = _ARQ_CRED.read_bytes()
        _, dados = win32crypt.CryptUnprotectData(criptografado, None, None, None, 0)
        usuario, _, senha = dados.decode("utf-8").partition("\n")
        return usuario, senha
    except Exception:
        # Arquivo corrompido, ou criptografado por outro usuário/máquina — ignora.
        return None


def remover_credenciais() -> None:
    if _ARQ_CRED.exists():
        _ARQ_CRED.unlink()


def existe_credencial_salva() -> bool:
    return _ARQ_CRED.exists()
