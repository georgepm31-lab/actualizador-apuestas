import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import requests
import os
from google import genai

# --- CONFIGURACIONES GLOBALES ---
NOMBRE_SHEET = "Datos_Apuestas_Miseojeu"
ARCHIVO_CREDENCIALES = "credenciales.json"
NOMBRE_PESTAÑA_REPORTE = "Reporte_Cuantitativo_Hoy"

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

def generar_analisis_cuantitativo(df_partidos):
    print("Ejecutando modelo cuantitativo con Gemini...")
    
    # Verificamos que la API Key esté disponible en el entorno de GitHub Actions
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "Error: No se encontró la GEMINI_API_KEY en las variables de entorno de GitHub."

    client = genai.Client(api_key=api_key)
    
    # Convertimos los partidos del DataFrame a texto para que la IA los lea
    cartelera_texto = df_partidos.to_string(index=False)
    
    prompt_cuantitativo = f"""
    Eres un Especialista Cuantitativo de Apuestas de Fútbol y Modelador de Datos (Data Scientist). 
    Tu objetivo es auditar la siguiente cartelera de partidos del día y buscar valor esperado positivo (+EV) en Mise-o-jeu.

    CARTELERA DE PARTIDOS:
    {cartelera_texto}

    REGLAS MATEMÁTICAS ESTRICTAS DE EJECUCIÓN:
    1. ELIMINA LA NARRATIVA: Queda prohibido basar tus decisiones en "Momentum", "necesidad de puntos" o "historial H2H". Analiza pura y exclusivamente mediante deltas de xG (Goles Esperados) y xGA (Goles Esperados en Contra) recientes utilizando búsqueda web interna si es necesario.
    2. NUEVO FILTRO DE CUOTAS: El rango operativo es estrictamente de 1.70 a 2.30. Ignora de inmediato a cualquier "favorito local" con cuotas inferiores a 1.70.
    3. PROHIBICIÓN DEL 1X2 DIRECTO Y BTTS NO: Se prohíbe el uso de Victoria Simple (1X2) y de "Ambos Anotan: No". Prioriza Hándicap Asiático, Empate No Apuesta (DNB) o Doble Oportunidad. En totales, apóyate en Menos de 2.5 goles (Under) sólo si el xGA combinado es inferior a 1.80.
    4. GESTIÓN DE BANCA: Sistema Flat Betting innegociable de 1 Unidad ($1.00) por partido. Jamás agrupes selecciones en parlays.

    ESTRUCTURA OBLIGATORIA DEL REPORTE:
    Para cada partido validado que cumpla con el filtro matemático, presenta:
    * Partido: [Equipo 1 vs Equipo 2]
    * Auditoría Avanzada xG/xGA: (Resumen de la disparidad métrica).
    * Ineficiencia del Mercado (+EV): (Por qué la línea está mal calculada matemáticamente).
    * Selección Cuantitativa: [Mercado protegido: DNB / Hándicap / Under] @ [Cuota]
    * Gestión: 1.00 Unidad (Flat)

    REGLA DE ABSTENCIÓN (NO BET):
    Si tras la auditoría no encuentras ninguna selección que cumpla íntegramente estas directrices matemáticas de valor, emite únicamente el siguiente texto: "NO BET TODAY - Evitando Riesgo y Fugas de Valor".
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_cuantitativo,
        )
        return response.text
    except Exception as e:
        return f"Error al generar el análisis cuantitativo con Gemini: {str(e)}"

def guardar_reporte_en_sheets(cliente_sheets, texto_reporte):
    print(f"Actualizando la pestaña '{NOMBRE_PESTAÑA_REPORTE}' en Google Sheets...")
    spreadsheet = cliente_sheets.open(NOMBRE_SHEET)
    
    # Intentamos acceder a la pestaña del reporte, si no existe, la creamos
    try:
        hoja_reporte = spreadsheet.worksheet(NOMBRE_PESTAÑA_REPORTE)
    except gspread.exceptions.WorksheetNotFound:
        hoja_reporte = spreadsheet.add_worksheet(title=NOMBRE_PESTAÑA_REPORTE, rows=100, cols=5)
    
    # SOBREESCRITURA LIMPIA: Borramos todo lo anterior para que no se acumule basura
    hoja_reporte.clear()
    
    # Transformamos el texto del reporte en filas de una sola columna para la hoja
    lineas = texto_reporte.split('\n')
    datos_para_sheets = [[linea] for linea in lineas]
    
    # Escribimos el reporte fresco del día
    hoja_reporte.update(datos_para_sheets)
    print("¡Reporte cuantitativo sincronizado y sobrescrito con éxito!")

def actualizar_google_sheets(df, hoja):
    print("Actualizando Google Sheets con la cartelera...")
    hoja.clear()
    hoja.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Sincronización de cartelera completada!")

if __name__ == "__main__":
    cliente = conectar_sheets()
    
    # 1. Actualizamos la cartelera base de partidos en la hoja principal
    hoja_destino = cliente.open(NOMBRE_SHEET).sheet1
    df_partidos = obtener_partidos_en_vivo()
    actualizar_google_sheets(df_partidos, hoja_destino)
    
    # 2. Generamos el análisis inteligente de Gemini con nuestras reglas estrictas
    texto_analisis = generar_analisis_cuantitativo(df_partidos)
    
    # 3. Guardamos/Sobrescribimos el reporte limpio en su pestaña dedicada
    guardar_reporte_en_sheets(cliente, texto_analisis)

