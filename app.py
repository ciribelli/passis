import io
from flask import Flask, request, Response, json, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from flask_migrate import Migrate
from dotenv import load_dotenv
import os

import context_gpt35turbo
import context_gpt35turboFuncCalling
import main, chathub
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests

load_dotenv()

app = Flask(__name__)
# configuracao do url db postgres externo ou local (arquivo .env deve estar na raiz do projeto)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL_EXTERNA')
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Whatsapp webhook token:
token = os.environ.get('WHATSAPP_TOKEN')
verify_token = os.environ.get('VERIFY_TOKEN')

# Rota principal (página inicial)
@app.route('/')
def index():
    return "Servidor ativo"

@app.route('/v1/jogos/<data_hora>', methods=['GET'])
def get_jogos(data_hora):
    jogos = main.get_jogos(data_hora)
    return Response(response=jogos, status=200, mimetype='application/json')

@app.route('/v1/time/<nome_time>', methods=['GET'])
def get_time(nome_time):
    jogos = main.get_time(nome_time)
    return Response(response=jogos, status=200, mimetype='application/json')

@app.route('/v1/x/<perfil>', methods=['GET'])
def get_X(perfil):
    token = os.getenv('token_X')
    info_from_X = main.busca_X(perfil, token)
    return Response(response=info_from_X, status=200, mimetype='application/json')

@app.route('/v1/clima', methods=['GET'])
def get_clima():
    token = os.getenv('token_clima')
    coletor, resposta = main.busca_Clima(token)
    return Response(response=resposta, status=200, mimetype='application/json')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # Verifica se o objeto 'object' está presente no corpo da solicitação
    if 'object' in data:
        entry = data.get('entry', [])[0]
        chathub.chatflow(entry)
    return '', 200


@app.route('/webhook', methods=['GET'])
def verify_webhook():

    # Analise os parâmetros da solicitação de verificação do webhook
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    # Verifique se um token e modo foram enviados
    if mode and token:
        # Verifique se o modo e o token enviados estão corretos
        if mode == "subscribe" and token == verify_token:
            # Responda com 200 OK e o token de desafio da solicitação
            return challenge, 200
        else:
            # Responda com '403 Forbidden' se os tokens de verificação não coincidirem
            return "Forbidden", 403

    return "Bad Request", 400

# Modelos

class Checkin(db.Model):
    __tablename__ = 'checkins'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    direction = db.Column(db.String(10))
    checkin = db.Column(db.String(100))

    def __init__(self, direction, checkin, data=None):
        self.direction = direction
        self.checkin = checkin
        if data is None:
            data = datetime.utcnow()
        self.data = data


# referencia do crud https://stackabuse.com/using-sqlalchemy-with-flask-and-postgresql/
# $ flask db init
# $ flask db migrate
# $ flask db upgrade
@app.route('/checkin', methods=['POST', 'GET'])
def handle_checkin():
    if request.method == 'POST':
        if request.is_json:
            dados = request.get_json()
            new_checkin = Checkin(checkin=dados['checkin'], direction=dados['direction'], data=dados['data'])
            db.session.add(new_checkin)
            db.session.commit()
            return {"message": f"checkin em {new_checkin.checkin} foi criado com sucesso."}
        else:
            return {"error": "Formato diferente de JSON"}

    elif request.method == 'GET':
        checkins = Checkin.query.all()
        results = [
            {
                "id": checkin.id,
                "data": checkin.data,
                "direction": checkin.direction,
                "checkin": checkin.checkin
            } for checkin in checkins]

        return {"count": len(results), "checkins": results}

