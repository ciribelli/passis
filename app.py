import io
from flask import Flask, request, Response, json, send_file, current_app, jsonify
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
import pandas as pd
import agent
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

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        expected_key = os.environ.get('PASSIS_API_KEY')
        if not expected_key:
            return f(*args, **kwargs)

        token_sent = (
            request.args.get('key') or
            request.args.get('api_key') or
            request.headers.get('X-API-Key') or
            request.headers.get('Authorization', '').replace('Bearer ', '').strip() or
            (request.is_json and (request.get_json(silent=True) or {}).get('key'))
        )

        if token_sent and token_sent == expected_key:
            return f(*args, **kwargs)

        return jsonify({'error': 'Não autorizado (API Key inválida ou ausente)'}), 401
    return decorated

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
@require_api_key
def handle_checkin():
    if request.method == 'POST':
        if request.is_json:
            dados = request.get_json()
            new_checkin = Checkin(checkin=dados['checkin'], direction=dados['direction'], data=dados['data'])
            db.session.add(new_checkin)
            db.session.commit()
            return {"message": f"checkin em {new_checkin.checkin} foi criado com sucesso.", "id": new_checkin.id}, 201
        else:
            return {"error": "Formato diferente de JSON"}, 400

    elif request.method == 'GET':
        # Paginação
        try:
            limit = min(int(request.args.get('limit', 50)), 200)  # Default 50, max 200
            offset = int(request.args.get('offset', 0))
        except ValueError:
            return {"error": "limit e offset devem ser números inteiros"}, 400
        
        # Filtros opcionais
        direction = request.args.get('direction')  # 'in' ou 'out'
        start_date = request.args.get('start_date')  # formato: YYYY-MM-DD
        end_date = request.args.get('end_date')  # formato: YYYY-MM-DD
        
        # Query base ordenada por data decrescente
        query = Checkin.query.order_by(Checkin.data.desc())
        
        # Aplicar filtros se fornecidos
        if direction:
            query = query.filter(Checkin.direction == direction)
        
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Checkin.data >= start_dt)
            except ValueError:
                return {"error": "start_date deve estar no formato YYYY-MM-DD"}, 400
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Checkin.data < end_dt)
            except ValueError:
                return {"error": "end_date deve estar no formato YYYY-MM-DD"}, 400
        
        # Total count para paginação
        total = query.count()
        
        # Aplicar paginação
        checkins = query.limit(limit).offset(offset).all()
        
        results = [
            {
                "id": checkin.id,
                "data": checkin.data.strftime('%Y-%m-%d %H:%M:%S') if checkin.data else None,
                "direction": checkin.direction,
                "checkin": checkin.checkin
            } for checkin in checkins]

        return {
            "count": len(results),
            "total": total,
            "limit": limit,
            "offset": offset,
            "checkins": results
        }

@app.route('/checkin/<int:checkin_id>', methods=['GET', 'PUT', 'DELETE'])
@require_api_key
def handle_checkin_id(checkin_id):
    checkin = Checkin.query.get_or_404(checkin_id)

    if request.method == 'GET':
        response = {
            "id": checkin.id,
            "direction": checkin.direction,
            "checkin": checkin.checkin,
            "data": checkin.data.strftime('%Y-%m-%d %H:%M:%S') if checkin.data else None
        }
        return {"message": "success", "checkin": response}

    elif request.method == 'PUT':
        if not request.is_json:
            return {"error": "Formato diferente de JSON"}, 400
            
        dados = request.get_json()
        
        if 'direction' in dados:
            checkin.direction = dados['direction']
        if 'checkin' in dados:
            checkin.checkin = dados['checkin']
        if 'data' in dados:
            checkin.data = dados['data']
            
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
@require_api_key
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
@require_api_key
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
@require_api_key
def deletar_clima(clima_id):
    clima = Clima.query.get(clima_id)
    
    if clima:
        db.session.delete(clima)
        db.session.commit()
        return {"message": f"Registro de clima {clima_id} deletado com sucesso."}
    else:
        return {"message": f"Registro de clima {clima_id} não encontrado."}, 404

# nova classe Health

class RestingHeartRate(db.Model):
    __tablename__ = 'resting_heart_rates'
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True)  # YYYY-MM-DD
    resting_hr = db.Column(db.Float, nullable=False)        # Valor numérico
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, data, resting_hr):
        self.data = data
        self.resting_hr = resting_hr


