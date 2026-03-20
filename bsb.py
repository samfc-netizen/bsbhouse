import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(page_title="DRE Imobiliária", layout="wide")

# =========================
# LOGIN
# =========================
USUARIO_CORRETO = "bsbhouse"
SENHA_CORRETA = "House10"

if "logado" not in st.session_state:
    st.session_state["logado"] = False


def tela_login():
    st.title("Login - BSB House")
    st.caption("Informe usuário e senha para acessar o dashboard.")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar", use_container_width=True):
        if usuario == USUARIO_CORRETO and senha == SENHA_CORRETA:
            st.session_state["logado"] = True
            st.session_state["usuario"] = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos.")


if not st.session_state["logado"]:
    tela_login()
    st.stop()


ARQUIVO_PADRAO = "BSB IMOBILIARIA.xlsx"

MESES_PT = {
    1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ"
}

MESES_ORDENADOS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

DRE_ROWS = [
    "RECEITA",
    "Impostos/deduções",
    "Despesas Administrativas",
    "Despesas Comerciais",
    "Despesas com Marketing",
    "Despesas Financeiras",
    "Retiradas",
    "Despesas Fazenda da Matta",
    "Despesas Mandarim",
    "Resultado antes das retiradas",
    "Resultado Caixa",
]


def normalizar_texto(s):
    if pd.isna(s):
        return ""
    return str(s).strip()


def parse_moeda_ou_numero(valor):
    if pd.isna(valor):
        return 0.0

    if isinstance(valor, (int, float, np.number)):
        return float(valor)

    txt = str(valor).strip()
    if txt == "":
        return 0.0

    txt = txt.replace("R$", "").replace(" ", "")
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")

    try:
        return float(txt)
    except Exception:
        return 0.0


def parse_data_robusta(serie):
    return pd.to_datetime(serie, errors="coerce", dayfirst=True)


def formatar_brl(x):
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_perc(x):
    if pd.isna(x):
        return ""
    return f"{x:.1f}%"


def montar_chave_texto(df):
    partes = []
    for col in ["Nome do fornecedor", "Descrição", "Observações"]:
        if col in df.columns:
            partes.append(df[col].fillna("").astype(str))
        else:
            partes.append(pd.Series([""] * len(df), index=df.index))
    return (partes[0] + " " + partes[1] + " " + partes[2]).str.lower()


def aplicar_filtro_ano_mes(df, ano=None, mes=None):
    df = df.copy()
    if ano is not None:
        df = df[df["DATA_REF"].dt.year == ano]
    if mes is not None:
        df = df[df["DATA_REF"].dt.month == mes]
    return df


@st.cache_data
def carregar_planilha(caminho_arquivo):
    base = pd.read_excel(caminho_arquivo, sheet_name="BASE DE DADOS")
    receitas = pd.read_excel(caminho_arquivo, sheet_name="RECEITAS")
    contas_resultado = pd.read_excel(caminho_arquivo, sheet_name="BASE CONTAS DE RESULTADO", header=None)

    base.columns = [str(c).strip() for c in base.columns]
    receitas.columns = [str(c).strip() for c in receitas.columns]

    contas_resultado.columns = ["Categoria 1", "Grupo Resultado"]
    contas_resultado["Categoria 1"] = contas_resultado["Categoria 1"].astype(str).str.strip()
    contas_resultado["Grupo Resultado"] = contas_resultado["Grupo Resultado"].astype(str).str.strip()

    mapa_categoria_grupo = dict(zip(
        contas_resultado["Categoria 1"],
        contas_resultado["Grupo Resultado"]
    ))

    if "Data prevista" not in base.columns:
        raise ValueError("A coluna 'Data prevista' não foi encontrada na aba BASE DE DADOS.")
    if "Data prevista" not in receitas.columns:
        raise ValueError("A coluna 'Data prevista' não foi encontrada na aba RECEITAS.")

    base["DATA_REF"] = parse_data_robusta(base["Data prevista"])
    receitas["DATA_REF"] = parse_data_robusta(receitas["Data prevista"])

    base["VALOR_CAT"] = base["Valor na Categoria 1"].apply(parse_moeda_ou_numero).abs()
    receitas["VALOR_CAT"] = receitas["Valor na Categoria 1"].apply(parse_moeda_ou_numero)

    for col in ["Categoria 1", "Centro de Custo 1", "Observações", "Descrição"]:
        if col not in base.columns:
            base[col] = ""
        if col not in receitas.columns:
            receitas[col] = ""

    if "Nome do fornecedor" not in base.columns:
        base["Nome do fornecedor"] = ""
    if "Nome do cliente" not in receitas.columns:
        receitas["Nome do cliente"] = ""

    base["Categoria 1"] = base["Categoria 1"].apply(normalizar_texto)
    base["Centro de Custo 1"] = base["Centro de Custo 1"].apply(normalizar_texto)
    receitas["Categoria 1"] = receitas["Categoria 1"].apply(normalizar_texto)
    receitas["Centro de Custo 1"] = receitas["Centro de Custo 1"].apply(normalizar_texto)

    base["Grupo Resultado"] = base["Categoria 1"].map(mapa_categoria_grupo).fillna("NÃO CLASSIFICADO")

    texto_base = montar_chave_texto(base)
    base["FLAG_MANDARIM"] = texto_base.str.contains(r"\bmandarim\b", regex=True, na=False)
    base["FLAG_FAZENDA"] = texto_base.str.contains(r"fazenda da matta|f\. da matta|f da matta|da matta", regex=True, na=False)

    receitas["FLAG_RECEITA_VALIDA"] = (
        receitas["Categoria 1"]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.contains(r"receitas? de servi", regex=True, na=False)
    )

    return base, receitas


