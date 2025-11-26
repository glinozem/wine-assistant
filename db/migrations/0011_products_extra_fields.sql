BEGIN;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS vivino_url     text,
    ADD COLUMN IF NOT EXISTS vivino_rating  numeric,
    ADD COLUMN IF NOT EXISTS supplier       text,
    ADD COLUMN IF NOT EXISTS features       text,
    ADD COLUMN IF NOT EXISTS producer_site  text,
    ADD COLUMN IF NOT EXISTS vintage        integer,
    ADD COLUMN IF NOT EXISTS image_url      text;

COMMIT;
