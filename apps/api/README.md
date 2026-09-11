# Caramurú API

API da plataforma de engenharia de campo Caramurú Construções.

Implementada com FastAPI, Python 3.12, SQLAlchemy 2.0 assíncrono,
Alembic e PostgreSQL com PostGIS.

## Recursos

- Sincronização de projetos, equipamentos, inspeções e registros de APR.
- Autenticação JWT e isolamento dos dados por empresa.
- Controle de acesso por papel e políticas de segurança no banco de dados.
- Registros de segurança do trabalho e permissões de trabalho.
- Upload de evidências fotográficas para armazenamento compatível com S3.

## Contrato HTTP

Os contratos OpenAPI estão em `packages/contracts/openapi.json`.
A aplicação disponibiliza a documentação interativa em `/docs`
e a verificação de disponibilidade em `/health`.

A sincronização utiliza `GET /api/v1/sync` e `POST /api/v1/sync`,
com autenticação Bearer e identificação da empresa no header `X-Tenant-ID`.
O processamento contempla recibos persistidos, controle de versões
e resolução de conflitos por campo.
