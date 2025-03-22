<h1 align="center">Fingerprint Generator</h1>

<p align="center">A fast browser data generator that mimics actual traffic patterns in the wild. With <i>extensive</i> data coverage.</p>

<p align="center">Created by <a href="https://github.com/daijro">daijro</a>. Data provided by Scrapfly.</p>

---

## Features

- Uses a Bayesian generative network to mimic real-world web traffic patterns
- Extensive data coverage for **nearly all known** browser data points
- Creates complete fingerprints in a few milliseconds ⚡
- Easily specify custom criteria for any data point (e.g. "only Windows + Chrome, with Intel GPUs")
- Simple for humans to use 🚀

## Demo Video

Here is a demonstration of what fpgen generates & its ability to filter data points:

https://github.com/user-attachments/assets/5c56691a-5804-4007-b179-0bae7069a111

---

# Installation

Install the package using pip:

```bash
pip install fpgen
```

<hr width=50>

### Downloading the model

Fetch the latest model:

```bash
fpgen fetch
```

This will be ran automatically on the first import, or every 5 weeks.

To decompress the model for faster generation (_up to 10-50x faster!_), run:

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

# Usage

### Generate a fingerprint

Simple usage:

```python
>>> import fpgen
>>> fpgen.generate(browser='Chrome', os='Windows')
```

Or use the Generator object to pass filters downward:

```python
>>> gen = fpgen.Generator(browser='Chrome')  # Filter by Chrome
>>> gen.generate(os='Windows')  # Generate Windows & Chrome fingerprints
```

<details>
<summary>
Parameters list
</summary>

```
Initializes the Generator with the given options.
Values passed to the Generator object will be inherited when calling Generator.generate()

Parameters:
    conditions (dict, optional): Conditions for the generated fingerprint.
    window_bounds (WindowBounds, optional): Constrain the output window size.
    strict (bool, optional): Whether to raise an exception if the conditions are too strict.
    flatten (bool, optional): Whether to flatten the output dictionary
    target (Optional[Union[str, StrContainer]]): Only generate specific value(s)
    **conditions_kwargs: Conditions for the generated fingerprint (passed as kwargs)
```

</details>

