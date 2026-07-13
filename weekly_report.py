import os
import matplotlib
matplotlib.use('Agg')  # Necessário para rodar sem interface gráfica (GUI)
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import io

def obter_dados_semana(start_date, end_date):
    from app import Checkin, Clima
    
    # Consulta checkins no período
    checkins = Checkin.query.filter(Checkin.data.between(start_date, end_date)).order_by(Checkin.data).all()
    
    # Consulta climas no período
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
    
    gym_w1, gym_w2, gym_w3 = 0, 0, 0
    terco_w1, terco_w2, terco_w3 = 0, 0, 0
    
    gym_daily_w3 = {d: 0 for d in days_range_w3}
    terco_daily_w3 = {d: 0 for d in days_range_w3}
    
    offices = {'EDISEN', 'EDIHB', 'CENPES'}
    
    for c in checkins:
        dt_date = c.data.date()
        is_gym = (c.checkin == 'academia' and c.direction == 'in')
        is_terco = (c.checkin == 'terco' and c.direction == 'in')
        
        if w1_start <= dt_date <= w1_end:
            if is_gym: gym_w1 += 1
            if is_terco: terco_w1 += 1
        elif w2_start <= dt_date <= w2_end:
            if is_gym: gym_w2 += 1
            if is_terco: terco_w2 += 1
        elif w3_start <= dt_date <= w3_end:
            if is_gym:
                gym_w3 += 1
                gym_daily_w3[dt_date] += 1
            if is_terco:
                terco_w3 += 1
                terco_daily_w3[dt_date] += 1
                
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
    
    # Processar Clima (Temperatura - Semana atual)
    temp_min_w3 = {d: np.nan for d in days_range_w3}
    temp_max_w3 = {d: np.nan for d in days_range_w3}
    
    clima_por_dia = {}
    for c in climas:
        d = c.data.date()
        if w3_start <= d <= w3_end:
            try:
                temp_val = float(c.temperatura.replace('°C', '').strip())
                clima_por_dia.setdefault(d, []).append(temp_val)
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
        'gym_daily_w3': gym_daily_w3,
        'terco_daily_w3': terco_daily_w3,
        'sleep_daily_w3': sleep_daily_w3,
        'commute_daily_w3': commute_daily_w3,
        'temp_min_w3': temp_min_w3,
        'temp_max_w3': temp_max_w3,
        
        # Histórico comparativo
        'semanas_labels': ['Semana -2', 'Semana -1', 'Semana Atual'],
        'gym_trends': [gym_w1, gym_w2, gym_w3],
        'terco_trends': [terco_w1, terco_w2, terco_w3],
        'sleep_trends': [avg_sleep_w1, avg_sleep_w2, avg_sleep_w3],
        'commute_trends': [avg_commute_w1, avg_commute_w2, avg_commute_w3]
    }

