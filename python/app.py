import json
import threading
from datetime import datetime, timezone

import tkinter as tk
from tkinter import ttk, messagebox

import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ============================================================
# CONFIGURACIÓN MQTT
# ============================================================

MQTT_BROKER = "localhost"
MQTT_PORT = 1883

MQTT_TOPIC = "iot/co2"


# ============================================================
# CONFIGURACIÓN INFLUXDB
# ============================================================

INFLUXDB_URL = "http://localhost:8086"
INFLUXDB_TOKEN = "TOKEN"
INFLUXDB_ORG = "universidad"
INFLUXDB_BUCKET = "iot_co2"


# ============================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ============================================================

MEASUREMENT = "co2_measurements"

# Límite de referencia utilizado para generar alerta
CO2_LIMIT = 1000


# ============================================================
# VARIABLES GLOBALES
# ============================================================

latest_co2 = 0.0
latest_device = "-"
latest_location = "-"
latest_sensor_timestamp = "-"
latest_influx_timestamp = "-"
latest_latency = 0.0

co2_history = []
time_history = []


# ============================================================
# CONEXIÓN CON INFLUXDB
# ============================================================

try:
    influx_client = InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG
    )

    write_api = influx_client.write_api(
        write_options=SYNCHRONOUS
    )

except Exception as error:
    print("Error al conectar con InfluxDB:")
    print(error)

    influx_client = None
    write_api = None


# ============================================================
# FUNCIONES DE FECHA Y HORA
# ============================================================

def parse_sensor_timestamp(timestamp):
    """
    Convierte el timestamp enviado por el sensor a datetime UTC.
    """

    if not timestamp:
        return None

    try:
        timestamp = timestamp.replace("Z", "+00:00")

        sensor_time = datetime.fromisoformat(timestamp)

        if sensor_time.tzinfo is None:
            sensor_time = sensor_time.replace(
                tzinfo=timezone.utc
            )

        return sensor_time.astimezone(timezone.utc)

    except ValueError:
        return None


# ============================================================
# GUARDAR DATOS EN INFLUXDB
# ============================================================

def save_to_influx(
    sensor_timestamp,
    influx_timestamp,
    device_id,
    location,
    co2_ppm,
    latency
):
    """
    Guarda una medición de CO₂ en InfluxDB.

    Tags:
        dispositivo_id
        ubicacion

    Fields:
        co2_ppm
        latencia_segundos
        timestamp_sensor
    """

    if write_api is None:
        print("InfluxDB no está disponible.")
        return

    try:

        point = (
            Point(MEASUREMENT)

            # Tags
            .tag("dispositivo_id", device_id)
            .tag("ubicacion", location)

            # Fields
            .field("co2_ppm", float(co2_ppm))
            .field("latencia_segundos", float(latency))

            # Se conserva el timestamp original como texto
            # para trazabilidad del dato generado por el sensor.
            .field(
                "timestamp_sensor",
                sensor_timestamp.isoformat()
            )

            # _time corresponde al timestamp de recepción.
            .time(influx_timestamp)
        )

        write_api.write(
            bucket=INFLUXDB_BUCKET,
            org=INFLUXDB_ORG,
            record=point
        )

        print(
            f"Datos guardados: "
            f"{device_id} | "
            f"{location} | "
            f"{co2_ppm:.1f} ppm | "
            f"Latencia: {latency:.3f} s"
        )

    except Exception as error:
        print("Error al guardar en InfluxDB:")
        print(error)


# ============================================================
# MQTT - RECEPCIÓN DE DATOS
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties=None):

    if reason_code == 0:

        print("Conectado al broker MQTT.")

        client.subscribe(MQTT_TOPIC)

        print(
            f"Suscrito al tópico: {MQTT_TOPIC}"
        )

    else:

        print(
            f"Error de conexión MQTT: {reason_code}"
        )


