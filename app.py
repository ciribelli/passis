from flask import Flask, jsonify, request

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

@app.route('/time/<nome_time>', methods=['GET'])
def get_time(nome_time):
    import main
    jogos = main.get_time(nome_time)
    return jogos

# Executa o aplicativo Flask
if __name__ == '__main__':
    app.run(debug=True)


