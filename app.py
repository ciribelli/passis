import io
from flask import Flask, request, Response, json, send_file, current_app
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
import pandas as pd
import context_FuncCalling
import main, chathub
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import requests
import threading
import pytz
from flask_cors import CORS
from sqlalchemy import text # necessidade para o endpoint de predicoes
load_dotenv()

app = Flask(__name__)
CORS(app) # Habilita CORS para todas as rotas para viabilizar request da web
# configuracao do url db postgres externo ou local (arquivo ..env deve estar na raiz do projeto)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL_AZURE')
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Whatsapp webhook token:
token = os.environ.get('WHATSAPP_TOKEN')
verify_token = os.environ.get('VERIFY_TOKEN')

# Rota principal (página inicial)
@app.route('/')
def index():
    return "Servidor ativo"


@app.route('/log')
def log():
    with open("logs.txt", "r") as file:
        logs = file.readlines()
    return Response(logs, mimetype="text/plain")

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
    info_from_X = main.busca_X2(token)
    return Response(response=info_from_X, status=200, mimetype='application/json')

@app.route('/v1/clima', methods=['GET'])
def get_clima():
    token = os.getenv('token_clima')
    coletor, resposta = main.busca_Clima(token)
    return Response(response=resposta, status=200, mimetype='application/json')

def process_message(entry):
    # Cria um contexto da app dentro da thread
    with app.app_context():
        chathub.chatflow(entry)  # agora sua função pode acessar db.session

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print('-------------------------')
    print(data)
    print('-------------------------')

    if 'object' in data:
        entry = data.get('entry', [])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        # Processa apenas se houver 'messages'
        if "messages" in value:
            # Passa somente a entrada que contém a mensagem
            threading.Thread(target=process_message, args=(entry,)).start()

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
    # Função para converter objetos Checkin em dicionários
    def serialize_checkin(checkin):
        return {
            'id': checkin.id,
            'data': str(checkin.data),
            'direction': checkin.direction,
            'checkin': checkin.checkin
        }
    # Serializando a lista de checkins
    serialized_checkins = [serialize_checkin(checkin) for checkin in checkins]
    # Serializando a lista de checkins para JSON
    json_result = json.dumps([serialize_checkin(checkin) for checkin in checkins], default=str)
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
        day_entries = daily_entries.get(formatted_date, [])
        day_entries.append({'hour': extract_time(entry.data), 'checkin': entry.checkin})
        daily_entries[formatted_date] = day_entries
    result_string = ""
    for date, entries in daily_entries.items():
        result_string += f'📅 {date} \n'
        for entry in entries:
            result_string += f'✅ {entry["hour"]}  {entry["checkin"]}\n'
    return result_string, json_result
# ______________________

class Clima(db.Model):
    __tablename__ = 'climas'
    id = db.Column(db.Integer, primary_key=True)
    #data = db.Column(db.String)
    data = db.Column(db.DateTime)  # Alteração para o tipo DateTime
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
# funcao nao utilizada:
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

# para ser utilizado pelas functions:
def obter_cidade_atual_e_clima(start_date=None, end_date=None):
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%d-%m-%Y')
        end_date = datetime.strptime(end_date, '%d-%m-%Y') + timedelta(days=1)
        climas = Clima.query.filter(Clima.data.between(start_date, end_date)).order_by(Clima.data).all()
    # Função para converter objetos Clima em dicionários
    def serialize_clima(clima):
        return {
            'id': clima.id,
            'data': str(clima.data),
            'umidade': clima.umidade,
            'temperatura': clima.temperatura,
            'probabilidade': clima.probabilidade,
            'velvento': clima.velvento,
            'condicao': clima.condicao,
            'cidade': clima.cidade
        }
    # Serializando a lista de checkins
    serialized_checkins = [serialize_clima(clima) for clima in climas]
    # Serializando a lista de checkins para JSON
    json_result = json.dumps([serialize_clima(clima) for clima in climas], default=str)
    # Função para extrair o horário da data
    def extract_time(date_obj):
        return date_obj.strftime('%H:%M')
    # Função para formatar a data
    def format_date(date_obj):
        return date_obj.strftime('%d/%m/%Y')
    # Dicionário para armazenar os dados agrupados por dia
    daily_entries = {}
    # Organizar os dados por dia
    for entry in climas:
        formatted_date = format_date(entry.data)
        day_entries = daily_entries.get(formatted_date, [])
        day_entries.append({'hour': extract_time(entry.data), 'cidade': entry.cidade, 'temperatura': entry.temperatura, 'umidade': entry.umidade, 'velvento': entry.velvento})
        daily_entries[formatted_date] = day_entries
    result_string = ""
    for date, entries in daily_entries.items():
        result_string += f'📅 {date} \n'
        for entry in entries:
            result_string += f'🧭 {entry["hour"]}  {entry["cidade"]} {entry["temperatura"]} {entry["umidade"]} {entry["velvento"]}\n'
    return result_string, json_result