def on_message(client, userdata, message):

    global latest_co2
    global latest_device
    global latest_location
    global latest_sensor_timestamp
    global latest_influx_timestamp
    global latest_latency

    try:

        # ----------------------------------------------------
        # Decodificación del mensaje
        # ----------------------------------------------------

        payload = message.payload.decode("utf-8")

        data = json.loads(payload)

        # ----------------------------------------------------
        # Datos recibidos
        # ----------------------------------------------------

        timestamp_sensor_text = data["timestamp_sensor"]

        device_id = data["dispositivo_id"]

        location = data["ubicacion"]

        co2_ppm = float(data["co2_ppm"])

        # ----------------------------------------------------
        # Timestamp del sensor
        # ----------------------------------------------------

        sensor_timestamp = parse_sensor_timestamp(
            timestamp_sensor_text
        )

        if sensor_timestamp is None:

            print(
                "Timestamp del sensor inválido."
            )

            return

        # ----------------------------------------------------
        # Timestamp de recepción en InfluxDB
        # ----------------------------------------------------

        influx_timestamp = datetime.now(
            timezone.utc
        )

        # ----------------------------------------------------
        # Cálculo de latencia
        # ----------------------------------------------------

        latency = (
            influx_timestamp - sensor_timestamp
        ).total_seconds()

        # Evita valores negativos debido a diferencias
        # de sincronización entre relojes.

        if latency < 0:
            latency = 0.0

        # ----------------------------------------------------
        # Actualización de variables
        # ----------------------------------------------------

        latest_co2 = co2_ppm

        latest_device = device_id

        latest_location = location

        latest_sensor_timestamp = (
            sensor_timestamp.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        latest_influx_timestamp = (
            influx_timestamp.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        latest_latency = latency

        # ----------------------------------------------------
        # Historial para la gráfica
        # ----------------------------------------------------

        time_history.append(
            influx_timestamp
        )

        co2_history.append(
            co2_ppm
        )

        # Mantener máximo 1000 puntos en memoria

        if len(time_history) > 1000:

            time_history.pop(0)
            co2_history.pop(0)

        # ----------------------------------------------------
        # Guardar en InfluxDB
        # ----------------------------------------------------

        save_to_influx(
            sensor_timestamp,
            influx_timestamp,
            device_id,
            location,
            co2_ppm,
            latency
        )

        # ----------------------------------------------------
        # Actualizar interfaz
        # ----------------------------------------------------

        root.after(
            0,
            update_interface
        )

    except Exception as error:

        print(
            "Error procesando mensaje MQTT:"
        )

        print(error)


# ============================================================
# CLIENTE MQTT
# ============================================================

mqtt_client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


# ============================================================
# CONEXIÓN MQTT EN SEGUNDO PLANO
# ============================================================

def mqtt_thread():

    try:

        mqtt_client.connect(
            MQTT_BROKER,
            MQTT_PORT,
            60
        )

        mqtt_client.loop_forever()

    except Exception as error:

        print(
            "No fue posible conectar con MQTT:"
        )

        print(error)


# ============================================================
# INTERFAZ GRÁFICA
# ============================================================

root = tk.Tk()

root.title(
    "Sistema IoT de Monitoreo de CO₂"
)

root.geometry(
    "1100x700"
)


# ============================================================
# ENCABEZADO
# ============================================================

title_label = ttk.Label(
    root,
    text="MONITOREO IoT DE CO₂",
    font=("Arial", 20, "bold")
)

title_label.pack(
    pady=15
)


subtitle_label = ttk.Label(
    root,
    text="Sistema de monitoreo de concentración de dióxido de carbono"
)

subtitle_label.pack(
    pady=5
)


# ============================================================
# PANEL DE INFORMACIÓN
# ============================================================

info_frame = ttk.Frame(root)

info_frame.pack(
    fill="x",
    padx=20,
    pady=10
)


co2_label = ttk.Label(
    info_frame,
    text="CO₂: -- ppm",
    font=("Arial", 28, "bold")
)

co2_label.grid(
    row=0,
    column=0,
    padx=20,
    pady=10
)


location_label = ttk.Label(
    info_frame,
    text="Ubicación: --",
    font=("Arial", 12)
)

location_label.grid(
    row=1,
    column=0,
    padx=20
)


device_label = ttk.Label(
    info_frame,
    text="Dispositivo: --",
    font=("Arial", 12)
)

device_label.grid(
    row=2,
    column=0,
    padx=20
)


latency_label = ttk.Label(
    info_frame,
    text="Latencia: -- s",
    font=("Arial", 12)
)

latency_label.grid(
    row=3,
    column=0,
    padx=20
)


sensor_time_label = ttk.Label(
    info_frame,
    text="Timestamp sensor: --"
)

sensor_time_label.grid(
    row=1,
    column=1,
    padx=30
)


influx_time_label = ttk.Label(
    info_frame,
    text="Timestamp InfluxDB: --"
)

influx_time_label.grid(
    row=2,
    column=1,
    padx=30
)


status_label = ttk.Label(
    info_frame,
    text="Estado: esperando datos..."
)

status_label.grid(
    row=3,
    column=1,
    padx=30
)


# ============================================================
# GRÁFICA
# ============================================================

figure = Figure(
    figsize=(9, 4),
    dpi=100
)

ax = figure.add_subplot(111)

ax.set_title(
    "Concentración de CO₂"
)

ax.set_xlabel(
    "Tiempo"
)

ax.set_ylabel(
    "CO₂ (ppm)"
)

ax.grid(
    True
)


canvas = FigureCanvasTkAgg(
    figure,
    master=root
)

canvas.get_tk_widget().pack(
    fill="both",
    expand=True,
    padx=20,
    pady=10
)


# ============================================================
# ACTUALIZAR INTERFAZ
# ============================================================

def update_interface():

    # --------------------------------------------------------
    # Valor de CO₂
    # --------------------------------------------------------

    co2_label.config(
        text=f"CO₂: {latest_co2:.1f} ppm"
    )

    # --------------------------------------------------------
    # Dispositivo y ubicación
    # --------------------------------------------------------

    device_label.config(
        text=f"Dispositivo: {latest_device}"
    )

    location_label.config(
        text=f"Ubicación: {latest_location}"
    )

    # --------------------------------------------------------
    # Latencia
    # --------------------------------------------------------

    latency_label.config(
        text=f"Latencia: {latest_latency:.3f} s"
    )

    # --------------------------------------------------------
    # Timestamps
    # --------------------------------------------------------

    sensor_time_label.config(
        text=(
            "Timestamp sensor: "
            f"{latest_sensor_timestamp}"
        )
    )

    influx_time_label.config(
        text=(
            "Timestamp InfluxDB: "
            f"{latest_influx_timestamp}"
        )
    )

    # --------------------------------------------------------
    # Estado de CO₂
    # --------------------------------------------------------

    if latest_co2 > CO2_LIMIT:

        status_label.config(
            text=(
                f"ALERTA: CO₂ superior a "
                f"{CO2_LIMIT} ppm"
            )
        )

    else:

        status_label.config(
            text="Estado: concentración dentro del límite"
        )

    # --------------------------------------------------------
    # Actualizar gráfica
    # --------------------------------------------------------

    ax.clear()

    if len(time_history) > 0:

        ax.plot(
            time_history,
            co2_history,
            marker="o",
            markersize=3
        )

    ax.axhline(
        y=CO2_LIMIT,
        linestyle="--",
        label=f"Límite {CO2_LIMIT} ppm"
    )

    ax.set_title(
        "Concentración de CO₂"
    )

    ax.set_xlabel(
        "Tiempo"
    )

    ax.set_ylabel(
        "CO₂ (ppm)"
    )

    ax.grid(
        True
    )

    ax.legend()

    figure.autofmt_xdate()

    canvas.draw()


# ============================================================
# CERRAR APLICACIÓN
# ============================================================

def close_application():

    try:

        mqtt_client.disconnect()

    except Exception:
        pass

    try:

        if influx_client is not None:
            influx_client.close()

    except Exception:
        pass

    root.destroy()


root.protocol(
    "WM_DELETE_WINDOW",
    close_application
)


# ============================================================
# INICIAR MQTT
# ============================================================

thread = threading.Thread(
    target=mqtt_thread,
    daemon=True
)

thread.start()


# ============================================================
# INICIAR INTERFAZ
# ============================================================

root.mainloop()
```