# Endpoint para receber resting_hr
@app.route('/health/resting_hr', methods=['POST', 'GET'])
@require_api_key
def handle_resting_hr():
    if request.method == 'POST':
        if not request.is_json:
            return {"error": "Formato deve ser JSON"}, 400
        
        dados = request.get_json()
        
        # Validação
        if 'data' not in dados or 'resting_hr' not in dados:
            return {"error": "Campos obrigatórios: data (YYYY-MM-DD) e resting_hr"}, 400
        
        try:
            data = datetime.strptime(dados['data'], '%Y-%m-%d').date()
            resting_hr = float(dados['resting_hr'])
        except ValueError:
            return {"error": "Formato inválido. data=YYYY-MM-DD, resting_hr=número"}, 400
        
        # Upsert: atualiza se já existe, senão cria novo
        entry = RestingHeartRate.query.filter_by(data=data).first()
        if entry:
            entry.resting_hr = resting_hr
            db.session.commit()
            return {"message": f"Resting HR para {data} atualizado.", "id": entry.id}, 200
        
        new_entry = RestingHeartRate(data=data, resting_hr=resting_hr)
        db.session.add(new_entry)
        db.session.commit()
        return {"message": f"Resting HR para {data} criado.", "id": new_entry.id}, 201
    
    elif request.method == 'GET':
        entries = RestingHeartRate.query.order_by(RestingHeartRate.data.desc()).limit(30).all()
        results = [{"data": str(e.data), "resting_hr": e.resting_hr} for e in entries]
        return {"count": len(results), "results": results}, 200
# ------ fim classe Health ----

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

@app.route('/v1/weekly-report', methods=['POST'])
def trigger_weekly_report():
    data = request.get_json(silent=True) or {}
    
    phone_number_id = data.get('phone_number_id') or os.getenv('PHONE_NUMBER_ID', '233405413182343')
    recipient = data.get('recipient') or os.getenv('WHATSAPP_PHONE_NUMBER', '5521983163900')
    
    import weekly_report
    try:
        insight = weekly_report.gerar_e_enviar_relatorio(phone_number_id, recipient)
        return {"status": "success", "message": "Relatório semanal gerado e enviado.", "insight": insight}, 200
    except Exception as e:
        current_app.logger.error(f"Erro no endpoint /v1/weekly-report: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500

# ==========================================
# SEÇÃO BANCO DOS FILHOS (Maria Antonia e José Pedro)
# ==========================================

class KidAccount(db.Model):
    __tablename__ = 'kid_accounts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    passcode = db.Column(db.String(20), nullable=False, default='1234')
    avatar_url = db.Column(db.String(255), nullable=True)
    theme_color = db.Column(db.String(50), default='pink')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        deposits = db.session.query(db.func.sum(KidTransaction.amount)).filter(
            KidTransaction.kid_id == self.id, KidTransaction.type == 'deposit'
        ).scalar() or 0.0
        withdrawals = db.session.query(db.func.sum(KidTransaction.amount)).filter(
            KidTransaction.kid_id == self.id, KidTransaction.type == 'withdrawal'
        ).scalar() or 0.0
        
        balance = deposits - withdrawals

        return {
            'id': self.id,
            'name': self.name,
            'age': self.age,
            'avatar_url': self.avatar_url,
            'theme_color': self.theme_color,
            'balance': round(balance, 2),
            'total_earned': round(deposits, 2),
            'total_spent': round(withdrawals, 2),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

class KidTransaction(db.Model):
    __tablename__ = 'kid_transactions'
    id = db.Column(db.Integer, primary_key=True)
    kid_id = db.Column(db.Integer, db.ForeignKey('kid_accounts.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'deposit' ou 'withdrawal'
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), default='Geral')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'kid_id': self.kid_id,
            'type': self.type,
            'amount': round(self.amount, 2),
            'description': self.description,
            'category': self.category,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None
        }

class KidChatMessage(db.Model):
    __tablename__ = 'kid_chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    kid_id = db.Column(db.Integer, db.ForeignKey('kid_accounts.id'), nullable=False)
    sender = db.Column(db.String(20), nullable=False)  # 'kid' ou 'father'
    message = db.Column(db.Text, nullable=False)
    action_type = db.Column(db.String(50), default='custom')  # 'alexa', 'home', 'withdraw', 'custom', 'reply'
    whatsapp_status = db.Column(db.String(20), default='sent')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'kid_id': self.kid_id,
            'sender': self.sender,
            'message': self.message,
            'action_type': self.action_type,
            'whatsapp_status': self.whatsapp_status,
            'timestamp': self.timestamp.strftime('%d/%m/%Y %H:%M') if self.timestamp else None
        }


