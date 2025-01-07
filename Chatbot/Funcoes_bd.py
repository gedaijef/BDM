# Importações
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import Error, OperationalError

load_dotenv()

# Função de conexão com o BD
def conectar_bd ():
    return psycopg2.connect(os.getenv('URL_BD'))

# Função para inserir na tabela client_message
def call_insert_new_client_message_cost(pergunta, categoria_juiz, resposta_juiz, resposta_sql, categoria_escritor, resposta_escritor, cliente_numero, input_tokens, output_tokens, preco):
    """
    Args:
    pergunta (text): Mensagem do cliente.
    categoria_juiz (int): Categoria do prompt do agente SQL.
    resposta_juiz (text): Resposta do agente juiz.
    resposta_sql (text): Resposta SQL gerada.
    categoria_escritor (int): Categoria do prompt do agente escritor.
    resposta_escritor (text): Resposta do agente escritor.
    cliente_numero (varchar(13)): Número de telefone do cliente.
    input_tokens (int): Quantidade de tokens de entrada.
    output_tokens (int): Quantidade de tokens de saída.
    preco (numeric): Custo total gerado.
    """
    try:
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute('SET timezone to "GMT+3";')
        
        query_sql = """
        CALL insert_client_message_and_cost(
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """
        
        cur.execute(query_sql, (
            cliente_numero,
            pergunta,
            resposta_juiz,       
            resposta_sql,         
            resposta_escritor,
            input_tokens,
            output_tokens,
            preco,
            categoria_escritor,
            categoria_juiz
        ))
        
        print('\033[34mInsert na tabela client_message e client_message_cost realizado com sucesso.\033[0m')
    
    except (OperationalError, Error) as e:
        print(f"\033[34mErro ao inserir na tabela client_message: {e}\033[0m")
    
    conn.commit()
    conn.close()


# Função para selecionar os números dos clientes
def select_client (numero):
    conn = conectar_bd()
    cur = conn.cursor()
    query_sql = """
    SELECT default_category.id
    FROM client
    JOIN default_category_client ON client.id = default_category_client.client_id
    JOIN default_category ON default_category.id = default_category_client.default_category_id
    WHERE client.phone_number = %s;
    """
    try:
        cur.execute(query_sql,(numero,))
        lista_selects = cur.fetchall()
        lista_selects = [item[0] for item in lista_selects]
    except (OperationalError, Error) as e:
        print(f"\033[34mErro ao selecionar na tabela client: {e}\033[0m")
        lista_selects = []
    conn.close()
    return lista_selects

# Função para selecionar as notícias da tabela group_message da categoria 8
def select_group_message_servicos():
    conn = psycopg2.connect(os.getenv('URL_BD'))
    cur = conn.cursor()
    try:
        cur.execute("""(SELECT DISTINCT date, time, content
    FROM group_message
    JOIN default_category_group_message ON group_message.id = default_category_group_message.group_message_id
    WHERE default_category_group_message.default_category_id = 8
    AND only_image IS false
    AND content ILIKE '%_Caros amigos, bom dia!_
    _Iniciamos as transmissões do BDM %'
    AND date IS NOT null
    AND time IS NOT null
    ORDER BY date DESC, time DESC
    LIMIT 1)
    UNION
    (SELECT DISTINCT date, time, content
    FROM group_message
    JOIN default_category_group_message ON group_message.id = default_category_group_message.group_message_id
    WHERE default_category_group_message.default_category_id = 8
    AND only_image IS false
    AND content ILIKE '%*Encerramento das transmissões*%'
    ORDER BY date DESC, time DESC
    LIMIT 1)
    UNION
    (SELECT DISTINCT date, time, content
    FROM group_message
    JOIN default_category_group_message ON group_message.id = default_category_group_message.group_message_id
    WHERE default_category_group_message.default_category_id = 8
    AND date = day_month_year()
    ORDER BY date DESC, time DESC
    )""")
        lista_noticias = cur.fetchall()
    except (OperationalError, Error) as e:
        print(f"\033[34mErro ao selecionar na tabela group_message: {e}\033[0m")
        lista_noticias = []
    conn.close()
    return lista_noticias

# Função para selecionar as notícias retornadas pela Query gerada
def select_mensagem(query):
    conn = psycopg2.connect(os.getenv('URL_BD'))
    cur = conn.cursor()
    cur.execute(query)
    lista_noticias = cur.fetchall()
    conn.close()
    return lista_noticias

# Função para inserir na tabela summary
def insert_summary (categoria, conteudo):
    try:
        conn = conectar_bd()
        cur = conn.cursor()
        cur.execute('SET timezone to "GMT+3";')
        query_sql = """INSERT INTO summary VALUES (%s, day_month_year() -1 , %s)"""
        cur.execute(query_sql, (conteudo, categoria))
        print('Insert na tabela summary realizado com sucesso.')
    except (OperationalError, Error) as e:
        print(f"Erro ao inserir na tabela summary: {e}")
    conn.commit()
    conn.close()

# Função para selecionar na tabela group_message
def select_group_message (categoria):
    conn = conectar_bd()
    cur = conn.cursor()
    query_sql = """
	SELECT group_message.content, default_category_group_message.default_category_id
	FROM group_message
	JOIN default_category_group_message on group_message.id = default_category_group_message.group_message_id
	WHERE date = day_month_year() -1
	AND default_category_group_message.default_category_id = %s;"""
    try:
        cur.execute(query_sql,(categoria,))
        lista_selects = cur.fetchall()
        lista_selects = [item[0] for item in lista_selects]
    except (OperationalError, Error) as e:
        print(f"Erro ao buscar na tabela group_message: {e}")
        lista_selects = []
    conn.close()
    return lista_selects