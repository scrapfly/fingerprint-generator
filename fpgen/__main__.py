import click
import zstandard

from .pkgman import download_model
from .query import NETWORK_FILE
from .unpacker import VALUES_DATA, VALUES_JSON

FILES_TO_COMPRESS = {
    NETWORK_FILE: NETWORK_FILE.with_suffix('.json.zst'),
    VALUES_JSON: VALUES_JSON.with_suffix('.json.zst'),
    VALUES_DATA: VALUES_DATA.with_suffix('.dat.zst'),
}


@click.group()
def cli():
    pass


@cli.command()
@click.option('-d', is_flag=True, help='Also decompress the model files after downloading')
def fetch(d):
    """Fetch the latest model from GitHub"""
    download_model()
    if d:
        ctx = click.get_current_context()
        ctx.invoke(decompress)
    click.echo(click.style("Complete!", fg="green"))


@cli.command()
def remove():
    """Remove all downloaded and/or extracted model files"""
    for file_pair in FILES_TO_COMPRESS.items():
        found = False
        for file in file_pair:
            if not file.exists():
                continue
            click.echo(f"Removing {file}")
            file.unlink()
            found = True
    if not found:
        click.echo(click.style("No files found to remove.", fg="yellow"))
        return
    click.echo(click.style("Complete!", fg="green"))


@cli.command()
def decompress():
    """Decompress model files for speed efficiency (will take 100mb+)"""
    dctx = zstandard.ZstdDecompressor()

    for src_zst, dst in {v: k for k, v in FILES_TO_COMPRESS.items()}.items():
        if not src_zst.exists():
            click.echo(f"Warning: {src_zst} not found, skipping")
            continue

        click.echo(f"Decompressing {src_zst} -> {dst}")
        with open(src_zst, 'rb') as src, open(dst, 'wb') as dst_f:
            dctx.copy_stream(src, dst_f)
        src_zst.unlink()


@cli.command()
def recompress():
    """Compress model files after running decompress"""
    cctx = zstandard.ZstdCompressor(level=19)

    for src, dst_zst in FILES_TO_COMPRESS.items():
        if not src.exists():
            click.echo(f"Warning: {src} not found, skipping")
            continue

        click.echo(f"Compressing {src} -> {dst_zst}")
        with open(src, 'rb') as src_f:
            data = src_f.read()
            compressed = cctx.compress(data)
            with open(dst_zst, 'wb') as dst:
                dst.write(compressed)
        src.unlink()


if __name__ == '__main__':
    cli()
