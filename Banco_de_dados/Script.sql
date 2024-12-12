-----------------------------
CREATE TABLE Default_Category 
( 
    name varchar(75),  
    id serial PRIMARY KEY
); 
-------------------
CREATE TABLE Client 
( 
    name varchar(120),  
    phone_number varchar(13) unique not null,  
    profession varchar(100) unique not null,  
    cpf varchar(11),  
    email varchar(260),
    date date,
    id serial PRIMARY KEY
);
--------------------------
CREATE TABLE Group_Message 
( 
    content text unique not null,  
    date date,  
    time time,  
    has_image boolean, 
	distributed int,
    id serial PRIMARY KEY
); 
-------------------------------------------
CREATE TABLE Default_Category_Group_Message
( 
    default_category_id INT REFERENCES Default_Category(id),  
    group_message_id INT REFERENCES Group_Message(id),  
    primary key(default_category_id, group_message_id)
); 
------------------------------------
CREATE TABLE Default_Category_Client 
( 
    client_id INT REFERENCES Client(id),  
    default_category_id INT REFERENCES Default_Category(id),  
    primary key(client_id, default_category_id)
); 
--------------------
CREATE TABLE Summary 
( 
    content text,  
    date date,    
    default_category_id INT REFERENCES Default_Category(id),  
    id serial PRIMARY KEY
); 
-----------------------------------
CREATE TABLE Prompt_Writer_Category 
( 
    name varchar(75),  
    id serial PRIMARY KEY
); 
----------------------------------
CREATE TABLE Prompt_Judge_Category 
( 
    name varchar(75),  
    id serial PRIMARY KEY
); 
---------------------------
CREATE TABLE Client_Message 
( 
    content text not null,  
    prompt_judge text,  
    prompt_sql text,  
    prompt_writer text,  
    date date,  
    time time,    
    client_id INT REFERENCES Client(id),  
    prompt_writer_category_id INT REFERENCES Prompt_Writer_Category(id),  
    prompt_judge_category_id INT REFERENCES Prompt_Judge_Category(id),  
    id serial PRIMARY KEY
); 
--------------------------------
CREATE TABLE Group_Message_Costs 
( 
    input_tokens int,  
    output_tokens int,  
    total_cost numeric,    
    group_message_id INT REFERENCES Group_Message(id),
    id serial PRIMARY KEY
); 
--------------------------------
CREATE TABLE Client_Message_Cost 
(   
    input_tokens INT,  
    output_tokens INT,  
    total_cost numeric,    
    client_message_id INT REFERENCES Client_Message(id),
    id serial PRIMARY KEY
); 
-------------------------------------------
CREATE OR REPLACE FUNCTION day_month_year()
RETURNS DATE AS 
$$
DECLARE
    year NUMERIC;
    month NUMERIC;
    day NUMERIC;
BEGIN 
    SELECT EXTRACT(YEAR FROM NOW()) INTO year;
    SELECT EXTRACT(MONTH FROM NOW()) INTO month;
    SELECT EXTRACT(DAY FROM NOW()) INTO day;

    RETURN TO_DATE(year || '-' || month || '-' || day, 'YYYY-MM-DD');
END;
$$ LANGUAGE plpgsql;
-----------------------------------------
CREATE OR REPLACE FUNCTION hour_min_sec()
RETURNS time AS 
$$
DECLARE
	hour INT;
	min INT;
	sec INT;
BEGIN 
	SELECT EXTRACT(HOUR FROM NOW()) INTO hour;
	SELECT EXTRACT(MINUTE FROM NOW()) INTO min;
	SELECT EXTRACT(SECOND FROM NOW()) INTO sec;
	RETURN (hour||':'||min||':'||sec)::TIME;
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------
CREATE OR REPLACE FUNCTION daily_group_message_cost()
RETURNS numeric AS 
$$
DECLARE
    total numeric;
BEGIN
    SELECT sum(total_cost) INTO total FROM group_message_cost where data = day_month_year();
    RETURN total;
END;
$$ LANGUAGE plpgsql;
----------------------------------------------------------------
CREATE OR REPLACE FUNCTION count_group_message_by_date_category(
    start_date DATE,
    end_date DATE,
    category_input VARCHAR(25)
)
RETURNS TABLE(quantity BIGINT, distributed BIGINT, clients BIGINT) AS $$
DECLARE
    query TEXT;
