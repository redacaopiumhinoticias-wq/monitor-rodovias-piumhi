import os
import time
import requests
from flask import Flask
from threading import Thread
from waze_traffic_alerts import WazeData, BoundingBox, Location

app = Flask('')

@app.route('/')
def home():
    return "Bot de Monitoramento Rodoviário Online!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Coordenadas ajustadas para Piumhi e região da MG-050
BOTTOM = -20.90
LEFT = -46.40
TOP = -20.00
RIGHT = -45.40

PIUMHI_LAT = -20.46
PIUMHI_LON = -45.95

# Inicializa o cliente do Waze com a caixa de seleção geográfica (BoundingBox)
bbox = BoundingBox(
    bottom_left=Location(lat=BOTTOM, lon=LEFT),
    top_right=Location(lat=TOP, lon=RIGHT)
)
waze = WazeData(bbox)

alertas_enviados = set()
last_update_id = 0
inicio_bot = time.time()

def enviar_telegram(mensagem):
    if not TOKEN or not CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN ou CHAT_ID nao configurados!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Envio Telegram Status: {r.status_code}")
    except Exception as e:
        print(f"Erro ao enviar mensagem no Telegram: {e}")

def checar_status_waze():
    """Testa a conexão com o Waze usando o cliente oficial da biblioteca."""
    try:
        data = waze.get_traffic_data()
        total_alerts = len(data.alerts) if data.alerts else 0
        total_jams = len(data.jams) if data.jams else 0
        return True, f"Conectado ({total_alerts} alertas / {total_jams} retenções)"
    except Exception as e:
        return False, f"Falha na conexão: {e}"

def obter_clima():
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={PIUMHI_LAT}&longitude={PIUMHI_LON}&current_weather=true"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            weather = r.json().get("current_weather", {})
            temp = weather.get("temperature", "N/A")
            wind = weather.get("windspeed", "N/A")
            return f"☀️ *Clima em Piumhi:* {temp}°C | Vento: {wind} km/h"
    except Exception:
        pass
    return "Não foi possível obter dados do clima no momento."

def processar_comandos():
    global last_update_id
    if not TOKEN:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=2"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            for update in updates:
                last_update_id = update.get("update_id", last_update_id)
                message = update.get("message", {})
                text = message.get("text", "").strip()
                
                if text.startswith("/ping") or text.startswith("/ajuda"):
                    waze_ok, waze_info = checar_status_waze()
                    status_waze_str = f"🟢 *Lendo Waze:* {waze_info}" if waze_ok else f"🔴 *Waze Inacessível:* {waze_info}"
                    tempo_ativo_min = round((time.time() - inicio_bot) / 60)
                    
                    resposta = (
                        f"🤖 *STATUS DO BOT*\n\n"
                        f"✅ *Servidor Render:* Ativo / Online\n"
                        f"⏱️ *Tempo no ar:* ~{tempo_ativo_min} min\n"
                        f"{status_waze_str}\n\n"
                        f"📌 *Comandos disponíveis:*\n"
                        f"• `/ping` - Checa se o bot está ativo\n"
                        f"• `/status` - Varre o tráfego da região agora\n"
                        f"• `/clima` - Consulta a temperatura atual"
                    )
                    enviar_telegram(resposta)

                elif text.startswith("/status"):
                    enviar_telegram("🔎 *Verificando tráfego na região de Piumhi...*")
                    monitorar(forcar_envio_status=True)

                elif text.startswith("/clima"):
                    enviar_telegram(obter_clima())

    except Exception as e:
        print(f"Erro ao checar comandos: {e}")

def monitorar(forcar_envio_status=False):
    print("Verificando alertas e congestionamentos no Waze...")
    try:
        traffic_data = waze.get_traffic_data()
        alerts = traffic_data.alerts or []
        jams = traffic_data.jams or []
        
        alertas_novos = 0
        
        # 1. Processa Alertas
        for alert in alerts:
            alert_id = getattr(alert, "uuid", None) or getattr(alert, "id", None)
            alert_type = getattr(alert, "type", "ALERTA")
            subtype = getattr(alert, "subtype", alert_type)
            street = getattr(alert, "street", "Via não informada")
            report_description = getattr(alert, "report_description", "")
            city = getattr(alert, "city", "")

            if alert_id and alert_id not in alertas_enviados:
                mensagem = (
                    f"🚨 *ALERTA DE TRÂNSITO*\n\n"
                    f"📍 *Local:* {street} ({city if city else 'Região'})\n"
                    f"⚠️ *Tipo:* {subtype}\n"
                    f"📝 *Detalhes:* {report_description or 'Sem descrição extra'}"
                )
                enviar_telegram(mensagem)
                alertas_enviados.add(alert_id)
                alertas_novos += 1

        # 2. Processa Retenções
        for jam in jams:
            jam_id = getattr(jam, "uuid", None) or getattr(jam, "id", None)
            street = getattr(jam, "street", "Via não informada")
            city = getattr(jam, "city", "")
            speed = getattr(jam, "speed", 0) or 0
            speed_kmh = speed * 3.6
            delay = getattr(jam, "delay", 0) or 0
            delay_min = round(delay / 60)
            length_m = getattr(jam, "length", 0)

            if jam_id and jam_id not in alertas_enviados:
                mensagem = (
                    f"🐢 *LENTIDÃO / CONGESTIONAMENTO*\n\n"
                    f"📍 *Local:* {street} ({city if city else 'Região'})\n"
                    f"⏱️ *Atraso estimado:* ~{delay_min} min\n"
                    f"📏 *Extensão:* {length_m} metros\n"
                    f"🚗 *Velocidade média:* {speed_kmh:.1f} km/h"
                )
                enviar_telegram(mensagem)
                alertas_enviados.add(jam_id)
                alertas_novos += 1

        if forcar_envio_status and alertas_novos == 0:
            enviar_telegram(f"✅ *Tráfego Normal:* Nenhum NOVO alerta registrado no momento nas rodovias da região (Total ativo no Waze: {len(alerts)} alertas).")

    except Exception as e:
        print(f"Erro ao buscar dados do Waze: {e}")

if __name__ == "__main__":
    print("Iniciando servidor Flask de sustentação...")
    keep_alive()
    
    enviar_telegram("🤖 *Bot Atualizado!* Digite `/ping` para checar o status.")
    
    monitorar()
    ultimo_monitoramento = time.time()
    
    while True:
        processar_comandos()
        
        agora = time.time()
        if agora - ultimo_monitoramento >= 300:
            monitorar()
            ultimo_monitoramento = agora
            
        time.sleep(3)
