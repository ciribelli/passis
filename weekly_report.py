import os
import matplotlib
matplotlib.use('Agg')  # Necessário para rodar sem interface gráfica (GUI)
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import io

def obter_metricas_ml(start_date, end_date):
    from app import db
    from sqlalchemy import text
    try:
        query = text("""
            SELECT target_checkin, COUNT(*) AS eventos_avaliados, 
                   ROUND(AVG(minutos_antes)::numeric, 1) AS media_minutos_antes, 
                   ROUND(AVG(prediction)::numeric, 3) AS media_pred_antes, 
                   ROUND(AVG(erro_absoluto)::numeric, 3) AS mae 
            FROM ml.v_precisao_modelo 
            WHERE evento_real >= :start AND evento_real <= :end 
            GROUP BY target_checkin 
            ORDER BY mae ASC
        """)
        resultado = db.session.execute(query, {"start": start_date, "end": end_date}).fetchall()
        return [{"checkin": row.target_checkin, "count": int(row.eventos_avaliados), "min_antes": float(row.media_minutos_antes), "avg_prob": float(row.media_pred_antes), "mae": float(row.mae)} for row in resultado]
    except Exception as e:
        print(f"Erro ao obter métricas ML: {e}")
        return []

def obter_dados_semana(start_date, end_date):
    from app import Checkin, Clima
    
    # Consulta checkins no período de 21 dias
    checkins = Checkin.query.filter(Checkin.data.between(start_date, end_date)).order_by(Checkin.data).all()
    
    # Consulta climas no período de 21 dias
    climas = Clima.query.filter(Clima.data.between(start_date, end_date)).order_by(Clima.data).all()
    
    return checkins, climas

