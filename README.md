<h1 align="center">Fingerprint Generator</h1>

<p align="center">A fast & comprehensive browser fingerprint generator that mimics real world traffic & browser API data in the wild.</p>

<p align="center">Created by <a href="https://github.com/daijro">daijro</a>. Data provided by Scrapfly.</p>

---

## Demo Video

Here is a demonstration of what fpgen generates & its ability to pin certain data points:

https://github.com/user-attachments/assets/f0ce9160-24dd-4748-9b17-4a031134b310

---

## Installation

Install the package using pip:

```bash
pip install fpgen
```

Then, fetch the latest model:

```bash
fpgen fetch
```

To decompress the model for faster generation, run:

```bash
fpgen decompress
```

Note: This action will use an additional 100mb+ of storage.

<details>
<summary>CLI Usage</summary>

```
Usage: python -m fpgen [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  decompress  Decompress model files for speed efficiency (will take 100mb+)
  fetch       Fetch the latest model from GitHub
  recompress  Compress model files after running decompress
  remove      Remove all downloaded and/or extracted model files

```

</details>

---

## Usage

### Generate a fingerprint

To generate a fingerprint, import the `Generator` object and use it like this:

```python
>>> from fpgen import Generator
>>> gen = Generator()
>>> gen.generate()
```

<hr width=50>

### Filters

In fpgen, you can filter the fingerprint based on certain data points. The generator can be constrained by any part of its output.

Multiple possibilities can be passed as a constraint using a tuple. They will be selected based on their respected probability. 

```python
gen.generate(
    os='Windows',
    browser=('Chrome', 'Firefox'),  # Allow Chrome and Firefox
    gpu={'vendor': 'Google Inc. (Intel)'}  # Nested key search
)
```

Or, pass as a dictionary:

```python
gen.generate({
    'os': 'Windows',
    'browser': ('Chrome', 'Firefox'),
    'gpu': {'vendor': 'Google Inc. (Intel)'},
})
```

Constraint keys & values are case-insensitive.

> [!NOTE]
> If you are passing many nested constraints, you may want to run `fpgen decompress` to improve model performance.

<hr width=50>

## Generate specific data points

To generate only certain data points, pass a string or a list of strings to the target parameter. This allows you to request specific information instead of a full fingerprint.

#### Examples

Generate headers:

```python
>>> gen.generate(target='headers')
{'accept-language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7', 'accept-encoding': 'gzip, deflate, br, zstd', 'accept': '*/*', 'priority': 'u=1, i', 'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"macOS"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site', 'sec-gpc': None}
```

User-Agent, given OS and browser:

```python
>>> gen.generate(
...     os='Mac OS X',
...     browser='Chrome',
...     target='gpu.vendor'
... )
'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.134 Safari/537.36'
```

TLS fingerprint:

```python
>>> gen.generate(
...     browser='Firefox',
...     target='network.tls.scrapfly_fp'
... )
{'version': '772', 'ch_ciphers': '4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53', 'ch_extensions': '0-5-10-11-13-16-23-27-28-34-35-43-45-51-65037-65281', 'groups': '4588-29-23-24-25-256-257', 'points': '0', 'compression': '0', 'supported_versions': '772-771', 'supported_protocols': 'h2-http11', 'key_shares': '4588-29-23', 'psk': '1', 'signature_algs': '1027-1283-1539-2052-2053-2054-1025-1281-1537-515-513', 'early_data': '0'}
```

Targets to nested data points must be a valid path seperated by dots.

If multiple targets are provided as an array, the output will be a dictionary of each target to their generated value.

<hr width=50>

## Query possible values

You can get a list of a target's possible values by passing it into `fpgen.query`:

List all possible browsers:

```python
>>> fpgen.query('browser')
['Chrome', 'Edge', 'Firefox', 'Opera', 'Safari', 'Samsung Internet', 'Yandex Browser']
```

Passing a nested target:
```python
>>> fpgen.query('navigator.maxTouchPoints') # Dot seperated path
[0, 1, 2, 5, 6, 9, 10, 17, 20, 40, 256]
```

---

## Generated data

- **Browser data:**

  - All navigator data
  - All mimetype data: Audio, video, media source, playtypes, PDF, etc
  - All window viewport data (position, inner/outer viewport sizes, toolbar & scrollbar sizes, etc)
  - Supported & unsupported DRM modules
  - Memory heap limit

- **System data:**

  - GPU data (vendor, renderer, WebGL/WebGL2, extensions, context attributes, parameters, shader precision formats, etc)
  - Battery data (charging, charging time, discharging time, level)
  - Screen size, color depth, taskbar size, etc.
  - Full fonts list
  - Cast receiver data

- **Network data:**

  - HTTP headers
  - TLS fingerprint data
  - HTTP/2 fingerprint & frames
  - RTC video & audio capabilities, codecs, clock rates, mimetypes, header extensions, etc

- **Audio data:**

  - Audio signal
  - All Audio API constants (AnalyserNode, BiquadFilterNode, DynamicsCompressorNode, OscillatorNode, etc)

- **Internationalization data:**

  - Regional internationalization (Locale, calendar, numbering system, timezone, date format, etc)
  - Voices

- And much more!

---