@app.route('/v1/kids/init-defaults', methods=['POST'])
def init_kids_defaults():
    try:
        db.create_all()
        maria = KidAccount.query.filter_by(name='Maria Antonia').first()
        if not maria:
            maria = KidAccount(
                name='Maria Antonia',
                age=14,
                passcode='1234',
                avatar_url='/imagens.jpg',
                theme_color='violet'
            )
            db.session.add(maria)

        jose = KidAccount.query.filter_by(name='Jose Pedro').first()
        if not jose:
            jose = KidAccount(
                name='Jose Pedro',
                age=11,
                passcode='1234',
                avatar_url='/imagens.jpg',
                theme_color='neon-blue'
            )
            db.session.add(jose)

        db.session.commit()
        return jsonify({
            'message': 'Contas de Maria Antonia e Jose Pedro inicializadas com sucesso!',
            'kids': [maria.to_dict(), jose.to_dict()]
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/v1/kids', methods=['GET'])
def get_kids():
    try:
        kids = KidAccount.query.order_by(KidAccount.id).all()
        if not kids:
            init_kids_defaults()
            kids = KidAccount.query.order_by(KidAccount.id).all()
        return jsonify({'kids': [k.to_dict() for k in kids]}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/v1/kids/<int:kid_id>/auth', methods=['POST'])
def auth_kid(kid_id):
    data = request.get_json(silent=True) or {}
    passcode = str(data.get('passcode', '')).strip()
    is_admin = data.get('is_admin', False)

    admin_pin = os.environ.get('KIDS_ADMIN_PIN', '8888')

    if is_admin:
        if passcode == admin_pin:
            return jsonify({'success': True, 'role': 'admin'}), 200
        return jsonify({'success': False, 'error': 'Senha de Administrador incorreta'}), 401

    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    if passcode == kid.passcode or passcode == admin_pin:
        return jsonify({'success': True, 'kid': kid.to_dict()}), 200

    return jsonify({'success': False, 'error': 'Senha incorreta'}), 401

@app.route('/v1/kids/<int:kid_id>/history', methods=['GET'])
def get_kid_history(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    transactions = KidTransaction.query.filter_by(kid_id=kid_id).order_by(KidTransaction.timestamp.asc()).all()

    running_balance = 0.0
    timeline = []
    story_steps = []

    for tx in transactions:
        if tx.type == 'deposit':
            running_balance += tx.amount
            step_str = f"Ganhou R$ {tx.amount:.2f} ({tx.description}) ➔ Saldo foi para R$ {running_balance:.2f}"
        else:
            running_balance -= tx.amount
            step_str = f"Gastei/Sacou R$ {tx.amount:.2f} ({tx.description}) ➔ Saldo foi para R$ {running_balance:.2f}"

        story_steps.append(step_str)
        t_dict = tx.to_dict()
        t_dict['balance_after'] = round(running_balance, 2)
        timeline.append(t_dict)

    timeline.reverse()

    return jsonify({
        'kid': kid.to_dict(),
        'current_balance': round(running_balance, 2),
        'transactions': timeline,
        'story_steps': story_steps
    }), 200

@app.route('/v1/kids/<int:kid_id>/deposit', methods=['POST'])
def deposit_kid(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Valor inválido'}), 400

    description = data.get('description', 'Depósito do Pai').strip()
    category = data.get('category', 'Geral').strip()

    if amount <= 0:
        return jsonify({'error': 'O valor do depósito deve ser maior que R$ 0'}), 400

    tx = KidTransaction(
        kid_id=kid.id,
        type='deposit',
        amount=amount,
        description=description,
        category=category
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'message': f'R$ {amount:.2f} depositados com sucesso para {kid.name}!',
        'kid': kid.to_dict(),
        'transaction': tx.to_dict()
    }), 201

@app.route('/v1/kids/<int:kid_id>/withdraw', methods=['POST'])
def withdraw_kid(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Valor inválido'}), 400

    description = data.get('description', 'Saque').strip()
    passcode = str(data.get('passcode', '')).strip()

    admin_pin = os.environ.get('KIDS_ADMIN_PIN', '8888')
    if passcode != kid.passcode and passcode != admin_pin:
        return jsonify({'error': 'Senha incorreta para realizar o saque'}), 401

    if amount <= 0:
        return jsonify({'error': 'O valor do saque deve ser maior que R$ 0'}), 400

    current_balance = kid.to_dict()['balance']
    if amount > current_balance:
        return jsonify({'error': f'Saldo insuficiente! {kid.name} possui R$ {current_balance:.2f}'}), 400

    tx = KidTransaction(
        kid_id=kid.id,
        type='withdrawal',
        amount=amount,
        description=description,
        category=data.get('category', 'Saque')
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({
        'message': f'Saque de R$ {amount:.2f} realizado com sucesso para {kid.name}!',
        'kid': kid.to_dict(),
        'transaction': tx.to_dict()
    }), 201

@app.route('/v1/kids/transactions/<int:tx_id>', methods=['DELETE'])
def delete_kid_transaction(tx_id):
    tx = KidTransaction.query.get(tx_id)
    if not tx:
        return jsonify({'error': 'Transação não encontrada'}), 404

    db.session.delete(tx)
    db.session.commit()
    return jsonify({'message': f'Transação #{tx_id} apagada com sucesso.'}), 200

# Chat dos Filhos ➔ WhatsApp do Pai
@app.route('/v1/kids/<int:kid_id>/chat/send', methods=['POST'])
def send_kid_message(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    data = request.get_json(silent=True) or {}
    message_text = str(data.get('message', '')).strip()
    action_type = str(data.get('action_type', 'custom')).strip()

    if not message_text:
        return jsonify({'error': 'A mensagem não pode ser vazia'}), 400

    db.create_all()

    chat_msg = KidChatMessage(
        kid_id=kid.id,
        sender='kid',
        message=message_text,
        action_type=action_type,
        whatsapp_status='sending'
    )
    db.session.add(chat_msg)
    db.session.commit()

    # Dispara notificação via Meta WhatsApp Cloud API
    phone_number_id = os.environ.get('PHONE_NUMBER_ID', '233405413182343')
    recipient = os.environ.get('WHATSAPP_PHONE_NUMBER', '5521983163900')

    is_maria = 'maria' in kid.name.lower()
    icon = '👧' if is_maria else '👦'
    wapp_text = f"{icon} *{kid.name}* (via Cofre dos Filhos):\n\n\"{message_text}\""

    try:
        wapp_resp = send_msg.send_wapp_msg(phone_number_id, recipient, wapp_text)
        if wapp_resp and wapp_resp.status_code == 200:
            chat_msg.whatsapp_status = 'delivered'
        else:
            chat_msg.whatsapp_status = 'sent'
        db.session.commit()
    except Exception as e:
        print(f"Erro ao enviar WhatsApp do filho para o pai: {e}")
        chat_msg.whatsapp_status = 'failed'
        db.session.commit()

    return jsonify({
        'message': 'Mensagem enviada com sucesso ao Papai!',
        'chat_message': chat_msg.to_dict()
    }), 201

@app.route('/v1/kids/<int:kid_id>/chat/reply', methods=['POST'])
def reply_kid_message(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    data = request.get_json(silent=True) or {}
    message_text = str(data.get('message', '')).strip()

    if not message_text:
        return jsonify({'error': 'A resposta não pode ser vazia'}), 400

    db.create_all()

    chat_msg = KidChatMessage(
        kid_id=kid.id,
        sender='father',
        message=message_text,
        action_type='reply',
        whatsapp_status='sent'
    )
    db.session.add(chat_msg)
    db.session.commit()

    return jsonify({
        'message': 'Resposta enviada!',
        'chat_message': chat_msg.to_dict()
    }), 201

@app.route('/v1/kids/<int:kid_id>/chat/messages', methods=['GET'])
def get_kid_chat_messages(kid_id):
    kid = KidAccount.query.get(kid_id)
    if not kid:
        return jsonify({'error': 'Conta não encontrada'}), 404

    db.create_all()
    messages = KidChatMessage.query.filter_by(kid_id=kid_id).order_by(KidChatMessage.timestamp.asc()).all()
    return jsonify({
        'kid_id': kid_id,
        'messages': [m.to_dict() for m in messages]
    }), 200

def salvar_resposta_pai_whatsapp(texto, from_number, target_kid_id=None):
    try:
        db.create_all()
        if not target_kid_id:
            last_kid_msg = KidChatMessage.query.filter_by(sender='kid').order_by(KidChatMessage.timestamp.desc()).first()
            target_kid_id = last_kid_msg.kid_id if last_kid_msg else 1

        kid = KidAccount.query.get(target_kid_id)
        kid_name = kid.name if kid else "Filhos"

        reply = KidChatMessage(
            kid_id=target_kid_id,
            sender='father',
            message=texto,
            action_type='whatsapp_reply',
            whatsapp_status='received'
        )
        db.session.add(reply)
        db.session.commit()
        return True, kid_name
    except Exception as e:
        print(f"Erro ao salvar resposta do pai vinda do WhatsApp: {e}")
        return False, "Filhos"



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
@require_api_key
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

def salvar_documento_direto(nome, descricao, binario_data):
    try:
        novo_documento = DocumentoBinario(
            nome_do_documento=nome[:255],
            descricao=descricao,
            binario_data=binario_data
        )
        db.session.add(novo_documento)
        db.session.commit()
        return "Documento salvo com sucesso!"
    except Exception as e:
        print(f"Erro ao salvar documento direto: {e}")
        return str(e)

# Rota para recuperar um documento binário pelo ID
@app.route('/recuperar_documento/<int:documento_id>', methods=['GET'])
@require_api_key
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
@require_api_key
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
@require_api_key
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
@require_api_key
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
    wapp_id = db.Column(db.String(100), nullable=True)
    reminder_time = db.Column(db.DateTime, nullable=True)
    reminder_status = db.Column(db.String(20), default='pendente', nullable=True)

    def __init__(self, content, wapp_id=None, reminder_time=None):
        self.content = content
        self.wapp_id = wapp_id
        self.reminder_time = reminder_time
        self.reminder_status = 'pendente' if reminder_time else None

# salvando memorias diretamente sem uso da API
def salvar_memoria_recebida(content):
    memoria = Memoria(content=content)
    db.session.add(memoria)
    db.session.commit()
    return "Memória eternizada ✅"

def salvar_lembrete(content, wapp_id, reminder_time):
    lembrete = Memoria(content=content, wapp_id=wapp_id, reminder_time=reminder_time)
    db.session.add(lembrete)
    db.session.commit()
    return f"Lembrete agendado para {reminder_time} ✅"

import send_msg

@app.route('/trigger_reminders', methods=['POST'])
def trigger_reminders():
    # Segurança básica via header CRON_SECRET
    secret = request.headers.get('Authorization')
    if os.environ.get('CRON_SECRET') and secret != os.environ.get('CRON_SECRET'):
        return Response("Unauthorized", status=401)

    # O reminder_time salvo no banco está no horário do Brasil (America/Sao_Paulo)
    # Precisamos comparar com a hora atual também no horário do Brasil.
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br).replace(tzinfo=None)
    
    # Busca lembretes pendentes cujo horário já passou
    lembretes = Memoria.query.filter(
        Memoria.reminder_time <= agora,
        Memoria.reminder_status == 'pendente'
    ).all()

    phone_number_id = os.environ.get('PHONE_NUMBER_ID', '233405413182343') # fallback pro seu ID atual se não tiver env var

    for lembrete in lembretes:
        if lembrete.wapp_id:
            # Envia lembrete com botões interativos (Feito / Soneca / Arquivar)
            send_msg.send_wapp_reminder(phone_number_id, lembrete.wapp_id, lembrete.content, lembrete.id)
        
        lembrete.reminder_status = 'enviado'
    
    db.session.commit()
    return Response(json.dumps({'message': f'{len(lembretes)} lembretes processados.'}), status=200, content_type='application/json')

def snooze_lembrete(memoria_id, minutos=15):
    """Adia um lembrete para daqui a X minutos."""
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br).replace(tzinfo=None)
    
    memoria = Memoria.query.get(memoria_id)
    if not memoria:
        return None
    
    memoria.reminder_time = agora + timedelta(minutes=minutos)
    memoria.reminder_status = 'pendente'
    db.session.commit()
    
    hora_formatada = memoria.reminder_time.strftime('%H:%M')
    return f"💤 Ok! Vou te lembrar de novo às {hora_formatada}."

def get_lembretes_perdidos(dias_atras=1):
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br).replace(tzinfo=None)
    limite = agora - timedelta(days=dias_atras)
    
    lembretes = Memoria.query.filter(
        Memoria.reminder_status == 'enviado',
        Memoria.reminder_time >= limite,
        Memoria.reminder_time <= agora
    ).order_by(Memoria.reminder_time.desc()).all()
    
    if not lembretes:
        return f"Nenhum lembrete perdido (não respondido) nos últimos {dias_atras} dias."
    
    resumo = f"Lembretes perdidos/não respondidos (últimos {dias_atras} dias):\n"
    for l in lembretes:
        hora_str = l.reminder_time.strftime('%d/%m às %H:%M') if l.reminder_time else 'Desconhecido'
        resumo += f"- {hora_str}: {l.content}\n"
    
    return resumo


@app.route('/memorias', methods=['POST'])
@require_api_key
def create_memoria():
    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content')
        reminder_time_str = data.get('reminder_time')

        if not content:
            return Response(json.dumps({'message': 'O campo "content" é obrigatório'}), status=400, content_type='application/json')

        reminder_time = None
        if reminder_time_str:
            try:
                reminder_time = datetime.strptime(reminder_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    reminder_time = datetime.strptime(reminder_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    return Response(json.dumps({'message': 'Formato de reminder_time inválido. Use YYYY-MM-DD HH:MM:SS ou YYYY-MM-DDTHH:MM'}), status=400, content_type='application/json')

        nova_memoria = Memoria(content=content, reminder_time=reminder_time)

        db.session.add(nova_memoria)
        db.session.commit()

        return Response(json.dumps({'message': 'Nova memória criada com sucesso!'}), status=201, content_type='application/json')

@app.route('/memorias', methods=['GET'])
@require_api_key
def get_memorias():
    if request.method == 'GET':
        memorias = Memoria.query.order_by(Memoria.date_created.desc()).all()
        serialized_memorias = []
        for memoria in memorias:
            reminder_time_str = memoria.reminder_time.strftime('%Y-%m-%d %H:%M:%S') if memoria.reminder_time else None
            serialized_memorias.append({
                'id': memoria.id,
                'content': memoria.content,
                'date_created': memoria.date_created.strftime('%Y-%m-%d %H:%M:%S'),
                'reminder_time': reminder_time_str,
                'reminder_status': memoria.reminder_status
            })

        return Response(json.dumps(serialized_memorias), status=200, content_type='application/json')

@app.route('/memorias/<int:memoria_id>', methods=['PUT'])
@require_api_key
def update_memoria(memoria_id):
    try:
        memoria = Memoria.query.get(memoria_id)
        if not memoria:
            return Response(json.dumps({'message': f'Memória com ID {memoria_id} não encontrada'}), status=404, content_type='application/json')

        data = request.get_json()
        content = data.get('content')
        reminder_time_str = data.get('reminder_time')
        reminder_status = data.get('reminder_status')

        if content:
            memoria.content = content

        if 'reminder_time' in data:
            if reminder_time_str:
                try:
                    memoria.reminder_time = datetime.strptime(reminder_time_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        memoria.reminder_time = datetime.strptime(reminder_time_str, '%Y-%m-%dT%H:%M')
                    except ValueError:
                        return Response(json.dumps({'message': 'Formato de reminder_time inválido.'}), status=400, content_type='application/json')
                # Se mudou o reminder_time, atualiza o status de volta pra pendente (ou o status enviado)
                memoria.reminder_status = reminder_status if reminder_status else 'pendente'
            else:
                memoria.reminder_time = None
                memoria.reminder_status = None

        elif 'reminder_status' in data:
            # Caso só mude o status
            memoria.reminder_status = reminder_status

        db.session.commit()
        return Response(json.dumps({'message': 'Memória atualizada com sucesso!'}), status=200, content_type='application/json')
    except Exception as e:
        db.session.rollback()
        return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

@app.route('/memorias/<int:memoria_id>', methods=['DELETE'])
@require_api_key
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
@require_api_key
def get_threads():
    if request.method == 'GET':
        threads = Thread.query.order_by(Thread.date_created.desc()).limit(6).all()
        serialized_threads = [thread.content for thread in threads]
        return serialized_threads, 200

def get_thread_content_by_wapp_id(wapp_id):
    thread = Thread.query.filter_by(wapp_id=wapp_id).first()
    if thread:
        try:
            content_json = json.loads(thread.content, strict=False)
            return content_json['content']
        except (json.JSONDecodeError, KeyError) as e:
            return None
    return None

@app.route('/apagar_threads', methods=['DELETE'])
@require_api_key
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
@require_api_key
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
@require_api_key
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
@require_api_key
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
@require_api_key
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
        saida, first_item, tipo_pergunta, prompt_final = agent.responde_mcp(pergunta, dados, threads, data_atual, hora_atual, phone_number_id, from_number)
        print("--> Disparando responde_mcp por evento")
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