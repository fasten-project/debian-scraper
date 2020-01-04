# Ultimate Debian Database scraper

This Python script queries [udd-mirror](https://udd-mirror.debian.net/),
and it either forwards it to Kafka or print to stdout.
The scraper script provides a command-line interface with many abilities,
and it can be extended easily.
It queries UDD, and then it produces JSONs with releases metadata.
The scraper also supports incremental updates on Debian Packages releases.

## Prerequisites

Install all dependencies:

```bash
python3 -m venv venv
. ./venv/bin/activate
pip install psycopg2 kafka-python
```

__To install Psycopg2 on mac osx run the following commands:__

```bash
brew install postgresql
env LDFLAGS='-L/usr/local/lib -L/usr/local/opt/openssl/lib \
    -L/usr/local/opt/readline/lib' pip install psycopg2
```

## How To Run

```bash
usage: Scrape Debian packages releases, and optionally push them to Kafka.
       [-h] [-a ARCHITECTURE] [-b BOOTSTRAP_SERVERS] [-C] [-d START_DATE] [-f]
       [-p PACKAGE] [-r RELEASE] [-s SLEEP_TIME] [-t TOPIC] [-v VERSION]

optional arguments:
  -h, --help            show this help message and exit
  -a ARCHITECTURE, --architecture ARCHITECTURE
                        Specify an architecture (e.g. amd64).
  -b BOOTSTRAP_SERVERS, --bootstrap_servers BOOTSTRAP_SERVERS
                        Kafka servers, comma separated.
  -C, --not-only-c      Fetch all types of packages releases (not only C
                        packages).
  -d START_DATE, --start-date START_DATE
                        The date to start scraping from. Must be in %Y-%m-%d
                        %H:%M:%S format.
  -f, --forever         Run forever. Always use it with --start-date.
  -p PACKAGE, --package PACKAGE
                        Package name to fetch.
  -r RELEASE, --release RELEASE
                        Specify Debian Release (e.g. buster).
  -s SLEEP_TIME, --sleep-time SLEEP_TIME
                        Time to sleep in between each scrape (in sec). Use it
                        with --start-date option. Default 43.200 seconds (12
                        hours).
  -t TOPIC, --topic TOPIC
                        Kafka topic to push to.
  -v VERSION, --version VERSION
                        Version of
```

For example:

```bash
python scraper.py --start-date '2019-06-1 00:00:00' --topic cf_deb_releases \
    --bootstrap_servers localhost:9092 --sleep-time 60
```

This will find releases from `2019-06-1 00:00:00` (+ incremental updates)
pushes it to `cf_deb_releases` located at `localhost:9092`.
Incremental updates are checked every `60` seconds.

**Note**: `start_date` must be in `%Y-%m-%d %H:%M:%S` format.
Multiple bootstrap servers should be `,` separated. Sleep time is in _seconds_.

or:

```sh
python scraper.py --release buster --architecture amd64 \
    --start-date '2019-06-1 00:00:00' --topic cf_deb_releases \
    --bootstrap_servers localhost:9092 --sleep-time 60
```

To query only for releases in `buster` Debian release and
for `amd64` architecture.

## Sample data

Data will be send in the following format:

```json
{
  "package": "xenstore-utils",
  "version": "4.11.1+92-g6c33308a8d-2",
  "arch": "amd64",
  "release": "buster",
  "source": "xen",
  "source_version": "4.11.1+92-g6c33308a8d-2",
  "date": "2019-06-24 11:21:15"
}
```

## Run in Docker

```bash
docker build -t debian-scraper .
docker run debian-scraper --help
```

or alternatively

```bash
docker run schaliasos/debian-scraper --help
```