@app.route('/checkin/<checkin_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_checkin_id(checkin_id):
    checkin = Checkin.query.get_or_404(checkin_id)

    if request.method == 'GET':
        response = {
            "id": checkin.id,
            "direction": checkin.direction,
            "checkin": checkin.checkin,
            "data": checkin.data
        }
        return {"message": "success", "checkin": response}

    elif request.method == 'PUT':
        dados = request.get_json()
        checkin.direction = dados['direction']
        checkin.checkin = dados['checkin']
        checkin.data = dados['data']
        db.session.add(checkin)
        db.session.commit()
        return {"message": f"checkin {checkin.checkin} successfully updated"}

    elif request.method == 'DELETE':
        db.session.delete(checkin)
        db.session.commit()
        return {"message": f"Checkin {checkin.checkin} successfully deleted."}

# Função para recuperar checkins com base em diferentes critérios temporais
def get_checkins_by_date(start_date=None, end_date=None):
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%d-%m-%Y')
        end_date = datetime.strptime(end_date, '%d-%m-%Y') + timedelta(days=1)
        checkins = Checkin.query.filter(Checkin.data.between(start_date, end_date)).order_by(Checkin.data).all()

    # Função para extrair o horário da data
    def extract_time(date_obj):
        return date_obj.strftime('%H:%M')

    # Função para formatar a data
    def format_date(date_obj):
        return date_obj.strftime('%d/%m/%Y')

    # Dicionário para armazenar os dados agrupados por dia
    daily_entries = {}

    # Organizar os dados por dia
    for entry in checkins:
        formatted_date = format_date(entry.data)
        cidade = get_cidade(formatted_date)
        print(cidade, '-------------')
        day_entries = daily_entries.get(formatted_date, [])
        day_entries.append({'hour': extract_time(entry.data), 'checkin': entry.checkin})
        daily_entries[formatted_date] = day_entries

    result_string = ""
    for date, entries in daily_entries.items():
        result_string += f'📅 {date} \n'
        for entry in entries:
            result_string += f'✅ {entry["hour"]}  {entry["checkin"]}\n'

    return result_string
# ______________________


class Clima(db.Model):
    __tablename__ = 'climas'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String)  # Manter o formato ISO 8601
    umidade = db.Column(db.Float)
    temperatura = db.Column(db.String)
    probabilidade = db.Column(db.Float)
    velvento = db.Column(db.String)
    condicao = db.Column(db.String)
    cidade = db.Column(db.String)

    def __init__(self, data, umidade, temperatura, probabilidade, velvento, condicao, cidade):
        self.data = data
        self.umidade = umidade
        self.temperatura = temperatura
        self.probabilidade = probabilidade
        self.velvento = velvento
        self.condicao = condicao
        self.cidade = cidade

@app.route('/adicionar_clima', methods=['POST'])
def adicionar_clima():
    dados = request.json

    data = dados['data']
    umidade = dados['umidade']
    temperatura = dados['temperatura']
    probabilidade = dados['probabilidade']
    velvento = dados['velvento']
    condicao = dados['condicao']
    cidade = dados['cidade']

    novo_clima = Clima(data=data, umidade=umidade, temperatura=temperatura, probabilidade=probabilidade, velvento=velvento, condicao=condicao, cidade=cidade)
    db.session.add(novo_clima)
    db.session.commit()

    return {"message": "Dados de clima adicionados com sucesso!"}

@app.route('/obter_climas', methods=['GET'])
def obter_climas():
    climas = Clima.query.all()
    clima_lista = []

    for clima in climas:
        clima_dict = {
            'id': clima.id,
            'data': clima.data,
            'umidade': clima.umidade,
            'temperatura': clima.temperatura,
            'probabilidade': clima.probabilidade,
            'velvento': clima.velvento,
            'condicao': clima.condicao,
            'cidade': clima.cidade
        }
        clima_lista.append(clima_dict)

    return {"message": "success", "climas": clima_lista}

@app.route('/deletar_clima/<int:clima_id>', methods=['DELETE'])
def deletar_clima(clima_id):
    clima = Clima.query.get(clima_id)
    
    if clima:
        db.session.delete(clima)
        db.session.commit()
        return {"message": f"Registro de clima {clima_id} deletado com sucesso."}
    else:
        return {"message": f"Registro de clima {clima_id} não encontrado."}, 404

