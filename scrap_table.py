"""API Serverless: diez reportes sísmicos recientes del IGP a DynamoDB."""
import json
import os
import re
from datetime import datetime

import boto3
import requests
from bs4 import BeautifulSoup

URL = 'https://ultimosismo.igp.gob.pe/productos/reportes-sismicos'
TABLE_NAME = os.environ.get('TABLE_NAME', 'TablaWebScrapping')
CODE_RE = re.compile(r'IGP\s*/\s*CENSIS\s*/\s*RS\s*\d{4}\s*-\s*\d+', re.I)
DATE_RE = re.compile(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}')


def limpiar(texto):
    return ' '.join(texto.split()).strip()


def extraer_sismos(html):
    soup = BeautifulSoup(html, 'html.parser')
    resultados = []
    vistos = set()

    # La vista publicada por el IGP incluye una tabla con estas columnas.
    for tabla in soup.find_all('table'):
        headers = [limpiar(h.get_text(' ', strip=True)).lower() for h in tabla.select('thead th')]
        if not headers:
            encabezado = tabla.find('tr')
            if encabezado:
                headers = [limpiar(h.get_text(' ', strip=True)).lower() for h in encabezado.find_all('th')]
        for tr in tabla.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue
            cells = [limpiar(td.get_text(' ', strip=True)) for td in tds]
            codigo = next((CODE_RE.search(c).group(0) for c in cells if CODE_RE.search(c)), None)
            if not codigo:
                continue
            fecha = next((DATE_RE.search(c).group(0) for c in cells if DATE_RE.search(c)), None)
            # Según la tabla pública: posición, código, referencia, semáforo, magnitud, fecha.
            cod_idx = next(i for i, c in enumerate(cells) if CODE_RE.search(c))
            referencia = cells[cod_idx + 1] if len(cells) > cod_idx + 1 else ''
            semaforo = cells[cod_idx + 2].lower() if len(cells) > cod_idx + 2 else ''
            magnitud_texto = cells[cod_idx + 3] if len(cells) > cod_idx + 3 else ''
            agregar(resultados, vistos, codigo, referencia, semaforo, magnitud_texto, fecha)

    # Vista alternativa del sitio: tarjetas etiquetadas como "Fila #".
    if len(resultados) < 10:
        contenido = soup.get_text('\n', strip=True)
        patron = re.compile(
            r'Cod reporte:\s*(IGP\s*/\s*CENSIS\s*/\s*RS\s*\d{4}\s*-\s*\d+)'
            r'\s*Referencia:\s*(.*?)\s*Semáforo:\s*(.*?)\s*Magnitud:\s*([\d.,]+)'
            r'\s*Fecha y hora de origen local:\s*(' + DATE_RE.pattern + ')', re.I | re.S
        )
        for m in patron.finditer(contenido):
            agregar(resultados, vistos, *m.groups())

    # Orden cronológico para devolver exclusivamente los diez más recientes.
    resultados.sort(key=lambda r: datetime.strptime(r['fecha_hora_local'], '%d/%m/%Y %H:%M:%S'), reverse=True)
    return resultados[:10]


def agregar(resultados, vistos, codigo, referencia, semaforo, magnitud_texto, fecha):
    codigo = limpiar(codigo)
    if not fecha or codigo in vistos:
        return
    try:
        magnitud = str(float(magnitud_texto.replace(',', '.')))
        datetime.strptime(fecha, '%d/%m/%Y %H:%M:%S')
    except (ValueError, AttributeError):
        return
    vistos.add(codigo)
    resultados.append({
        'id': codigo,  # Clave primaria de DynamoDB; evita duplicados entre ejecuciones.
        'codigo_reporte': codigo,
        'referencia': limpiar(referencia),
        'semaforo': limpiar(semaforo).lower(),
        'magnitud': magnitud,
        'fecha_hora_local': fecha,
        'fuente': URL,
    })


def respuesta(status, contenido):
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json; charset=utf-8'},
        'body': json.dumps(contenido, ensure_ascii=False),
    }


def lambda_handler(event, context):
    try:
        r = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; TallerScraping/1.0)'}, timeout=20)
        r.raise_for_status()
        sismos = extraer_sismos(r.text)
        if len(sismos) != 10:
            return respuesta(502, {
                'error': 'No se pudieron extraer diez reportes de la página pública del IGP.',
                'encontrados': len(sismos),
                'detalle': 'Revisar el HTML/selector; la página podría cargar datos mediante JavaScript.',
            })

        table = boto3.resource('dynamodb').Table(TABLE_NAME)
        # Reemplaza los elementos de la tabla, como en el ejemplo del taller.
        # DynamoDB Scan necesita paginación para limpiar completamente.
        scan_kwargs = {'ProjectionExpression': 'id'}
        with table.batch_writer() as batch:
            while True:
                page = table.scan(**scan_kwargs)
                for item in page.get('Items', []):
                    batch.delete_item(Key={'id': item['id']})
                if 'LastEvaluatedKey' not in page:
                    break
                scan_kwargs['ExclusiveStartKey'] = page['LastEvaluatedKey']
            for sismo in sismos:
                batch.put_item(Item=sismo)
        return respuesta(200, {'total': len(sismos), 'sismos': sismos})
    except requests.RequestException as exc:
        return respuesta(502, {'error': 'No se pudo consultar IGP', 'detalle': str(exc)})
    except Exception as exc:
        print('Error en scraping/DynamoDB:', repr(exc))
        return respuesta(500, {'error': 'Error interno al guardar los reportes'})