def preparar_mes_ano(df):
    df = df.copy()
    df["ANO"] = df["DATA_REF"].dt.year
    df["MES"] = df["DATA_REF"].dt.month
    return df


def gerar_colunas_mes_percentual(meses_ordenados):
    colunas = []
    for ano, mes in meses_ordenados:
        rot = f"{MESES_PT[mes]}/{str(ano)[-2:]}"
        colunas.append((ano, mes, rot))
    return colunas


def montar_dre_mensal(base_f, receitas_f):
    base_f = preparar_mes_ano(base_f)
    receitas_f = preparar_mes_ano(receitas_f)

    meses_base = set(zip(base_f["ANO"], base_f["MES"]))
    meses_rec = set(zip(receitas_f["ANO"], receitas_f["MES"]))
    meses_ordenados = sorted(meses_base.union(meses_rec))
    colunas_mes = gerar_colunas_mes_percentual(meses_ordenados)

    base_generica = base_f[~base_f["FLAG_MANDARIM"] & ~base_f["FLAG_FAZENDA"]].copy()

    grupo_mes = (
        base_generica.groupby(["Grupo Resultado", "ANO", "MES"], dropna=False)["VALOR_CAT"]
        .sum()
        .reset_index()
    )

    padrao_financeiro = re.compile(r"juros|iof|tarifa|encargo|multa|cart[aã]o|banco|financeir", re.IGNORECASE)
    base_fin = base_generica[
        base_generica["Categoria 1"].fillna("").str.contains(padrao_financeiro, na=False)
    ].copy()

    fin_mes = (
        base_fin.groupby(["ANO", "MES"])["VALOR_CAT"]
        .sum()
        .reset_index()
        .assign(LINHA_DRE="Despesas Financeiras")
    )

    imp_mes = grupo_mes[grupo_mes["Grupo Resultado"].eq("Impostos/ deduções")].copy()
    imp_mes["LINHA_DRE"] = "Impostos/deduções"

    adm_mes = grupo_mes[grupo_mes["Grupo Resultado"].eq("Despesas Admnistrativas")].copy()
    adm_mes["LINHA_DRE"] = "Despesas Administrativas"

    com_mes = grupo_mes[grupo_mes["Grupo Resultado"].eq("Despesas comerciais")].copy()
    com_mes["LINHA_DRE"] = "Despesas Comerciais"

    mkt_mes = grupo_mes[grupo_mes["Grupo Resultado"].eq("Marketing")].copy()
    mkt_mes["LINHA_DRE"] = "Despesas com Marketing"

    ret_mes = grupo_mes[grupo_mes["Grupo Resultado"].eq("Retiradas")].copy()
    ret_mes["LINHA_DRE"] = "Retiradas"

    faz_mes = (
        base_f[base_f["FLAG_FAZENDA"]]
        .groupby(["ANO", "MES"])["VALOR_CAT"]
        .sum()
        .reset_index()
        .assign(LINHA_DRE="Despesas Fazenda da Matta")
    )

    man_mes = (
        base_f[base_f["FLAG_MANDARIM"]]
        .groupby(["ANO", "MES"])["VALOR_CAT"]
        .sum()
        .reset_index()
        .assign(LINHA_DRE="Despesas Mandarim")
    )

    receita_valida = receitas_f[receitas_f["FLAG_RECEITA_VALIDA"]].copy()
    rec_mes = (
        receita_valida.groupby(["ANO", "MES"])["VALOR_CAT"]
        .sum()
        .reset_index()
        .assign(LINHA_DRE="RECEITA")
    )

    blocos = []
    for df_temp in [rec_mes, imp_mes, adm_mes, com_mes, mkt_mes, fin_mes, ret_mes, faz_mes, man_mes]:
        if not df_temp.empty and "LINHA_DRE" in df_temp.columns:
            blocos.append(df_temp[["LINHA_DRE", "ANO", "MES", "VALOR_CAT"]])

    if blocos:
        dre_base = pd.concat(blocos, ignore_index=True)
    else:
        dre_base = pd.DataFrame(columns=["LINHA_DRE", "ANO", "MES", "VALOR_CAT"])

    if dre_base.empty:
        tabela_vazia = pd.DataFrame({"LINHA": DRE_ROWS})
        return tabela_vazia

    pivot = dre_base.pivot_table(
        index="LINHA_DRE",
        columns=["ANO", "MES"],
        values="VALOR_CAT",
        aggfunc="sum",
        fill_value=0.0
    )

    for row in DRE_ROWS:
        if row not in pivot.index:
            pivot.loc[row] = 0.0

    for ano, mes in meses_ordenados:
        if (ano, mes) not in pivot.columns:
            pivot[(ano, mes)] = 0.0

    pivot = pivot.sort_index().sort_index(axis=1)

    for ano, mes in meses_ordenados:
        receita = pivot.loc["RECEITA", (ano, mes)]

        despesas_total = (
            pivot.loc["Impostos/deduções", (ano, mes)]
            + pivot.loc["Despesas Administrativas", (ano, mes)]
            + pivot.loc["Despesas Comerciais", (ano, mes)]
            + pivot.loc["Despesas com Marketing", (ano, mes)]
            + pivot.loc["Despesas Financeiras", (ano, mes)]
            + pivot.loc["Retiradas", (ano, mes)]
            + pivot.loc["Despesas Fazenda da Matta", (ano, mes)]
            + pivot.loc["Despesas Mandarim", (ano, mes)]
        )

        resultado_caixa = receita - despesas_total
        resultado_antes = resultado_caixa + pivot.loc["Retiradas", (ano, mes)]

        pivot.loc["Resultado Caixa", (ano, mes)] = resultado_caixa
        pivot.loc["Resultado antes das retiradas", (ano, mes)] = resultado_antes

    pivot = pivot.loc[DRE_ROWS]

    tabela = pd.DataFrame(index=DRE_ROWS)

    for ano, mes, rot in colunas_mes:
        val_col = (ano, mes)
        perc_col = f"{rot}%"

        tabela[rot] = pivot[val_col].values

        perc_vals = []
        receita_mes = pivot.loc["RECEITA", val_col]

        for linha in DRE_ROWS:
            valor_linha = pivot.loc[linha, val_col]
            if linha == "RECEITA":
                perc = 100.0 if receita_mes != 0 else np.nan
            else:
                perc = (valor_linha / receita_mes * 100.0) if receita_mes != 0 else np.nan
            perc_vals.append(perc)

        tabela[perc_col] = perc_vals

    tabela = tabela.reset_index().rename(columns={"index": "LINHA"})
    return tabela


