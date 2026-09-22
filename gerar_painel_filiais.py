# -*- coding: utf-8 -*-
"""
Gera um PAINEL SEMANAL por FILIAL (HTML pronto pra imprimir, 1 página por filial)
apontando rotas e cidades ofensoras de Danos e Faltas — SEM nome de motorista/cliente
(apenas dados agregados: filial, rota, cidade/bairro, contagens). LGPD-safe.

Rodar:  py gerar_painel_filiais.py
Saída:  outputs/painel_semanal_filiais.html   (abrir no navegador e Ctrl+P)
"""
import html
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
TOP_N = 8  # quantas rotas/cidades por filial

_FILIAIS_DCX = {
    "DIAS MD MEGA RIO DE JANEIRO", "DIAS DCX BAIXADA FLUMINENSE",
    "DIAS DUQUE DE CAXIAS MEGA FILIAL",
}


def _norm(s):
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def _achar(nome: str):
    """ROOT/nome; senão o mais recente em outputs/<data>/nome."""
    p = ROOT / nome
    if p.exists():
        return p
    cand = sorted(ROOT.glob(f"outputs/*/{nome}"))
    return cand[-1] if cand else None


def _geo_maps():
    frames = []
    for nome in ("relatorionotas.csv", "relatorionotas_falta.csv"):
        p = _achar(nome)
        if not p:
            continue
        try:
            rn = pd.read_csv(p, sep=";", encoding="latin-1", skiprows=7, low_memory=False)
            rn.columns = [str(c).strip() for c in rn.columns]
            if "Pedido" in rn.columns and "Cidade" in rn.columns:
                frames.append(rn[["Pedido", "Cidade", "Bairro"]])
        except Exception:
            pass
    if not frames:
        return {}, {}
    ref = pd.concat(frames, ignore_index=True)
    ref["Pedido"] = _norm(ref["Pedido"])
    ref = ref[ref["Pedido"].ne("") & ref["Pedido"].ne("nan")]
    ref = ref.sort_values("Cidade", na_position="last").drop_duplicates("Pedido")
    return dict(zip(ref["Pedido"], ref["Cidade"])), dict(zip(ref["Pedido"], ref["Bairro"]))


def _carrega():
    mapa_cid, mapa_bai = _geo_maps()
    partes = []

    pd_danos = _achar("base_pronta.csv")
    if pd_danos:
        d = pd.read_csv(pd_danos, sep=";", encoding="latin-1", low_memory=False)
        d.columns = [c.replace("﻿", "").replace("ï»¿", "").strip().lower() for c in d.columns]
        partes.append(pd.DataFrame({
            "Filial": d["filial"].astype(str).str.strip(),
            "Rota": _norm(d["id_rota"]),
            "Pedido": _norm(d["pedido"]),
            "Qtd": pd.to_numeric(d["qtd_reclamada"], errors="coerce").fillna(0),
            "Data": pd.to_datetime(d.iloc[:, 0], dayfirst=True, format="mixed", errors="coerce"),
            "Tipo": "Dano",
        }))

    pf = _achar("base_falta_pronta.csv")
    if pf:
        f = pd.read_csv(pf, sep=";", encoding="latin-1", low_memory=False)
        f.columns = [c.replace("﻿", "").replace("ï»¿", "").strip().lower() for c in f.columns]
        partes.append(pd.DataFrame({
            "Filial": f["filial"].astype(str).str.strip(),
            "Rota": _norm(f["rota"]),
            "Pedido": _norm(f["nm_pedido"]),
            "Qtd": pd.to_numeric(f["cantidad_itens"], errors="coerce").fillna(0),
            "Data": pd.to_datetime(f.iloc[:, 0], dayfirst=True, format="mixed", errors="coerce"),
            "Tipo": "Falta",
        }))

    uni = pd.concat(partes, ignore_index=True).dropna(subset=["Data"])
    uni["Filial"] = uni["Filial"].where(~uni["Filial"].isin(_FILIAIS_DCX), "DIAS DUQUE DE CAXIAS")
    uni["Cidade"] = uni["Pedido"].map(mapa_cid).fillna("Não Identificada")
    uni["Bairro"] = uni["Pedido"].map(mapa_bai).fillna("—")
    return uni


def _resumo(df, chave):
    """Agrega por chave: ocorrências e itens de Dano e Falta + total; ordena pelos piores."""
    g = df.groupby([chave, "Tipo"]).agg(oc=("Qtd", "size"), it=("Qtd", "sum")).reset_index()
    piv = g.pivot_table(index=chave, columns="Tipo", values=["oc", "it"], fill_value=0)
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    for c in ("oc_Dano", "it_Dano", "oc_Falta", "it_Falta"):
        if c not in piv.columns:
            piv[c] = 0
    piv["tot_it"] = piv["it_Dano"] + piv["it_Falta"]
    piv["tot_oc"] = piv["oc_Dano"] + piv["oc_Falta"]
    return piv.sort_values("tot_it", ascending=False).reset_index()


