# NEXO AI · Primera aplicación móvil (RF-009)

Requiere Node.js 22 o superior, Expo SDK 57, un dispositivo Android/iOS con Expo Go compatible y la API FastAPI en funcionamiento.

1. Desde PowerShell, en `services/api`, iniciar API con `./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000` y mantener esa consola abierta (solo desarrollo dentro de red confiable).
2. En otra consola en `apps/mobile`, ejecutar `Copy-Item .env.example .env`; editar `EXPO_PUBLIC_API_URL=http://IP_LAN_DEL_PC:8000/api/v1`. Sustituir la IP de ejemplo, no usar `localhost` en el teléfono.
3. `npm install` y `npx expo install --check` (resolver versiones si aparecen discrepancias).
4. `npm run check` para TypeScript; `npm run start` para levantar Expo. Abrir con Expo Go compatible con SDK 57. PC y teléfono deben usar la misma Wi-Fi; puede requerirse permitir el puerto 8000 en el firewall.
5. Iniciar sesión con el UUID de organización, correo y contraseña reales del RF-002. El token solo permanece en memoria, se pierde al reiniciar la app.
6. Probar permiso concedido: grabar, detener, escuchar, enviar, listar audios. Probar permiso denegado: cambiar a Texto manual, guardar un borrador de RF-008.

No se transcribe audio automáticamente. La nota se guarda de manera privada en la API; su archivo no se expone de forma pública. La descarga requiere JWT.

Solo para desarrollo se admite HTTP dentro de la LAN. Para usuarios finales usar HTTPS y un servicio de almacenamiento privado apropiado. En iOS el simulador no sirve para validar el micrófono: usar un dispositivo real.
