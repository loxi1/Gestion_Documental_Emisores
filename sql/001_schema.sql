CREATE DATABASE gestiondocumental_mvp;
\connect gestiondocumental_mvp;

CREATE TABLE IF NOT EXISTS clientes_destino (
    id SERIAL PRIMARY KEY,
    nombre_oficial VARCHAR(200) NOT NULL,
    abreviatura VARCHAR(30) NOT NULL,
    ruc VARCHAR(11) UNIQUE NOT NULL,
    ruta_windows TEXT,
    descripcion TEXT,
    estado BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS proveedores (
    id SERIAL PRIMARY KEY,
    ruc VARCHAR(11) UNIQUE,
    razon_social VARCHAR(250),
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lotes_proceso (
    id SERIAL PRIMARY KEY,
    codigo_lote VARCHAR(40) UNIQUE NOT NULL,
    carpeta_origen TEXT,
    estado VARCHAR(40) DEFAULT 'iniciado',
    total_archivos INTEGER DEFAULT 0,
    total_clasificados INTEGER DEFAULT 0,
    total_revision INTEGER DEFAULT 0,
    total_no_identificados INTEGER DEFAULT 0,
    observacion TEXT,
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grupos_documentales (
    id SERIAL PRIMARY KEY,
    lote_id INTEGER REFERENCES lotes_proceso(id),
    grupo_codigo VARCHAR(20),
    cliente_destino_id INTEGER REFERENCES clientes_destino(id),
    factura_documento_id INTEGER,
    estado VARCHAR(40) DEFAULT 'pendiente',
    observacion TEXT,
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_en TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documentos (
    id SERIAL PRIMARY KEY,
    lote_id INTEGER REFERENCES lotes_proceso(id),
    grupo_id INTEGER REFERENCES grupos_documentales(id),
    cliente_destino_id INTEGER REFERENCES clientes_destino(id),
    proveedor_id INTEGER REFERENCES proveedores(id),
    tipo_documental VARCHAR(40),
    serie VARCHAR(20),
    numero VARCHAR(40),
    ruc_emisor VARCHAR(11),
    razon_social_emisor VARCHAR(250),
    fecha_emision DATE,
    importe NUMERIC(14,2),
    igv NUMERIC(14,2),
    oc_numero VARCHAR(40),
    estado_documento VARCHAR(40),
    observacion TEXT,
    nombre_original TEXT,
    nombre_final TEXT,
    ruta_origen TEXT,
    ruta_destino TEXT,
    hash_sha256 VARCHAR(64),
    paginas INTEGER,
    es_principal BOOLEAN DEFAULT FALSE,
    qr_raw TEXT,
    creado_en TIMESTAMP DEFAULT NOW(),
    actualizado_en TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documentos_hash ON documentos(hash_sha256);
CREATE INDEX IF NOT EXISTS idx_documentos_estado ON documentos(estado_documento);
