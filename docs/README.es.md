# Xulcan

<p align="center">
    <a href="../README.md">Inglés 🇬🇧</a>
    · <b>Español 🇲🇽</b>
</p>

**Framework de backend API-first para construir agentes de IA con orquestación de LLMs, gestión de memoria y ejecución de herramientas.**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Enabled-blue.svg)](https://www.docker.com/)

---

## Inicio Rápido

### Requisitos Previos
- Docker y Docker Compose
- Make (Estándar en Linux/Mac. Usuarios de Windows pueden usar WSL2 o Git Bash)
- Python 3.11+ (recomendado para herramientas locales)

### Configuración (2 minutos)

Usamos un `Makefile` para estandarizar las tareas de desarrollo. Olvídate de los scripts sueltos.

```bash
# 1. Clonar el repositorio
git clone https://github.com/ActraStride/xulcan.git
cd xulcan

# 2. Configurar entorno (Genera secretos, .env y construye imágenes)
make setup

# 3. Iniciar servicios en segundo plano (background)
make dev

# 4. Verificar instalación
curl http://localhost:8000/health/live
```

### Puntos de Acceso

| Servicio | URL | Credenciales |
|---------|-----|-------------|
| **API** | http://localhost:8000 | - |
| **API Docs** | http://localhost:8000/docs | - |
| **pgAdmin** | http://localhost:5050 | `admin@xulcan.dev` / (ver `.secrets/pgadmin_password`) |
| **Redis Insight** | http://localhost:5540 | Configurar manualmente al primer acceso |

---

## Interfaz de Desarrollador (Make)

Proporcionamos un `Makefile` robusto para manejar tareas comunes. Ejecuta `make help` para ver todos los comandos disponibles.

| Comando | Descripción |
|---------|-------------|
| `make setup` | Genera secretos, archivo `.env` y construye las imágenes Docker. |
| `make dev` | Inicia el stack completo (API + BD + Herramientas) y muestra los logs. |
| `make up` | Inicia el stack en modo "detached" (silencioso/segundo plano). |
| `make stop` | Detiene los contenedores sin eliminarlos. |
| `make clean` | **Destructivo**. Elimina contenedores, volúmenes y caché local. |
| `make test` | Ejecuta la suite de pytest dentro del contenedor. |
| `make shell` | Abre una terminal bash dentro del contenedor de la API. |
| `make db-shell`| Abre una sesión `psql` directamente a la base de datos. |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Application                 │
│                                                         │
│  • REST API (Ejecutor Universal)                        │
│  • Health checks (/health/live)                         │
│  • Logging Estructurado (JSON/Consola)                  │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌─────────▼───────┐
│   PostgreSQL   │    │      Redis      │
│(Vectores/Datos)│    │   (Caché/Cola)  │
└────────────────┘    └─────────────────┘
```

### Componentes Principales

- **FastAPI**: API REST asíncrona con documentación OpenAPI automática.
- **PostgreSQL**: Almacén de datos principal. Soportará `pgvector` para RAG.
- **Redis**: Caché de alto rendimiento, limitación de velocidad (rate limiting) y broker de colas.
- **Arq**: (Planeado) Cola de trabajos asíncronos construida sobre Redis para el razonamiento de agentes en segundo plano.
- **Docker Secrets**: Gestión segura de credenciales para seguridad de grado producción.

---

## Configuración

### Variables de Entorno

La configuración se gestiona mediante el archivo `.env` (creado automáticamente por `make setup`) y Docker Secrets.

```bash
# Aplicación
APP_ENV=development
LOG_LEVEL=debug

# Base de Datos y Redis
POSTGRES_USER=xulcan
POSTGRES_DB=xulcan_core
REDIS_PORT=6379

# Proveedores de IA (Obtén tus propias claves)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Gestión de Secretos

Las contraseñas sensibles **nunca** se almacenan en variables de entorno. Se gestionan mediante archivos en el directorio `.secrets/`, montados directamente en los contenedores.

Para regenerar secretos (por ejemplo, si olvidaste la contraseña de pgAdmin):

```bash
# Advertencia: Esto sobrescribe los secretos existentes
rm .secrets/*
make setup
```

---

## Estructura del Proyecto

```
xulcan/
├── app/
│   └── xulcan/
│       ├── main.py              # Punto de entrada de la aplicación
│       ├── config.py            # Configuraciones Pydantic
│       └── core/                # Lógica del núcleo
├── scripts/
│   └── setup_dev_secrets.sh     # Lógica de generación de secretos
├── tests/                       # Suite de pruebas Pytest
├── docker-compose.yaml          # Orquestación
├── Makefile                     # Ejecutor de Tareas (Task Runner)
├── pytest.ini                   # Configuración de pruebas
└── README.md
```

---

## Despliegue

### Lista de Verificación para Producción

- [ ] Establecer `ENVIRONMENT=production` en `.env`.
- [ ] Usar `make setup` en el servidor para generar secretos únicos.
- [ ] Establecer reglas de firewall estrictas para los puertos de Redis y Postgres.
- [ ] Configurar un proxy inverso (Nginx/Traefik) con SSL.
- [ ] Usar un Gestor de Secretos externo (como Infisical) para las API Keys.

### Build de Docker para Producción

```bash
# Construir imagen de producción
docker build -t xulcan-api:latest .

# Ejecutar con secretos de producción
docker run -d \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  --secret postgres_password \
  --secret redis_password \
  xulcan-api:latest
```

---

## Hoja de Ruta (Roadmap)

### ✅ Completado
- Infraestructura base (Docker, Postgres, Redis).
- **Experiencia de Desarrollador**: Makefile, Healthchecks, Hot-reload.
- Seguridad: Docker Secrets, contenedores non-root.
- Herramientas de desarrollo: pgAdmin, Redis Insight.

### 🚧 En Progreso (Q1 2025)
- **Ejecutor Universal**: Motor de ejecución de herramientas no-code.
- **Registro de Agentes**: Esquema de base de datos para definir agentes vía JSON/YAML.
- **Gateway de Autenticación**: Integración con Vault/Infisical para autenticación de herramientas.

### 📋 Planeado (Q2 2025)
- **Integración RAG**: Soporte nativo de `pgvector`.
- **Razonamiento Asíncrono**: Workers en segundo plano usando **Arq**.
- **Panel de Administración**: Interfaz web (UI) para gestionar agentes y ver métricas.

---

## Solución de Problemas (Troubleshooting)

### Los servicios se comportan de forma inesperada
Ejecuta un reinicio limpio completo para asegurar que no existan volúmenes obsoletos:
```bash
make clean
make setup
make dev
```

### "Redis is unhealthy"
Asegúrate de haber ejecutado `make setup` para generar el archivo `.secrets/redis_password`. El contenedor requiere este archivo para pasar los chequeos de salud (health checks).

### Conflictos de puertos
Si los puertos 8000, 5432 o 6379 están ocupados, modifica el archivo `.env` generado por `make setup`.

---

## Licencia

Este proyecto está bajo la Licencia MIT - mira el archivo [LICENSE](../LICENSE) para más detalles.

---

**Estado**: 🚀 Desarrollo Activo | **Versión**: 0.1.1-alpha