import os
import time
import requests
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot de Monitoramento Rodoviário (TomTom) Online!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOMTOM_KEY = os.getenv("TOMTOM_KEY")

BBOX = "-46.30,-20.80,-45.50,-20.10"
PIUMHI_LAT, PIUMHI_LON = -20.46, -45.95

alertas_enviados = set()
last_update_id = 0
inicio_bot = time.time()

def enviar_telegram(mensagem):
    if not TOKEN or not CHAT_ID:
        print("ERRO: TELEGRAM_TOKEN ou CHAT_ID não configurados!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Envio Telegram Status: {r.status_code}")
    except Exception as e:
        print(f"Erro ao enviar mensagem no Telegram: {e}")

def obter_dados_tomtom():
    if not TOMTOM_KEY:
        return False, "TOMTOM_KEY não configurada no Render"
    
    key_limpa = TOMTOM_KEY.strip()
    
    # URL formatada diretamente com URL Encoding explícito nos caracteres de chaves
    url = (
        f"https://api.tomtom.com/traffic/services/5/incidentDetails"
        f"?key={key_limpa}"
        f"&bbox={BBOX}"
        f"&fields=%7Bincidents%7Bid,geometry%7Btype,coordinates%7D,properties%7BiconCategory,magnitudeOfDelay,events%7Bdescription,code%7D%7D%7D%7D"
    )
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True, r.json()
        return False, f"HTTP {r.status_code} - {r.text[:100]}"
    except Exception as e:
        return False, str(e)

def checar_status_tomtom():
    ok, resultado = obter_dados_tomtom()
    if ok:
        incidents = resultado.get("incidents", [])
        return True, f"Conectado ({len(incidents)} incidentes ativos)"
    return False, f"Erro: {resultado}"

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

def loop_comandos_telegram():
    global last_update_id
    print("Iniciando escuta de comandos do Telegram...")
    while True:
        if not TOKEN:
            time.sleep(5)
            continue
        
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=5"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for update in updates:
                    last_update_id = update.get("update_id", last_update_id)
                    message = update.get("message", {})
                    text = message.get("text", "").strip()
                    
                    if text.startswith("/ping") or text.startswith("/ajuda"):
                        tomtom_ok, tomtom_info = checar_status_tomtom()
                        status_str = f"🟢 *Monitor TomTom:* {tomtom_info}" if tomtom_ok else f"🔴 *TomTom:* {tomtom_info}"
                        tempo_ativo_min = round((time.time() - inicio_bot) / 60)
                        
                        resposta = (
                            f"🤖 *STATUS DO BOT*\n\n"
                            f"✅ *Servidor Render:* Ativo / Online\n"
                            f"⏱️ *Tempo no ar:* ~{tempo_ativo_min} min\n"
                            f"{status_str}\n\n"
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
            print(f"Erro no loop de comandos: {e}")
        
        time.sleep(1)

def monitorar(forcar_envio_status=False):
    print("Verificando incidentes na TomTom...")
    ok, data = obter_dados_tomtom()
    if ok:
        incidents = data.get("incidents", [])
        novos = 0
        
        for inc in incidents:
            inc_id = inc.get("id")
            props = inc.get("properties", {})
            events = props.get("events", [])
            descricao = events[0].get("description", "Incidente de trânsito") if events else "Aviso na via"
            
            if inc_id and inc_id not in alertas_enviados:
                mensagem = (
                    f"🚨 *ALERTA DE TRÂNSITO (TomTom)*\n\n"
                    f"📍 *Região:* Piumhi / MG-050\n"
                    f"⚠️ *Detalhes:* {descricao}"
                )
                enviar_telegram(mensagem)
                alertas_enviados.add(inc_id)
                novos += 1

        if forcar_envio_status and novos == 0:
            enviar_telegram(f"✅ *Tráfego Normal:* Nenhum NOVO alerta registrado na TomTom para a região (Total ativo: {len(incidents)}).")
    else:
        if forcar_envio_status:
            enviar_telegram(f"⚠️ *Erro na conexão TomTom:* {data}")

def loop_monitoramento():
    print("Iniciando loop de monitoramento a cada 5 minutos...")
    monitorar()
    while True:
        time.sleep(300)
        monitorar()

if __name__ == "__main__":
    print("Iniciando servidor Flask de sustentação...")
    keep_alive()
    
    t_comandos = Thread(target=loop_comandos_telegram)
    t_comandos.daemon = True
    t_comandos.start()
    
    enviar_telegram("🤖 *Bot Atualizado com Sucesso!* Digite `/ping` para checar o status.")
    
    loop_monitoramento()