def get_cidade(date=None):
    if date:
        try:
            date = datetime.strptime(date, '%Y-%m-%dT%H:%M:%S%z')
            clima = Clima.query.filter_by(data=date).first()
            if clima:
                return clima.cidade
            else:
                return "Dados não encontrados para a data fornecida"
        except ValueError:
            return "Formato de data inválido. Use o formato '%Y-%m-%dT%H:%M:%S%z'."
    else:
        return "Por favor, forneça uma data válida"

# Classe documentos
class DocumentoBinario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_do_documento = db.Column(db.String(255))
    descricao = db.Column(db.Text)
    binario_data = db.Column(db.LargeBinary)
    data_de_upload = db.Column(db.TIMESTAMP, server_default=db.func.now())
    versao = db.Column(db.Integer, default=1)

@app.route('/criar_documento', methods=['POST'])
def criar_documento():
    try:
        nome = request.form.get('nome_do_documento')
        descricao = request.form.get('descricao')
        arquivo = request.files['arquivo']  # Assumindo que o arquivo binário é enviado como um arquivo

        novo_documento = DocumentoBinario(
            nome_do_documento=nome,
            descricao=descricao,
            binario_data=arquivo.read()
        )

        db.session.add(novo_documento)
        db.session.commit()

        # Substitua jsonify por json.dumps para criar uma resposta JSON
        return json.dumps({'mensagem': 'Documento binário criado com sucesso!'})
    except Exception as e:
        # Substitua jsonify por json.dumps para criar uma resposta JSON de erro
        return json.dumps({'erro': str(e)})

# Rota para recuperar um documento binário pelo ID
@app.route('/recuperar_documento/<int:documento_id>', methods=['GET'])
def recuperar_documento(documento_id):
    try:
        documento = DocumentoBinario.query.get(documento_id)

        if documento:
            # Crie uma resposta Flask com o arquivo binário e o tipo MIME adequados (imagem/jpeg para JPG)
            return send_file(io.BytesIO(documento.binario_data), mimetype='image/jpeg')

        return json.dumps({'erro': 'Documento não encontrado.'}), 404
    except Exception as e:
        return json.dumps({'erro': str(e)})

# recuperar uma lista com todos os documentos
@app.route('/recuperar_lista_documentos', methods=['GET'])
def recuperar_lista_documentos():
    try:
        # Consulta o banco de dados para obter todos os documentos
        documentos = DocumentoBinario.query.all()

        # Crie uma lista para armazenar os dados dos documentos
        lista_documentos = []

        # Itera pelos documentos e cria um dicionário para cada um
        for documento in documentos:
            documento_info = {
                'id': documento.id,
                'nome_do_documento': documento.nome_do_documento,
                'descricao': documento.descricao,
                'data_de_upload': documento.data_de_upload.strftime('%Y-%m-%d %H:%M:%S'),
                'versao': documento.versao
            }
            lista_documentos.append(documento_info)

        # Converte a lista em JSON e retorna como resposta
        return json.dumps(lista_documentos)
    except Exception as e:
        # Em caso de erro, retorna uma resposta de erro JSON
        return json.dumps({'erro': str(e)})

# Rota para excluir um documento pelo ID
@app.route('/excluir_documento/<int:documento_id>', methods=['DELETE'])
def excluir_documento(documento_id):
    try:
        documento = DocumentoBinario.query.get(documento_id)

        if documento:
            db.session.delete(documento)
            db.session.commit()
            return json.dumps({'mensagem': 'Documento excluído com sucesso!'})
        else:
            return json.dumps({'erro': 'Documento não encontrado.'}), 404
    except Exception as e:
        return json.dumps({'erro': str(e)}), 500

# Rota para atualizar informações de um documento pelo ID
@app.route('/atualizar_documento/<int:documento_id>', methods=['PUT'])
def atualizar_documento(documento_id):
    try:
        documento = DocumentoBinario.query.get(documento_id)

        if documento:
            nome = request.form.get('nome_do_documento')
            descricao = request.form.get('descricao')

            # Atualiza as informações do documento
            documento.nome_do_documento = nome
            documento.descricao = descricao

            db.session.commit()
            return json.dumps({'mensagem': 'Documento atualizado com sucesso!'})
        else:
            return json.dumps({'erro': 'Documento não encontrado.'}), 404
    except Exception as e:
        return json.dumps({'erro': str(e)}), 500