def estilizar_dre(df):
    df_fmt = df.copy()
    for col in df_fmt.columns:
        if col == "LINHA":
            continue
        if str(col).endswith("%"):
            df_fmt[col] = df_fmt[col].apply(formatar_perc)
        else:
            df_fmt[col] = df_fmt[col].apply(formatar_brl)
    return df_fmt


def obter_dataframe_drill(base_f, receitas_f, linha_selecionada):
    receitas_validas = receitas_f[receitas_f["FLAG_RECEITA_VALIDA"]].copy()

    if linha_selecionada == "RECEITA":
        df = (
            receitas_validas.groupby("Centro de Custo 1", dropna=False)["VALOR_CAT"]
            .sum()
            .reset_index()
            .rename(columns={"Centro de Custo 1": "DETALHE", "VALOR_CAT": "VALOR"})
            .sort_values("VALOR", ascending=False)
        )
        total_linha = df["VALOR"].sum()
        receita_total = total_linha
        df["% da linha"] = np.where(total_linha != 0, df["VALOR"] / total_linha * 100, np.nan)
        df["% da receita"] = np.where(receita_total != 0, df["VALOR"] / receita_total * 100, np.nan)
        return df, total_linha, receita_total

    base_generica = base_f[~base_f["FLAG_MANDARIM"] & ~base_f["FLAG_FAZENDA"]].copy()

    if linha_selecionada == "Impostos/deduções":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Impostos/ deduções"].copy()
    elif linha_selecionada == "Despesas Administrativas":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Despesas Admnistrativas"].copy()
    elif linha_selecionada == "Despesas Comerciais":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Despesas comerciais"].copy()
    elif linha_selecionada == "Despesas com Marketing":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Marketing"].copy()
    elif linha_selecionada == "Despesas Financeiras":
        padrao_financeiro = re.compile(r"juros|iof|tarifa|encargo|multa|cart[aã]o|banco|financeir", re.IGNORECASE)
        df_src = base_generica[
            base_generica["Categoria 1"].fillna("").str.contains(padrao_financeiro, na=False)
        ].copy()
    elif linha_selecionada == "Retiradas":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Retiradas"].copy()
    elif linha_selecionada == "Despesas Fazenda da Matta":
        df_src = base_f[base_f["FLAG_FAZENDA"]].copy()
    elif linha_selecionada == "Despesas Mandarim":
        df_src = base_f[base_f["FLAG_MANDARIM"]].copy()
    else:
        df_src = pd.DataFrame(columns=base_f.columns)

    receita_total = receitas_validas["VALOR_CAT"].sum()

    if df_src.empty:
        return pd.DataFrame(columns=["DETALHE", "VALOR", "% da linha", "% da receita"]), 0.0, receita_total

    df = (
        df_src.groupby("Categoria 1", dropna=False)["VALOR_CAT"]
        .sum()
        .reset_index()
        .rename(columns={"Categoria 1": "DETALHE", "VALOR_CAT": "VALOR"})
        .sort_values("VALOR", ascending=False)
    )

    total_linha = df["VALOR"].sum()
    df["% da linha"] = np.where(total_linha != 0, df["VALOR"] / total_linha * 100, np.nan)
    df["% da receita"] = np.where(receita_total != 0, df["VALOR"] / receita_total * 100, np.nan)

    return df, total_linha, receita_total


