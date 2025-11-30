-- 0012_wineries.sql
-- Справочник виноделен (wineries) на базе поставщика (supplier).
-- Идемпотентная миграция: таблица создаётся только если её ещё нет.

CREATE TABLE IF NOT EXISTS public.wineries (
    id             bigserial PRIMARY KEY,
    supplier       text NOT NULL UNIQUE,  -- Ключ = products.supplier
    supplier_ru    text,                  -- Имя винодельни на русском
    region         text,                  -- Регион из каталога (например, "Savoie / Савойя")
    producer_site  text,                  -- Официальный сайт винодельни
    description_ru text,                  -- Описание винодельни на русском (из каталога)
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.wineries IS 'Справочник виноделен (по поставщику/supplier).';
COMMENT ON COLUMN public.wineries.supplier IS 'Ключ-идентификатор винодельни, совпадает с products.supplier.';
COMMENT ON COLUMN public.wineries.supplier_ru IS 'Имя винодельни на русском (из каталога).';
COMMENT ON COLUMN public.wineries.region IS 'Регион винодельни (нормализованный текст).';
COMMENT ON COLUMN public.wineries.producer_site IS 'Официальный сайт винодельни.';
COMMENT ON COLUMN public.wineries.description_ru IS 'Развёрнутое описание винодельни на русском.';
