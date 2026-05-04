INSERT INTO clientes_destino (nombre_oficial, abreviatura, ruc, ruta_windows, descripcion, estado)
VALUES
('BB TECNOLOGIA INDUSTRIAL S.A.C.', 'BBTEC', '20299922821', '\\servidor\documentos\BB TECNOLOGIA INDUSTRIAL SAC', 'Empresa destino', TRUE),
('BBTI S.A.C.', 'BBTI', '20565747356', '\\servidor\documentos\BBTI SAC', 'Empresa destino', TRUE),
('CONSORCIO CIMA ENERGY', 'CIMA', '20613521004', '\\servidor\documentos\CONSORCIO CIMA ENERGY', 'Consorcio', TRUE),
('CONSORCIO ILUMINACION TARMA 2025', 'TARMA', '20614307197', '\\servidor\documentos\CONSORCIO ILUMINACION TARMA 2025', 'Consorcio', TRUE),
('CONSORCIO HUANCAVELICA', 'HUANCA', '20612122416', '\\servidor\documentos\CONSORCIO HUANCAVELICA', 'Consorcio', TRUE)
ON CONFLICT (ruc) DO UPDATE SET
    nombre_oficial = EXCLUDED.nombre_oficial,
    abreviatura = EXCLUDED.abreviatura,
    ruta_windows = EXCLUDED.ruta_windows,
    descripcion = EXCLUDED.descripcion,
    estado = EXCLUDED.estado,
    actualizado_en = NOW();
