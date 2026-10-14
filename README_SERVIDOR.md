# Ejecutar en un servidor Ubuntu sin interfaz grafica

## Respuesta corta

Si. Un navegador no necesita una pantalla real. Hay tres formas de correrlo en un servidor:

| Modo | Que es | Ventaja | Riesgo |
|---|---|---|---|
| `headless` | Chrome sin ventana | El mas simple | Es el mas facil de detectar como bot |
| `xvfb` (**empieza por este**) | Chrome "con ventana" dibujada en una pantalla virtual (Xvfb) | Se comporta como el Chrome que ya funciono en tu PC | Algo mas de memoria |
| `cdp` (servicio interno) | Un Chrome permanente (systemd) al que los scripts se conectan por `127.0.0.1:9222` | Perfil y cookies persistentes, arranque mas rapido | Mas piezas que mantener |

Como el scraper corre una vez al dia durante unos minutos, **no hace falta un servicio permanente**:
`cron` + `xvfb` suele bastar. El modo `cdp` queda como opcion si el anti-bot pide mantener la sesion.

## Lo que NO puedo prometer: la IP del servidor

Hasta ahora todo se probo desde tu PC (IP residencial). Los servidores en la nube tienen IPs de
centro de datos, y los sitios con anti-bot suelen tratarlas con mas desconfianza, sin importar el modo
de navegador. Por eso existe `probar_modos.sh`: te dice con datos reales que modo pasa DESDE ESE servidor.

Si ningun modo pasa, las alternativas son:
1. Ejecutar el scraper en tu PC u oficina (IP residencial) y que cargue directo al Postgres del servidor
   (`cargar_postgres.py` se conecta por red; solo necesita host y puerto accesibles).
2. La API oficial de pago de Barchart (OnDemand): estable y sin anti-bot.

## Requisitos del servidor

- Ubuntu 22.04 o 24.04, usuario normal con `sudo`, minimo 2 GB de RAM y ~2 GB de disco (los navegadores pesan).
- Salida a internet por HTTPS y acceso al Postgres.

## Pasos

```bash
# 1) copiar el proyecto (por ejemplo a /opt/barchart) y entrar
cd /opt/barchart

# 2) instalar todo (paquetes, entorno virtual, navegadores)
./deploy/instalar_ubuntu.sh

# 3) credenciales de Postgres (el archivo solo lo lee tu usuario)
cp .env.example .env && chmod 600 .env && nano .env

# 4) ver que modo pasa el anti-bot desde este servidor
./deploy/probar_modos.sh

# 5) prueba manual con el modo que salio OK (el Postgres en simulacion no escribe nada)
BARCHART_MODO=xvfb ./deploy/ejecutar_diario.sh      # revisa logs/diario_AAAA-MM-DD.log

# 6) programar
crontab -e      # pega la linea de deploy/cron.example
```

Antes del paso 5, ejecuta una vez `python cargar_postgres.py --archivo captura_diaria/barchart_ultima.csv`
(sin `--insertar`) para ver la simulacion contra tu tabla.

## Opcional: Chrome como servicio interno (modo cdp)

```bash
sudo useradd -r -m -d /opt/barchart barchart          # si quieres un usuario dedicado
sudo cp deploy/barchart-chrome.service /etc/systemd/system/   # edita User= y rutas
sudo systemctl daemon-reload && sudo systemctl enable --now barchart-chrome
curl -s http://127.0.0.1:9222/json/version             # debe responder JSON
BARCHART_MODO=cdp ./deploy/ejecutar_diario.sh
```

Chrome escucha **solo en 127.0.0.1**. No abras el puerto 9222 en el firewall: quien llegue a el
controla el navegador.

## Que hace cada archivo

| Archivo | Funcion |
|---|---|
| `deploy/instalar_ubuntu.sh` | Instala paquetes, entorno virtual, Playwright y Scrapling |
| `deploy/probar_modos.sh` | Prueba headless / xvfb / cdp y muestra cual pasa |
| `deploy/ejecutar_diario.sh` | Captura + carga a Postgres (con `--con-historico` tambien el historial). Bloqueo contra ejecuciones simultaneas y log por dia en `logs/` |
| `deploy/chrome_cdp.sh` + `barchart-chrome.service` | Chrome persistente sobre pantalla virtual |
| `deploy/cron.example` | Linea de cron |
| `captura_diaria/barchart_scraper.py` | Scraper diario de 17 columnas (Playwright). Variables: `BARCHART_HEADLESS`, `BARCHART_CDP_URL`, `BARCHART_EXCEL` |

## Notas

- La hora del cron debe respetar tu convencion historica de `fecha_reporte`. Revisa la zona horaria del servidor
  con `timedatectl`. La bolsa liquida el petroleo ~13:30 hora de Chicago y la sesion nueva abre a las 17:00.
- Si falla, mira `logs/diario_*.log`. Cron envia correo solo si el servidor tiene correo configurado.
- Respeta los terminos de uso de Barchart: una captura al dia, bajo volumen, sin rotar IPs.
