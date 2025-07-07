import typer
from hyphora_local.config import load_hyphora_config

app = typer.Typer()


@app.command()
def test_config():
    match load_hyphora_config():
        case ("ok", conf):
            typer.echo(conf.vault_path)
        case ("error", err):
            typer.echo(err)
