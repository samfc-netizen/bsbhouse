import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="DRE Imobiliária", layout="wide")

# =========================
# 🔐 LOGIN
# =========================

USUARIO_CORRETO = "bsbhouse"
SENHA_CORRETA = "House10"

if "logado" not in st.session_state:
    st.session_state["logado"] = False

def tela_login():
    st.title("🔐 Login - BSB House")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if usuario == USUARIO_CORRETO and senha == SENHA_CORRETA:
            st.session_state["logado"] = True
            st.success("Login realizado com sucesso!")
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")

if not st.session_state["logado"]:
    tela_login()
    st.stop()

# botão logout
st.sidebar.button("Sair", on_click=lambda: st.session_state.update({"logado": False}))

# =========================
# 🔽 SEU CÓDIGO ORIGINAL
# =========================

ARQUIVO_PADRAO = "BSB IMOBILIARIA.xlsx"

MESES_PT = {
    1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ"
}

MESES_ORDENADOS = [1,2,3,4,5,6,7,8,9,10,11,12]

DRE_ROWS = [
    "RECEITA","Impostos/deduções","Despesas Administrativas",
    "Despesas Comerciais","Despesas com Marketing",
    "Despesas Financeiras","Retiradas",
    "Despesas Fazenda da Matta","Despesas Mandarim",
    "Resultado antes das retiradas","Resultado Caixa",
]

def normalizar_texto(s):
    if pd.isna(s): return ""
    return str(s).strip()

def parse_moeda_ou_numero(valor):
    if pd.isna(valor): return 0.0
    if isinstance(valor,(int,float,np.number)): return float(valor)

    txt = str(valor).strip()
    if txt == "": return 0.0

    txt = txt.replace("R$","").replace(" ","")
    if "," in txt:
        txt = txt.replace(".","").replace(",",".")
    try:
        return float(txt)
    except:
        return 0.0

def parse_data_robusta(serie):
    return pd.to_datetime(serie,errors="coerce",dayfirst=True)

def formatar_brl(x):
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_perc(x):
    if pd.isna(x): return ""
    return f"{x:.1f}%"

def montar_chave_texto(df):
    partes=[]
    for col in ["Nome do fornecedor","Descrição","Observações"]:
        if col in df.columns:
            partes.append(df[col].fillna("").astype(str))
        else:
            partes.append(pd.Series([""]*len(df),index=df.index))
    return (partes[0]+" "+partes[1]+" "+partes[2]).str.lower()

def aplicar_filtro_ano_mes(df,ano=None,mes=None):
    df=df.copy()
    if ano is not None:
        df=df[df["DATA_REF"].dt.year==ano]
    if mes is not None:
        df=df[df["DATA_REF"].dt.month==mes]
    return df

@st.cache_data
def carregar_planilha(caminho_arquivo):
    base=pd.read_excel(caminho_arquivo,sheet_name="BASE DE DADOS")
    receitas=pd.read_excel(caminho_arquivo,sheet_name="RECEITAS")
    contas_resultado=pd.read_excel(caminho_arquivo,sheet_name="BASE CONTAS DE RESULTADO",header=None)

    base.columns=[str(c).strip() for c in base.columns]
    receitas.columns=[str(c).strip() for c in receitas.columns]

    contas_resultado.columns=["Categoria 1","Grupo Resultado"]
    contas_resultado["Categoria 1"]=contas_resultado["Categoria 1"].astype(str).str.strip()
    contas_resultado["Grupo Resultado"]=contas_resultado["Grupo Resultado"].astype(str).str.strip()

    mapa_categoria_grupo=dict(zip(contas_resultado["Categoria 1"],contas_resultado["Grupo Resultado"]))

    base["DATA_REF"]=parse_data_robusta(base["Data prevista"])
    receitas["DATA_REF"]=parse_data_robusta(receitas["Data prevista"])

    base["VALOR_CAT"]=base["Valor na Categoria 1"].apply(parse_moeda_ou_numero).abs()
    receitas["VALOR_CAT"]=receitas["Valor na Categoria 1"].apply(parse_moeda_ou_numero)

    base["Categoria 1"]=base["Categoria 1"].apply(normalizar_texto)
    receitas["Categoria 1"]=receitas["Categoria 1"].apply(normalizar_texto)

    base["Grupo Resultado"]=base["Categoria 1"].map(mapa_categoria_grupo).fillna("NÃO CLASSIFICADO")

    texto_base=montar_chave_texto(base)
    base["FLAG_MANDARIM"]=texto_base.str.contains(r"\bmandarim\b",regex=True)
    base["FLAG_FAZENDA"]=texto_base.str.contains(r"fazenda da matta",regex=True)

    receitas["FLAG_RECEITA_VALIDA"]=receitas["Categoria 1"].str.lower().str.contains("receitas de servi")

    return base,receitas

# =========================
# RESTANTE DO APP (mantido)
# =========================

st.sidebar.title("Filtros")

arquivo_upload = st.sidebar.file_uploader("Selecione a planilha Excel", type=["xlsx"])
caminho_arquivo = arquivo_upload if arquivo_upload else ARQUIVO_PADRAO

if not Path(ARQUIVO_PADRAO).exists() and arquivo_upload is None:
    st.error("Arquivo não encontrado")
    st.stop()

base, receitas = carregar_planilha(caminho_arquivo)

ano_escolhido = st.sidebar.selectbox("Ano", sorted(base["DATA_REF"].dt.year.dropna().unique()))
mes_escolhido_txt = st.sidebar.selectbox("Mês", ["Todos"]+[MESES_PT[m] for m in MESES_ORDENADOS])

mes_escolhido = None
if mes_escolhido_txt != "Todos":
    mes_escolhido = {v:k for k,v in MESES_PT.items()}[mes_escolhido_txt]

base_f = aplicar_filtro_ano_mes(base,ano_escolhido,mes_escolhido)
receitas_f = aplicar_filtro_ano_mes(receitas,ano_escolhido,mes_escolhido)

st.title("DRE Gerencial - Imobiliária")
st.write("Login ativo ✅")