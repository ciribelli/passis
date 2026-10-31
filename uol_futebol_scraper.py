"""Coletor de jogos de futebol da Central de Jogos do UOL.

A pagina embute os dados em JSON (nao precisa de JS):
  - <script id="VUELAND_CORE_STATE">  -> jogos, times, horario, estadio,
    transmissao, destaque (highlight), placar e status.
  - <script type="application/ld+json"> -> nome do campeonato (organizer).

A pagina cobre ~10 dias para tras e ~8 para frente da data atual.

Uso: python uol_futebol_scraper.py 31-10-2026
"""
import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

URL = 'https://www.uol.com.br/esporte/futebol/central-de-jogos/'
TZ = ZoneInfo('America/Sao_Paulo')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'}


def _parse_date(data):
    """Aceita dd-mm-yyyy, dd/mm/yyyy ou yyyy-mm-dd."""
    for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(data.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f'Data invalida: {data!r} (use dd-mm-yyyy)')


def _iso_to_local(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(TZ)


def _fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text


def _load_state(html):
    m = re.search(r'<script id="VUELAND_CORE_STATE"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError('UOL: VUELAND_CORE_STATE nao encontrado (layout mudou?)')
    comps = json.loads(m.group(1))['general']['components']
    for key, comp in comps.items():
        if key.startswith('FootballDailyMatches') and 'matches' in comp:
            return comp
    raise RuntimeError('UOL: componente FootballDailyMatches nao encontrado')


def _load_competitions(html):
    """Mapeia (mandante, visitante, inicio_utc) -> campeonato, via JSON-LD."""
    out = {}
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stack = [data]
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                stack.extend(o)
            elif isinstance(o, dict):
                if o.get('@type') == 'SportsEvent' and 'homeTeam' in o:
                    key = (o['homeTeam'].get('name'), o['awayTeam'].get('name'),
                           _iso_to_local(o['startDate']))
                    out[key] = (o.get('organizer') or {}).get('name')
                stack.extend(o.values())
    return out


def get_games(data=None):
    """Retorna jogos (dicts) da data informada, ordenados por horario.
    data=None retorna todos os jogos disponiveis na pagina."""
    alvo = _parse_date(data) if data else None
    html = _fetch_html()
    state = _load_state(html)
    comps = _load_competitions(html)
    teams = state.get('teams', {})

    def team(tid):
        return (teams.get(str(tid)) or {}).get('name', str(tid))

    jogos = {}
    for mid, m in state['matches'].items():
        inicio = _iso_to_local(m['isoDate'])
        if alvo and inicio.date() != alvo:
            continue
        casa, fora = team(m['teams']['home']), team(m['teams']['away'])
        gols = (m.get('score') or {}).get('goals') or {}
        content = m.get('content') or {}
        jogo = {
            'id': mid,
            'data': inicio.strftime('%d-%m-%Y'),
            'hora': inicio.strftime('%H:%M'),
            'time1': casa,
            'time2': fora,
            'competicao': comps.get((casa, fora, inicio)),
            'fase': (m.get('championship') or {}).get('phase'),
            'rodada': m.get('round'),
            'estadio': m.get('stadium'),
            'cidade': (m.get('location') or {}).get('city'),
            'transmissao': [b['name'] for b in content.get('broadcast') or [] if b.get('name')],
            'destaque': bool(content.get('highlight')),
            'status': m.get('status'),
            'placar': None if gols.get('home') is None else f"{gols['home']} x {gols['away']}",
            'link': content.get('scoreUrl') or None,
        }
        # o UOL as vezes lista o mesmo jogo com dois IDs: mescla os dados
        chave = (jogo['data'], jogo['hora'], casa, fora)
        if chave in jogos:
            atual = jogos[chave]
            for tv in jogo['transmissao']:
                if tv not in atual['transmissao']:
                    atual['transmissao'].append(tv)
            atual['destaque'] = atual['destaque'] or jogo['destaque']
            for k, v in jogo.items():
                if atual.get(k) in (None, '') and v not in (None, ''):
                    atual[k] = v
        else:
            jogos[chave] = jogo
    return sorted(jogos.values(), key=lambda j: (j['data'][6:], j['data'][3:5], j['data'][:2], j['hora'], j['time1']))


def format_games(jogos):
    """Texto pronto para WhatsApp."""
    if not jogos:
        return 'Nenhum jogo encontrado para essa data.'
    linhas = []
    for j in jogos:
        icone = '🥇' if j['destaque'] else '⚽️'
        tv = ', '.join(j['transmissao']) or '-'
        placar = f" ({j['placar']})" if j['placar'] else ''
        linhas.append(f"{icone} {j['time1']} ✖️ {j['time2']}{placar} ⏰ {j['hora']} 📺 {tv}")
    return '\n'.join(linhas)


if __name__ == '__main__':
    data = sys.argv[1] if len(sys.argv) > 1 else datetime.now(TZ).strftime('%d-%m-%Y')
    jogos = get_games(data)
    print(format_games(jogos))
    print(f'\n{len(jogos)} jogos')