def gerar_dashboard(metricas):
    days_range_w3 = metricas['days_range_w3']
    days_str_w3 = [d.strftime('%a\n%d/%m') for d in days_range_w3]
    
    # Cores e Estilo Escuro Premium (Design Vertical 9:17)
    plt.style.use('dark_background')
    fig, axs = plt.subplots(4, 1, figsize=(9, 17))
    fig.patch.set_facecolor('#0f0f13') # Fundo profundo escuro
    
    # Paleta de Cores Premium
    color_gym = '#06d6a0'     # Mint Teal
    color_terco = '#ffb703'   # Amber Gold
    color_sleep = '#7b2cbf'   # Royal Indigo/Purple
    color_sleep_line = '#a29bfe' # Lavender
    color_commute = '#f72585' # Deep Pink/Coral
    
    for ax in axs:
        ax.set_facecolor('#16161a') # Cartões ligeiramente mais claros
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#2e2e33')
        ax.spines['bottom'].set_color('#2e2e33')
        ax.tick_params(colors='#a0a0aa', labelsize=10)
        ax.yaxis.grid(True, linestyle='-', color='#222226', alpha=0.8) # Gridlines escuras e discretas
        ax.set_axisbelow(True)
        
    x = np.arange(7)
    width = 0.3
    
    # 1. Hábitos Diários (Semana Atual)
    gym_vals = [metricas['gym_daily_w3'][d] for d in days_range_w3]
    terco_vals = [metricas['terco_daily_w3'][d] for d in days_range_w3]
    axs[0].bar(x - width/2, gym_vals, width, label='Academia', color=color_gym)
    axs[0].bar(x + width/2, terco_vals, width, label='Terço', color=color_terco)
    axs[0].set_title('Semana Atual: Hábitos Diários', color='#f1f1f1', fontsize=12, pad=8, weight='bold')
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(days_str_w3)
    axs[0].legend(facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6')
    axs[0].set_ylabel('Frequência', color='#a0a0aa')
    axs[0].set_ylim(0, max(gym_vals + terco_vals + [2]))
    
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
    axs[1].set_title('Semana Atual: Horas de Sono por Noite', color='#f1f1f1', fontsize=12, pad=8, weight='bold')
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(days_str_w3)
    axs[1].set_ylabel('Horas', color='#a0a0aa')
    axs[1].set_ylim(0, 12)
    axs[1].legend(facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6')
    
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
            axs[2].text(i, val + 2, f"{val:.0f}m\n({office_name})", ha='center', va='bottom', color='#e0e0e6', fontsize=8, weight='bold')
            
    axs[2].set_title('Semana Atual: Tempo de Trânsito para o Escritório', color='#f1f1f1', fontsize=12, pad=8, weight='bold')
    axs[2].set_xticks(x)
    axs[2].set_xticklabels(days_str_w3)
    axs[2].set_ylabel('Minutos', color='#a0a0aa')
    axs[2].set_ylim(0, max(commute_vals + [60]) + 20)
    
    # 4. Comparação de Desempenho (3 Semanas)
    semanas_labels = metricas['semanas_labels']
    gym_trends = metricas['gym_trends']
    sleep_trends = metricas['sleep_trends']
    
    axs[3].bar(np.arange(3) - 0.2, gym_trends, width=0.3, color=color_gym, label='Academia (Total)')
    axs[3].set_ylabel('Treinos (Total)', color=color_gym)
    axs[3].tick_params(axis='y', labelcolor=color_gym)
    
    ax3_twin = axs[3].twinx()
    ax3_twin.spines['top'].set_visible(False)
    ax3_twin.spines['left'].set_visible(False)
    ax3_twin.spines['right'].set_color('#2e2e33')
    ax3_twin.plot(np.arange(3), sleep_trends, marker='s', markersize=8, color=color_sleep_line, linewidth=3, label='Sono (Média)')
    ax3_twin.fill_between(np.arange(3), sleep_trends, color=color_sleep, alpha=0.1)
    ax3_twin.set_ylabel('Sono (Média Horas)', color=color_sleep_line)
    ax3_twin.tick_params(axis='y', labelcolor=color_sleep_line)
    ax3_twin.set_ylim(0, 10)
    
    # Juntar legenda de ambos os eixos
    lines, labels = axs[3].get_legend_handles_labels()
    lines2, labels2 = ax3_twin.get_legend_handles_labels()
    axs[3].legend(lines + lines2, labels + labels2, facecolor='#16161a', edgecolor='none', labelcolor='#e0e0e6', loc='upper left')
    
    axs[3].set_title('Histórico: Comparativo das Últimas 3 Semanas', color='#f1f1f1', fontsize=12, pad=8, weight='bold')
    axs[3].set_xticks(np.arange(3))
    axs[3].set_xticklabels(semanas_labels)
    axs[3].yaxis.grid(False)
    
    w3_start = metricas['w3_start']
    w3_end = metricas['w3_end']
    plt.suptitle(f"Relatório de Performance\nOtávio — {w3_start.strftime('%d/%m')} a {w3_end.strftime('%d/%m/%Y')}", color='#ffffff', fontsize=16, weight='bold', y=0.99)
    plt.tight_layout()
    
    # Exporta para bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), edgecolor='none')
    buf.seek(0)
    plt.close()
    return buf.read()

def gerar_resumo_ia(metricas):
    gym_trends = metricas['gym_trends']
    terco_trends = metricas['terco_trends']
    sleep_trends = metricas['sleep_trends']
    commute_trends = metricas['commute_trends']
    
    # Clima da semana atual
    t_min_vals = [metricas['temp_min_w3'][d] for d in metricas['days_range_w3']]
    t_max_vals = [metricas['temp_max_w3'][d] for d in metricas['days_range_w3']]
    t_min_clean = [v for v in t_min_vals if not np.isnan(v)]
    t_max_clean = [v for v in t_max_vals if not np.isnan(v)]
    t_min = min(t_min_clean) if t_min_clean else 20.0
    t_max = max(t_max_clean) if t_max_clean else 25.0
    
    prompt = (
        f"Consolidei o histórico das últimas 3 semanas do Otávio:\n\n"
        f"Semana -2 (Mais antiga):\n"
        f"- Academia: {gym_trends[0]} treinos\n"
        f"- Terço: {terco_trends[0]} rezas\n"
        f"- Sono Médio: {sleep_trends[0]:.1f}h/noite\n"
        f"- Trânsito Médio: {commute_trends[0]:.1f} min\n\n"
        f"Semana -1:\n"
        f"- Academia: {gym_trends[1]} treinos\n"
        f"- Terço: {terco_trends[1]} rezas\n"
        f"- Sono Médio: {sleep_trends[1]:.1f}h/noite\n"
        f"- Trânsito Médio: {commute_trends[1]:.1f} min\n\n"
        f"Semana Atual (Mais recente):\n"
        f"- Academia: {gym_trends[2]} treinos\n"
        f"- Terço: {terco_trends[2]} rezas\n"
        f"- Sono Médio: {sleep_trends[2]:.1f}h/noite\n"
        f"- Trânsito Médio: {commute_trends[2]:.1f} min\n"
        f"- Temperaturas na Semana Atual: Mínima de {t_min:.1f}°C, Máxima de {t_max:.1f}°C\n\n"
        f"Escreva uma análise comparativa dos hábitos dele ao longo dessas 3 semanas. Identifique tendências "
        f"(se ele está melhorando o sono, diminuindo ou aumentando academia, mantendo rezas do terço consistentes). "
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
        f"Otávio, nas últimas 3 semanas seus treinos foram de {gym_trends[0]} para {gym_trends[1]} e depois {gym_trends[2]} nesta semana. "
        f"Seu terço foi de {terco_trends[0]} para {terco_trends[1]} e depois {terco_trends[2]}. "
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
    insight_text = gerar_resumo_ia(metricas)
    
    # 7. Enviar via WhatsApp (imagem + legenda)
    endpoint = f"recuperar_documento/{doc.id}"
    send_msg.send_wapp_image(phone_number_id, from_number, insight_text, endpoint)
    
    return insight_text
