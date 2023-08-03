# Passis
My Personal Assistant

## API de Consulta de Jogos e Times
Este repositório contém uma API simples em Python utilizando o framework Flask para consultar informações sobre jogos e times. A API fornece duas rotas principais: uma para obter uma lista de jogos e outra para obter informações sobre um time específico.

## Requisitos
* Python 3.x
* Flask (instalado via pip install Flask)
* Melhor opção seria instalar os requirements.txt:
 ```
pip install -r requirements.txt
```

## Como usar a API
* Inicie o servidor Flask:
 ```
python app.py
```
A API será executada localmente em http://127.0.0.1:5000/.

## Rotas da API
### Rota Principal
 ```
GET /
```
Esta rota retorna uma mensagem indicando que o servidor está ativo.

### Consultar Jogos
 ```
GET /jogos
```
Esta rota retorna uma lista de jogos disponíveis no dia. Os jogos são obtidos através da função main.get_jogos().

### Consultar Time
 ```
GET /time/<nome_time>
```

## Exemplo de uso
Para obter a lista de jogos do dia, envie uma solicitação GET para:
 ```
GET http://127.0.0.1:5000/jogos
```
Para consultar jogos do dia sobre um time específico, substitua <nome_time> pelo nome do time desejado na URL a seguir:
 ```
GET http://127.0.0.1:5000/time/<nome_time>
```


## Considerações Finais
Esta é uma API básica para consulta de jogos diários, criada com Flask. Sinta-se à vontade para utilizar, modificar e melhorar de acordo com as suas necessidades. Para mais detalhes sobre as funções main.get_jogos() e main.get_time(nome_time), consulte o código-fonte no arquivo main.py.

Lembre-se de que esta é apenas uma aplicação de demonstração e pode não ser adequada para uso em produção, considerando que não possui recursos avançados de segurança e escalabilidade.
