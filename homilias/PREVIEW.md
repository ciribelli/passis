# Prévia e stage das homilias

A página individual existente (`/homilias/p/<token>`) continua usando o mesmo link. Ela mostra o status da versão, os campos finais de título e descrição com botões de copiar, a capa PNG e o áudio tratado M4A com downloads. A mensagem recebida fica recolhida na seção de dados de entrada. Baixar ou copiar não aprova nem publica o episódio.

O painel privado em `/homilias/stage/<token-do-stage>` lista todos os episódios do proprietário configurado em `HOMILIA_OWNER_WA_ID`, inclusive os que ainda não têm prévia, com busca, filtro por status e página individual. A lista está em ordem alfabética de título. Os status vêm do Passis; publicações manuais no Spotify não alteram esses registros automaticamente.

## Obter o link do painel

Envie **painel homilias** ao Passis pelo WhatsApp. Ele responde com o link privado do painel. Também aceita “painel de homilias”, “painel das homilias”, “stage homilias” e “painel do podcast”. O atalho exige o número proprietário (`HOMILIA_OWNER_WA_ID`) e a assinatura válida do webhook. Funciona sem consultar banco ou modelo e tem prioridade sobre a associação de textos a áudios, inclusive ao responder outra mensagem.

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

O token do stage é diferente dos tokens de prévia. A prévia individual é somente de consulta. No painel privado, Preparar inicia o worker da edição no dyno atual. Se o dyno reiniciar durante o preparo, use Retomar preparo. Lixeira retira a cópia da fila e da lista após confirmação e revoga a prévia. O registro é preservado para reconhecer novas entregas da mesma mensagem. As páginas não são indexadas e enviam `Cache-Control: private, no-store` e `Referrer-Policy: no-referrer`. Os downloads mantêm as regras atuais de acesso à edição: uma prévia cancelada ou substituída deixa de fornecer arquivos.
