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

# Coordenadas da região de Piumhi / MG-050
MIN_LAT, MIN_LON = -20.90, -46.40
MAX_LAT, MAX_LON = -20.00, -45.40
PIUMHI_LAT, PIUMHI_LON = -20.46, -45.95

# Endpoint público do OpenStreetMap (Overpass API)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Consulta Overpass para buscar construções, barreiras e alertas nas vias da região
OVERPASS_QUERY = f"""
[out:json][timeout:10];
(
  node({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON})["highway"="construction"];
  way({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON})["highway"="construction"];
  node({MIN_LAT},{MIN_LON},{MAX_LAT},{MAX_LON})["barrier"];
);
out body;
"""

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

def obter_dados_osm():
    try:
        r = requests.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, timeout=10)
        if r.status_code == 200:
            return True, r.json().get("elements", [])
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

def checar_status_osm():
    ok, resultado = obter_dados_osm()
    if ok:
        return True, f"Conectado ({len(resultado)} alertas/obras detectados)"
    return False, f"Erro na consulta ({resultado})"

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
                    osm_ok, osm_info = checar_status_osm()
                    status_str = f"🟢 *Trânsito/Vias:* {osm_info}" if osm_ok else f"🔴 *Trânsito/Vias:* {osm_info}"
                    tempo_ativo_min = round((time.time() - inicio_bot) / 60)
                    
                    resposta = (
                        f"🤖 *STATUS DO BOT*\n\n"
                        f"✅ *Servidor Render:* Ativo / Online\n"
                        f"⏱️ *Tempo no ar:* ~{tempo_ativo_min} min\n"
                        f"{status_str}\n\n"
                        f"📌 *Comandos disponíveis:*\n"
                        f"• `/ping` - Checa se o bot está ativo\n"
                        f"• `/status` - Varre a região de Piumhi agora\n"
                        f"• `/clima` - Consulta a temperatura atual"
                    )
                    enviar_telegram(resposta)

                elif text.startswith("/status"):
                    enviar_telegram("🔎 *Verificando situação das rodovias na região de Piumhi...*")
                    monitorar(forcar_envio_status=True)

                elif text.startswith("/clima"):
                    enviar_telegram(obter_clima())

    except Exception as e:
        print(f"Erro ao checar comandos: {e}")

def monitorar(forcar_envio_status=False):
    print("Verificando vias na região...")
    ok, elementos = obter_dados_osm()
    if ok:
        novos = 0
        for elem in elementos:
            elem_id = elem.get("id")
            tags = elem.get("tags", {})
            nome_via = tags.get("name", "Rodovia/Via na região de Piumhi")
            tipo = tags.get("highway", tags.get("barrier", "Alerta na via"))
            
            if elem_id and elem_id not in alertas_enviados:
                mensagem = (
                    f"🚨 *ALERTA RODOVIÁRIO*\n\n"
                    f"📍 *Local:* {nome_via}\n"
                    f"⚠️ *Tipo:* {tipo}"
                )
                enviar_telegram(mensagem)
                alertas_enviados.add(elem_id)
                novos += 1

        if forcar_envio_status and novos == 0:
            enviar_telegram(f"✅ *Tráfego Normal:* Nenhum NOVO bloqueio ou obra detectado nas rodovias da região (Total de registros mapeados: {len(elementos)}).")
    else:
        if forcar_envio_status:
            enviar_telegram(f"⚠️ *Aviso de conexão:* {elementos}")

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
