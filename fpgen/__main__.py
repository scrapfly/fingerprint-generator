import click

from .pkgman import (
    FILE_PAIRS,
    decompress_model,
    download_model,
    recompress_model,
    remove_model,
)


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    '--decompress', is_flag=True, help='Also decompress the model files after downloading'
)
def fetch(decompress):
    """
    Fetch the latest model from GitHub
    """
    # Remove existing files
    remove_model(log=False)
    # Download new files
    download_model()
    if decompress:
        decompress_model()
    click.echo(click.style("Complete!", fg="green"))


@cli.command()
def remove():
    """
    Remove all downloaded and/or extracted model files
    """
    found = remove_model()
    if not found:
        click.echo(click.style("No files found to remove.", fg="yellow"))
        return
    click.echo(click.style("Complete!", fg="green"))


@cli.command()
def decompress():
    """
    ecompress model files for speed efficiency (will take 100mb+)
    """
    decompress_model()


@cli.command()
def recompress():
    """
    Compress model files after running decompress
    """
    recompress_model()


if __name__ == '__main__':
    cli()
