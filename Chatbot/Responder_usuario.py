# Essa versão do sistema contém: Threads para responder o usuário, delay reduzido, resposta para usuários fora do banco e implementação do juiz

# Importações
import os
from langchain_openai import ChatOpenAI
import google.generativeai as genai
from langchain.prompts import ChatPromptTemplate
from langchain_community.callbacks import get_openai_callback
import requests
import json
from datetime import datetime, timedelta
from time import sleep, time
from dotenv import load_dotenv
import threading
import ast
import psutil
from Funcoes_bd import *

load_dotenv()

# Leitura dos Prompts
with open("Prompts/Judge.txt", encoding="utf-8") as arquivo:
    template_juiz = arquivo.read()

with open("Prompts/SQL.txt", encoding="utf-8") as arquivo:
    template_sql = arquivo.read()

with open("Prompts/Writer.txt", encoding="utf-8") as arquivo:
    template_responder = arquivo.read()

with open("Prompts/Writer_s_memoria.txt", encoding="utf-8") as arquivo:
    template_responder_s_memoria = arquivo.read()

with open("Prompts/Judge_s_memoria.txt", encoding="utf-8") as arquivo:
    template_juiz_s_memoria = arquivo.read()

with open("Prompts/Judge_guardrail.txt", encoding="utf-8") as arquivo:
    template_juiz_guardrail = arquivo.read()

with open("Prompts/Judge_guardrail_s_memoria.txt", encoding="utf-8") as arquivo:
    template_juiz_guardrail_s_memoria = arquivo.read()

with open("Prompts/Writer_guardrail.txt", encoding="utf-8") as arquivo:
    template_responder_guardrail = arquivo.read()

with open("Prompts/Writer_guardrail_s_memoria.txt", encoding="utf-8") as arquivo:
    template_responder_guardrail_s_memoria = arquivo.read()

# Estruturas da GREEN API
url_ler = os.getenv('URL_LER')
url_enviar = os.getenv('URL_ENVIAR')
url_memoria = os.getenv('URL_MEMORIA')

# Especificações da LLM
llm = ChatOpenAI(
    model="gpt-4o-2024-08-06",
    temperature=0.5,
    api_key=os.getenv('OPENAI_API_KEY')
)

# Especificações do Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

# Função para calcular o preço do Prompt
def calcular_preco(dados):
    # Extrair os dados para manipulação
    lines = dados.splitlines() 
    valores_dados = {}
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1) 
            valores_dados[key.strip()] = value.strip()

    # Definição dos custos por mil tokens
    input_custo = 0.0025
    output_custo = 0.01

    # Recuperar os tokens de entrada e saída do dicionário
    input_tokens = int(valores_dados['Prompt Tokens'])
    output_tokens = int(valores_dados['Completion Tokens'])

    # Calcula o custo total
    custo = ((input_tokens/1000*input_custo)+(output_tokens/1000*output_custo))
    return [custo, input_tokens, output_tokens]

# ----------------------------------------------------------------------------------------------------------------
def verificar_24_horas(timestamp):
    data_envio = datetime.fromtimestamp(timestamp)  
    agora = datetime.now()
    return agora - timedelta(days=1) <= data_envio <= agora

def gerar_memoria(historico):
    memoria = []
    contador_incoming = 0
    
    # Itera de trás para frente, ignorando a última mensagem 'incoming'
    for i in range(len(historico) - 2, -1, -1):
        mensagem = historico[i]
        
        # Verifica se a mensagem é do tipo 'incoming' e está dentro de 24 horas
        if mensagem['type'] == 'incoming' and verificar_24_horas(mensagem['timestamp']):
            # Incrementa o contador de mensagens 'incoming'
            contador_incoming += 1
            
            # Seleciona as próximas duas mensagens após a mensagem 'incoming'
            respostas = historico[i + 1:i + 3]
            
            # Verifica se a mensagem e todas as respostas possuem 'textMessage'
            if 'textMessage' in mensagem and all('textMessage' in resposta for resposta in respostas):
                memoria.append({
                    "horario": str(datetime.fromtimestamp(mensagem['timestamp']).time()),
                    "mensagem_usuario": mensagem['textMessage'],
                    "respostas": [
                        resposta['textMessage']
                        for resposta in respostas 
                        if resposta['type'] == 'outgoing'
                    ]
                })
            
            # Para após encontrar as três últimas mensagens 'incoming', exceto a última
            if contador_incoming == 3:
                break

    return memoria
