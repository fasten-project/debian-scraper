# Incremental Debian packages releases to Kafka

This Python script queries [udd-mirror](https://udd-mirror.debian.net/)
and forwards it to Kafka.
The scraper script requires: `start_date`, `kafka_topic`, `bootstrap_servers`
and `sleeptime`. It will find all releases from `start_date` and push them
to the `kafka_topic` running on `bootstrap_servers`.
It will keep repeating after `sleep_time` seconds with
`start_time == date_of_latest_release`. I.e. it does incremental updates
on Debian Packages releases.

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
usage: Push Debian packages releases to Kafka. [-h] [-n] [-r RELEASE]
                                               [-a ARCHITECTURE]
                                               start_date topic
                                               bootstrap_servers sleep_time

positional arguments:
  start_date            The date to start scraping from. Must be in %Y-%m-%d
                        %H:%M:%S format.
  topic                 Kafka topic to push to.
  bootstrap_servers     Kafka servers, comma separated.
  sleep_time            Time to sleep in between each scrape (in sec).

optional arguments:
  -h, --help            show this help message and exit
  -n, --not-only-c      Fetch all types of packages releases(not only C
                        packages)
  -r RELEASE, --release RELEASE
                        Specify Debian Release (e.g. buster)
  -a ARCHITECTURE, --architecture ARCHITECTURE
                        Specify an architecture (e.g. amd64)
```

For example:

```sh
python scraper.py '2019-06-1 00:00:00' cf_deb_releases localhost:9092 60
```

This will find releases from `2019-06-1 00:00:00` (+ incremental updates)
pushes it to `cf_deb_releases` located at `localhost:9092`.
Incremental updates are checked every `60` seconds.

**Note**: `start_date` must be in `%Y-%m-%d %H:%M:%S` format.
Multiple bootstrap servers should be `,` separated. Sleep time is in _seconds_.

or:

```sh
python scraper.py -r buster -a amd64 '2019-06-1 00:00:00' cf_deb_releases localhost:9092 60
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
docker run debian-scraper -r buster -a amd64 '2019-06-1 00:00:00' cf_deb_releases localhost:9092 60
```

or alternatively

```bash
docker run schaliasos/debian-scraper -r buster -a amd64 '2019-06-1 00:00:00' cf_deb_releases localhost:9092 60
```
