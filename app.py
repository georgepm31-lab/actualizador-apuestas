import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests

# --- CONFIGURACIONES GLOBALES ---
NOMBRE_SHEET = "Datos_Apuestas_Miseojeu"
ARCHIVO_CREDENCIALES = "credenciales.json"

def conectar_sheets():
    print("Conectando a Google Sheets...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(ARCHIVO_CREDENCIALES, scope)
    client = gspread.authorize(creds)
    return client

def obtener_partidos_en_vivo():
    print("Consultando partidos del día desde la fuente abierta...")
    hoy_str = datetime.now().strftime("%Y%m%d")
    fecha_formato = datetime.now().strftime("%Y-%m-%d")
    
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={hoy_str}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            datos = response.json()
            eventos = datos.get('events', [])
            
            partidos = []
            for ev in eventos:
                competencia = ev.get('competitions', [{}])[0]
                competitors = competencia.get('competitors', [])
                
                if len(competitors) >= 2:
                    local = competitors[0]['team']['displayName']
                    visitante = competitors[1]['team']['displayName']
                    
                    liga = 'Fútbol Internacional'
                    if 'tournament' in competencia:
                        liga = competencia['tournament'].get('name', 'Fútbol Internacional')
                    
                    partidos.append({
                        "Fecha": fecha_formato,
                        "Local": local,
                        "Visitante": visitante,
                        "Liga": liga
                    })
            
            if partidos:
                print(f"¡Se extrajeron {len(partidos)} partidos reales con éxito!")
                return pd.DataFrame(partidos)
        
    except Exception as e:
        print(f"Aviso de red: {e}")
    
    return pd.DataFrame([{
        "Fecha": fecha_formato,
        "Local": "Sin eventos en curso",
        "Visitante": "Verificar más tarde",
        "Liga": "N/A"
    }])

def actualizar_google_sheets(df, hoja):
    print("Actualizando Google Sheets con la cartelera...")
    hoja.clear()
    hoja.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Sincronización de cartelera completada!")

if __name__ == "__main__":
    cliente = conectar_sheets()
    spreadsheet = cliente.open(NOMBRE_SHEET)
    
    # Actualizamos la cartelera base de partidos en la hoja principal
    hoja_destino = spreadsheet.sheet1
    df_partidos = obtener_partidos_en_vivo()
    actualizar_google_sheets(df_partidos, hoja_destino)