# ----------------------------------------------------------------------------------------------------------------

# Função para responder uma mensagem padrão de pessoas fora do banco ou quando o tipo for inadequado
def responder_outras(remetente_numero, resposta):
    """
    Tipos de mensagens adequados:
    - textMessage
    - extendedTextMessage
    Tipos de mensagens ignorados pelo sistema:
    - reactionMessage
    - stickerMessage
    """
    payload = {
        "chatId": remetente_numero+'@c.us', 
        "message": resposta
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
    print("     Enviou para o número: ", response.text.encode('utf8'))

# Função para criar a resposta para o cliente
def responder_cliente (message, remetente_categorias, remetente_numero, template_juiz, template_sql, template_responder):
    """
    Requisitos:
    - Usuário estar no Banco de Dados
    - Tipo de mensagem ser textMessage ou extendedTextMessage
    """
    
    # Variável para acumular o custo dos 3 Agentes
    informacoes_custos = [0,0,0]

    # Executar o Agente Juiz e enviar a resposta inicial ao usuário
    try: 
        # Verificar o tipo da mensagem e extraí-la
        if 'textMessage' in message:
            print('é textMessage')
            remetente_mensagem = message['textMessage']
        
        elif 'extendedTextMessage' in message:
            # Se a mensagem do usuário fizer referência a outra mensagem, armazenar também a mensagem referenciada
            remetente_mensagem = message['extendedTextMessage']['text']
            try: 
                # Concatenar o contexto com a mensagem enviada
                remetente_mensagem += f"\n\nEste é o contexto da mensagem do cliente: {message['quotedMessage']['textMessage']}"
            except:
                print('A mensagem que o usuário mencionou não é de texto.')

        print("Mensagem do usuário:", remetente_mensagem)

        # Extrair a data da mensagem
        remetente_data = datetime.fromtimestamp(message['timestamp'])
        
        # Buscar o histórico de mensagens do usuário
        payload = {
        "chatId": remetente_numero+"@c.us", 
        "count": 50
        }
        headers = {
        'Content-Type': 'application/json'
        }

        response = requests.post(url_memoria, json=payload)

        historico = json.loads(response.text)
        
        historico_respostas = gerar_memoria(historico[::-1])

        # Verificar se existe memória
        if historico_respostas != None:

            memoria = "Mémoria mais recente --->\n"
            cont =1 
            for item in historico_respostas:
                memoria+=f"### Mensagem {cont}\n"
                memoria+=f"Horário: {item['horario']}\n"
                memoria += f"Usuário: {item['mensagem_usuario']}\n"
                memoria += f"Chatbot 1: {item['respostas'][0]}\n"
                if len(item['respostas']) ==2:
                    memoria += f"Chatbot 2: {item['respostas'][1]}\n"
                cont+=1
            memoria += " <- Memória mais antiga"

            print(memoria)
            
            # Executar o Prompt do Juiz com memória
            prompt_juiz = template_juiz.format(mensagem=remetente_mensagem, memoria=memoria, categorias= [item for item in remetente_categorias if item != 8], horario= remetente_data.time())
        
        else:
            # Executar o Prompt do Juiz sem memória
            prompt_juiz = template_juiz_s_memoria.format(mensagem=remetente_mensagem, categorias=[item for item in remetente_categorias if item != 8], horario=remetente_data.time())

        # Obter as informações do Prompt do Juiz
        with get_openai_callback() as dados:
            resposta_juiz = llm.invoke(prompt_juiz)
            dados = str(dados)

        # Obter o preço gasto pelo Prompt e adicionar ao informacoes_custos
        custo_juiz = calcular_preco(dados)
        for i in range(len(informacoes_custos)):
            informacoes_custos[i] += custo_juiz[i]

        # Exibir a resposta do Prompt e seu custo
        print("\033[1mResposta Juiz\033[0m\n" + resposta_juiz.content)
        print(f"\033[31mCusto para o Prompt Juiz: {custo_juiz}\033[0m\n")

        # Transformar a resposta do Juiz em uma lista
        resposta_juiz = ast.literal_eval(resposta_juiz.content)

        # Fazer a verificação com o Gemini com memória
        if historico_respostas != None:
            prompt_juiz_guardrail = template_juiz_guardrail.format(mensagem=remetente_mensagem,resposta_judge=resposta_juiz[0],memoria=memoria)
            resposta_juiz_guardrail = model.generate_content(prompt_juiz_guardrail)
            print(resposta_juiz_guardrail.text)
            resposta_juiz_guardrail = ast.literal_eval(resposta_juiz_guardrail.text)
        else:
            prompt_juiz_guardrail = template_juiz_guardrail_s_memoria.format(mensagem=remetente_mensagem,resposta_judge=resposta_juiz[0])
            resposta_juiz_guardrail = model.generate_content(prompt_juiz_guardrail)
            print(resposta_juiz_guardrail.text)
            resposta_juiz_guardrail = ast.literal_eval(resposta_juiz_guardrail.text)

        # Alterar as respostas caso seja identificado um erro
        if resposta_juiz_guardrail[0] ==1:
            print('entrou')
            prompt_juiz += f"""## Considerações Finais
            Anteriormente, você respondeu esta pergunta, porém foi identificado um erro na resposta gerada. Seguem as observações que você deve considerar para responder de forma correta desta vez
            
            Observação: {resposta_juiz_guardrail[1]}"""

            # Obter as informações do Prompt do Juiz
            with get_openai_callback() as dados:
                resposta_juiz = llm.invoke(prompt_juiz)
                dados = str(dados)

            # Obter o preço gasto pelo Prompt e adicionar ao informacoes_custos
            custo_juiz = calcular_preco(dados)
            for i in range(len(informacoes_custos)):
                informacoes_custos[i] += custo_juiz[i]

            # Exibir a resposta do Prompt e seu custo
            print("\033[1mResposta Juiz\033[0m\n" + resposta_juiz.content)
            print(f"\033[31mCusto para o Prompt Juiz: {custo_juiz}\033[0m\n")

            # Transformar a resposta do Juiz em uma lista
            resposta_juiz = ast.literal_eval(resposta_juiz.content)

            print(resposta_juiz)

        # Enviar a mensagem inicial ao usuário
        payload = {
        "chatId": remetente_numero+'@c.us', 
        "message": "🤖- "+resposta_juiz[0]
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
        print("     Enviou a resposta inicial para o número: ", response.text.encode('utf8'))

    # Enviar mensagem de erro ao usuário, caso ocorra
    except Exception as e:
        print(f'Ocorreu um erro durante o Agente Juiz: {e}')
        payload = {
        "chatId": remetente_numero+'@c.us', 
        "message": "🤖- Um erro ocorreu! Tente utilizar esse serviço mais tarde."
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
        print("     Enviou a resposta inicial para o número: ", response.text.encode('utf8'))

    # Caso nenhum erro ocorra durante o Agente Juiz
    else:
        # Se a mensagem do usuário for classificada como Relevante (0), obter a Query SQL e escrever uma resposta
        if resposta_juiz[1] == 0 or resposta_juiz[1] == 1: 

            # Executar o Agente Consultor SQL
            try:
                # Obter as categorias do usuário e formatá-las
                remetente_categorias = str(remetente_categorias)[1:-1]

                if resposta_juiz[1] == 0:
                    # Executar o Prompt do Consultor SQL
                    prompt_sql = template_sql.format(message=message, remetente_categorias=remetente_categorias, remetente_data=remetente_data)
                else:
                    prompt_sql = template_sql.format(message=resposta_juiz[2], remetente_categorias=remetente_categorias, remetente_data=remetente_data)

                # Obter as informações do Prompt do Consultor SQL
                with get_openai_callback() as dados:
                    resposta_sql = llm.invoke(prompt_sql)    
                    dados = str(dados)
                
                # Obter o preço gasto pelo Prompt do Consultor SQL e adicionar ao informacoes_custos
                custo_sql = calcular_preco(dados)
                for i in range(len(informacoes_custos)):
                    informacoes_custos[i] += custo_sql[i]

                print("Query SQL gerada:", resposta_sql.content)

                print(f"\033[31mCusto para o prompt resposta: {custo_sql}\033[0m")
                print(f"\033[32mCusto total: {informacoes_custos}\033[0m")

                # Acessar o conteúdo da resposta e garantir que seja uma String
                query = resposta_sql.content if isinstance(resposta_sql.content, str) else resposta_sql.content.decode('utf-8')

                # Buscar as notícias no Banco de Dados
                noticias = select_mensagem(query)

                if len(noticias) == 0:
                    noticias = select_group_message_servicos()

                # Concatenar e formatar as notícias retornadas
                contador = 1
                noticias_formatadas = ""
                for noticia in noticias:
                    noticias_formatadas += "Notícia {}: {}\n".format(contador, noticia)
                    contador += 1

                print('Retorno SQL:', noticias_formatadas)

            # Exibir mensagem de erro, caso ocorra
            except Exception as e:
                print(f'Ocorreu um erro durante o Agente Consultor SQL: {e}')
            
            # Caso nenhum erro ocorra durante o Agente Consultor SQL
            else:
                # Executar o Agente Escritor de Resposta
                try:
                    if resposta_juiz[1] == 1:
                        prompt_escritor = template_responder.format(mensagem=remetente_mensagem, noticias=noticias_formatadas, memoria=memoria, resposta_inicial=resposta_juiz[0])
                    else:
                        prompt_escritor = template_responder_s_memoria.format(mensagem=remetente_mensagem, noticias=noticias_formatadas, resposta_inicial=resposta_juiz[0])

                    # Obter as informações do Prompt Escritor de Resposta
                    with get_openai_callback() as dados:
                        resposta_escritor = llm.invoke(prompt_escritor)
                        dados = str(dados)

                    # Obter o preço gasto pelo Prompt do Escritor de Resposta e adicionar ao informacoes_custos
                    custo_escritor = calcular_preco(dados)
                    for i in range(len(informacoes_custos)):
                        informacoes_custos[i] = custo_escritor[i]
                    
                    print("Resposta Escritor:", resposta_escritor.content)

                    print(f"\033[31mCusto para o prompt resposta: {custo_escritor}\033[0m")
                    print(f"\033[32mCusto total: {informacoes_custos}\033[0m")

                    # Transformar a resposta do Juiz em uma lista
                    resposta_escritor = ast.literal_eval(resposta_escritor.content)

                    resposta_escritor[0] = resposta_escritor[0].replace('**','*')


                    print(resposta_escritor)

                     # Fazer a verificação com o Gemini com memória
                    if historico_respostas != None:
                        prompt_escritor_guardrail = template_responder_guardrail.format(mensagem=remetente_mensagem,resposta_judge=resposta_juiz[0],memoria=memoria, resposta_writer = resposta_escritor[0],noticias=noticias_formatadas)
                        resposta_escritor_guardrail = model.generate_content(prompt_escritor_guardrail)
                        print(resposta_escritor_guardrail.text)
                        resposta_escritor_guardrail = ast.literal_eval(resposta_escritor_guardrail.text)

                    else:
                        prompt_escritor_guardrail = template_responder_guardrail_s_memoria.format(mensagem=remetente_mensagem,resposta_judge=resposta_juiz[0], resposta_writer = resposta_escritor[0],noticias=noticias_formatadas)
                        resposta_escritor_guardrail = model.generate_content(prompt_escritor_guardrail)
                        print(resposta_escritor_guardrail.text)
                        resposta_escritor_guardrail = ast.literal_eval(resposta_escritor_guardrail.text)

                    # Alterar as respostas caso seja identificado um erro
                    if resposta_escritor_guardrail[0] ==1:
                        prompt_escritor += f"""## Considerações Finais
                        Anteriormente, você respondeu esta pergunta, porém foi identificado um erro na resposta gerada. Seguem as observações que você deve considerar para responder de forma correta desta vez
                        
                        Observação: {resposta_escritor_guardrail[1]}"""

                        # Obter as informações do Prompt Escritor de Resposta
                        with get_openai_callback() as dados:
                            resposta_escritor = llm.invoke(prompt_escritor)
                            dados = str(dados)

                        # Obter o preço gasto pelo Prompt do Escritor de Resposta e adicionar ao informacoes_custos
                        custo_escritor = calcular_preco(dados)
                        for i in range(len(informacoes_custos)):
                            informacoes_custos[i] = custo_escritor[i]

                        print(f"\033[31mCusto para o prompt resposta: {custo_escritor}\033[0m")
                        print(f"\033[32mCusto total: {informacoes_custos}\033[0m")

                        # Transformar a resposta do Juiz em uma lista
                        resposta_escritor = ast.literal_eval(resposta_escritor.content)

                        resposta_escritor[0] = resposta_escritor[0].replace('**','*')

                        print("Nova resposta gerada: "+resposta_escritor[0])

                    # Alterar as respostas caso seja identificado um erro
                    if resposta_escritor_guardrail[0] ==1:
                        prompt_escritor += f"""## Considerações Finais
                        Anteriormente, você respondeu esta pergunta, porém foi identificado um erro na resposta gerada. Seguem as observações que você deve considerar para responder de forma correta desta vez
                        
                        Observação: {resposta_escritor_guardrail[1]}"""

                        # Obter as informações do Prompt Escritor de Resposta
                        with get_openai_callback() as dados:
                            resposta_escritor = llm.invoke(prompt_escritor)
                            dados = str(dados)

                        # Obter o preço gasto pelo Prompt do Escritor de Resposta e adicionar ao informacoes_custos
                        custo_escritor = calcular_preco(dados)
                        for i in range(len(informacoes_custos)):
                            informacoes_custos[i] = custo_escritor[i]

                        print(f"\033[31mCusto para o prompt resposta: {custo_escritor}\033[0m")
                        print(f"\033[32mCusto total: {informacoes_custos}\033[0m")

                        # Transformar a resposta do Juiz em uma lista
                        resposta_escritor = ast.literal_eval(resposta_escritor.content)

                        resposta_escritor[0] = resposta_escritor[0].replace('**','*')

                        print("Nova resposta gerada: "+resposta_escritor[0])

                    # Inserir na tabela client_message
                    call_insert_new_client_message_cost(pergunta=remetente_mensagem, categoria_juiz=resposta_juiz[1], resposta_juiz=resposta_juiz[0], categoria_escritor=resposta_escritor[1], resposta_escritor=resposta_escritor[0], resposta_sql=resposta_sql.content, preco=informacoes_custos[0], cliente_numero=remetente_numero,input_tokens=informacoes_custos[1],output_tokens=informacoes_custos[2])

                # Exibir mensagem de erro, caso ocorra
                except Exception as e:
                    print(f'Ocorreu um erro durante o Agente Escritor de Respostas: {e}')

            # Enviar a resposta para o usuário  
            try:
                payload = {
                "chatId": remetente_numero+'@c.us', 
                "message": "🤖- "+resposta_escritor[0]
                }
                headers = {'Content-Type': 'application/json'}
                response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
                print("     Enviou para o número: ", response.text.encode('utf8'))

                # Se a resposta do Agente Escritor for classificada como Sem notícias correspondentes (1)
                if resposta_escritor[1] == 1 or resposta_escritor[1] == 2:

                    # Caso a memória tenha sido utilizada, mandar a reestruturação
                    if resposta_juiz[1] == 1:
                        payload = {
                            "chatId": "120363360919838255@g.us", 
                            "message": f"*Mensagem não respondida*\n\nCliente: {remetente_numero}\n\nMensagem: {resposta_juiz[2]}"
                        }
                    else:
                        payload = {
                            "chatId": "120363360919838255@g.us", 
                            "message": f"*Mensagem não respondida*\n\nCliente: {remetente_numero}\n\nMensagem: {remetente_mensagem}"
                        }

                    # Enviar aos jornalistas
                    headers = {'Content-Type': 'application/json'}
                    # response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
                    print("     Enviou para o Grupo dos Jornalistas: ", response.text.encode('utf8'))

            # Enviar uma mensagem de erro ao usuário, caso ocorra
            except Exception as e:
                # Enviar um aviso ao cliente quando algum erro ocorrer 
                print(f'Ocorreu um erro durante o envio da mensagem: {e}') 
                payload = {
                "chatId": remetente_numero+'@c.us', 
                "message": "🤖- Um erro ocorreu! Tente utilizar esse serviço mais tarde."
                }
                headers = {'Content-Type': 'application/json'}
                response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
                print("     Enviou para o número:", response.text.encode('utf8'))

        # Se a classificação do Agente Juiz for diferente de Relevante (0) e de Memória (6)
        else:
            # Enviar aos jornalistas caso a mensagem esteja indicando um erro
            if resposta_juiz[1] == 8:
                payload = {
                    "chatId": "120363360919838255@g.us", 
                    "message": f"*Mensagem indicando correção*\n\nCliente: {remetente_numero}\n\nMensagem: {remetente_mensagem}"
                }

                headers = {'Content-Type': 'application/json'}
                response = requests.request("POST", url_enviar, data=json.dumps(payload), headers=headers)
                print("     Enviou para o Grupo dos Jornalistas: ", response.text.encode('utf8'))

            # Inserir na tabela client_message com os parâmetros não utilizados como None
            call_insert_new_client_message_cost(pergunta=remetente_mensagem, categoria_juiz=resposta_juiz[1], resposta_juiz=resposta_juiz[0], categoria_escritor=None, resposta_escritor=None, resposta_sql=None, preco=informacoes_custos[0], cliente_numero=remetente_numero,input_tokens=informacoes_custos[1],output_tokens=informacoes_custos[2])

# ---------------------------------------------------------------------------------------------------------------

# Listas para guardar os IDs e os horários das mensagens do último minuto
idMessage_1min = []
horario_1min = []

while True:
    # Iterar pela listas das mensagens do último minuto (de trás para frente para evitar erros)
    for i in range(len(horario_1min)-1, -1, -1):
        # Calcula o total de segundos do horário atual
        segundos_totais_atual =  datetime.now().hour * 3600 +  datetime.now().minute * 60 +  datetime.now().second

        # Primeira Condição: Se o horário atual for maior que o horário da mensagem e a diferença for maior que 75 segundos
        # Segunda Condição: Evitar erro com a transição de dias (mensagens enviadas meia-noite)
        if (segundos_totais_atual > horario_1min[i] and horario_1min[i] - segundos_totais_atual > 75) or (segundos_totais_atual < horario_1min[i] and 86400 - horario_1min[i] +segundos_totais_atual> 75):

            # Remover o ID e horário das listas
            idMessage_1min.pop(i)
            horario_1min.pop(i)

    # Faz uma requisição para a url_ler
    response = requests.get(url_ler, headers={})
    print("Response status:", response.status_code)
    
    # Se a requisição for realizada com sucesso (200)
    if response.status_code == 200:
        # Carregar as mensagens
        messages = json.loads(response.text)

        # Iterar pelas mensagens enviadas
        for i in range(len(messages)-1,-1,-1):

            # Adicionar as novas mensagens à lista de mensagens do último minuto e responder
            if  messages[i]['idMessage'] not in idMessage_1min:

                # Adicionar na lista das mensagens
                segundos_totais_atual = datetime.now().hour * 3600 +  datetime.now().minute * 60 +  datetime.now().second
                horario_1min.append(segundos_totais_atual)
                idMessage_1min.append(messages[i]['idMessage'])

                # Armazenar o número do usuário e o horário da mensagem
                remetente_numero = messages[i]['chatId'][:-5]

                # Fazer a seleção da(s) categoria(s) do usuário
                remetente_categorias = select_client(remetente_numero)

                # Mandar mensagem padrão para o usuário, caso não estiver cadastrado no Banco de Dados
                if not remetente_categorias:
                    print("\n\n-----------------------------------")
                    print("     Usuário fora do banco.")
                    resposta = """O chatbot da BDM é um serviço exclusivo para assinantes. Para acessar nossas funcionalidades e continuar a interação, você pode realizar a assinatura através deste link: https://www.bomdiamercado.com.br/finalizar-compra/

                    Caso tenha alguma dúvida, estamos à disposição para ajudar. Será um prazer tê-lo(a) conosco!"""
                    # threading.Thread(target=responder_outras, args=(remetente_numero,resposta)).start()
                    
                # Mandar mensagem padrão para o usuário, caso o tipo da mensagem seja inadequado
                elif 'textMessage' not in messages[i] and messages[i]['typeMessage'] != "stickerMessage" and 'extendedTextMessage' not in messages[i] and messages[i]['typeMessage'] != "reactionMessage" :
                    print("\n\n-----------------------------------")
                    print("     Outra mídia além de texto.")
                    resposta = """🤖- Nosso sistema atualmente só aceita perguntas em formato de texto. Infelizmente, não conseguimos processar outros tipos de mídia, como vídeos, áudios ou imagens."""
                    threading.Thread(target=responder_outras, args=(remetente_numero,resposta)).start()

                # Responder ao usuário
                elif ('textMessage' in messages[i] or 'extendedTextMessage' in messages[i]):
                    print("\n\n-----------------------------------")
                    print("     Usuário dentro do banco.")

                    # Verificar o tamanho da mensagem
                    if ('textMessage' in messages[i] and len(messages[i]['textMessage']) > 500) or ('extendedTextMessage' in messages[i] and len(messages[i]['extendedTextMessage']['text']) > 500):
                        print('Mensagem muito grande')
                        resposta = """🤖- Infelizmente, sua mensagem excede o limite permitido de 500 caracteres. Caso você a ajuste para esse tamanho, ficarei muito feliz em ajudá-lo!"""
                        threading.Thread(target=responder_outras, args=(remetente_numero,resposta)).start()

                    else:
                        threading.Thread(target=responder_cliente, args=(messages[i], remetente_categorias, remetente_numero, template_juiz, template_sql, template_responder)).start()
    
    sleep(10)