# Rota para criar registros simples de memoria
class Memoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(10000), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, content):
        self.content = content

# salvando memorias diretamente sem uso da API
def salvar_memoria_recebida(content):
    memoria = Memoria(content=content)
    db.session.add(memoria)
    db.session.commit()
    return "Memória eternizada ✅"

@app.route('/memorias', methods=['POST'])
def create_memoria():
    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content')

        if not content:
            return Response(json.dumps({'message': 'O campo "content" é obrigatório'}), status=400, content_type='application/json')

        nova_memoria = Memoria(content=content)

        db.session.add(nova_memoria)
        db.session.commit()

        return Response(json.dumps({'message': 'Nova memória criada com sucesso!'}), status=201, content_type='application/json')

@app.route('/memorias', methods=['GET'])
def get_memorias():
    if request.method == 'GET':
        memorias = Memoria.query.order_by(Memoria.date_created.desc()).all()
        serialized_memorias = [{'id': memoria.id, 'content': memoria.content, 'date_created': memoria.date_created.strftime('%Y-%m-%d %H:%M:%S')} for memoria in memorias]

        return Response(json.dumps(serialized_memorias), status=200, content_type='application/json')


# Rota para registrar Threads com o Assistente
class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(5000), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, content):
        self.content = content

# salvando thread diretamente sem uso da API
def salvar_thread(content):
    thread = Thread(content=content)
    db.session.add(thread)
    db.session.commit()
    return "Thread registrada ✅"

@app.route('/threads', methods=['GET'])
def get_threads():
    if request.method == 'GET':
        threads = Thread.query.order_by(Thread.date_created.desc()).limit(6).all()
        serialized_threads = [thread.content for thread in threads]
        return serialized_threads, 200

@app.route('/apagar_threads', methods=['DELETE'])
def apagar_threads():
    try:
        # Apaga todos os itens da tabela Thread
        Thread.query.delete()
        db.session.commit()
        return "Todos os itens da tabela Thread foram apagados", 200
    except Exception as e:
        db.session.rollback()
        return f"Erro ao apagar itens da tabela Thread: {str(e)}", 500


# Embeddings ----------------
class VectorEmbedding(db.Model):
    __tablename__ = 'vectors'

    id = db.Column(db.Integer, primary_key=True)
    tabela = db.Column(db.String)
    index = db.Column(db.Integer)
    texto = db.Column(db.String)
    n_tokens = db.Column(db.Integer)
    embeddings = db.Column(JSONB)  # Correção aqui

@app.route('/recuperar_dados', methods=['GET'])
def recuperar_dados():
    try:
        # Consulte todos os registros na tabela VectorEmbedding
        registros = VectorEmbedding.query.all()

        # Crie uma lista de dicionários para representar os registros
        dados = [
            {
                'id': registro.id,
                'tabela': registro.tabela,
                'index': registro.index,
                'texto': registro.texto,
                'n_tokens': registro.n_tokens,
                'embeddings': registro.embeddings
            }
            for registro in registros
        ]

        # Retorne os dados como JSON
        return json.dumps(dados)
    except Exception as e:
        return str(e), 400

# busca as memorias e registros do DB
# calcula n_tokens, embeddings e retorna para o DB
@app.route('/inserir_dados', methods=['POST'])
def inserir_dados():
    # primeiro apago todos os embeddings
    apagar_todos_os_embeddings()

    import embeddings_db
    df = embeddings_db.atualiza_embedding()
    print(df)

    for index, row in df.iterrows():
        novo_registro = VectorEmbedding(
            tabela=row['tabela'],
            index=row['index'],
            texto=row['texto'],
            n_tokens=row['n_tokens'],
            embeddings=row['embeddings']
        )
        db.session.add(novo_registro)

        # Commit das alterações ao banco de dados
    db.session.commit()

    return 'Dados atualizados ✅'

