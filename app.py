from flask import Flask, request, Response, json
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
import urllib.parse as up
from dotenv import load_dotenv
import os
import main

load_dotenv()

app = Flask(__name__)
# configuracao do url db postgres externo ou local (arquivo .env deve estar na raiz do projeto)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL_EXTERNA')
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Rota principal (página inicial)
@app.route('/')
def index():
    return "Servidor ativo"

@app.route('/v1/jogos', methods=['GET'])
def get_jogos():
    jogos = main.get_jogos()
    return Response(response=jogos, status=200, mimetype='application/json')

@app.route('/v1/time/<nome_time>', methods=['GET'])
def get_time(nome_time):
    jogos = main.get_time(nome_time)
    return Response(response=jogos, status=200, mimetype='application/json')

@app.route('/v1/checkin/', methods=['POST'])
def checkin():
    try:
        n_checkin = request.get_json()  # Tenta obter o JSON da solicitação
        if n_checkin is None:
            raise json.JSONDecodeError("Invalid JSON", "", 0)
    except json.JSONDecodeError:
        res = {"erro": "Mensagem não tem formato JSON"}
        return Response(response=json.dumps(res), status=400, mimetype='application/json')

    res = main.location_logger(n_checkin)
    return Response(response=res, status=200, mimetype='application/json')

# Executa o aplicativo Flask
if __name__ == '__main__':
    app.run(debug=True)

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
def handle_car(checkin_id):
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
    
