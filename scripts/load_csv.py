import os, argparse, pandas as pd, psycopg2, psycopg2.extras
from dotenv import load_dotenv
load_dotenv()
def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("PGHOST","localhost"),
        port=int(os.getenv("PGPORT","5432")),
        user=os.getenv("PGUSER","postgres"),
        password=os.getenv("PGPASSWORD","postgres"),
        dbname=os.getenv("PGDATABASE","wine_db"),
    )
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    with get_conn() as conn, conn.cursor() as cur:
        for _, r in df.iterrows():
            cur.execute("""
              INSERT INTO products (code, producer, title_ru, title_en, country, region, color, style, grapes, abv, pack, volume, price_rub)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT (code) DO UPDATE SET
                producer=EXCLUDED.producer, title_ru=EXCLUDED.title_ru, title_en=EXCLUDED.title_en,
                country=EXCLUDED.country, region=EXCLUDED.region, color=EXCLUDED.color, style=EXCLUDED.style,
                grapes=EXCLUDED.grapes, abv=EXCLUDED.abv, pack=EXCLUDED.pack, volume=EXCLUDED.volume, price_rub=EXCLUDED.price_rub;
            """, (r.get("code"), r.get("producer"), r.get("title_ru"), r.get("title_en"), r.get("country"),
                    r.get("region"), r.get("color"), r.get("style"), r.get("grapes"), r.get("abv"),
                    r.get("pack"), r.get("volume"), float(r.get("price_rub") or 0)))
        conn.commit()
    print("CSV loaded")
