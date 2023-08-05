from flask import Flask, jsonify, request, Response, json
import main

# Criação do objeto do aplicativo Flask
app = Flask(__name__)

# Rota principal (página inicial)
@app.route('/')
def index():
    return "Servidor ativo"

@app.route('/jogos', methods=['GET'])
def get_jogos():
    jogos = main.get_jogos()
    return jogos

@app.route('/v1/jogos', methods=['GET'])
def get_jogos2():
    jogos = main.get_jogos()
    return Response(response=jogos, status=200, mimetype='application/json')

@app.route('/time/<nome_time>', methods=['GET'])
def get_time(nome_time):
    jogos = main.get_time(nome_time)
    return jogos

# Executa o aplicativo Flask
if __name__ == '__main__':
    app.run(debug=True)