@app.route("/get_last_weather_ML", methods=["GET"])
def get_last_weather_ML():
    input_data_str = request.args.get("data")

    if not input_data_str:
        return {"error": "Parâmetro ?data=YYYY-MM-DD HH:MM:SS é obrigatório"}, 400

    try:
        input_data = datetime.strptime(input_data_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"error": "Formato inválido. Use YYYY-MM-DD HH:MM:SS"}, 400

    clima = (
        Clima.query
        .filter(Clima.data <= input_data)
        .order_by(Clima.data.desc())
        .first()
    )

    if not clima:
        return {"error": "Nenhum dado climático encontrado antes da data informada"}, 404

    # normaliza vento
    vel_raw = str(clima.velvento)
    vel_raw = vel_raw.replace("km/h", "").replace("KM/H", "").replace(",", ".").strip()
    vel = float(vel_raw)

    json_result = {
        "ultimo_clima": str(clima.data),
        "temperatura": clima.temperatura.replace("°C", ""),
        "umidade": clima.umidade,
        "probabilidade": clima.probabilidade,
        "velvento": vel,
        "condicao": clima.condicao,
        "cidade": clima.cidade
    }

    texto = (
        "🌦 Última medição climática\n"
        f"Data: {clima.data}\n"
        f"Condição: {clima.condicao}\n"
        f"🌡️ {clima.temperatura}  💧 {clima.umidade}%  💨 {vel} km/h\n"
        f"Cidade: {clima.cidade}"
    )

    return {"json": json_result, "texto": texto}