def obter_historicos(base_f, receitas_f, linha_selecionada):
    if linha_selecionada == "RECEITA":
        df_src = receitas_f[receitas_f["FLAG_RECEITA_VALIDA"]].copy()

        hist_sint = (
            df_src.groupby("Categoria 1", dropna=False)["VALOR_CAT"]
            .sum()
            .reset_index()
            .rename(columns={"Categoria 1": "Categoria", "VALOR_CAT": "Valor"})
            .sort_values("Valor", ascending=False)
        )

        hist_det = df_src[[
            "DATA_REF", "Nome do cliente", "Descrição", "Observações",
            "Categoria 1", "Centro de Custo 1", "VALOR_CAT"
        ]].copy()

        hist_det = hist_det.rename(columns={
            "DATA_REF": "Data",
            "Nome do cliente": "Cliente",
            "Categoria 1": "Categoria",
            "Centro de Custo 1": "Centro de Custo",
            "VALOR_CAT": "Valor"
        }).sort_values(["Data", "Valor"], ascending=[False, False])

        return hist_sint, hist_det

    base_generica = base_f[~base_f["FLAG_MANDARIM"] & ~base_f["FLAG_FAZENDA"]].copy()

    if linha_selecionada == "Impostos/deduções":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Impostos/ deduções"].copy()
    elif linha_selecionada == "Despesas Administrativas":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Despesas Admnistrativas"].copy()
    elif linha_selecionada == "Despesas Comerciais":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Despesas comerciais"].copy()
    elif linha_selecionada == "Despesas com Marketing":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Marketing"].copy()
    elif linha_selecionada == "Despesas Financeiras":
        padrao_financeiro = re.compile(r"juros|iof|tarifa|encargo|multa|cart[aã]o|banco|financeir", re.IGNORECASE)
        df_src = base_generica[
            base_generica["Categoria 1"].fillna("").str.contains(padrao_financeiro, na=False)
        ].copy()
    elif linha_selecionada == "Retiradas":
        df_src = base_generica[base_generica["Grupo Resultado"] == "Retiradas"].copy()
    elif linha_selecionada == "Despesas Fazenda da Matta":
        df_src = base_f[base_f["FLAG_FAZENDA"]].copy()
    elif linha_selecionada == "Despesas Mandarim":
        df_src = base_f[base_f["FLAG_MANDARIM"]].copy()
    else:
        df_src = pd.DataFrame(columns=base_f.columns)

    hist_sint = (
        df_src.groupby("Categoria 1", dropna=False)["VALOR_CAT"]
        .sum()
        .reset_index()
        .rename(columns={"Categoria 1": "Categoria", "VALOR_CAT": "Valor"})
        .sort_values("Valor", ascending=False)
    )

    hist_det = df_src[[
        "DATA_REF", "Nome do fornecedor", "Descrição", "Observações",
        "Categoria 1", "VALOR_CAT"
    ]].copy()

    hist_det = hist_det.rename(columns={
        "DATA_REF": "Data",
        "Nome do fornecedor": "Fornecedor",
        "Categoria 1": "Categoria",
        "VALOR_CAT": "Valor"
    }).sort_values(["Data", "Valor"], ascending=[False, False])

    return hist_sint, hist_det


