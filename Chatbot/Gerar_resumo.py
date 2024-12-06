# Importações
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_community.callbacks import get_openai_callback
import os
from dotenv import load_dotenv
from datetime import datetime
import psycopg2
from psycopg2 import Error, OperationalError
from Funcoes_bd import *

load_dotenv()

# Especificações da LLM
llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model='gpt-4o-2024-08-06',
    temperature=0.5)

# Leitura do Prompt
with open("Prompts/Resumista.txt", encoding="utf-8") as arquivo:
    template = arquivo.read()

# Função de conexão com o BD
def conectar_bd ():
    return psycopg2.connect(os.getenv('URL_BD'))

# Inserir na tabela summary
for i in range(1, 8):
    categoria = i

    # Selecionando as notícias de acordo com sua categoria
    registros = select_group_message(categoria)

    # Formatando as notícias
    contador = 1
    noticias_filtradas = ""
    for registro in registros:
        noticias_filtradas += f"Notícia {contador}: {registro}\n"
        contador += 1

    print(noticias_filtradas)

    if len(noticias_filtradas) > 0:

        prompt_resumos = template.format(noticias_filtradas)

        # Financeiro e contagem de tokens
        with get_openai_callback() as cb:
            resposta = llm.invoke(prompt_resumos)
            dados = str(cb)
            
        lines = dados.splitlines() 
        valores_dados = {}
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1) 
                valores_dados[key.strip()] = value.strip()

        input_custo = 0.0025
        output_custo = 0.01

        input_tokens = int(valores_dados['Prompt Tokens'])
        output_tokens = int(valores_dados['Completion Tokens'])

        custo = ((input_tokens/1000*input_custo)+(output_tokens/1000*output_custo))

        print(f"\033Tokens_totais: {input_tokens+output_tokens}\nCusto Total: {custo} \033[0m")

        # Printando o resumo
        resumo = resposta.content
        print(resumo)

        # Inserindo o resumo no Banco de Dados
        insert_summary(categoria, resumo)