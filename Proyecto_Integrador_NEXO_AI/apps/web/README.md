# NEXO AI — Panel web RF-015

**Alcance:** consulta web de solicitudes creadas en móvil y sus cotizaciones. Se usa la API `services/api` + la misma base PostgreSQL Neon; **no existe una segunda base de datos**. La página web es de solo lectura para evitar cambios duplicados; las operaciones se realizan desde la app móvil.

## Requisitos

- Node.js 22.12+ o 24.x, npm.
- FastAPI disponible en `http://127.0.0.1:8000/api/v1` desde esta computadora.
- Usuario propietario u operador existente; identificador UUID de su empresa, correo y contraseña.

## Instalación

```powershell
cd "$HOME\Projects\nexo-ai\apps\web"
Copy-Item .env.example .env.local
npm install
npm run check
npm run build
npm run dev
```

Abrir **http://127.0.0.1:3000**. Iniciar sesión con la misma organización y cuenta de NEXO AI. Crear un pedido y una cotización aprobada desde Expo en iPhone, actualizar la web o esperar un ciclo de 10 segundos. Buscar pedido y comprobar versiones, total y PDF. No se crea ni modifica nada desde el panel.

## Seguridad

- Login a través de route handler de Next.js: el JWT de FastAPI se guarda en cookie **HttpOnly, SameSite=Strict**. No se almacena la contraseña ni el token en `localStorage`.
- Operaciones de lectura pasan por rutas `GET /api/data/...` con lista blanca; no hay proxy libre ni endpoints mutadores.
- `cache: 'no-store'`, `Cache-Control: private, no-store`, validación del JWT y separación por empresa en FastAPI.
- Cerrar sesión revoca el JWT y borra la cookie. La sesión expira según la política de FastAPI (15 min en la configuración actual).
- Nunca incluir el JWT ni la contraseña en capturas/logs. El campo `NEXO_API_BASE_URL` es **solo de servidor**, jamás `NEXT_PUBLIC_`.
- Para despliegue accesible fuera del equipo, utilizar HTTPS y una API protegida por HTTPS. Este paquete se inicia únicamente en localhost.

## No se necesita migración

RF-015 reutiliza las tablas, permisos y endpoints de RF-001 a RF-014. La verificación en Neon usa organizaciones temporales y las elimina después. No modifica los datos de tu empresa.

## Pruebas

`npm run check` — reglas del proxy. `npm run build` — compilación real de Next.js. `python -m pytest -q tests/test_rf015_sync.py` — lectura desde sesiones distintas y seguridad. `python -m scripts.smoke_rf015_postgres` — Neon real.
