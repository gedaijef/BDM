# Importações
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import Error, OperationalError

load_dotenv()

# Função de conexão com o BD
def conectar_bd ():
    return psycopg2.connect(os.getenv('URL_BD'))

# Insert na tabela group_message (content (text) e has_image (boolean))
def insert_group_message (mensagem, imagem):
    execao = False
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute('SET timezone to "GMT+3";')
    query_sql = """
    INSERT INTO group_message (content, date, time, has_image)
    VALUES (%s,DAY_MONTH_YEAR(),HOUR_MIN_SEC(),%s);
    """
    try:
        cur.execute(query_sql,(mensagem,imagem))
    except (OperationalError, Error) as e:
        print(f"Erro ao executar o insert na tabela group_message: {e}")
        execao = True
    conn.commit()
    conn.close()
    return execao

# Call com a procedure insert_defaut_category_cost (categoria (array int), custo (numeric), input_token (int), output_token (int))
def call_insert_defaut_category_cost (categoria, custo, input_token, output_token):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute('SET timezone to "GMT+3";')
    query_sql = """
    CALL insert_group_category_cost(
        ARRAY[%s],
        %s,
        %s,
        %s);
    """
    try:
        cur.execute(query_sql, (categoria, custo, input_token, output_token)) 
        print('Procedure insert_group_category_cost realizada com sucesso.')
    except (OperationalError, Error) as e:
        print(f"Erro ao executar a procedure insert_group_category_cost: {e}")
    conn.commit()
    conn.close()

# Select na tabela client (categoria (array int))
def select_client (categoria):
    conn = conectar_bd()
    cur = conn.cursor()
    query_sql = """
    SELECT DISTINCT client.phone_number
    FROM client
    JOIN default_category_client ON client.id = default_category_client.client_id
    JOIN default_category ON default_category.id = default_category_client.default_category_id
    WHERE default_category.id = any(%s);
    """
    try:
        cur.execute(query_sql,(categoria,))
        lista_selects = cur.fetchall()
        lista_selects = [item[0] for item in lista_selects]
        print('Select na tabela client feito com sucesso.')
    except (OperationalError, Error) as e:
        print(f"Erro ao executar o select na tabela client: {e}")
        lista_selects = []
    conn.close()
    return lista_selects

# Update na tabela group_message_control (distribuidas (int))
def update_group_message_control (distribuidas):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute('SET timezone to "GMT+3";')
    query_sql = """
    UPDATE group_message_control 
    SET distributed = distributed + %s 
    WHERE date = DAY_MONTH_YEAR();
    """
    try:
        cur.execute(query_sql,(distribuidas,))
        print('Update na tabela group_message_control realizado com sucesso')
    except (OperationalError, Error) as e:
        print(f"Erro ao dar update na tabela group_message_control: {e}")
    conn.commit()
    conn.close()

# Update no campo distributed da tabela group_message (distributed (int))
def update_group_message (quantidade):
    conn = conectar_bd()
    cur = conn.cursor()
    cur.execute('SET timezone to "GMT+3";')
    query_sql = """
    UPDATE group_message 
    SET distributed = %s 
    WHERE id = (SELECT id
    FROM group_message
	where date is not null and time is not null
    ORDER BY date DESC, time DESC 
    LIMIT 1)
    """
    try:
        cur.execute(query_sql, (quantidade,)) 
        print('Update na tabela group_message realizado com sucesso')
    except (OperationalError, Error) as e:
        print(f"Erro ao executar o update na tabela group_message: {e}")
    conn.commit()
    conn.close()