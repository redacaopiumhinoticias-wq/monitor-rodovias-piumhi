import os
import time
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

# Configurações do Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Coordenadas de Piumhi - MG e margens para cobrir 100km de raio
LAT_CENTER = -20.4544
LON_CENTER = -45.7142
DELTA = 0.95  # ~100 km de raio aproximado em graus

TOP = LAT_CENTER + DELTA
BOTTOM = LAT_CENTER - DELTA
RIGHT = LON_CENTER + DELTA
LEFT = LON_CENTER - DELTA

# Armazenar IDs de alertas já enviados para evitar duplicidade
alertas_enviados = set()

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
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
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Erro na API do Waze: {response.status_code}")
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
            
            # Regra dos 3 minutos de delay mínimo
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
        print(f"Erro ao processar dados do Waze: {e}")

if __name__ == "__main__":
    print("Iniciando Bot de Monitoramento de Rodovias...")
    scheduler = BlockingScheduler()
    scheduler.add_job(buscar_alertas_waze, 'interval', minutes=2)
    
    buscar_alertas_waze()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Bot interrompido.")
