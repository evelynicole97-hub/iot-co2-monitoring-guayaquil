/*
 * NODO IoT PARA MONITOREO DE CO2
 * ESP32 DevKit V1 + Sensirion SCD30 + SX1276
 * MCCI Catena Arduino-LMIC / LoRaWAN OTAA
 *
 * Variable monitoreada: CO2 (ppm)
 * Frecuencia: una medicion cada 5 minutos
 *
 * IMPORTANTE: las credenciales OTAA incluidas son ficticias.
 * No publicar DEVEUI/APPEUI/APPKEY reales en GitHub.
 */

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <SensirionI2cScd30.h>
#include <lmic.h>
#include <hal/hal.h>

// -------------------- SCD30 --------------------
SensirionI2cScd30 scd30;
#define SDA_PIN 21
#define SCL_PIN 22
const char* DEVICE_ID = "NODE_AULA";

// 5 minutos
const unsigned long MEASUREMENT_INTERVAL = 300000UL;

// -------------------- LoRaWAN OTAA --------------------
// Valores ficticios de ejemplo.
static const u1_t PROGMEM DEVEUI[8] = {
    0x70, 0xB3, 0xD5, 0x7E, 0xD0, 0x01, 0x23, 0x45
};

static const u1_t PROGMEM APPEUI[8] = {
    0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77
};

static const u1_t PROGMEM APPKEY[16] = {
    0x2B, 0x7E, 0x15, 0x16, 0x28, 0xAE, 0xD2, 0xA6,
    0xAB, 0xF7, 0x15, 0x88, 0x09, 0xCF, 0x4F, 0x3C
};

void os_getDevEui(u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }
void os_getArtEui(u1_t* buf) { memcpy_P(buf, APPEUI, 8); }
void os_getDevKey(u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

// -------------------- Pines SX1276 --------------------
// SCK=18, MISO=19, MOSI=23, NSS=5, RESET=14,
// DIO0=26, DIO1=33, DIO2=32
const lmic_pinmap lmic_pins = {
    .nss = 5,
    .rxtx = LMIC_UNUSED_PIN,
    .rst = 14,
    .dio = {26, 33, 32}
};

float co2_ppm = 0.0;
unsigned long lastMeasurement = 0;
bool firstMeasurement = true;

void printSCD30Error(const char* mensaje, int16_t error)
{
    Serial.print("ERROR SCD30: ");
    Serial.print(mensaje);
    Serial.print(" | Codigo: ");
    Serial.println(error);
}

// Lee exclusivamente la concentracion de CO2.
bool readCO2()
{
    uint16_t dataReady = 0;
    int16_t error = scd30.getDataReady(dataReady);

    if (error != 0) {
        printSCD30Error("No se pudo consultar la disponibilidad de datos", error);
        return false;
    }

    if (dataReady == 0) {
        Serial.println("SCD30: medicion de CO2 todavia no disponible");
        return false;
    }

    // La API del SCD30 devuelve tres valores; solo se utiliza CO2.
    float discardedValue1 = 0.0;
    float discardedValue2 = 0.0;

    error = scd30.readMeasurement(co2_ppm, discardedValue1, discardedValue2);

    if (error != 0) {
        printSCD30Error("No se pudo obtener la medicion de CO2", error);
        return false;
    }

    Serial.println("----------------------------------------");
    Serial.print("Dispositivo: ");
    Serial.println(DEVICE_ID);
    Serial.print("CO2: ");
    Serial.print(co2_ppm, 0);
    Serial.println(" ppm");
    Serial.println("----------------------------------------");

    return true;
}

// Transmite exclusivamente el valor de CO2.
void sendCO2()
{
    if (LMIC.opmode & OP_TXRXPEND) {
        Serial.println("LoRaWAN: existe una transmision pendiente");
        return;
    }

    uint16_t co2 = (uint16_t)co2_ppm;
    byte payload[2];
    payload[0] = highByte(co2);
    payload[1] = lowByte(co2);

    LMIC_setTxData2(1, payload, sizeof(payload), 0);

    Serial.print("LoRaWAN: CO2 transmitido = ");
    Serial.print(co2);
    Serial.println(" ppm");
}

void onEvent(ev_t event)
{
    Serial.print("Evento LoRaWAN: ");

    switch (event) {
        case EV_JOINING:
            Serial.println("Intentando unirse mediante OTAA...");
            break;
        case EV_JOINED:
            Serial.println("Nodo conectado correctamente");
            Serial.println("OTAA: JOIN ACCEPT recibido");
            LMIC_setLinkCheckMode(0);
            break;
        case EV_JOIN_FAILED:
            Serial.println("Fallo en la union OTAA");
            break;
        case EV_REJOIN_FAILED:
            Serial.println("Fallo en el reintento OTAA");
            break;
        case EV_TXCOMPLETE:
            Serial.println("Transmision LoRaWAN completada");
            break;
        default:
            Serial.println("Evento procesado");
            break;
    }
}

bool initializeSCD30()
{
    Serial.println("Inicializando SCD30...");
    Wire.begin(SDA_PIN, SCL_PIN);
    scd30.begin(Wire, SCD30_I2C_ADDR_61);
    scd30.stopPeriodicMeasurement();
    delay(500);
    scd30.softReset();
    delay(2000);

    int16_t error = scd30.startPeriodicMeasurement(0);

    if (error != 0) {
        printSCD30Error("No se pudo iniciar la medicion periodica", error);
        return false;
    }

    Serial.println("SCD30 inicializado correctamente");
    return true;
}

void setup()
{
    Serial.begin(115200);
    delay(2000);

    Serial.println();
    Serial.println("==========================================");
    Serial.println("       NODO IoT - MONITOREO DE CO2");
    Serial.println("==========================================");
    Serial.println("Hardware: ESP32 DevKit V1");
    Serial.println("Sensor: Sensirion SCD30");
    Serial.println("Radio: SX1276");
    Serial.println("Protocolo: LoRaWAN");
    Serial.println("Activacion: OTAA");
    Serial.println("Variable: CO2 (ppm)");
    Serial.println("Frecuencia: 1 medicion cada 5 minutos");
    Serial.println("==========================================");

    if (!initializeSCD30()) {
        Serial.println("ERROR CRITICO: SCD30 no disponible");
        while (true) { delay(1000); }
    }

    Serial.println("Inicializando LoRaWAN...");
    os_init();
    LMIC_reset();
    LMIC_setLinkCheckMode(0);
    Serial.println("Iniciando conexion OTAA...");
    LMIC_startJoining();
    Serial.println("Esperando JOIN ACCEPT...");
}

void loop()
{
    os_runloop_once();

    // Primera medicion despues del proceso OTAA.
    if (firstMeasurement) {
        if (!(LMIC.opmode & OP_JOINING)) {
            if (readCO2()) {
                sendCO2();
                lastMeasurement = millis();
                firstMeasurement = false;
            }
        }
    }

    // Mediciones posteriores cada cinco minutos.
    if (!firstMeasurement &&
        millis() - lastMeasurement >= MEASUREMENT_INTERVAL) {

        Serial.println();
        Serial.println("==========================================");
        Serial.println("NUEVO CICLO DE MONITOREO");
        Serial.println("==========================================");

        if (readCO2()) {
            sendCO2();
            lastMeasurement = millis();
        }
    }

    delay(10);
}