# ------- predicoes ---
@app.route('/predicoes', methods=['GET'])
def get_predicoes():
    """
    Retorna logs de inference filtrados por data e opcionalmente por model_name.
    
    Query params:
    - data: YYYY-MM-DD (obrigatório)
    - model_name: string (opcional)
    - limit: int (default: 100, max: 1000)
    - offset: int (default: 0)
    """
    data_param = request.args.get('data')
    model_name = request.args.get('model_name')
    timezone_param = request.args.get('timezone', os.getenv('APP_TIMEZONE', 'America/Sao_Paulo'))
    
    # Validação de data
    if not data_param:
        return Response(
            json.dumps({'error': 'Parâmetro ?data=YYYY-MM-DD é obrigatório'}),
            status=400,
            content_type='application/json'
        )
    
    try:
        # Parse data em horário local
        data_local = datetime.strptime(data_param, '%Y-%m-%d').date()
        
        # Converter pra UTC usando timezone do usuário
        user_timezone = pytz.timezone(timezone_param)
        start_local = user_timezone.localize(datetime.combine(data_local, datetime.min.time()))
        start_utc = start_local.astimezone(pytz.UTC)
        
        data_param_formatted = start_utc.date()
    except ValueError:
        return Response(
            json.dumps({'error': 'Formato de data inválido. Use YYYY-MM-DD'}),
            status=400,
            content_type='application/json'
        )
    
    # Paginação
    try:
        limit = min(int(request.args.get('limit', 100)), 1000)  # Max 1000
        offset = int(request.args.get('offset', 0))
    except ValueError:
        return Response(
            json.dumps({'error': 'limit e offset devem ser números inteiros'}),
            status=400,
            content_type='application/json'
        )
    
    try:
        # Range da data (usando timestamptz)
        start_of_day = datetime.combine(data_param_formatted, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        # Query base
        query = """
            SELECT 
                id, model_name, model_version, inference_datetime, 
                prediction, evento_anterior_int, hora_decimal, 
                delta_tempo, cidade_int, dia_semana, context_features, created_at
            FROM ml.inference_log
            WHERE inference_datetime >= :start AND inference_datetime < :end
        """
        
        params = {"start": start_of_day, "end": end_of_day}
        
        # Filtro opcional por model_name
        if model_name:
            query += " AND model_name = :model_name"
            params["model_name"] = model_name
        
        # Ordenação e paginação
        query += " ORDER BY inference_datetime DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        # Executar query
        predicoes = db.session.execute(
            text(query),
            params
        ).fetchall()
        
        # Serializar resultados
        resultado = []
        # Timezone pra conversão de saída (default: UTC)
        output_tz = pytz.timezone(request.args.get('return_timezone', 'UTC'))
        
        for idx, pred in enumerate(predicoes):
            # JSONB do PostgreSQL já vem como dict/parsed
            context_features = pred.context_features
            
            # Converter timestamp pra timezone desejado
            inference_dt = pred.inference_datetime
            
            # DEBUG: primeiros 3 registros
            if idx < 3:
                current_app.logger.info(f"=== PRED {idx} ===")
                current_app.logger.info(f"inference_dt raw: {inference_dt}")
                current_app.logger.info(f"inference_dt type: {type(inference_dt)}")
                current_app.logger.info(f"inference_dt tzinfo: {inference_dt.tzinfo}")
                current_app.logger.info(f"inference_dt utcoffset: {inference_dt.utcoffset()}")
            
            # timestamptz do PostgreSQL já vem com timezone info
            if inference_dt.tzinfo is None:
                # Se não tiver tzinfo, assume UTC
                inference_dt = pytz.UTC.localize(inference_dt)
            else:
                # Converte pra UTC primeiro
                inference_dt = inference_dt.astimezone(pytz.UTC)
            
            # Agora converte pra timezone desejado
            inference_dt_local = inference_dt.astimezone(output_tz)
            
            if idx < 3:
                current_app.logger.info(f"inference_dt_local: {inference_dt_local}")
                current_app.logger.info(f"inference_dt_local str: {inference_dt_local.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Mesmo pra created_at (que é timestamp sem tz)
            created_at_dt = pred.created_at
            if created_at_dt:
                if created_at_dt.tzinfo is None:
                    created_at_dt = pytz.UTC.localize(created_at_dt)
                created_at_local = created_at_dt.astimezone(output_tz)
            else:
                created_at_local = None
            
            resultado.append({
                'id': pred.id,
                'model_name': pred.model_name,
                'model_version': pred.model_version,
                'inference_datetime': inference_dt_local.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                'prediction': float(pred.prediction),
                'evento_anterior_int': int(pred.evento_anterior_int),
                'hora_decimal': float(pred.hora_decimal),
                'delta_tempo': float(pred.delta_tempo) if pred.delta_tempo else None,
                'cidade_int': int(pred.cidade_int) if pred.cidade_int else None,
                'dia_semana': int(pred.dia_semana) if pred.dia_semana else None,
                'context_features': context_features,
                'created_at': created_at_local.strftime('%Y-%m-%d %H:%M:%S') if created_at_local else None
            })
        
        # Total count para paginação
        count_query = """
            SELECT COUNT(*) as total
            FROM ml.inference_log
            WHERE inference_datetime >= :start AND inference_datetime < :end
        """
        
        count_params = {"start": start_of_day, "end": end_of_day}
        if model_name:
            count_query += " AND model_name = :model_name"
            count_params["model_name"] = model_name
        
        total = db.session.execute(
            text(count_query),
            count_params
        ).scalar()
        
        # Response com metadata
        response_data = {
            'data': resultado,
            'pagination': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'returned': len(resultado)
            }
        }
        
        return Response(
            json.dumps(response_data),
            status=200,
            content_type='application/json'
        )
    
    except Exception as e:
        current_app.logger.error(f"Erro em /predicoes: {str(e)}", exc_info=True)
        return Response(
            json.dumps({'error': f'Erro ao processar requisição: {str(e)}'}),
            status=500,
            content_type='application/json'
        )
# --- fim predicoes ---

if __name__ == '__main__':
    app.run(debug=True)

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

@app.route('/memorias/<int:memoria_id>', methods=['DELETE'])
def delete_memoria(memoria_id):
    memoria = Memoria.query.get(memoria_id)

    if not memoria:
        return Response(json.dumps({'message': f'Memória com ID {memoria_id} não encontrada'}), status=404, content_type='application/json')

    db.session.delete(memoria)
    db.session.commit()

    return Response(json.dumps({'message': f'Memória {memoria_id} deletada com sucesso!'}), status=200, content_type='application/json')

# Rota para registrar Threads com o Assistente
class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(5000), nullable=False)
    wapp_id = db.Column(db.String(100), nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, content, wapp_id):
        self.content = content
        self.wapp_id = wapp_id

# salvando thread diretamente sem uso da API
def salvar_thread(content, wapp_id):
    thread = Thread(content=content, wapp_id=wapp_id)
    db.session.add(thread)
    db.session.commit()
    return "Thread registrada ✅"

@app.route('/threads', methods=['GET'])
def get_threads():
    if request.method == 'GET':
        threads = Thread.query.order_by(Thread.date_created.desc()).limit(6).all()
        serialized_threads = [thread.content for thread in threads]
        return serialized_threads, 200

def get_thread_content_by_wapp_id(wapp_id):
    thread = Thread.query.filter_by(wapp_id=wapp_id).first()
    if thread:
        try:
            content_json = json.loads(thread.content)
            return content_json['content']
        except (json.JSONDecodeError, KeyError) as e:
            return None
    return None

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

