import os
import time
import requests
from flask import Flask
from threading import Thread

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

# Coordenadas da região de Piumhi
BOTTOM = -22.75
LEFT = -48.30
TOP = -18.25
RIGHT = -43.70
PIUMHI_LAT = -20.46
PIUMHI_LON = -45.95

WAZE_URL = f"https://www.waze.com/row-rtserver/web/TGeoRSS?top={TOP}&bottom={BOTTOM}&left={LEFT}&right={RIGHT}&env=row&types=alerts,jams"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

alertas_enviados = set()
last_update_id = 0

TIPOS_IGNORADOS = ["POLICE", "POLICE_HIDE", "POLICE_VISIBLE", "SPEED_CAM", "ROAD_CLOSED_EVENT"]

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
                
                if text.startswith("/status"):
                    enviar_telegram("🔎 *Verificando tráfego atual...*")
                    monitorar(forcar_envio_status=True)
                elif text.startswith("/clima"):
                    enviar_telegram(obter_clima())
    except Exception as e:
        print(f"Erro ao checar comandos: {e}")

def monitorar(forcar_envio_status=False):
    print("Verificando tráfego e alertas no Waze...")
    try:
        response = requests.get(WAZE_URL, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts", [])
            jams = data.get("jams", [])
            
            alertas_novos = 0
            
            for alert in alerts:
                alert_type = alert.get("type", "")
                subtype = alert.get("subtype", alert_type)
                
                if alert_type in TIPOS_IGNORADOS or subtype in TIPOS_IGNORADOS:
                    continue
                
                alert_id = alert.get("uuid")
                street = alert.get("street", "Via não informada")
                report_description = alert.get("reportDescription", "")
                city = alert.get("city", "")

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

            for jam in jams:
                jam_id = jam.get("uuid")
                street = jam.get("street", "Via não informada")
                city = jam.get("city", "")
                speed_kmh = jam.get("speed", 0) * 3.6
                delay_min = round(jam.get("delay", 0) / 60)
                length_m = jam.get("length", 0)

                if jam_id and jam_id not in alertas_enviados and delay_min >= 2:
                    mensagem = (
                        f"🐢 *LENTIDÃO DETECTADA*\n\n"
                        f"📍 *Local:* {street} ({city if city else 'Região'})\n"
                        f"⏱️ *Atraso estimado:* ~{delay_min} min\n"
                        f"📏 *Extensão:* {length_m} metros\n"
                        f"🚗 *Velocidade média:* {speed_kmh:.1f} km/h"
                    )
                    enviar_telegram(mensagem)
                    alertas_enviados.add(jam_id)
                    alertas_novos += 1

            if forcar_envio_status and alertas_novos == 0:
                enviar_telegram("✅ *Tráfego Normal:* Nenhum alerta importante ou retenção relevante detectada no momento nas rodovias da região.")

        else:
            print(f"Erro na API do Waze: {response.status_code}")
    except Exception as e:
        print(f"Erro na requisição: {e}")

if __name__ == "__main__":
    print("Iniciando servidor Flask de sustentação...")
    keep_alive()
    
    enviar_telegram("🤖 *Bot Atualizado!* Monitoramento e comandos prontos.")
    
    # Força a primeira checagem imediata ao iniciar
    monitorar()
    ultimo_monitoramento = time.time()
    
    while True:
        processar_comandos()
        
        agora = time.time()
        if agora - ultimo_monitoramento >= 300:
            monitorar()
            ultimo_monitoramento = agora
            
        time.sleep(3)