def processar_metricas(checkins, climas, start_date, end_date):
    w1_start = start_date.date()
    w1_end = w1_start + timedelta(days=6)
    
    w2_start = w1_start + timedelta(days=7)
    w2_end = w2_start + timedelta(days=6)
    
    w3_start = w1_start + timedelta(days=14)
    w3_end = w3_start + timedelta(days=6)
    
    days_range_w3 = [w3_start + timedelta(days=i) for i in range(7)]
    
    # Mapeamento de hábitos dinâmicos
    offices = {'EDISEN', 'EDIHB', 'CENPES'}
    exclusoes = {'awake', 'casa', 'drive'}.union(offices)
    
    # Identifica todos os hábitos distintos com check-in "in" no período de 21 dias (excluindo sono/transito)
    todos_habitos = set()
    for c in checkins:
        if c.direction == 'in' and c.checkin not in exclusoes:
            todos_habitos.add(c.checkin)
            
    # Inicializa contagens para todos os hábitos encontrados
    habitos_trends = {}  # hab -> [w1_count, w2_count, w3_count]
    habitos_daily_w3 = {}  # hab -> {date: count}
    
    for hab in todos_habitos:
        habitos_trends[hab] = [0, 0, 0]
        habitos_daily_w3[hab] = {d: 0 for d in days_range_w3}
        
    for c in checkins:
        dt_date = c.data.date()
        is_in = (c.direction == 'in')
        hab = c.checkin
        
        if is_in and hab in todos_habitos:
            if w1_start <= dt_date <= w1_end:
                habitos_trends[hab][0] += 1
            elif w2_start <= dt_date <= w2_end:
                habitos_trends[hab][1] += 1
            elif w3_start <= dt_date <= w3_end:
                habitos_trends[hab][2] += 1
                habitos_daily_w3[hab][dt_date] += 1
                
    # Determinar os top 2 hábitos com base na semana atual (w3), senão pelo histórico geral
    habitos_ordenados = sorted(todos_habitos, key=lambda h: (habitos_trends[h][2], sum(habitos_trends[h])), reverse=True)
    top_habitos = habitos_ordenados[:2]
    
    # Fallback caso tenhamos menos de 2 hábitos
    defaults_fallback = ['academia', 'terco']
    for df_val in defaults_fallback:
        if len(top_habitos) < 2 and df_val not in top_habitos:
            top_habitos.append(df_val)
    while len(top_habitos) < 2:
        top_habitos.append('habito')
        
    # Processar Sono
    df_awake = [c for c in checkins if c.checkin == 'awake']
    sleep_w1, sleep_w2, sleep_w3 = [], [], []
    sleep_daily_w3 = {d: 0.0 for d in days_range_w3}
    
    last_out = None
    for c in df_awake:
        if c.direction == 'out':
            last_out = c.data
        elif c.direction == 'in' and last_out is not None:
            duration = c.data - last_out
            duration_hours = duration.total_seconds() / 3600.0
            if 2.0 <= duration_hours <= 18.0:
                acordou_date = c.data.date()
                if w1_start <= acordou_date <= w1_end:
                    sleep_w1.append(duration_hours)
                elif w2_start <= acordou_date <= w2_end:
                    sleep_w2.append(duration_hours)
                elif w3_start <= acordou_date <= w3_end:
                    sleep_w3.append(duration_hours)
                    sleep_daily_w3[acordou_date] = round(duration_hours, 2)
            last_out = None
            
    avg_sleep_w1 = np.mean(sleep_w1) if sleep_w1 else 0
    avg_sleep_w2 = np.mean(sleep_w2) if sleep_w2 else 0
    avg_sleep_w3 = np.mean(sleep_w3) if sleep_w3 else 0
    
    # Processar Trânsito
    commutes_w1, commutes_w2, commutes_w3 = [], [], []
    commute_daily_w3 = {d: 0.0 for d in days_range_w3}
    
    commute_rel = [c for c in checkins if c.checkin in offices or c.checkin == 'casa']
    last_casa_out = None
    for c in commute_rel:
        if c.checkin == 'casa' and c.direction == 'out':
            last_casa_out = c.data
        elif c.checkin in offices and c.direction == 'in':
            if last_casa_out is not None and last_casa_out.date() == c.data.date():
                duration = c.data - last_casa_out
                duration_minutes = duration.total_seconds() / 60.0
                if 10.0 <= duration_minutes <= 240.0:
                    commute_date = c.data.date()
                    if w1_start <= commute_date <= w1_end:
                        commutes_w1.append(duration_minutes)
                    elif w2_start <= commute_date <= w2_end:
                        commutes_w2.append(duration_minutes)
                    elif w3_start <= commute_date <= w3_end:
                        commutes_w3.append(duration_minutes)
                        commute_daily_w3[commute_date] = round(duration_minutes, 1)
            last_casa_out = None
            
    avg_commute_w1 = np.mean(commutes_w1) if commutes_w1 else 0
    avg_commute_w2 = np.mean(commutes_w2) if commutes_w2 else 0
    avg_commute_w3 = np.mean(commutes_w3) if commutes_w3 else 0
    
    # Processar Clima (Temperatura e Cidade - Semana atual)
    temp_min_w3 = {d: np.nan for d in days_range_w3}
    temp_max_w3 = {d: np.nan for d in days_range_w3}
    cidade_dia_w3 = {d: 'Rio de Janeiro' for d in days_range_w3} # default
    
    clima_por_dia = {}
    for c in climas:
        d = c.data.date()
        if w3_start <= d <= w3_end:
            try:
                temp_val = float(c.temperatura.replace('°C', '').strip())
                clima_por_dia.setdefault(d, []).append(temp_val)
                # Salva a última cidade registrada para esse dia
                if c.cidade:
                    cidade_dia_w3[d] = c.cidade
            except:
                pass
                
    for d, temps in clima_por_dia.items():
        if temps:
            temp_min_w3[d] = min(temps)
            temp_max_w3[d] = max(temps)
            
    return {
        'w3_start': w3_start,
        'w3_end': w3_end,
        'days_range_w3': days_range_w3,
        'sleep_daily_w3': sleep_daily_w3,
        'commute_daily_w3': commute_daily_w3,
        'temp_min_w3': temp_min_w3,
        'temp_max_w3': temp_max_w3,
        'cidade_dia_w3': cidade_dia_w3,
        
        # Hábitos dinâmicos top 2
        'top_habitos': top_habitos,
        'habitos_trends': habitos_trends,
        'habitos_daily_w3': habitos_daily_w3,
        
        # Histórico comparativo geral
        'semanas_labels': ['Semana -2', 'Semana -1', 'Semana Atual'],
        'sleep_trends': [avg_sleep_w1, avg_sleep_w2, avg_sleep_w3],
        'commute_trends': [avg_commute_w1, avg_commute_w2, avg_commute_w3]
    }