CSS = """
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; color:#0B2E3A; margin:0; background:#fff; }
.filial { padding: 10mm 8mm; page-break-after: always; }
.filial:last-child { page-break-after: auto; }
.hdr { display:flex; justify-content:space-between; align-items:flex-end; border-bottom:3px solid #1A8090; padding-bottom:6px; margin-bottom:10px; }
.hdr h1 { font-size:20px; margin:0; color:#1A5A68; text-transform:uppercase; }
.hdr .sub { font-size:12px; color:#555; }
.marca { font-size:22px; font-weight:900; color:#2DC5B4; }
.kpis { display:flex; gap:10px; margin:10px 0 14px; }
.kpi { flex:1; border:1px solid #ddd; border-radius:6px; padding:8px 10px; }
.kpi .lab { font-size:11px; color:#666; text-transform:uppercase; }
.kpi .val { font-size:22px; font-weight:800; }
.kpi.dano .val { color:#1A8090; }
.kpi.falta .val { color:#C0392B; }
.kpi .det { font-size:11px; color:#888; }
h2 { font-size:13px; color:#1A5A68; margin:14px 0 4px; text-transform:uppercase; }
table { width:100%; border-collapse:collapse; font-size:11px; }
th, td { border:1px solid #ccc; padding:4px 6px; text-align:center; }
th { background:#EAF4F5; color:#1A5A68; }
td.l, th.l { text-align:left; }
tr:nth-child(even) td { background:#fafafa; }
.tot { font-weight:800; background:#f1f8f8; }
.foot { font-size:10px; color:#999; margin-top:10px; }
@page { size:A4 portrait; margin:8mm; }
"""


def _tabela(piv, rotulo_chave, mostrar_cidade):
    linhas = []
    cab_cidade = "<th class='l'>Cidade / Bairro</th>" if mostrar_cidade else ""
    linhas.append(
        "<table><thead><tr>"
        f"<th class='l'>{rotulo_chave}</th>{cab_cidade}"
        "<th>Danos<br>ocorr.</th><th>Danos<br>itens</th>"
        "<th>Faltas<br>ocorr.</th><th>Faltas<br>itens</th>"
        "<th>Total<br>itens</th></tr></thead><tbody>"
    )
    for _, r in piv.head(TOP_N).iterrows():
        chave_val = html.escape(str(r.iloc[0]))
        cidade_td = ""
        if mostrar_cidade:
            cidade_td = f"<td class='l'>{html.escape(str(r.get('cidade_bairro', '')))}</td>"
        linhas.append(
            f"<tr><td class='l'>{chave_val}</td>{cidade_td}"
            f"<td>{int(r['oc_Dano'])}</td><td>{int(r['it_Dano'])}</td>"
            f"<td>{int(r['oc_Falta'])}</td><td>{int(r['it_Falta'])}</td>"
            f"<td class='tot'>{int(r['tot_it'])}</td></tr>"
        )
    linhas.append("</tbody></table>")
    return "".join(linhas)


def gerar():
    uni = _carrega()
    ultima = uni["Data"].max()
    ini = (ultima - pd.Timedelta(days=int(ultima.weekday()))).normalize()
    fim = ini + pd.Timedelta(days=6, hours=23, minutes=59, seconds=59)
    semana = uni[(uni["Data"] >= ini) & (uni["Data"] <= fim)]
    periodo = f"{ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"

    paginas = []
    for filial in sorted(semana["Filial"].dropna().unique()):
        sub = semana[semana["Filial"] == filial]
        if sub.empty:
            continue
        d_oc = int((sub["Tipo"] == "Dano").sum()); d_it = int(sub[sub["Tipo"] == "Dano"]["Qtd"].sum())
        f_oc = int((sub["Tipo"] == "Falta").sum()); f_it = int(sub[sub["Tipo"] == "Falta"]["Qtd"].sum())

        # Rotas (com cidade principal de cada rota)
        piv_rota = _resumo(sub, "Rota")
        cid_por_rota = sub.groupby("Rota").agg(
            cidade_bairro=("Cidade", lambda x: x.mode().iloc[0] if not x.mode().empty else "—")).reset_index()
        piv_rota = piv_rota.merge(cid_por_rota, on="Rota", how="left")

        piv_cid = _resumo(sub, "Cidade")

        paginas.append(f"""
        <section class="filial">
          <div class="hdr">
            <div><h1>{html.escape(str(filial))}</h1>
                 <div class="sub">Painel semanal de ocorrências · {periodo}</div></div>
            <div class="marca">Dias+</div>
          </div>
          <div class="kpis">
            <div class="kpi dano"><div class="lab">Danos</div><div class="val">{d_it}</div>
                 <div class="det">itens · {d_oc} ocorrências</div></div>
            <div class="kpi falta"><div class="lab">Faltas</div><div class="val">{f_it}</div>
                 <div class="det">itens · {f_oc} ocorrências</div></div>
            <div class="kpi"><div class="lab">Total itens</div><div class="val">{d_it + f_it}</div>
                 <div class="det">{d_oc + f_oc} ocorrências</div></div>
          </div>
          <h2>Top rotas ofensoras</h2>
          {_tabela(piv_rota, "Rota", mostrar_cidade=True)}
          <h2>Top cidades ofensoras</h2>
          {_tabela(piv_cid, "Cidade", mostrar_cidade=False)}
          <div class="foot">Gerado em {date.today().strftime('%d/%m/%Y')} · dados agregados (sem identificação de motorista/cliente) · Dias+ / Natura</div>
        </section>""")

    doc = f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>" \
          f"<title>Painel Semanal por Filial — {periodo}</title><style>{CSS}</style></head>" \
          f"<body>{''.join(paginas)}</body></html>"

    saida = ROOT / "outputs" / "painel_semanal_filiais.html"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(doc, encoding="utf-8")
    print(f"Painel gerado: {saida}")
    print(f"   Semana: {periodo} | {len(paginas)} filiais | abra no navegador e Ctrl+P")


if __name__ == "__main__":
    gerar()
