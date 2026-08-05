import os
import threading
import time
import requests
from datetime import datetime
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler

# Inicializa o Flask para manter o serviço ativo no Render.com
app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Variáveis globais para monitoramento de estado
TEMPO_INICIO = datetime.now()
status_waze_atual = "ativo"

# Coordenadas de Piumhi - MG (100km de raio)
LAT_CENTER = -20.4544
LON_CENTER = -45.7142
DELTA = 0.95

TOP = LAT_CENTER + DELTA
BOTTOM = LAT_CENTER - DELTA
RIGHT = LON_CENTER + DELTA
LEFT = LON_CENTER - DELTA

alertas_enviados = set()

def enviar_telegram(mensagem, chat_id=None):
    target_chat = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Erro ao enviar mensagem para o Telegram: {e}")

def formatar_tempo_no_ar():
    agora = datetime.now()
    diferenca = agora - TEMPO_INICIO
    segundos_totais = int(diferenca.total_seconds())
    
    dias = segundos_totais // 86400
    horas = (segundos_totais % 86400) // 3600
    minutos = (segundos_totais % 3600) // 60
    
    partes = []
    if dias > 0:
        partes.append(f"{dias}d")
    if horas > 0 or dias > 0:
        partes.append(f"{horas}h")
    partes.append(f"{minutos}m")
    
    return " ".join(partes) if partes else "menos de 1m"

def gerar_texto_ping():
    servidor_render = "✅ Ativo (Online)"
    tempo_ar = formatar_tempo_no_ar()
    
    if status_waze_atual == "ativo":
        waze_status = "🟢 Ativo"
    else:
        waze_status = "🔴 Erro"
        
    texto = (
        "🤖 **STATUS DO BOT**\n\n"
        f"✅ **Servidor Render:** {servidor_render}\n"
        f"⏱️ **Tempo no ar:** {tempo_ar}\n"
        f"🔴 **Waze:** {waze_status}\n\n"
        "📌 **Comandos disponíveis:**\n"
        "• `/ping` - Checa se o bot está ativo\n"
        "• `/status` - Varre o tráfego da região agora"
    )
    return texto

def buscar_alertas_waze():
    global status_waze_atual
    print(f"[{datetime.now()}] Consultando Waze para a região de Piumhi...")
    url = f"https://www.waze.com/row-rtserver/web/Traf/WazeTrafficServer/alerts?bottom={BOTTOM}&left={LEFT}&top={TOP}&right={RIGHT}&types=alerts"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            status_waze_atual = "erro"
            return
        
        status_waze_atual = "ativo"
        data = response.json()
        alerts = data.get("alerts", [])
        agora = datetime.utcnow()
        
        for alert in alerts:
            alert_id = alert.get("uuid")
            if not alert_id or alert_id in alertas_enviados:
                continue
                
            pub_millis = alert.get("pubMillis", 0)
            pub_time = datetime.utcfromtimestamp(pub_millis / 1000.0)
            diferenca_minutos = (agora - pub_time).total_seconds() / 60.0
            
            # Respeita o delay mínimo de 3 minutos
            if diferenca_minutos < 3:
                continue
                
            tipo = alert.get("type", "GERAL")
            subtipo = alert.get("subtype", "N/A")
            rua = alert.get("street", "Via não especificada")
            cidade = alert.get("city", "Região de Piumhi")
            
            tipos_map = {
                "ACCIDENT": "🚗 **Acidente**",
                "HAZARD": "⚠️ **Perigo / Obstáculo / Buraco**",
                "JAM": "🛑 **Lentidão / Trânsito**",
                "ROAD_CLOSED": "🚧 **Via Interditada / Obras**",
                "POLICE": "👮 **Polícia**"
            }
            
            tipo_formatado = tipos_map.get(tipo, f"📢 **Alerta: {tipo}**")
            
            mensagem = (
                f"{tipo_formatado} (@alertarodpiumhi_bot)\n\n"
                f"🛣️ **Local:** {rua}, {cidade}\n"
                f"📋 **Detalhes:** {subtipo}\n"
                f"⏱️ **Postado há:** cerca de {int(diferenca_minutos)} minutos\n"
                f"📍 [Ver no Google Maps](https://maps.google.com/?q={alert.get('location', {}).get('y')},{alert.get('location', {}).get('x')})"
            )
            
            enviar_telegram(mensagem)
            alertas_enviados.add(alert_id)
            
            if len(alertas_enviados) > 1000:
                alertas_enviados.clear()
                
    except Exception as e:
        print(f"Erro ao processar Waze: {e}")
        status_waze_atual = "erro"

# Rota simples para o Render saber que o app está ativo
@app.route('/')
def home():
    return "Bot @alertarodpiumhi_bot está rodando com sucesso!"

# Webhook para receber mensagens do Telegram e responder aos comandos /ping e /status
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def receber_telegram():
    data = request.get_json()
    if data and "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        texto = message.get("text", "").strip()
        
        if texto == "/ping":
            resposta = gerar_texto_ping()
            enviar_telegram(resposta, chat_id)
            
        elif texto == "/status":
            enviar_telegram("🔄 Executando varredura manual imediata no Waze...", chat_id)
            buscar_alertas_waze()
            enviar_telegram("✅ Varredura manual concluída com sucesso!", chat_id)
            
    return "OK", 200

def configurar_webhook():
    if TELEGRAM_TOKEN:
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url:
            webhook_url = f"{render_url}/{TELEGRAM_TOKEN}"
            url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
            requests.get(url_api)
            print(f"Webhook configurado para: {webhook_url}")

if __name__ == "__main__":
    # Inicia o agendador de tarefas em background para checar o Waze a cada 2 minutos
    scheduler = BackgroundScheduler()
    scheduler.add_job(buscar_alertas_waze, 'interval', minutes=2)
    scheduler.start()
    
    # Configura o webhook do Telegram após 5 segundos para garantir que o app subiu
    threading.Timer(5.0, configurar_webhook).start()
    
    # Roda o servidor Flask na porta exigida pelo Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