@app.route('/apagar_todos_os_embeddings', methods=['DELETE'])
def apagar_todos_os_embeddings():
    try:
        num_registros_apagados = db.session.query(VectorEmbedding).delete()
        db.session.commit()
        response_data = {'message': f'{num_registros_apagados} registros apagados com sucesso.'}
        response = Response(json.dumps(response_data), status=200, content_type='application/json'
        )
        return response
    except Exception as e:
        return str(e), 400

    
def fazer_perguntas(pergunta, data_atual, hora_atual):
    try:
        registros = VectorEmbedding.query.all()

        dados = [
            {
                'id': registro.id,
                'tabela': registro.tabela,
                'index': registro.index,
                'texto': registro.texto,
                'n_tokens': registro.n_tokens,
                'embeddings': registro.embeddings
            }
            for registro in registros
        ]
        threads = Thread.query.with_entities(Thread.content).order_by(Thread.date_created.desc()).limit(4).all()
        #saida, first_item = context_gpt35turbo.responde_emb(pergunta, dados, threads, data_atual, hora_atual)
        saida, first_item = context_gpt35turboFuncCalling.responde_emb(pergunta, dados, threads, data_atual, hora_atual)
        return saida, first_item
    except Exception as e:
        return str(e), 400

def plota_grafico(checkin_type, color):
    # Dados fictícios para simular check-ins
    fake_checkins = [
        {'checkin': checkin_type, 'data': '2023-09-03', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-05', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-07', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-08', 'direction': 'out'},
        {'checkin': checkin_type, 'data': '2023-09-10', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-12', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-15', 'direction': 'out'},
        {'checkin': checkin_type, 'data': '2023-09-16', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-18', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-20', 'direction': 'out'},
        {'checkin': checkin_type, 'data': '2023-09-22', 'direction': 'in'},
        {'checkin': checkin_type, 'data': '2023-09-23', 'direction': 'in'},
    ]

    # Convertendo datas de string para objetos datetime
    for checkin in fake_checkins:
        checkin['data'] = datetime.strptime(checkin['data'], '%Y-%m-%d').date()

    # Criar um dicionário com contagem de check-ins por dia
    counts_by_day = {date: 0 for date in sorted(set(checkin['data'] for checkin in fake_checkins))}

    # Contar os check-ins do tipo específico e direção por dia
    for checkin in fake_checkins:
        if checkin['checkin'] == checkin_type and checkin['direction'] == 'in':
            counts_by_day[checkin['data']] += 1

    # Ordenar as datas e contagens
    sorted_dates = sorted(counts_by_day.keys())
    sorted_counts = [counts_by_day[date] for date in sorted_dates]

    # Criar o gráfico de barras
    plt.figure(figsize=(10, 6))
    plt.bar(sorted_dates, sorted_counts, color=color)

    plt.title(f'Número de Check-ins do Tipo "{checkin_type}"')
    plt.xlabel('Data')
    plt.ylabel('Número de Check-ins')
    plt.yticks(range(max(sorted_counts) + 2))
    plt.gca().yaxis.grid(True, linestyle='--')
    plt.tight_layout()

    # Salvar o gráfico como imagem e retornar o nome do arquivo
    img_filename = f"{checkin_type}_checkins.png"
    plt.savefig(img_filename)
    plt.close()

    # Obter o caminho absoluto do arquivo
    full_path = os.path.abspath(img_filename)

    url = str(os.getenv('url')) + "criar_documento"

    payload = {'nome_do_documento': 'grafico',
               'descricao': 'grafico gerado automaticamente para checkin do tipo ' + checkin_type}
    files = [
        ('arquivo', ('grafico.jpg', open(full_path, 'rb'), 'image/jpeg'))
    ]
    headers = {}

    response = requests.post(url, data=payload, files=files)
    print('Imagem gravada nas nuvens!')
    return full_path



# Executa o aplicativo Flask
if __name__ == '__passis__':
    app.run(port=int(os.environ.get('PORT', 1337)))