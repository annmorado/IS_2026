# NEXO AI

Plataforma inteligente de decisiones operativas para negocios que trabajan por pedido.

## Descripcion

NEXO AI es una plataforma multiplataforma que permite gestionar solicitudes, pedidos, productos, inventarios y cotizaciones mediante herramientas de inteligencia artificial, prediccion y simulacion operativa.

El sistema esta disenado para ayudar a pequenas y medianas empresas a tomar decisiones basadas en datos.

## Arquitectura tecnologica

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.12, FastAPI |
| Aplicacion movil | React Native, Expo, TypeScript |
| Plataforma web | Next.js, React, TypeScript |
| Base de datos | PostgreSQL |
| ORM | SQLAlchemy |
| Migraciones | Alembic |
| Inteligencia artificial | Python, Machine Learning, NLP |
| Optimizacion | Google OR-Tools |
| Pruebas | Pytest |
| Versionado | Git y GitHub |

## Estructura del proyecto

- apps/mobile: Aplicacion movil iOS y Android.
- apps/web: Plataforma web administrativa.
- services/api: API REST y logica de negocio.
- services/ml: Modelos de inteligencia artificial.
- infra: Configuracion de infraestructura y nube.
- docs: Documentacion tecnica y requisitos IEEE.
- tests: Pruebas generales del sistema.
- .github/workflows: Integracion y despliegue continuo.

## Modulos previstos

1. Autenticacion y usuarios.
2. Organizaciones y roles.
3. Productos e inventarios.
4. Gestion de pedidos.
5. Captura inteligente por voz y texto.
6. Prediccion de cumplimiento.
7. Simulacion y optimizacion.
8. Cotizaciones y documentos PDF.
9. Dashboard administrativo.
10. Auditoria y recomendaciones de IA.

## Metodologia de desarrollo

Se utilizara desarrollo modular e incremental.

Cada requisito debera cumplir:

1. Implementacion del codigo.
2. Ejecucion funcional.
3. Pruebas satisfactorias.
4. Correccion de errores.
5. Verificacion y aceptacion.

No se iniciara el siguiente requisito hasta aprobar el anterior.

## Estado del proyecto

Fase actual: Preparacion del entorno y repositorio.

Los modulos funcionales todavia no estan implementados.

## Documento de referencia

NEXO-SRS-001 - Especificacion de Requisitos de Software,
version 1.0, basada en ISO/IEC/IEEE 29148:2018.

## Objetivo

Construir una solucion escalable, verificable y preparada
para implementarse en la nube y evolucionar hacia un
producto comercial.
