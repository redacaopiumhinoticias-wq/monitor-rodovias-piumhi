import os
import threading
import requests
from datetime import datetime
from flask import flask
from apscheduler.schedulers.background import BackgroundScheduler

# Inicializa o Flask (necessário para manter o serviço ativo no Render.com)
app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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

def buscar_alertas_waze():
    print(f"[{datetime.now()}] Consultando Waze para a região de Piumhi...")
    url = f"https://www.waze.com/row-rtserver/web/Traf/WazeTrafficServer/alerts?bottom={BOTTOM}&left={LEFT}&top={TOP}&right={RIGHT}&types=alerts"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return
        
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

# Rota simples para o Render saber que o app está ativo
@app.route('/')
def home():
    return "Bot @alertarodpiumhi_bot está rodando com sucesso!"

# Webhook simples para receber mensagens do Telegram e responder ao comando /status
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def receber_telegram():
    from flask import request
    data = request.get_json()
    if data and "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        texto = message.get("text", "")
        
        if texto.strip() == "/status":
            enviar_telegram("✅ **Tudo OK!** O bot está ativo, monitorando as rodovias ao redor de Piumhi e conectado corretamente.", chat_id)
            
    return "OK", 200

def configurar_webhook():
    if TELEGRAM_TOKEN:
        # Pega a URL pública gerada pelo Render automaticamente
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
