import "influxdata/influxdb"

option task = {
    name: "iot_co2_monitoring",
    every: 5m
}

// ------------------------------------------------------------
// Parámetros de configuración
// ------------------------------------------------------------

org = "universidad"
bucketName = "iot_co2"

// ------------------------------------------------------------
// Creación del bucket
// ------------------------------------------------------------

influxdb.createBucket(
    orgID: influxdb.getOrgID(org: org),
    name: bucketName,
    description: "Bucket para almacenamiento de mediciones de CO2 del sistema IoT",
    retentionPeriod: 30d
)

// ------------------------------------------------------------
// Estructura lógica de los registros
// ------------------------------------------------------------

// Measurement:
        co2_measurements

// Tags:
        dispositivo_id
        ubicacion

// Fields:
        co2_ppm
        latencia_segundos
        timestamp_sensor

// Timestamp:
        _time = timestamp_influxdb

// ------------------------------------------------------------
// Consulta de prueba
// ------------------------------------------------------------

from(bucket: bucketName)
    |> range(start: -1h)
    |> filter(fn: (r) =>
        r._measurement == "co2_measurements"
    )
```
