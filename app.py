from flask import Flask, jsonify, request, Response, json
import main

# Criação do objeto do aplicativo Flask
app = Flask(__name__)

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


