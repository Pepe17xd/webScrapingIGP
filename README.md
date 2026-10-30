# Ejercicio 2 — IGP (Taller Serverless)

Se reutiliza la estructura original de Bomberos (`scrap_table.py`, `requirements.txt`, `serverless.yml`). La API GET `/dev/scrape/table` intenta leer los 10 reportes más recientes del catálogo del IGP y reemplaza el contenido de `TablaWebScrapping` en DynamoDB.

## Antes de desplegar
1. Configurar AWS Academy (`~/.aws/credentials`) y actualizar el ARN real `LabRole` en `serverless.yml` si el laboratorio requiere el rol preasignado. No publicar credenciales en GitHub.
2. Configurar `org` (si corresponde) en `serverless.yml`.
3. En la MV de desarrollo:
   ```bash
   cd /home/ubuntu/lambdas
   git clone URL_DE_TU_REPOSITORIO
   cd api-web-scraping
   pip3 install -r requirements.txt -t .
   sls deploy
   ```
4. Invocar la URL GET que imprime `sls deploy` y comprobar **10 elementos** en `TablaWebScrapping` (AWS Console > DynamoDB > Explore items). Guardar capturas de la respuesta y los diez registros para Padlet.

## Importante
No se ha verificado un despliegue real de AWS ni el HTML recibido por Lambda. Si el IGP entrega contenido únicamente por JavaScript, la función devuelve un error 502 y no modifica la tabla. En ese caso hay que identificar la petición de datos real mediante la pestaña *Network* del navegador y adaptar `extraer_sismos` a su respuesta. No uses como evidencia que funciona hasta probar la URL desplegada.