st.sidebar.title("Filtros")
st.sidebar.success(f"Logado como: {st.session_state.get('usuario', 'bsbhouse')}")

if st.sidebar.button("Sair"):
    st.session_state["logado"] = False
    st.session_state.pop("usuario", None)
    st.rerun()

arquivo_upload = st.sidebar.file_uploader("Selecione a planilha Excel", type=["xlsx"])
caminho_arquivo = arquivo_upload if arquivo_upload is not None else ARQUIVO_PADRAO

if not Path(ARQUIVO_PADRAO).exists() and arquivo_upload is None:
    st.error(f"Arquivo padrão '{ARQUIVO_PADRAO}' não encontrado. Faça upload da planilha.")
    st.stop()

try:
    base, receitas = carregar_planilha(caminho_arquivo)
except Exception as e:
    st.error(f"Erro ao ler a planilha: {e}")
    st.stop()

datas_base = base["DATA_REF"].dropna()
datas_rec = receitas["DATA_REF"].dropna()

if datas_base.empty and datas_rec.empty:
    st.error("Não foram encontradas datas válidas nas abas BASE DE DADOS e RECEITAS.")
    st.stop()

anos_disponiveis = sorted(
    set(datas_base.dt.year.dropna().astype(int).tolist()) |
    set(datas_rec.dt.year.dropna().astype(int).tolist())
)

if not anos_disponiveis:
    st.error("Não foi possível identificar anos válidos para filtro.")
    st.stop()

ano_escolhido = st.sidebar.selectbox("Ano", anos_disponiveis, index=len(anos_disponiveis) - 1)

mes_opcoes = ["Todos"] + [MESES_PT[m] for m in MESES_ORDENADOS]
mes_escolhido_txt = st.sidebar.selectbox("Mês", mes_opcoes, index=0)

mes_escolhido = None
if mes_escolhido_txt != "Todos":
    mes_escolhido = {v: k for k, v in MESES_PT.items()}[mes_escolhido_txt]

base_f = aplicar_filtro_ano_mes(base, ano=ano_escolhido, mes=mes_escolhido)
receitas_f = aplicar_filtro_ano_mes(receitas, ano=ano_escolhido, mes=mes_escolhido)

st.title("DRE Gerencial - Imobiliária")
st.caption("Filtros por ano e mês baseados em 'Data prevista'.")

dre_df = montar_dre_mensal(base_f, receitas_f)

st.subheader("Tabela DRE")
if len(dre_df.columns) > 1:
    st.dataframe(estilizar_dre(dre_df), use_container_width=True, hide_index=True)
else:
    st.info("Sem dados para a DRE no filtro selecionado.")

st.subheader("Drill da DRE")

linhas_disponiveis_drill = [
    "RECEITA",
    "Impostos/deduções",
    "Despesas Administrativas",
    "Despesas Comerciais",
    "Despesas com Marketing",
    "Despesas Financeiras",
    "Retiradas",
    "Despesas Fazenda da Matta",
    "Despesas Mandarim",
]

colf1, colf2 = st.columns([2, 1])

with colf1:
    linha_escolhida = st.selectbox(
        "Selecione a linha para detalhamento",
        options=linhas_disponiveis_drill,
        index=0
    )

with colf2:
    mes_drill_txt = st.selectbox(
        "Mês do drill",
        options=mes_opcoes,
        index=0
    )

mes_drill = None
if mes_drill_txt != "Todos":
    mes_drill = {v: k for k, v in MESES_PT.items()}[mes_drill_txt]