def gerar_dashboard(metricas):
    days_range_w3 = metricas['days_range_w3']
    days_str_w3 = [d.strftime('%a\n%d/%m') for d in days_range_w3]
    
    # Cores e Estilo Escuro Premium (Design Vertical 9:21)
    plt.style.use('dark_background')
    fig, axs = plt.subplots(5, 1, figsize=(9, 21)) # Aumentado de 4 para 5 subplots, altura para 21
    fig.patch.set_facecolor('#0f0f13') # Fundo profundo escuro
    
    # Paleta de Cores Premium
    top_habitos = metricas['top_habitos']
    color_h1 = '#06d6a0'      # Mint Teal
    color_h2 = '#ffb703'      # Amber Gold
    color_sleep = '#7b2cbf'   # Royal Indigo/Purple
    color_sleep_line = '#a29bfe' # Lavender
    color_commute = '#f72585' # Deep Pink/Coral
    color_temp_max = '#ff5a5f' # Warm Red
    color_temp_min = '#3a86c8' # Soft Blue
    
    for ax in axs:
        ax.set_facecolor('#16161a') # Cartões ligeiramente mais claros
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#2e2e33')
        ax.spines['bottom'].set_color('#2e2e33')
        ax.tick_params(colors='#a0a0aa', labelsize=11)
        ax.yaxis.grid(True, linestyle='-', color='#222226', alpha=0.8) # Gridlines escuras e discretas
        ax.set_axisbelow(True)
        
    x = np.arange(7)
    width = 0.3
    
    # 1. Hábitos Diários Dinâmicos (Semana Atual)
    h1_name = top_habitos[0]
    h2_name = top_habitos[1]
    
    h1_vals = [metricas['habitos_daily_w3'][h1_name][d] if h1_name in metricas['habitos_daily_w3'] else 0 for d in days_range_w3]
    h2_vals = [metricas['habitos_daily_w3'][h2_name][d] if h2_name in metricas['habitos_daily_w3'] else 0 for d in days_range_w3]
    
    axs[0].bar(x - width/2, h1_vals, width, label=h1_name.capitalize(), color=color_h1)
    axs[0].bar(x + width/2, h2_vals, width, label=h2_name.capitalize(), color=color_h2)
    axs[0].set_title('Semana Atual: Hábitos Diários', color='#f1f1f1', fontsize=14, pad=10, weight='bold')
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(days_str_w3, fontsize=11)
    axs[0].legend(facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6', fontsize=11)
    axs[0].set_ylabel('Frequência', color='#a0a0aa', fontsize=12)
    axs[0].set_ylim(0, max(h1_vals + h2_vals + [2]))
    
    # 2. Sono Diário (Semana Atual)
    sleep_vals = [metricas['sleep_daily_w3'][d] for d in days_range_w3]
    plot_sleep_x = [i for i, v in enumerate(sleep_vals) if v > 0]
    plot_sleep_y = [v for v in sleep_vals if v > 0]
    
    # Gráfico de Área Suave (Premium Area Chart)
    axs[1].plot(plot_sleep_x, plot_sleep_y, marker='o', linewidth=2.5, color=color_sleep_line, label='Sono Real')
    axs[1].fill_between(plot_sleep_x, plot_sleep_y, color=color_sleep, alpha=0.15)
    
    if len(plot_sleep_y) > 0:
        avg_sleep_w3 = np.mean(plot_sleep_y)
        axs[1].axhline(avg_sleep_w3, linestyle='--', color='#ff6b6b', alpha=0.9, label=f'Média Sem. Atual ({avg_sleep_w3:.1f}h)')
    axs[1].set_title('Semana Atual: Horas de Sono por Noite', color='#f1f1f1', fontsize=14, pad=10, weight='bold')
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(days_str_w3, fontsize=11)
    axs[1].set_ylabel('Horas', color='#a0a0aa', fontsize=12)
    axs[1].set_ylim(0, 12)
    axs[1].legend(facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6', fontsize=11)
    
    # 3. Trânsito para o Escritório (Semana Atual)
    commute_vals = [metricas['commute_daily_w3'][d] for d in days_range_w3]
    axs[2].bar(x, commute_vals, color=color_commute, width=0.4, label='Trânsito')
    
    offices = {'EDISEN', 'EDIHB', 'CENPES'}
    for i, d in enumerate(days_range_w3):
        val = commute_vals[i]
        if val > 0:
            from app import Checkin
            office_c = Checkin.query.filter(
                Checkin.data >= datetime.combine(d, datetime.min.time()),
                Checkin.data <= datetime.combine(d, datetime.max.time()),
                Checkin.checkin.in_(offices)
            ).first()
            office_name = office_c.checkin if office_c else 'Esc.'
            axs[2].text(i, val + 2, f"{val:.0f}m\n({office_name})", ha='center', va='bottom', color='#e0e0e6', fontsize=9, weight='bold')
            
    axs[2].set_title('Semana Atual: Tempo de Trânsito para o Escritório', color='#f1f1f1', fontsize=14, pad=10, weight='bold')
    axs[2].set_xticks(x)
    axs[2].set_xticklabels(days_str_w3, fontsize=11)
    axs[2].set_ylabel('Minutos', color='#a0a0aa', fontsize=12)
    axs[2].set_ylim(0, max(commute_vals + [60]) + 20)
    
    # 4. Clima & Cidades Visitadas (Reintroduzido com rótulo dinâmico)
    t_min_vals = [metricas['temp_min_w3'][d] for d in days_range_w3]
    t_max_vals = [metricas['temp_max_w3'][d] for d in days_range_w3]
    axs[3].plot(x, t_max_vals, marker='^', color=color_temp_max, linewidth=2, label='Máx')
    axs[3].plot(x, t_min_vals, marker='v', color=color_temp_min, linewidth=2, label='Mín')
    axs[3].fill_between(x, t_min_vals, t_max_vals, color='#585b70', alpha=0.15)
    
    ultima_cidade = None
    for i, d in enumerate(days_range_w3):
        cid = metricas['cidade_dia_w3'][d]
        t_max = t_max_vals[i]
        if not np.isnan(t_max):
            # Mostra a cidade quando ela muda ou no primeiro dia
            if cid != ultima_cidade:
                axs[3].text(i, t_max + 1, cid, ha='center', va='bottom', color='#cdd6f4', fontsize=9, weight='bold')
                ultima_cidade = cid
                
    axs[3].set_title('Semana Atual: Clima & Cidades Visitadas', color='#f1f1f1', fontsize=14, pad=10, weight='bold')
    axs[3].set_xticks(x)
    axs[3].set_xticklabels(days_str_w3, fontsize=11)
    axs[3].set_ylabel('Graus Celsius (°C)', color='#a0a0aa', fontsize=11)
    axs[3].set_ylim(10, 35)
    axs[3].legend(facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6', fontsize=11)
    
    # 5. Comparação de Desempenho (3 Semanas - Ambos os Hábitos + Sono!)
    semanas_labels = metricas['semanas_labels']
    h1_trends = metricas['habitos_trends'][h1_name] if h1_name in metricas['habitos_trends'] else [0, 0, 0]
    h2_trends = metricas['habitos_trends'][h2_name] if h2_name in metricas['habitos_trends'] else [0, 0, 0]
    sleep_trends = metricas['sleep_trends']
    
    # Desenhar barras agrupadas para os dois hábitos principais
    bar_x = np.arange(3)
    axs[4].bar(bar_x - 0.15, h1_trends, width=0.3, color=color_h1, label=f'{h1_name.capitalize()}')
    axs[4].bar(bar_x + 0.15, h2_trends, width=0.3, color=color_h2, label=f'{h2_name.capitalize()}')
    axs[4].set_ylabel('Hábitos (Total)', color='#a0a0aa', fontsize=12)
    axs[4].tick_params(axis='y', labelsize=11)
    
    ax4_twin = axs[4].twinx()
    ax4_twin.spines['top'].set_visible(False)
    ax4_twin.spines['left'].set_visible(False)
    ax4_twin.spines['right'].set_color('#2e2e33')
    ax4_twin.plot(bar_x, sleep_trends, marker='s', markersize=8, color=color_sleep_line, linewidth=3, label='Sono (Média)')
    ax4_twin.fill_between(bar_x, sleep_trends, color=color_sleep, alpha=0.1)
    ax4_twin.set_ylabel('Sono (Média Horas)', color=color_sleep_line, fontsize=12)
    ax4_twin.tick_params(axis='y', labelcolor=color_sleep_line, labelsize=11)
    ax4_twin.set_ylim(0, 10)
    
    # Juntar legenda de ambos os eixos
    lines, labels = axs[4].get_legend_handles_labels()
    lines2, labels2 = ax4_twin.get_legend_handles_labels()
    axs[4].legend(lines + lines2, labels + labels2, facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6', loc='upper left', fontsize=11)
    
    axs[4].set_title('Histórico: Comparativo das Últimas 3 Semanas', color='#f1f1f1', fontsize=14, pad=10, weight='bold')
    axs[4].set_xticks(bar_x)
    axs[4].set_xticklabels(semanas_labels, fontsize=11)
    axs[4].yaxis.grid(False)
    
    w3_start = metricas['w3_start']
    w3_end = metricas['w3_end']
    plt.suptitle(f"Relatório de Performance\nOtávio — {w3_start.strftime('%d/%m')} a {w3_end.strftime('%d/%m/%Y')}", color='#ffffff', fontsize=18, weight='bold', y=0.99)
    plt.tight_layout()
    
    # Exporta para bytes com resolução DPI=150
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none', dpi=150)
    buf.seek(0)
    plt.close()
    return buf.read()

def gerar_resumo_ia(metricas, metricas_ml=None):
    sleep_trends = metricas['sleep_trends']
    commute_trends = metricas['commute_trends']
    
    # Clima da semana atual
    t_min_vals = [metricas['temp_min_w3'][d] for d in metricas['days_range_w3']]
    t_max_vals = [metricas['temp_max_w3'][d] for d in metricas['days_range_w3']]
    t_min_clean = [v for v in t_min_vals if not np.isnan(v)]
    t_max_clean = [v for v in t_max_vals if not np.isnan(v)]
    t_min = min(t_min_clean) if t_min_clean else 20.0
    t_max = max(t_max_clean) if t_max_clean else 25.0
    
    # Cidades visitadas na semana atual
    cidades_visitadas = sorted(list(set(metricas['cidade_dia_w3'].values())))
    cidades_str = ", ".join(cidades_visitadas)
    
    # Gerar a string de hábitos dinâmicos
    habitos_trends = metricas['habitos_trends']
    trends_str = ""
    for hab, counts in habitos_trends.items():
        if sum(counts) > 0:
            trends_str += f"- {hab.capitalize()}: {counts[0]} (Semana -2) -> {counts[1]} (Semana -1) -> {counts[2]} (Semana Atual)\n"
            
    ml_str = ""
    if metricas_ml:
        ml_str = "Precisão da Inteligência Artificial (Modelos Preditivos):\n"
        for m in metricas_ml:
            acuracia = 1 - m['mae']
            ml_str += f"- {m['checkin'].capitalize()}: {m['count']} eventos | Previstos c/ média de {m['min_antes']:.1f}min de antecedência | Acurácia {acuracia*100:.1f}%\n"

    prompt = (
        f"Consolidei o histórico das últimas 3 semanas do Otávio:\n\n"
        f"Hábitos registrados:\n{trends_str}\n"
        f"Média de Sono por noite:\n"
        f"- {sleep_trends[0]:.1f}h (Semana -2) -> {sleep_trends[1]:.1f}h (Semana -1) -> {sleep_trends[2]:.1f}h (Semana Atual)\n\n"
        f"Tempo de Trânsito médio:\n"
        f"- {commute_trends[0]:.1f}m (Semana -2) -> {commute_trends[1]:.1f}m (Semana -1) -> {commute_trends[2]:.1f}m (Semana Atual)\n\n"
        f"Localização na Semana Atual:\n"
        f"- Cidades visitadas/onde esteve: {cidades_str}\n"
        f"- Temperaturas na Semana Atual: Mínima de {t_min:.1f}°C, Máxima de {t_max:.1f}°C\n\n"
        f"{ml_str}\n"
        f"Escreva uma análise comparativa dos hábitos dele ao longo dessas 3 semanas. Identifique tendências "
        f"(se ele está melhorando o sono, diminuindo ou aumentando academia, mantendo rezas do terço consistentes, ou se apareceram hábitos novos de forma dinâmica). "
        f"Comente de forma inteligente e descontraída se ele viajou ou esteve em cidades diferentes (como {cidades_str}) e o clima por lá. "
        f"Se os dados de 'Precisão da Inteligência Artificial' estiverem disponíveis, elogie ou brinque rapidamente com o fato de que a IA (Skynet) está conseguindo prever os passos dele com X% de acurácia ou Y min de antecedência. "
        f"Gere um texto curto, motivacional, descontraído e inteligente para enviar pelo WhatsApp (máximo 450 caracteres). "
        f"Use asteriscos para negrito e fale diretamente com o Otávio."
    )
    
    # Usa OpenAI o3-mini
    try:
        from agent import client
        completion = client.chat.completions.create(
            model="o3-mini",
            messages=[
                {
                    "role": "user",
                    "content": f"Você é um assistente virtual descontraído que gera análises e insights sobre o histórico de hábitos semanais do usuário. Fale em português do Brasil.\n\nDados:\n{prompt}"
                }
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Erro ao chamar OpenAI o3-mini: {e}")
        
    # Fallback estático
    return (
        f"🤖 *Histórico de Performance:* \n"
        f"Otávio, nas últimas 3 semanas seus hábitos evoluíram. Você esteve em {cidades_str}. "
        f"O sono médio oscilou: {sleep_trends[0]:.1f}h -> {sleep_trends[1]:.1f}h -> {sleep_trends[2]:.1f}h. Continue buscando consistência!"
    )

def gerar_e_enviar_relatorio(phone_number_id, from_number):
    from app import salvar_documento_direto, DocumentoBinario
    import send_msg
    
    # Período: 21 dias (terminando hoje)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=20)
    
    # Normalizar datas
    start_date = datetime.combine(start_date.date(), datetime.min.time())
    end_date = datetime.combine(end_date.date(), datetime.max.time())
    
    # 1. Recuperar dados
    checkins, climas = obter_dados_semana(start_date, end_date)
    if not checkins:
        return "Nenhum check-in registrado nas últimas 3 semanas para gerar o relatório."
        
    # 1.5. Obter métricas de Machine Learning (Precisão dos modelos preditivos)
    metricas_ml = obter_metricas_ml(start_date, end_date)
    
    # 2. Processar métricas
    metricas = processar_metricas(checkins, climas, start_date, end_date)
    
    # 3. Gerar imagem do painel vertical
    img_data = gerar_dashboard(metricas)
    
    # 4. Salvar imagem no banco como DocumentoBinario
    titulo = f"Relatorio_Semanal_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
    desc = f"Painel vertical de performance com histórico de 3 semanas (de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')})."
    
    salvar_documento_direto(titulo, desc, img_data)
    
    # 5. Recuperar o ID do documento
    doc = DocumentoBinario.query.filter_by(nome_do_documento=titulo).order_by(DocumentoBinario.id.desc()).first()
    if not doc:
        return "Não foi possível recuperar a imagem do relatório recém-gerada."
        
    # 6. Gerar resumo explicativo e comparativo via IA
    insight_text = gerar_resumo_ia(metricas, metricas_ml)
    
    # 7. Enviar via WhatsApp (imagem + legenda)
    endpoint = f"recuperar_documento/{doc.id}"
    send_msg.send_wapp_image(phone_number_id, from_number, insight_text, endpoint)
    
    return insight_text
