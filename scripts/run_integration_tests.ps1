param(
    [string]$Pattern = "tests/integration"
)

$env:RUN_DB_TESTS = "1"

$env:DB_HOST     = "localhost"
$env:DB_PORT     = "15432"
$env:DB_NAME     = "wine_db"
$env:DB_USER     = "postgres"
$env:DB_PASSWORD = "postgres"

$env:PGHOST      = $env:DB_HOST
$env:PGPORT      = $env:DB_PORT
$env:PGDATABASE  = $env:DB_NAME
$env:PGUSER      = $env:DB_USER
$env:PGPASSWORD  = $env:DB_PASSWORD

pytest $Pattern -v
