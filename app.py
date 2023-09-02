from flask import Flask, request, Response, json
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
import urllib.parse as up
from dotenv import load_dotenv
import requests
import jsonify
import os
import main

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

@app.route('/v1/hub/<content>', methods=['GET'])
def hub(content):

    # para JOGOS
    if content.lower() == "jogos" or content.lower() == "jogo":
        coletor, datajson = main.get_jogos_df()
    # para CIDADE e TRANSITO
    elif content.lower() == "cidade" or content.lower() == "cidades" or content.lower() == "transito":
        token = os.getenv('token_X')
        coletor, datajson = main.busca_X("operacoesrio", token)
    # para CLIMA
    elif content.lower() == "Clima" or content.lower() == "Climas" or content.lower() == "clima" or content.lower() == "climas":
        token = os.getenv('token_clima')
        coletor, datajson = main.busca_Clima(token)
    else:
        coletor = content + " ainda não é um comando conhecido 😊"
    return Response(response=coletor, status=200, mimetype='application/json')

@app.route('/v1/jogos', methods=['GET'])
def get_jogos():
    jogos = main.get_jogos()
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

        # Verifica se há mensagens na solicitação
        if 'changes' in entry and entry['changes'][0]['value'].get('messages'):
            message = entry['changes'][0]['value']['messages'][0]
            phone_number_id = message.get('metadata', {}).get('phone_number_id')
            from_number = message['from']

            # Verifica se há um ID de botão de resposta
            button_reply_id = message['interactive']['button_reply'][
                'id'] if 'interactive' in message and 'button_reply' in message['interactive'] else None

            # Verifica se há um corpo de mensagem de texto
            msg_body = message['text']['body'] if 'text' in message else None

            if button_reply_id:
                print("button_reply.id:", button_reply_id)
                # Faça algo com o button_reply.id

            elif msg_body:
                print("msg_body:", msg_body)

                content = ""
                # para JOGOS
                if content.lower() == "jogos" or content.lower() == "jogo":
                    coletor, datajson = main.get_jogos_df()
                # para CIDADE e TRANSITO
                elif content.lower() == "cidade" or content.lower() == "cidades" or content.lower() == "transito":
                    token = os.getenv('token_X')
                    coletor, datajson = main.busca_X("operacoesrio", token)
                # para CLIMA
                elif content.lower() == "Clima" or content.lower() == "Climas" or content.lower() == "clima" or content.lower() == "climas":
                    token = os.getenv('token_clima')
                    coletor, datajson = main.busca_Clima(token)
                else:
                    coletor = content + " ainda não é um comando conhecido 😊"

                try:
                    # Faz o envio da mensagem de volta
                    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={token}"
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": from_number,
                        "text": {"body": coletor}
                    }

                    # Converte o payload em uma representação JSON válida
                    payload_json = json.dumps(payload)

                    headers = {"Content-Type": "application/json"}
                    response = requests.request("POST", fb_url, headers=headers, data=payload_json)

                except requests.exceptions.RequestException as e:
                    # Tratamento de erros se a solicitação falhar
                    print("Erro ao consultar a URL:", str(e))

            else:
                print("Nem button_reply.id nem msg_body presentes.")

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
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            # Responda com '403 Forbidden' se os tokens de verificação não coincidirem
            return "Forbidden", 403

    return "Bad Request", 400

# Executa o aplicativo Flask
if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 1337)))



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

if __name__ == '__main__':
    app.run(debug=True)

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