# Prompts -------------------

# Rota para registrar Prompts com o Assistente

class Prompt(db.Model):
    __tablename__ = 'prompts'  
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(50000), nullable=False)
    wapp_id = db.Column(db.String(100), nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, content, wapp_id):
        self.content = content
        self.wapp_id = wapp_id

# salvando prompt diretamente sem uso da API
def salvar_prompt(content, wapp_id):
    prompt = Prompt(content=content, wapp_id=wapp_id)
    db.session.add(prompt)
    db.session.commit()
    return "Prompt registrado ✅"

@app.route('/prompts', methods=['GET'])
def get_prompts():
    if request.method == 'GET':
        prompts = Prompt.query.order_by(Prompt.date_created.desc()).limit(6).all()
        serialized_prompts = [prompt.content for prompt in prompts]
        return serialized_prompts, 200

def get_prompt_content_by_wapp_id(wapp_id):
    prompt = Prompt.query.filter_by(wapp_id=wapp_id).first()
    if prompt:
        try:
            content_json = json.loads(prompt.content)
            return content_json['content']
        except (json.JSONDecodeError, KeyError) as e:
            return None
    return None

def get_ultimo_prompt():
    prompt = Prompt.query.order_by(Prompt.date_created.desc()).first()
    if prompt:
        return prompt.content
    return None

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

    
def fazer_perguntas(pergunta, data_atual, hora_atual, phone_number_id, from_number):
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
        threads = Thread.query.with_entities(Thread.content).order_by(Thread.date_created.desc()).limit(10).all()
        # deprecated:
        #saida, first_item = context_gpt35turbo.responde_emb(pergunta, dados, threads, data_atual, hora_atual)
        saida, first_item, tipo_pergunta, prompt_final = context_FuncCalling.responde_emb(pergunta, dados, threads, data_atual, hora_atual, phone_number_id, from_number)
        print("--> Disparando responde_emb por evento")
        return saida, first_item, tipo_pergunta, prompt_final
    except Exception as e:
        return str(e), 400

@app.route('/get_last_checkin_details', methods=['GET'])
def get_last_checkin_details():
    last_checkin = Checkin.query.order_by(Checkin.id.desc()).first()

    if last_checkin:
        # Criando o dicionário 'response' diretamente dos atributos do objeto 'last_checkin'
        response = {
            "id": last_checkin.id,
            "direction": last_checkin.direction,
            "checkin": last_checkin.checkin,
            "data": last_checkin.data
        }

        # Criando o texto plano diretamente
        texto_plano = f"Check-in: {last_checkin.checkin}\nData: {last_checkin.data}\nDireção: {last_checkin.direction}\nID do check-in: {last_checkin.id}"

        return texto_plano
    else:
        return {"message": "No checkins found."}

@app.route('/get_last_checkin_details_ML', methods=['GET'])
def get_last_checkin_details_ML():
    input_data_str = request.args.get("data")
    if not input_data_str:
        return {"error": "Parâmetro 'data' é obrigatório no formato YYYY-MM-DD HH:MM:SS"}, 400

    # Parse simples sem microsegundos
    try:
        input_data = datetime.strptime(input_data_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"error": "Formato inválido. Use YYYY-MM-DD HH:MM:SS"}, 400

    last_checkin = Checkin.query.filter(Checkin.data < input_data) \
                                .order_by(Checkin.data.desc()) \
                                .first()

    if not last_checkin:
        return {"message": "Nenhum check-in anterior encontrado."}, 404

    delta = input_data - last_checkin.data
    delta_minutos = round(delta.total_seconds() / 60, 2)

    resposta_json = {
        "input_data": input_data_str,
        "ultimo_checkin": last_checkin.data.strftime("%Y-%m-%d %H:%M:%S"),
        "checkin": last_checkin.checkin,
        "direction": last_checkin.direction,
        "delta_tempo_minutos": delta_minutos
    }

    resposta_texto = (
        "🧪 Simulação de Delta de Check-in\n"
        f"Data informada: {input_data_str}\n"
        f"Último check-in real: {last_checkin.data}\n"
        f"Tipo de evento: {last_checkin.checkin}\n"
        f"Direção: {last_checkin.direction}\n"
        f"⏱️ Diferença: {delta_minutos} minutos"
    )

    return {"texto": resposta_texto, "json": resposta_json}


def delete_checkin_by_id(checkin_id):
    checkin = Checkin.query.get(checkin_id)

    if checkin:
        db.session.delete(checkin)
        db.session.commit()
        return {"message": f"Checkin {checkin.checkin} successfully deleted."}
    else:
        return {"message": f"Checkin with ID {checkin_id} not found."}

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