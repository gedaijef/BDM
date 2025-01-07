# Código para Ler, Categorizar e Armazenar no Banco de Dados

# Importações
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from langchain_community.callbacks import get_openai_callback
import os
import requests
from time import sleep
import time
import json
import psycopg2
from psycopg2 import OperationalError, Error
from Funcoes_bd import *

load_dotenv()

# Conexão da GREEN API
url = os.getenv('URL_LER')
url_enviar_imagem = os.getenv('URL_ENVIAR_IMAGEM')
url_enviar = os.getenv('URL_ENVIAR')
headers = {}
headers_enviar = {'Content-Type': 'application/json'}

# Especificações da LLM
llm = ChatOpenAI(
    model="gpt-4o-2024-08-06",
    temperature=0.5,
    api_key=os.getenv('OPENAI_API_KEY')
)

# Leitura dos Prompt
with open("Prompts/Categorizador.txt", encoding="utf-8") as arquivo:
    template = arquivo.read()

# Leitura do arquivo das Categorias
with open("../Categorias.txt", encoding="utf-8") as arquivo:
    categorias_padrao = arquivo.read()

# Função para Categorizar as notícias
def categorizar_noticias(llm, template, categorias, noticia):
    prompt = template.format(categorias_padrao=categorias, noticia=noticia)
    resposta = llm.invoke(prompt)
    print(f'Categoria(s) da mensagem: {resposta.content}')
    return resposta


# Repetição para ler, categorizar e armazenar as notícias

while True:
    response = requests.get(url, headers=headers)
    print('-------------------------------')
    print(response.status_code)
    # print(response.text.encode('utf8'))
    
    comeco = time.time()

    mensagens_totais = 0
    
    if response.status_code == 200:
        messages = json.loads(response.text)
        
        for message in reversed(messages):

            # Filtrar apenas as mensagens do grupo especificado
            if message['chatId'] == (os.getenv('CHAT_ID')):
                print(message)

                eh_mensagem_repetida = True

                # Selecionar a mensagem
                try:
                    if 'textMessage' in message:
                        # Pegar somente mensagem de texto
                        noticia = message['textMessage']
                        eh_mensagem_repetida = insert_group_message(message['textMessage'],False)
                        print('Apenas texto.')

                    elif 'extendedTextMessage' in message:
                        # Pegar somente mensagem de texto
                        noticia = message['extendedTextMessage']['text']
                        eh_mensagem_repetida = insert_group_message(message['extendedTextMessage']['text'],False)
                        print('Apenas texto.')

                    # Pegar somente imagem sem legenda
                    elif message["typeMessage"] in  ["imageMessage","videoMessage","documentMessage"]:
                        if message['caption'] == '':
                            noticia = ''
                            eh_mensagem_repetida = insert_group_message(message['fileName'],True)
                            print('Apenas imagem.')
                        
                        # Pegar somente imagem com legenda
                        else:
                            noticia = message['caption']
                            eh_mensagem_repetida = insert_group_message(message['caption'],False)
                            print('Imagem e texto.')

                except Exception as e:
                    print(f'Notícia fora dos padrões ou já está no banco de dados: {e}')

                # Caso o tipo da mensagem esteja certo, categorizar a notícia
                else:
                    if eh_mensagem_repetida == False:
                        try:
                            mensagens_totais +=1
                            categorias_lista = [9]
                            custo = 0
                            input_tokens = 0
                            output_tokens = 0
                        
                            # Fluxo para mensagem com texto
                            if noticia != '':
                                
                                # Chamar a API do OpenAI com a LangChain                    
                                with get_openai_callback() as cb:
                                    result = categorizar_noticias(llm, template, categorias_padrao, noticia)
                                    categorias = result.content
                                    dados = str(cb)
                                    
                                # Separar os dados de quantidade de tokens
                                lines = dados.splitlines() 
                                valores_dados = {}
                                for line in lines:
                                    if ':' in line:
                                        key, value = line.split(':', 1) 
                                        valores_dados[key.strip()] = value.strip()
                                
                                # Calcular o preço
                                input_custo = 0.0025
                                output_custo = 0.01

                                input_tokens = int(valores_dados['Prompt Tokens'])
                                output_tokens = int(valores_dados['Completion Tokens'])

                                custo = ((input_tokens/1000*input_custo)+(output_tokens/1000*output_custo))

                                # Tratar o retorno da IA
                                categorias_lista = [int(categoria.strip()) for categoria in categorias.split(',')]

                            else:
                                noticia = message['fileName']

                            call_insert_defaut_category_cost(categorias_lista,custo,input_tokens,output_tokens)

                        except Exception as e:
                            print(f'Erro ao categorizar a notícia: {e}')

                        else:
                            # Tentar enviar para o usuário
                            try:
                                # Filtrar as categorias para criar o select
                                numeros = select_client(categorias_lista)
                                numeros_totais = len(numeros)

                                print(numeros)
                                
                                # Iterar os números das categorias para o envio de mensagens
                                for numero in numeros:
                                    numero +='@c.us'

                                    # Paylod e url para as mensagens de texto
                                    if 'caption' not in message:
                                        payload = {
                                        "chatId": numero, 
                                        "message": noticia
                                        }
                                        url_certa = url_enviar

                                    # Payload e url para mensagens com imagem
                                    else:
                                        payload = {
                                        "chatId": numero,
                                        "chatIdFrom": (os.getenv('CHAT_ID')), 
                                        "messages": [  
                                        message['idMessage'] ]
                                        }
                                        url_certa = url_enviar_imagem
                        
                                    # Enviar mensagens para os números
                                    response = requests.request("POST", url_certa, data=json.dumps(payload), headers=headers_enviar)
                                    print("     enviou para o número: ",response.text.encode('utf8'))
                            
                                print(f"\033[31mNúmeros totais: {numeros_totais}\033[0m")

                                update_group_message(numeros_totais)

                            except Exception as e:
                                print(f"Erro ao enviar a notícia: {e}") 
 
    print(f"\033[31mMensagens totais: {mensagens_totais}\033[0m")

    # Finalizar e acionar o timer de 60 segundos menos o tempo de processamento
    termino = time.time()

    if (termino-comeco<60):
        sleep(60-(termino-comeco))