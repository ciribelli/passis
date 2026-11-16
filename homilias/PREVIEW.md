# Prévia e stage das homilias

A página individual existente (`/homilias/p/<token>`) continua usando o mesmo link. Ela mostra o status da versão, os campos finais de título e descrição com botões de copiar, a capa PNG e o áudio tratado M4A com downloads. A mensagem recebida fica recolhida na seção de dados de entrada. Baixar ou copiar não aprova nem publica o episódio.

O painel privado em `/homilias/stage/<token-do-stage>` lista todos os episódios do proprietário configurado em `HOMILIA_OWNER_WA_ID`, inclusive os que ainda não têm prévia, com busca, filtro por status e página individual. A lista está em ordem alfabética de título. Os status vêm do Passis; publicações manuais no Spotify não alteram esses registros automaticamente.

## Obter o link do painel

No ambiente com as variáveis do servidor:

```sh
python -m homilias.worker stage-url
```

No Heroku:

```sh
heroku run python -m homilias.worker stage-url --app passis
```

Esse comando apenas imprime o link, sem acessar o banco ou executar o worker. Guarde o link como favorito: ele permite consultar todos os episódios e baixar os materiais disponíveis. A prévia de um episódio não revela o link do stage.

Por padrão, o token do stage é derivado com HMAC de `WHATSAPP_APP_SECRET` e `HOMILIA_OWNER_WA_ID`, já usados pelo projeto. Não é necessário criar tabelas ou configurar outra variável. Alterar qualquer uma dessas variáveis altera o link. Opcionalmente, configure `HOMILIA_STAGE_TOKEN` com um valor aleatório longo para ter um token independente. Exemplo de geração local:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

O token do stage é diferente dos tokens de prévia. Todas as páginas são somente de consulta, não são indexadas e enviam `Cache-Control: private, no-store` e `Referrer-Policy: no-referrer`. Os downloads mantêm as regras atuais de acesso à edição: uma prévia cancelada ou substituída deixa de fornecer arquivos.
