import os
import time
import requests
from flask import Flask
from threading import Thread

# 1. Configuração do Servidor Web (Evita erro de Timed Out no Render)
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

# 2. Leitura Segura de Variáveis de Ambiente
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Coordenadas aproximadas (raio de 250 km a partir de Piumhi)
BOTTOM = -22.75
LEFT = -48.30
TOP = -18.25
RIGHT = -43.70

WAZE_URL = f"https://www.waze.com/row-rtserver/web/TGeoRSS?top={TOP}&bottom={BOTTOM}&left={LEFT}&right={RIGHT}&env=row&types=alerts"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

alertas_enviados = set()

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar mensagem no Telegram: {e}")

def monitorar():
    print("Verificando tráfego no Waze...")
    try:
        response = requests.get(WAZE_URL, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            alerts = data.get("alerts", [])
            
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

# 3. Execução Principal
if __name__ == "__main__":
    # Inicia o servidor para manter o Render ativo
    keep_alive()
    
    # Envia mensagem inicial para o seu Telegram
    if TOKEN and CHAT_ID:
        enviar_telegram("🤖 *Bot de Monitoramento Iniciado com Sucesso!*")
    
    # Loop de monitoramento (executa a cada 5 minutos)
    while True:
        monitorar()
        time.sleep(300)