BEGIN
    -- Construir a consulta dinamicamente
    query := 'SELECT 
                count(*) AS quantity, 
                sum(distributed) AS distributed,
                (SELECT COUNT(DISTINCT client.id) AS clients
                 FROM group_message
                 JOIN default_category_group_message dm ON dm.group_message_id = group_message.id
                 JOIN default_category_client dc ON dc.default_category_id = dm.default_category_id
                 JOIN client ON client.id = dc.client_id
                 WHERE group_message.date IS NOT NULL 
                   AND group_message.time IS NOT NULL
                   AND client.datetime <= concat(group_message.date, '' '', group_message.time)::timestamp';

    -- Adiciona condições dinâmicas na subquery
    IF category_input IS NOT NULL THEN
        query := query || ' AND dm.default_category_id = ANY(string_to_array($1, '','')::INT[])';
    END IF;

    IF end_date IS NOT NULL THEN
        query := query || ' AND group_message.date <= $2';
    END IF;

    IF start_date IS NOT NULL THEN
        query := query || ' AND group_message.date >= $3';
    END IF;

    -- Fecha a subquery e o restante da consulta principal
    query := query || ') AS recipients
              FROM group_message
              WHERE id IN 
              (SELECT DISTINCT group_message.id FROM group_message
               FULL JOIN default_category_group_message ON group_message.id = default_category_group_message.group_message_id 
               WHERE TRUE';

    -- Adiciona condições dinâmicas na query principal
    IF category_input IS NOT NULL THEN
        query := query || ' AND default_category_group_message.default_category_id = ANY(string_to_array($1, '','')::INT[])';
    END IF;

    IF end_date IS NOT NULL THEN
        query := query || ' AND group_message.date <= $2';
    END IF;

    IF start_date IS NOT NULL THEN
        query := query || ' AND group_message.date >= $3';
    END IF;

    -- Fecha a subquery da query principal
    query := query || ')';

    -- Executa a consulta dinâmica com os parâmetros
    RETURN QUERY EXECUTE query USING category_input, end_date, start_date;
END;
$$ LANGUAGE plpgsql;
----------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_group_messages_by_date_category(
    start_date DATE,
    end_date DATE,
    category_input VARCHAR
)
RETURNS TABLE(
    content TEXT,
    date DATE,
    "time" TIME,
    has_image BOOLEAN,
    distributed int,
    category TEXT
) AS $$
DECLARE
    query TEXT;
BEGIN
    -- Construir a consulta dinamicamente
    query := '
        SELECT 
            gm.content, 
            gm.date, 
            gm.time, 
            gm.has_image, 
            gm.distributed,
            STRING_AGG(dc.name, '','') AS category
        FROM group_message gm
        JOIN default_category_group_message dcc ON gm.id = dcc.group_message_id
        JOIN default_category dc ON dc.id = dcc.default_category_id
        WHERE TRUE';

    -- Adiciona condição para 'category_input' (IDs separados por vírgulas)
    IF category_input IS NOT NULL THEN
        query := query || ' AND dc.id = ANY(string_to_array($1, '','')::INT[])';
    END IF;

    -- Adiciona filtros de data, se fornecidos
    IF start_date IS NOT NULL THEN
        query := query || ' AND gm.date >= $2';
    END IF;

    IF end_date IS NOT NULL THEN
        query := query || ' AND gm.date <= $3';
    END IF;

    -- Agrupar e ordenar os resultados
    query := query || '
        GROUP BY gm.content, gm.date, gm.time, gm.has_image, gm.distributed
        ORDER BY gm.date, gm.time';

    -- Executar a consulta dinâmica com os parâmetros
    RETURN QUERY EXECUTE query USING category_input, start_date, end_date;
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------
CREATE OR REPLACE PROCEDURE insert_new_client(
	cpf_input varchar(11),
	phone_number_input varchar(13),
	email_input varchar(260), 
	category varchar(25), 
	name_input varchar(120),
	birth_date_input date,
	company_input varchar(100),
	position_input varchar(100)
)
	
LANGUAGE plpgsql AS $$

DECLARE
    idClient int;
BEGIN
    -- Inserir o cliente e recuperar o código gerado
    INSERT INTO client (phone_number, name, cpf, email, company, position, birth_date)
    VALUES (phone_number_input, name_input, cpf_input, email_input, company_input, position_input, birth_date_input)
	RETURNING id INTO idClient;

    -- Inserir as categorias relacionadas
    INSERT INTO default_category_client (client_id, default_category_id)
    SELECT idClient, CAST(category_now AS INTEGER)
    FROM unnest(string_to_array(category, ',')) AS category_now;
		
	EXCEPTION
	WHEN OTHERS THEN
		RAISE NOTICE 'Falha no insert de categoria_cliente ou no insert do cliente: %', SQLERRM;
END; $$;
-----------------------------------------------------------
CREATE OR REPLACE PROCEDURE insert_client_message_and_cost(
    phone_number_input varchar(13),
    content_input text,
    prompt_judge_input text,
    prompt_sql_input text,
    prompt_writer_input text, 
    input_tokens_input INT,
    output_tokens_input INT,
    total_cost_input numeric,
    prompt_writer_category_id_input INT,
    prompt_sql_category_id_input INT
)
LANGUAGE plpgsql AS $$

DECLARE
    idClient INT;
    idMessage INT;  -- Variável para armazenar o ID da mensagem
BEGIN
    -- Selecionar o id do cliente pelo telefone
    SELECT id INTO idClient 
    FROM client 
    WHERE phone_number = phone_number_input;

    -- Verificar se o cliente foi encontrado
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cliente com telefone % não encontrado.', phone_number_input;
    END IF;

    -- Inserir a mensagem do cliente e recuperar o ID gerado
    INSERT INTO client_message 
    (content, prompt_judge, prompt_sql, prompt_writer, date, time, client_id, prompt_writer_category_id, prompt_sql_category_id)
    VALUES 
    (content_input, prompt_judge_input, prompt_sql_input, prompt_writer_input, day_month_year(), hour_min_sec(), idClient, prompt_writer_category_id_input, prompt_sql_category_id_input)
    RETURNING id INTO idMessage;

    -- Inserir o custo relacionado à mensagem do cliente usando o idMessage
    INSERT INTO client_message_cost 
    (input_tokens, output_tokens, total_cost, client_message_id)
    VALUES 
    (input_tokens_input, output_tokens_input, total_cost_input, idMessage);

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Falha ao inserir client_message ou client_message_cost: %', SQLERRM;
END; $$;
----------------------------------------------------------
CREATE OR REPLACE PROCEDURE delete_client_by_phone_number(
	phone_number_input varchar(15)
)
LANGUAGE plpgsql AS $$
DECLARE
    idClient INTEGER;
BEGIN
    -- Seleciona o código do cliente com base no CPF informado
    SELECT id INTO idClient FROM client WHERE phone_number = phone_number_input;

    -- Verifica se o cliente existe antes de tentar deletar
    IF idClient IS NOT NULL THEN
        -- Apagar registros nas tabelas relacionadas com fk para o client_id
        DELETE FROM client_message_cost WHERE client_message_id IN 
        (SELECT id FROM client_message WHERE client_id = idClient);

        DELETE FROM client_message_unresponded WHERE client_message_id IN 
        (SELECT id FROM client_message WHERE client_id = idClient);

        DELETE FROM client_message WHERE client_id = idClient;

        DELETE FROM default_category_client WHERE client_id = idClient;

        -- Apagar o cliente
        DELETE FROM client WHERE id = idClient;

        ELSE
        RAISE NOTICE 'Cliente com CPF % não encontrado.', cpf_input;
    END IF;
END; $$;
-------------------------------------------------------
CREATE OR REPLACE PROCEDURE insert_group_category_cost(
    category INTEGER[],
    cost numeric, 
    input_token int, 
    output_token int
)
LANGUAGE plpgsql
AS $$
DECLARE
    idMessage INT;
BEGIN
    -- Seleciona o código da mensagem mais recente, data e hora
    SELECT id into idMessage
    FROM group_message
	where date is not null and time is not null
    ORDER BY date DESC, time DESC 
    LIMIT 1;
   
    -- Inserir as categorias relacionadas
    INSERT INTO default_category_group_message (group_message_id, default_category_id)
    SELECT idMessage, unnest(category);
    
    -- Inserir os custos na tabela financeiro
    INSERT INTO group_message_cost(total_cost, input_tokens, output_tokens, group_message_id)
    VALUES (cost, input_token, output_token, idMessage);
    
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Falha no insert cost ou no insert default_category: %', SQLERRM;
END;
$$;
---------------------------------------------
create or replace view group_message_today as
 SELECT gm.date,
    gm."time",
    gm.content,
    gm.has_image,
    dc.name
   FROM group_message gm
     JOIN default_category_group_message dcgm ON gm.id = dcgm.group_message_id
     JOIN default_category dc ON dc.id = dcgm.default_category_id
  WHERE gm.date = day_month_year()
  ORDER BY gm.date;
-----------------------------------------------
create or replace view group_message_control as
SELECT sum(distributed) AS distributed,count(*) AS registered,date
FROM group_message
WHERE date IS NOT NULL
GROUP BY date
ORDER BY date DESC;
