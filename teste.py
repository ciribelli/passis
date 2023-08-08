import requests
import json

# Dados em formato JSON
json_data = {"checkin": "academia", "direction": "in", "data": "08-08-2023 13:53:30"}
#json_data = "opa"
url = 'http://127.0.0.1:5000/v1/checkin/'

headers = {'Content-type': 'application/json'}

response = requests.post(url, data=json.dumps(json_data), headers=headers)

if response.status_code == 200:
    print('Requisicao bem-sucedida!')
    print('Resposta do servidor:', response.text)
else:
    print('Erro na requisicao. Codigo de status:', response.status_code)