base_drill = aplicar_filtro_ano_mes(base, ano=ano_escolhido, mes=mes_drill)
receitas_drill = aplicar_filtro_ano_mes(receitas, ano=ano_escolhido, mes=mes_drill)

drill_df, total_linha, receita_total = obter_dataframe_drill(base_drill, receitas_drill, linha_escolhida)
perc_linha_receita = (total_linha / receita_total * 100.0) if receita_total != 0 else np.nan

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Linha selecionada", linha_escolhida)
with c2:
    st.metric("Total da linha", formatar_brl(total_linha), formatar_perc(perc_linha_receita))
with c3:
    st.metric("Receita no drill", formatar_brl(receita_total), "100,0%")

st.markdown("### Detalhamento do drill")
if not drill_df.empty:
    drill_exib = drill_df.copy()
    drill_exib["VALOR"] = drill_exib["VALOR"].apply(formatar_brl)
    drill_exib["% da linha"] = drill_exib["% da linha"].apply(formatar_perc)
    drill_exib["% da receita"] = drill_exib["% da receita"].apply(formatar_perc)
    st.dataframe(drill_exib, use_container_width=True, hide_index=True)
else:
    st.info("Sem dados para o drill no filtro selecionado.")

st.markdown("### Gráfico de representatividade")
if not drill_df.empty:
    graf_df = drill_df.copy().sort_values("VALOR", ascending=False)

    titulo_periodo = f"{mes_drill_txt}/{ano_escolhido}" if mes_drill_txt != "Todos" else f"Todos os meses de {ano_escolhido}"

    titulo_graf = (
        f"Representatividade do Centro de Custo na Receita - {titulo_periodo}"
        if linha_escolhida == "RECEITA"
        else f"Representatividade das Categorias em {linha_escolhida} - {titulo_periodo}"
    )

    fig = px.bar(
        graf_df,
        x="DETALHE",
        y="VALOR",
        text="% da linha",
        title=titulo_graf
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(xaxis_title="Detalhe", yaxis_title="Valor", height=500)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados para o gráfico.")

st.subheader("Históricos")

hist_sint, hist_det = obter_historicos(base_drill, receitas_drill, linha_escolhida)

with st.expander("Abrir histórico sintetizado", expanded=False):
    if not hist_sint.empty:
        hist_sint_exib = hist_sint.copy()
        hist_sint_exib["Categoria"] = hist_sint_exib["Categoria"].replace("", "(sem categoria)")
        hist_sint_exib["Valor"] = hist_sint_exib["Valor"].apply(formatar_brl)
        st.dataframe(hist_sint_exib, use_container_width=True, hide_index=True)

        categorias_hist = hist_sint["Categoria"].fillna("").replace("", "(sem categoria)").tolist()
        categoria_escolhida_hist = st.selectbox(
            "Selecione a categoria do histórico",
            options=categorias_hist,
            index=0,
            key="categoria_hist_select"
        )

        categoria_filtro_real = "" if categoria_escolhida_hist == "(sem categoria)" else categoria_escolhida_hist

        hist_det_filtrado = hist_det.copy()
        hist_det_filtrado["Categoria"] = hist_det_filtrado["Categoria"].fillna("").astype(str)

        hist_det_filtrado = hist_det_filtrado[
            hist_det_filtrado["Categoria"] == categoria_filtro_real
        ].copy()

        st.markdown("#### Drill do histórico por categoria")
        if not hist_det_filtrado.empty:
            hist_det_filtrado_exib = hist_det_filtrado.copy()
            hist_det_filtrado_exib["Data"] = pd.to_datetime(
                hist_det_filtrado_exib["Data"], errors="coerce"
            ).dt.strftime("%d/%m/%Y")
            hist_det_filtrado_exib["Valor"] = hist_det_filtrado_exib["Valor"].apply(formatar_brl)
            st.dataframe(hist_det_filtrado_exib, use_container_width=True, hide_index=True)
        else:
            st.info("Sem lançamentos para a categoria selecionada.")
    else:
        st.info("Sem histórico sintetizado.")

with st.expander("Abrir histórico detalhado completo", expanded=False):
    if not hist_det.empty:
        hist_det_exib = hist_det.copy()
        hist_det_exib["Data"] = pd.to_datetime(hist_det_exib["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
        hist_det_exib["Valor"] = hist_det_exib["Valor"].apply(formatar_brl)
        st.dataframe(hist_det_exib, use_container_width=True, hide_index=True)
    else:
        st.info("Sem histórico detalhado.")