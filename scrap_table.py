"""Lambda: obtiene los 10 reportes sísmicos más recientes del IGP y los guarda en DynamoDB."""
import json
import os
from datetime import datetime, timezone

import boto3
import requests

BASE = "https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb"
TABLE_NAME = os.environ.get("TABLE_NAME", "TablaWebScrapping")
FUENTE = "https://ultimosismo.igp.gob.pe/productos/reportes-sismicos"


def responder(status, datos):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(datos, ensure_ascii=False, default=str),
    }


def obtener_reportes():
    anio = datetime.now(timezone.utc).year
    registros = []
    for year in (anio, anio - 1):
        respuesta = requests.get(f"{BASE}/{year}", timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0"})
        respuesta.raise_for_status()
        datos = respuesta.json()
        if not isinstance(datos, list):
            raise ValueError("La API del IGP no devolvió una lista JSON")
        registros.extend(x for x in datos if isinstance(x, dict) and
                         x.get("codigo") and str(x.get("publicado", "1")) == "1")
        if len(registros) >= 10:
            break

    # El endpoint devuelve los sismos del año en orden ascendente.
    # Numero_reporte y año permiten obtener los últimos, sin depender del orden JSON.
    registros.sort(key=lambda s: (
        int(str(s["codigo"]).split("-")[0]),
        int(s.get("numero_reporte") or str(s["codigo"]).split("-")[-1])
    ), reverse=True)
    vistos = set()
    ultimos = []
    for s in registros:
        if s["codigo"] not in vistos:
            vistos.add(s["codigo"])
            ultimos.append({
                "id": str(s["codigo"]),
                "codigo": str(s["codigo"]),
                "fecha_local": s.get("fecha_local"),
                "hora_local": s.get("hora_local"),
                "magnitud": str(s.get("magnitud", "")),
                "profundidad": s.get("profundidad"),
                "latitud": str(s.get("latitud", "")),
                "longitud": str(s.get("longitud", "")),
                "referencia": s.get("referencia"),
                "intensidad": s.get("intensidad"),
                "fuente": FUENTE,
            })
        if len(ultimos) == 10:
            break
    return ultimos


def lambda_handler(event, context):
    try:
        sismos = obtener_reportes()
        if len(sismos) != 10:
            return responder(502, {"error": "No se obtuvieron 10 reportes", "encontrados": len(sismos)})

        tabla = boto3.resource("dynamodb").Table(TABLE_NAME)
        # Elimina elementos anteriores para que la tabla represente solo los 10 últimos.
        keys = []
        parametros = {"ProjectionExpression": "id"}
        while True:
            pagina = tabla.scan(**parametros)
            keys.extend(item["id"] for item in pagina.get("Items", []))
            if "LastEvaluatedKey" not in pagina:
                break
            parametros["ExclusiveStartKey"] = pagina["LastEvaluatedKey"]
        with tabla.batch_writer() as batch:
            for clave in keys:
                batch.delete_item(Key={"id": clave})
            for sismo in sismos:
                # DynamoDB no acepta valores float, y los valores faltantes pueden ser null.
                batch.put_item(Item=sismo)

        return responder(200, {"total": len(sismos), "sismos": sismos})
    except Exception as exc:
        print("Error al consultar IGP o escribir en DynamoDB:", repr(exc))
        return responder(500, {"error": str(exc)})
