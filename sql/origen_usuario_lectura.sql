-- Crea un usuario de SOLO LECTURA para que "Vialidad Mapa" pueda leer los baches del proyecto original.
--
-- CÓMO EJECUTARLO (pgAdmin):
--   1. Conéctate a la base del proyecto ORIGINAL (la llamada "vialidad"), con el usuario postgres.
--   2. Clic derecho sobre "vialidad" -> Query Tool.
--   3. Cambia la contraseña de abajo, pega todo y pulsa F5.
--
-- Este usuario solo puede LEER estas cinco tablas. No puede modificar ni borrar nada del proyecto original.

CREATE ROLE mapa_lector LOGIN PASSWORD 'CAMBIA_ESTA_CLAVE';

GRANT CONNECT ON DATABASE vialidad TO mapa_lector;
GRANT USAGE ON SCHEMA public TO mapa_lector;
GRANT SELECT ON public.capturas, public.detecciones, public.tramos,
                public.videos, public.video_hallazgos TO mapa_lector;

-- Refuerzo: toda sesión de este usuario nace en modo solo lectura.
ALTER ROLE mapa_lector SET default_transaction_read_only = on;

-- Después, en backend/.env:
-- ORIGEN_DATABASE_URL=postgresql+psycopg://mapa_lector:CAMBIA_ESTA_CLAVE@localhost:5432/vialidad
