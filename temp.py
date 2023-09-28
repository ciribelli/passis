from app import app

# Agora você pode usar app.test_client() para fazer solicitações HTTP
response = app.test_client().get('/memorias')

