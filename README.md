# IoT CO2 Monitoring System

Arquitectura IoT para el monitoreo de concentraciones de CO2 en espacios académicos.

## Descripción

Sistema desarrollado para la adquisición, transmisión, almacenamiento y visualización de concentraciones de CO2.

## Hardware

- ESP32 DevKit V1
- Sensirion SCD30
- SX1276
- Gateway LoRaWAN

## Arquitectura

1. Capa de percepción
2. Capa de red
3. Capa de procesamiento
4. Capa de aplicación

## Tecnologías

- ESP32
- Arduino
- MCCI Catena Arduino-LMIC
- LoRaWAN
- MQTT
- InfluxDB
- Python

## Configuración

### LoRaWAN

Activación OTAA.

Las credenciales reales no se incluyen
por razones de seguridad.


## Adquisición de datos

Frecuencia de adquisición:
5 minutos.

Variable monitoreada:
CO2 (ppm).