[See example output.](https://raw.githubusercontent.com/scrapfly/fingerprint-generator/refs/heads/main/assets/example-output.json)

---

## Filtering the output

### Setting fingerprint criteria

You can narrow down generated fingerprints by specifying filters for **any** data field.

```python
# Only generate fingerprints with Windows, Chrome, and Intel GPU:
>>> fpgen.generate(
...     os='Windows',
...     browser='Chrome',
...     gpu={'vendor': 'Google Inc. (Intel)'}
... )
```

<details>
<summary>
This can also be passed as a dictionary.
</summary>

```python
>>> fpgen.generate({
...     'os': 'Windows',
...     'browser': 'Chrome',
...     'gpu': {'vendor': 'Google Inc. (Intel)'},
... })
```

</details>

### Multiple constraints

Pass in multiple constraints for the generator to select from.

```python
fpgen.generate({
    'os': ('Windows', 'MacOS'),
    'browser': ('Firefox', 'Chrome'),
})
```

If you are passing many nested constraints, run `fpgen decompress` to improve model performance.

### Custom filters

Pass in functions to filter the possible values:

#### Example: Setting a minimum browser version.

```python
# Constrain `client`:
fpgen.generate(client={'browser': {'major': lambda v: int(v) >= 130}})
# Or, just pass a dot seperated path:
fpgen.generate({'client.browser.major': lambda v: int(v) >= 130})
```

#### Example: Constrain the maximum/minimum window size.

```python
# Constrain `window`:
fpgen.generate(
  window={
    'outerWidth': lambda w: 1000 <= w <= 2000,
    'outerHeight': lambda h: 500 <= h <= 1500
  }
)
# Or, filter the `window` dict directly:
fpgen.generate(
  window=lambda w: w['outerWidth'] >= 1000 and w['outerWidth'] <= 2000
)
```

</details>

---

## Only generate specific data

To generate specific data fields, use the `target` parameter with a string (or a list of strings).

### Examples

Only generate HTTP headers:

```python
>>> fpgen.generate(target='headers')
{'accept-language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7', 'accept-encoding': 'gzip, deflate, br, zstd', 'accept': '*/*', 'priority': 'u=1, i', 'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"macOS"', 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site', 'sec-gpc': None}
```

Generate a User-Agent for Windows & Chrome:

```python
>>> fpgen.generate(
...     os='Windows',
...     browser='Chrome',
...     # Nested targets must be seperated by dots:
...     target='headers.user-agent'
... )
'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0'
```

Generate a Firefox TLS fingerprint:

```python
>>> fpgen.generate(
...     browser='Firefox',
...     target='network.tls.scrapfly_fp'
... )
{'version': '772', 'ch_ciphers': '4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53', 'ch_extensions': '0-5-10-11-13-16-23-27-28-34-35-43-45-51-65037-65281', 'groups': '4588-29-23-24-25-256-257', 'points': '0', 'compression': '0', 'supported_versions': '772-771', 'supported_protocols': 'h2-http11', 'key_shares': '4588-29-23', 'psk': '1', 'signature_algs': '1027-1283-1539-2052-2053-2054-1025-1281-1537-515-513', 'early_data': '0'}
```

You can provide multiple targets as a list.

---

## Get the probabilities of a target

Calculate the probability distribution of a target given any filter:

```python
>>> fpgen.trace(target='browser', os='Windows')
[<Chrome: 71.29276%>, <Edge: 12.96372%>, <Firefox: 12.64484%>, <Opera: 2.12217%>, <Yandex Browser: 0.94575%>, <Whale: 0.03076%>]
```

Multiple targets can be passed as a list/tuple.
Here is an example of tracking the probability of browser & OS given a GPU vendor:

```python
>>> fpgen.trace(
...   target=('browser', 'os'),
...   gpu={'vendor': 'Google Inc. (Intel)'}
... )
{'browser': [<Chrome: 76.46641%>, <Edge: 13.02665%>, <Firefox: 8.48189%>, <Opera: 1.36188%>, <Yandex Browser: 0.65133%>, <Whale: 0.01184%>],
 'os': [<Windows: 84.08380%>, <Linux: 8.07652%>, <MacOS: 7.46072%>, <ChromeOS: 0.37896%>]}
```

This also works in the Generator object:

```python
>>> gen = fpgen.Generator(os='ChromeOS')
>>> gen.trace(target='browser')
[<Chrome: 100.00000%>]
```

<details>
<summary>
Parameters for trace
</summary>

```
Compute the probability distribution(s) of a target variable given conditions.

Parameters:
    target (str): The target variable name.
    conditions (Dict[str, Any], optional): A dictionary mapping variable names
    flatten (bool, optional): If True, return a flattened dictionary.
    **conditions_kwargs: Additional conditions to apply

Returns:
    A dictionary mapping probabilities to the target's possible values.
```

</details>

<hr width=50>

### Reading TraceResult

To read the output `TraceResult` object:

```python
>>> chrome = fpgen.trace(target='browser', os='ChromeOS')[0]
>>> chrome.probability
1.0
>>> chrome.value
'Chrome'
```

---

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

<details>
<summary>
Parameters for query
</summary>

```
Query a list of possibilities given a target.

Parameters:
    target (str): Target node to query possible values for
    flatten (bool, optional): Whether to flatten the output dictionary
    sort (bool, optional): Whether to sort the output arrays
```

</details>

> [!NOTE]
> Since fpgen is trained on live data, queries may occasionally return invalid or anomalous values. Values lower a .001% probability will not appear in traces or generated fingerprints.

---

## Generated data

Here is a rough list of the data fpgen can generate:

- **Browser data:**
  - All navigator data
  - All mimetype data: Audio, video, media source, play types, PDF, etc
  - All window viewport data (position, inner/outer viewport sizes, toolbar & scrollbar sizes, etc)
  - All screen data
  - Supported & unsupported DRM modules
  - Memory heap limit

* **System data:**
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

* **Audio data:**
  - Audio signal
  - All Audio API constants (AnalyserNode, BiquadFilterNode, DynamicsCompressorNode, OscillatorNode, etc)

- **Internationalization data:**
  - Regional internationalization (Locale, calendar, numbering system, timezone, date format, etc)
  - Voices

* **_And much more!_**

For a more complete list, see the [full example output](https://raw.githubusercontent.com/scrapfly/fingerprint-generator/refs/heads/main/assets/example-output.json).

---
