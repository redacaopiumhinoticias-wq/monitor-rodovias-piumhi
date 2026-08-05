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

# Coordenadas da região (Piumhi e arredores)
BOTTOM = -22.75
LEFT = -48.30
TOP = -18.25
RIGHT = -43.70

WAZE_URL = f"https://www.waze.com/row-rtserver/web/TGeoRSS?top={TOP}&bottom={BOTTOM}&left={LEFT}&right={RIGHT}&env=row&types=alerts"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

alertas_enviados = set()

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

def monitorar():
    print("Verificando tráfego no Waze...")
    try:
        response = requests.get(WAZE_URL, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts", [])
            print(f"Alertas encontrados na regiao: {len(alerts)}")
            
            for alert in alerts:
                alert_id = alert.get("uuid")
                street = alert.get("street", "Via não informada")
                subtype = alert.get("subtype", alert.get("type", "Alerta"))
                report_description = alert.get("reportDescription", "")
                city = alert.get("city", "")

                if alert_id not in alertas_enviados:
                    mensagem = (
                        f"🚨 *ALERTA DE TRÂNSITO*\n\n"
                        f"📍 *Local:* {street} ({city})\n"
                        f"⚠️ *Tipo:* {subtype}\n"
                        f"📝 *Detalhes:* {report_description or 'Sem descrição extra'}"
                    )
                    enviar_telegram(mensagem)
                    alertas_enviados.add(alert_id)
        else:
            print(f"Erro na API do Waze: {response.status_code}")
    except Exception as e:
        print(f"Erro na requisição: {e}")

if __name__ == "__main__":
    print("Iniciando servidor Flask de sustentação...")
    keep_alive()
    
    print("Enviando mensagem de teste no Telegram...")
    enviar_telegram("🤖 *Bot de Monitoramento Iniciado com Sucesso!*")
    
    while True:
        monitorar()
        time.sleep(300)
