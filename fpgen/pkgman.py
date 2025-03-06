import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import click
import httpx

from .exceptions import MissingRelease

# Model files
DATA_DIR = Path(__file__).parent / 'data'

NETWORK_FILE = DATA_DIR / "fingerprint-network.json"
VALUES_JSON = DATA_DIR / 'values.json'
VALUES_DATA = DATA_DIR / 'values.dat'

# Mapping of files to their compressed variant
FILE_PAIRS = {
    NETWORK_FILE: NETWORK_FILE.with_suffix('.json.zst'),
    VALUES_JSON: VALUES_JSON.with_suffix('.json.zst'),
    VALUES_DATA: VALUES_DATA.with_suffix('.dat.zst'),
}

# Repo to pull releases from
GITHUB_REPO = 'scrapfly/fingerprint-generator'


class ModelPuller:
    """
    Pulls the model from GitHub and extracts it to the data directory.
    """

    def __init__(self) -> None:
        self.api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

    def check_asset(self, asset: Dict) -> Any:
        """
        Compare the asset to determine if it's the desired asset.

        Args:
            asset: Asset information from GitHub API

        Returns:
            Any: Data to be returned if this is the desired asset, or None/False if not
        """
        url = asset.get('browser_download_url')
        if url and url.endswith('.zip'):
            return url

    def missing_asset_error(self) -> None:
        """
        Raise a MissingRelease exception if no release is found.
        """
        raise MissingRelease(f"Could not find a release asset in {GITHUB_REPO}.")

    def get_asset(self) -> Any:
        """
        Fetch the latest release from the GitHub API.
        Gets the first asset that returns a truthy value from check_asset.
        """
        resp = httpx.get(self.api_url, timeout=20, verify=False)
        resp.raise_for_status()

        releases = resp.json()

        for release in releases:
            for asset in release['assets']:
                if data := self.check_asset(asset):
                    return data

        self.missing_asset_error()

    def download(self):
        """
        Download the model from GitHub and extract it to the data directory.
        """
        # Pull form a custom source, or the GitHub API

        url = os.getenv('FPGEN_MODEL_URL')
        if url:
            click.echo(f"Fetching model files from {url}...")
        else:
            click.echo("Fetching model files from GitHub...")
            url = self.get_asset()

        # Optionally get the model password
        password = os.getenv('FPGEN_MODEL_PASSWORD')
        if password:
            password = password.encode()

        # Stream to tempfile then extract using zipfile
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            with httpx.stream(
                'GET', url, timeout=20, verify=False, follow_redirects=True
            ) as r:  # nosec
                for chunk in r.iter_bytes():
                    temp_file.write(chunk)
                temp_file.flush()
            temp_file.close()
            # Print extraction message if running as module
            if __is_module__():
                click.echo(f"Extracting to {DATA_DIR}...")
            with zipfile.ZipFile(temp_file.name) as z:
                z.extractall(DATA_DIR, pwd=password)

            os.unlink(temp_file.name)


"""
Model file utility functions
"""


def download_model():
    """
    Call the model puller to download files
    """
    ModelPuller().download()


def decompress_model():
    """
    Decompress model files
    """
    import zstandard

    dctx = zstandard.ZstdDecompressor()
    for src_zst, dst in {v: k for k, v in FILE_PAIRS.items()}.items():
        if not src_zst.exists():
            click.echo(f"Warning: {src_zst} not found, skipping")
            continue

        click.echo(f"Decompressing {src_zst} -> {dst}")
        with open(src_zst, 'rb') as src, open(dst, 'wb') as dst_f:
            dctx.copy_stream(src, dst_f)
        src_zst.unlink()


def recompress_model():
    """
    Recompress model files after running decompress
    """
    import zstandard

    cctx = zstandard.ZstdCompressor(level=19)
    for src, dst_zst in FILE_PAIRS.items():
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


def remove_model(log=True):
    """
    Remove all model files
    """
    for file_pair in FILE_PAIRS.items():
        found = False
        for file in file_pair:
            if not file.exists():
                continue
            if log:
                click.echo(f"Removing {file}")
            file.unlink()
            found = True
    return found


def files_are_recent(file_list):
    """
    Checks if all passed files are <5 weeks old
    """
    cutoff = datetime.now() - timedelta(weeks=5)
    return all(datetime.fromtimestamp(f.stat().st_mtime) >= cutoff for f in file_list)


def assert_downloaded():
    """
    Checks if the model files are downloaded
    """
    if __is_module__():
        return  # Skip if running as a module

    # Check decompressed files (FILE_PAIRS keys)
    if all(file.exists() for file in FILE_PAIRS.keys()):
        # When updating decompressed files, decompress again after redownloading
        if not files_are_recent(FILE_PAIRS.keys()):
            ModelPuller().download()
            decompress_model()
        return

    # Check compressed files (FILE_PAIRS values)
    if all(file.exists() for file in FILE_PAIRS.values()) and files_are_recent(FILE_PAIRS.values()):
        return

    # First time importing
    ModelPuller().download()


def __is_module__() -> bool:
    """
    Checks if fpgen is being ran as a module
    """
    return bool(os.getenv('FPGEN_NO_INIT'))


# Check model files are downloaded
assert_downloaded()
